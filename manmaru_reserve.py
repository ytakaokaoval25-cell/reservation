"""
まんまるよやく 自動予約スクリプト
対象: https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2
目的: 令和08年06月19日 D面 16:00〜18:00 の予約自動化

【動作モード】
  python3 manmaru_reserve.py         → 5:00:00ちょうどに実行（本番用）
  python3 manmaru_reserve.py --now   → 即時実行（デバッグ・練習用）
  python3 manmaru_reserve.py --debug → 即時実行 + スクリーンショット保存 + 一時停止

【前提】
  Tampermonkey で window.confirm が無効化済み
"""

import asyncio
import datetime
import sys
import os
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ──────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────
LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"

# 予約対象日の日本語表示（ドロップダウンのvalue/textと一致させる）
# 実際のvalue値が数値の場合も考慮し、後述のマッチングロジックで対応
TARGET_DATE_JP = "令和08年06月19日"          # 2026-06-19
TARGET_DATE_YYYYMMDD = "20260619"            # 数値形式のvalue用フォールバック

# 検索結果で特定するセル情報
TARGET_COURT = "D面"
TARGET_TIME  = "16:00"     # 開始時刻（〜18:00まで含む）

# ブラウザ実行ファイルパス（環境に合わせて変更）
CHROMIUM_PATHS = [
    "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
    "/opt/pw-browsers/chromium_headless_shell-1148/chrome-linux/headless_shell",
    None,  # Noneの場合はPlaywrightのデフォルトを使用
]

# スクリーンショット保存先
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"

# ──────────────────────────────────────────────
# 引数処理
# ──────────────────────────────────────────────
MODE_SCHEDULED = "--now" not in sys.argv and "--debug" not in sys.argv
MODE_DEBUG     = "--debug" in sys.argv
MODE_NOW       = "--now" in sys.argv or MODE_DEBUG


def log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}", flush=True)


async def screenshot(page, name: str):
    """デバッグ用スクリーンショット保存（--debugモード時のみ）"""
    if not MODE_DEBUG:
        return
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    log(f"  📸 screenshot: {path}")


# ──────────────────────────────────────────────
# 時報待ちロジック（朝5:00:00ちょうどに起動）
# ──────────────────────────────────────────────
async def wait_until_5am():
    """
    朝5:00:00.000 ちょうどまでミリ秒単位で待機する。
    フライング防止のため、目標時刻の500ms前からポーリングループに入る。
    """
    now = datetime.datetime.now()
    target = now.replace(hour=5, minute=0, second=0, microsecond=0)
    if now >= target:
        target += datetime.timedelta(days=1)

    # ── Phase 1: 粗いsleep（目標30秒前まで）──
    rough_wait = (target - datetime.datetime.now()).total_seconds() - 30
    if rough_wait > 0:
        log(f"5:00:00まで {rough_wait + 30:.1f}秒。{rough_wait:.0f}秒間スリープします...")
        await asyncio.sleep(rough_wait)

    # ── Phase 2: 細かいsleep（目標1秒前まで）──
    fine_wait = (target - datetime.datetime.now()).total_seconds() - 1
    if fine_wait > 0:
        log(f"残り {fine_wait + 1:.1f}秒。細かい待機に入ります...")
        await asyncio.sleep(fine_wait)

    # ── Phase 3: ミリ秒単位ポーリング（目標時刻まで）──
    log("ミリ秒ポーリング開始...")
    while True:
        now = datetime.datetime.now()
        if now >= target:
            log(f"▶ 5:00:00到達！実行開始 ({now.strftime('%H:%M:%S.%f')[:-3]})")
            break
        remaining_ms = (target - now).total_seconds() * 1000
        sleep_ms = min(remaining_ms * 0.9, 10)  # 残り時間の90%か10ms小さい方
        await asyncio.sleep(sleep_ms / 1000)


# ──────────────────────────────────────────────
# ブラウザ起動ヘルパー
# ──────────────────────────────────────────────
def find_chromium_executable():
    for path in CHROMIUM_PATHS:
        if path is None:
            return None
        if os.path.exists(path):
            return path
    return None


# ──────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────
async def do_login(page):
    log("Step 1: ログインページへアクセス")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_load_state("networkidle", timeout=15_000)
    await screenshot(page, "01_login_page")

    # ── 利用者番号（ID）入力フィールド探索 ──
    # よくある名前パターンを優先度順に試す
    ID_SELECTORS = [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="kinid"]',
        'input[name="mem_id"]',
        'input[name="loginid"]',
        'input[name="login_id"]',
        'input[name="id"]',
        'input[name="ID"]',
        'input[name="no"]',
        'input[name="riyousyano"]',
        'input[name="riyousya_no"]',
        'input[type="text"]:first-of-type',
        'input[type="text"]',
    ]
    id_field = None
    for sel in ID_SELECTORS:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            id_field = el
            log(f"  ID入力フィールド発見: {sel}")
            break
    if not id_field:
        raise RuntimeError("利用者番号フィールドが見つかりません。セレクターを確認してください。")
    await id_field.fill(USER_ID)

    # ── パスワード入力フィールド探索 ──
    PW_SELECTORS = [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[name="pw"]',
    ]
    pw_field = None
    for sel in PW_SELECTORS:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            pw_field = el
            log(f"  パスワードフィールド発見: {sel}")
            break
    if not pw_field:
        raise RuntimeError("パスワードフィールドが見つかりません。")
    await pw_field.fill(PASSWORD)

    await screenshot(page, "02_login_filled")

    # ── ログインボタンクリック ──
    LOGIN_BTN_SELECTORS = [
        'input[type="submit"]',
        'button[type="submit"]',
        'input[value*="ログイン"]',
        'input[value*="login"]',
        'input[value*="LOGIN"]',
        'input[value*="確認"]',
        'button:has-text("ログイン")',
        'button',
    ]
    login_btn = None
    for sel in LOGIN_BTN_SELECTORS:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            login_btn = el
            log(f"  ログインボタン発見: {sel}")
            break
    if not login_btn:
        raise RuntimeError("ログインボタンが見つかりません。")

    await login_btn.click()
    await page.wait_for_load_state("networkidle", timeout=30_000)
    await screenshot(page, "03_after_login")
    log(f"  ログイン後URL: {page.url}")


# ──────────────────────────────────────────────
# Step 2: お気に入りクリック
# ──────────────────────────────────────────────
async def click_favorite(page):
    log("Step 2: お気に入りリンクをクリック")

    FAV_SELECTORS = [
        'a:has-text("お気に入り")',
        '[onclick*="fav"]',
        '[href*="fav"]',
        'a:has-text("よく使う")',
        'a:has-text("施設")',
        'input[value*="お気に入り"]',
        # 番号リンク（お気に入りメニューが数字ボタンの場合）
        'a[href*="favorite"]',
        'a[href*="okiniiri"]',
    ]

    fav_el = None
    for sel in FAV_SELECTORS:
        try:
            el = await page.wait_for_selector(sel, timeout=3_000)
            if el and await el.is_visible():
                fav_el = el
                log(f"  お気に入りリンク発見: {sel}")
                break
        except PlaywrightTimeout:
            continue

    if not fav_el:
        # ページ内のリンク一覧を出力してデバッグ支援
        links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a, input[type=submit], button')).map(el => ({
                tag: el.tagName,
                text: (el.innerText || el.value || '').trim().substring(0, 40),
                href: el.href || '',
                onclick: (el.getAttribute('onclick') || '').substring(0, 60),
            })).filter(x => x.text || x.href);
        }""")
        log("  [DEBUG] ページ内のリンク・ボタン一覧:")
        for lnk in links:
            log(f"    {lnk}")
        raise RuntimeError("お気に入りリンクが見つかりません。上記リンク一覧を確認してください。")

    await fav_el.click()
    await page.wait_for_load_state("networkidle", timeout=20_000)
    await screenshot(page, "04_after_fav")
    log(f"  お気に入り後URL: {page.url}")


# ──────────────────────────────────────────────
# Step 3: 日付選択 → 検索
# ──────────────────────────────────────────────
async def select_date_and_search(page):
    log("Step 3: 日付選択 → 検索")

    # ── 日付セレクトボックスを探す ──
    # パターンA: 単一selectに「令和08年06月19日」形式のoption
    # パターンB: 年・月・日が別々のselect
    # パターンC: YYYYMMDDなどの数値value

    date_selected = False

    # パターンA: 単一select（日本語表示）
    selects = await page.query_selector_all("select")
    for sel_el in selects:
        options = await sel_el.evaluate("""el => Array.from(el.options).map(o => ({value: o.value, text: o.text}))""")
        name = await sel_el.get_attribute("name") or ""
        id_ = await sel_el.get_attribute("id") or ""

        # 対象日付に対応するoption探索
        matched_value = None
        for opt in options:
            text = opt["text"].replace(" ", "").replace("　", "")
            val = opt["value"]
            if TARGET_DATE_JP.replace(" ", "") in text:
                matched_value = val
                break
            if TARGET_DATE_YYYYMMDD in val:
                matched_value = val
                break
            # 「06/19」「6月19日」などの部分一致
            if "06" in text and "19" in text and ("月" in text or "/" in text):
                matched_value = val

        if matched_value is not None:
            await sel_el.select_option(value=matched_value)
            log(f"  日付選択完了: name={name} id={id_} value={matched_value}")
            date_selected = True
            break

    # パターンB: 年・月・日が別々のselect
    if not date_selected:
        year_selectors = [
            'select[name*="year"]', 'select[name*="nen"]', 'select[name*="Year"]',
            'select[id*="year"]', 'select[id*="nen"]',
        ]
        month_selectors = [
            'select[name*="month"]', 'select[name*="tsuki"]', 'select[name*="Month"]',
            'select[id*="month"]', 'select[id*="tsuki"]',
        ]
        day_selectors = [
            'select[name*="day"]', 'select[name*="nichi"]', 'select[name*="Day"]',
            'select[id*="day"]', 'select[id*="nichi"]',
        ]

        year_el = month_el = day_el = None
        for sel in year_selectors:
            year_el = await page.query_selector(sel)
            if year_el:
                break
        for sel in month_selectors:
            month_el = await page.query_selector(sel)
            if month_el:
                break
        for sel in day_selectors:
            day_el = await page.query_selector(sel)
            if day_el:
                break

        if year_el and month_el and day_el:
            # 令和08年 = 2026年。value候補を試す
            for year_val in ["令和08", "令和8", "2026", "8", "08"]:
                try:
                    await year_el.select_option(value=year_val)
                    log(f"  年選択: {year_val}")
                    date_selected = True
                    break
                except Exception:
                    pass
            for month_val in ["06", "6", "令和08年06月"]:
                try:
                    await month_el.select_option(value=month_val)
                    log(f"  月選択: {month_val}")
                    break
                except Exception:
                    pass
            for day_val in ["19", "令和08年06月19日"]:
                try:
                    await day_el.select_option(value=day_val)
                    log(f"  日選択: {day_val}")
                    break
                except Exception:
                    pass

    if not date_selected:
        # select一覧を出力してデバッグ支援
        all_selects = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('select')).map(el => ({
                name: el.name, id: el.id,
                options: Array.from(el.options).slice(0, 5).map(o => ({v: o.value, t: o.text}))
            }));
        }""")
        log("  [DEBUG] ページ内のselectボックス一覧（最初の5件）:")
        for s in all_selects:
            log(f"    {s}")

    await screenshot(page, "05_date_selected")

    # ── 検索ボタンクリック ──
    SEARCH_BTN_SELECTORS = [
        'input[type="submit"]',
        'input[value*="検索"]',
        'button:has-text("検索")',
        'input[value*="照会"]',
        'input[value*="表示"]',
        'input[value*="確認"]',
        'button[type="submit"]',
    ]
    search_btn = None
    for sel in SEARCH_BTN_SELECTORS:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            search_btn = el
            log(f"  検索ボタン発見: {sel}")
            break

    if not search_btn:
        raise RuntimeError("検索ボタンが見つかりません。")

    await search_btn.click()
    await page.wait_for_load_state("networkidle", timeout=30_000)
    await screenshot(page, "06_search_results")
    log(f"  検索後URL: {page.url}")


# ──────────────────────────────────────────────
# Step 4: D面 16:00〜18:00 のセルをクリック
# ──────────────────────────────────────────────
async def click_target_slot(page):
    log(f"Step 4: 「{TARGET_COURT} {TARGET_TIME}〜18:00」セルを探してクリック")

    # ── 戦略1: テキスト内容でセルを特定 ──
    # 赤丸（×）でなく、予約可能な状態（○や空白）のセルを探す
    # ただし要件では「赤丸」セルを「クリック」とあるため、
    # 「赤丸」＝予約済みではなく「新規予約可能な強調表示」と解釈
    #
    # NOTE: 実際のシステムでは「赤丸」が以下のいずれかの意味の可能性:
    #   A) 「残り僅か」「当日キャンセル」など特定ステータス
    #   B) 「予約可能」の強調マーク
    #   この解釈でクリック対象として実装

    target_cell = None

    # ── 戦略1: XPathでD面 + 16:00 の組み合わせを探す ──
    # テーブルが「行=コート名、列=時間帯」構造の場合
    XPATH_PATTERNS = [
        # D面行の16:00列セル（リンクを含む）
        f'//tr[contains(., "{TARGET_COURT}")]//td[contains(., "{TARGET_TIME}")]//a',
        f'//tr[contains(., "{TARGET_COURT}")]//td[contains(., "16")]//a',
        # 時間帯行の場合
        f'//td[contains(., "{TARGET_COURT}") and contains(., "{TARGET_TIME}")]',
        f'//a[contains(@onclick, "{TARGET_COURT}") and contains(@onclick, "16")]',
    ]

    for xpath in XPATH_PATTERNS:
        try:
            el = await page.wait_for_selector(f"xpath={xpath}", timeout=3_000)
            if el and await el.is_visible():
                target_cell = el
                log(f"  セル発見 (XPath): {xpath}")
                break
        except PlaywrightTimeout:
            continue

    # ── 戦略2: テーブル全体を走査してD面・16:00のセルを特定 ──
    if not target_cell:
        log("  戦略2: テーブル走査でセルを特定...")
        cell_info = await page.evaluate(f"""() => {{
            const tables = document.querySelectorAll('table');
            const TARGET_COURT = '{TARGET_COURT}';
            const TARGET_TIME = '{TARGET_TIME}';

            for (const table of tables) {{
                const rows = table.querySelectorAll('tr');

                // 行インデックスでD面の行を特定
                let courtRowIndex = -1;
                let timeColIndex = -1;

                rows.forEach((row, ri) => {{
                    const cells = row.querySelectorAll('td, th');
                    cells.forEach((cell, ci) => {{
                        const text = cell.innerText || cell.textContent || '';
                        if (text.includes(TARGET_COURT)) courtRowIndex = ri;
                        if (text.includes(TARGET_TIME)) timeColIndex = ci;
                    }});
                }});

                if (courtRowIndex >= 0 && timeColIndex >= 0) {{
                    const targetRow = rows[courtRowIndex];
                    const targetCell = targetRow.querySelectorAll('td, th')[timeColIndex];
                    if (targetCell) {{
                        const link = targetCell.querySelector('a');
                        return {{
                            found: true,
                            courtRow: courtRowIndex,
                            timeCol: timeColIndex,
                            cellText: targetCell.innerText,
                            hasLink: !!link,
                        }};
                    }}
                }}
            }}
            return {{ found: false }};
        }}""")

        if cell_info.get("found"):
            log(f"  セル発見: row={cell_info['courtRow']} col={cell_info['timeCol']} text={cell_info['cellText']!r}")
            # 実際のクリックはJavaScriptで実行
            clicked = await page.evaluate(f"""() => {{
                const tables = document.querySelectorAll('table');
                const TARGET_COURT = '{TARGET_COURT}';
                const TARGET_TIME = '{TARGET_TIME}';

                for (const table of tables) {{
                    const rows = table.querySelectorAll('tr');
                    let courtRowIndex = -1;
                    let timeColIndex = -1;

                    rows.forEach((row, ri) => {{
                        const cells = row.querySelectorAll('td, th');
                        cells.forEach((cell, ci) => {{
                            const text = cell.innerText || cell.textContent || '';
                            if (text.includes(TARGET_COURT)) courtRowIndex = ri;
                            if (text.includes(TARGET_TIME)) timeColIndex = ci;
                        }});
                    }});

                    if (courtRowIndex >= 0 && timeColIndex >= 0) {{
                        const targetRow = rows[courtRowIndex];
                        const targetCell = targetRow.querySelectorAll('td, th')[timeColIndex];
                        if (targetCell) {{
                            const link = targetCell.querySelector('a');
                            if (link) {{ link.click(); return true; }}
                            targetCell.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }}""")
            if clicked:
                target_cell = True  # クリック済みフラグ
        else:
            # デバッグ: 全テーブルの内容を出力
            table_dump = await page.evaluate("""() => {
                const result = [];
                document.querySelectorAll('table').forEach((t, ti) => {
                    const rows = [];
                    t.querySelectorAll('tr').forEach((row, ri) => {
                        const cells = [];
                        row.querySelectorAll('td, th').forEach(cell => {
                            cells.push((cell.innerText || '').trim().substring(0, 20));
                        });
                        rows.push(cells);
                    });
                    result.push({tableIndex: ti, rows: rows.slice(0, 10)});
                });
                return result;
            }""")
            log("  [DEBUG] テーブル構造:")
            for tbl in table_dump[:3]:
                log(f"    Table {tbl['tableIndex']}:")
                for row in tbl['rows']:
                    log(f"      {row}")

    if not target_cell:
        raise RuntimeError(
            f"「{TARGET_COURT} {TARGET_TIME}」のセルが見つかりません。"
            "テーブル構造を確認し、セレクターを調整してください。"
        )

    # セルがPlaywrightElementの場合はクリック
    if hasattr(target_cell, "click"):
        await target_cell.click()

    await page.wait_for_load_state("networkidle", timeout=20_000)
    await screenshot(page, "07_slot_selected")
    log(f"  スロット選択後URL: {page.url}")


# ──────────────────────────────────────────────
# Step 5: 確定① (料金確認画面へ)
# ──────────────────────────────────────────────
async def click_confirm1(page):
    log("Step 5: 確定①ボタンをクリック（料金確認画面へ）")

    CONFIRM1_SELECTORS = [
        'input[value*="確定"]',
        'input[value*="次へ"]',
        'input[value*="confirm"]',
        'button:has-text("確定")',
        'button:has-text("次へ")',
        'input[type="submit"]',
        'button[type="submit"]',
    ]

    btn = None
    for sel in CONFIRM1_SELECTORS:
        try:
            el = await page.wait_for_selector(sel, timeout=5_000)
            if el and await el.is_visible():
                btn = el
                log(f"  確定①ボタン発見: {sel}")
                break
        except PlaywrightTimeout:
            continue

    if not btn:
        raise RuntimeError("確定①ボタンが見つかりません。")

    await btn.click()
    await page.wait_for_load_state("networkidle", timeout=20_000)
    await screenshot(page, "08_confirm1")
    log(f"  確定①後URL: {page.url}")


# ──────────────────────────────────────────────
# Step 6: 確定② (最終確定)
# ──────────────────────────────────────────────
async def click_confirm2(page):
    log("Step 6: 確定②ボタンをクリック（最終確定）")

    # window.confirmはTampermonkeyで無効化済み前提
    # 念のためPlaywright側でもconfirmダイアログを自動承認
    page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))

    CONFIRM2_SELECTORS = [
        'input[value*="確定"]',
        'input[value*="申込"]',
        'input[value*="予約"]',
        'button:has-text("確定")',
        'button:has-text("申込")',
        'input[type="submit"]',
        'button[type="submit"]',
    ]

    btn = None
    for sel in CONFIRM2_SELECTORS:
        try:
            el = await page.wait_for_selector(sel, timeout=5_000)
            if el and await el.is_visible():
                btn = el
                log(f"  確定②ボタン発見: {sel}")
                break
        except PlaywrightTimeout:
            continue

    if not btn:
        raise RuntimeError("確定②ボタンが見つかりません。")

    await btn.click()
    await page.wait_for_load_state("networkidle", timeout=20_000)
    await screenshot(page, "09_confirm2_final")
    log(f"  確定②後URL: {page.url}")
    log(f"  ページタイトル: {await page.title()}")

    # 完了確認
    body_text = await page.evaluate("document.body.innerText")
    if any(kw in body_text for kw in ["完了", "受付", "申込", "ありがとう", "予約番号"]):
        log("  ✅ 予約完了が確認されました！")
    else:
        log("  ⚠️  完了メッセージが確認できませんでした。ページを確認してください。")
        log(f"  ページ本文（先頭200字）: {body_text[:200]}")


# ──────────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────────
async def main():
    log("=" * 60)
    log("まんまるよやく 自動予約スクリプト 起動")
    log(f"対象: {TARGET_DATE_JP} {TARGET_COURT} {TARGET_TIME}〜18:00")
    log(f"モード: {'デバッグ' if MODE_DEBUG else '即時実行' if MODE_NOW else '5:00:00定時実行'}")
    log("=" * 60)

    # 時報待機（本番モード）
    if MODE_SCHEDULED:
        await wait_until_5am()

    # ブラウザ起動
    exe_path = find_chromium_executable()
    launch_kwargs = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    }
    if exe_path:
        launch_kwargs["executable_path"] = exe_path
        log(f"Chromium: {exe_path}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            await do_login(page)
            await click_favorite(page)
            await select_date_and_search(page)
            await click_target_slot(page)
            await click_confirm1(page)
            await click_confirm2(page)
            log("")
            log("=" * 60)
            log("✅ 全ステップ完了！予約が正常に処理されました。")
            log("=" * 60)

        except Exception as e:
            log(f"❌ エラー発生: {e}")
            await screenshot(page, "ERROR_final")
            # エラー時もHTMLを保存
            html = await page.content()
            err_path = Path(__file__).parent / "error_page.html"
            err_path.write_text(html, encoding="utf-8")
            log(f"  エラー時のHTMLを保存: {err_path}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
