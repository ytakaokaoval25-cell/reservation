"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）
本番: 令和08年07月XX日（2026-06-19 朝5:00 に予約開放）

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 動作の流れ（時報最適化）
  [~4:59] ログイン → お気に入り → 日付選択 まで完了して待機
  [5:00:00.000] 検索ボタンをクリック（最速）
  [5:00:00+] D面 16:00〜18:00 セル選択 → 確定① → 確定②

■ 準備
  pip install playwright
  playwright install chromium
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 練習: 令和08年06月19日 / 本番: 07月分に書き換える
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日",
    "令和０８年０６月１９日", "令和08年 06月19日",
    "2026年06月19日", "2026/06/19",
]

# 年月日分割プルダウン向け
YEAR_PATTERNS  = ["令和08", "令和8", "令和０８", "08", "2026", "R08", "R8", "8"]
MONTH_PATTERNS = ["06", "6", "６", "６月", "06月", "6月"]
DAY_PATTERNS   = ["19", "１９", "19日"]

# 予約対象コート・時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報設定（本番はここを朝5時ちょうど）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000
SS_DIR       = "screenshots"
# ──────────────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


async def wait_until_open():
    """
    朝 OPEN_HOUR:OPEN_MINUTE:OPEN_SECOND.000 まで段階的に待機。
    ※ この関数はログイン済み・日付選択済みの状態で呼ぶことで
       「検索ボタン直前」での最速実行を実現する。
    """
    now = datetime.datetime.now()
    target = now.replace(
        hour=OPEN_HOUR, minute=OPEN_MINUTE,
        second=OPEN_SECOND, microsecond=0,
    )
    if now >= target:
        print(f"[時報] 既に開放時刻を過ぎています: {now.strftime('%H:%M:%S.%f')}")
        return

    print(f"[時報待ち] 目標: {target.strftime('%H:%M:%S.000')}  現在: {now.strftime('%H:%M:%S.%f')}")
    while True:
        now = datetime.datetime.now()
        diff = (target - now).total_seconds()
        if diff <= 0:
            print(f"[時報] 開始: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
            return
        elif diff > 300:
            print(f"  あと {diff:.0f}秒 ({diff/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff > 10:
            await asyncio.sleep(1)
        elif diff > 0.1:
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.001)


def _ss_path(name):
    os.makedirs(SS_DIR, exist_ok=True)
    return f"{SS_DIR}/{name}.png"


async def save_ss(page, name: str):
    path = _ss_path(name)
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_click(page, selectors: list, label: str, timeout: int = 5000) -> bool:
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.click()
                print(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            print(f"  [skip] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


async def try_fill(page, selectors: list, value: str, label: str, timeout: int = 5000) -> bool:
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.fill(value)
                print(f"  [OK] {label}入力: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            print(f"  [skip] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: 入力フィールドが見つかりません")
    return False


# ──────────────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    ok1 = await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="uid"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid', '#user_id', '#uid',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")

    ok2 = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        '#passwd', '#password',
    ], PASSWORD, "パスワード")

    if not (ok1 and ok2):
        await save_ss(page, "ERROR_login_fields")
        raise RuntimeError(
            "ログインフォームのフィールドが見つかりません。"
            f"screenshots/01_login.png を確認してください。"
        )

    await try_click(page, [
        'input[value="ログイン"]',
        'input[value="LOGIN"]',
        'input[value="ログイン "]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("ログイン")',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if any(w in body for w in ["ログインに失敗", "パスワードが違", "利用者番号が", "エラー"]):
        raise RuntimeError(f"ログイン失敗: {body[:200]}")


# ──────────────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面
# ──────────────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        'a:text-matches("お気に入り")',
        '[class*="favorite"]',
        '[id*="favorite"]',
        '[name*="favorite"]',
        '[onclick*="favorite"]',
        '[onclick*="okiniri"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全探索フォールバック
        for tag in ["a", "button", "input"]:
            elems = await page.query_selector_all(tag)
            for elem in elems:
                try:
                    txt = (await elem.inner_text()).strip()
                    val = await elem.get_attribute("value") or ""
                    if "お気に入り" in txt or "お気に入り" in val:
                        await elem.click()
                        print(f"  [OK] お気に入り（フォールバック）: <{tag}> text={txt!r}")
                        clicked = True
                        break
                except Exception:
                    pass
            if clicked:
                break

    if not clicked:
        await save_ss(page, "ERROR_no_favorite")
        # ページ内テキストを列挙してデバッグ情報を提供
        links = await page.query_selector_all("a, button, input[type=button], input[type=submit]")
        print("  [DEBUG] ページ上のリンク・ボタン一覧:")
        for lnk in links:
            try:
                t = (await lnk.inner_text()).strip() or await lnk.get_attribute("value") or ""
                h = await lnk.get_attribute("href") or ""
                if t:
                    print(f"    {t!r}  href={h!r}")
            except Exception:
                pass
        raise RuntimeError("お気に入りリンクが見つかりません。screenshots/02_after_login.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────
# Step 3: 日付プルダウン選択（時報前に完了）
# ──────────────────────────────────────────────────────
async def step_select_date(page):
    """日付をプルダウンで選択する。検索ボタンはまだ押さない。"""
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI} (検索前)")

    date_selected = False
    selects = await page.query_selector_all("select")

    # ── パターンA: 1つのSELECTに日付テキスト/value が含まれる ──
    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v) if v else \
                    await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択(A): name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── パターンB: 年・月・日 が別々のSELECT ──────────────────
    if not date_selected:
        print("  [試行B] 年月日分割SELECT...")
        found_year = found_month = found_day = False
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if not found_year and any(p in txt or p == v for p in YEAR_PATTERNS):
                    await sel_elem.select_option(value=v) if v else \
                        await sel_elem.select_option(label=txt)
                    print(f"  [OK] 年: {txt!r} (value={v!r})")
                    found_year = True
                    break
            if found_year:
                break
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if not found_month and any(p == txt or p == v for p in MONTH_PATTERNS):
                    await sel_elem.select_option(value=v) if v else \
                        await sel_elem.select_option(label=txt)
                    print(f"  [OK] 月: {txt!r} (value={v!r})")
                    found_month = True
                    break
            if found_month:
                break
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if not found_day and any(p == txt or p == v for p in DAY_PATTERNS):
                    await sel_elem.select_option(value=v) if v else \
                        await sel_elem.select_option(label=txt)
                    print(f"  [OK] 日: {txt!r} (value={v!r})")
                    found_day = True
                    break
            if found_day:
                break
        date_selected = found_year or found_month or found_day

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        # プルダウン一覧をデバッグ出力
        print("  [DEBUG] ページ上の全SELECT:")
        for i, s in enumerate(selects):
            nm = await s.get_attribute("name") or ""
            opts = await s.query_selector_all("option")
            print(f"    SELECT[{i}] name={nm!r}")
            for opt in opts[:10]:
                tv = await opt.get_attribute("value") or ""
                tt = (await opt.inner_text()).strip()
                print(f"      value={tv!r}  text={tt!r}")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "screenshots/03_favorite_filter.png を確認してください。"
        )

    await save_ss(page, "03b_date_selected")
    print("  日付選択完了。時報待ちに入ります...")


# ──────────────────────────────────────────────────────
# Step 4: 【時報直後】検索ボタンをクリック
# ──────────────────────────────────────────────────────
async def step_click_search(page):
    print(f"\n[Step 4] 検索ボタンクリック @ {datetime.datetime.now().strftime('%H:%M:%S.%f')}")

    clicked = await try_click(page, [
        'input[value="検索"]',
        'button:text("検索")',
        'input[value*="検索"]',
        'input[value="空き照会"]',
        'input[value*="照会"]',
        'a:text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "検索ボタン", timeout=3000)

    if not clicked:
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────
# Step 5: D面 16:00〜18:00（赤丸）セルを選択
# ──────────────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 5] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    # 全テーブルとセルを取得
    tables = await page.query_selector_all("table")
    clicked = False

    # ─ アプローチA: ヘッダーから16:00〜18:00の列インデックスを特定 ─
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1
        d_row = None

        for row in rows:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                # 時間ヘッダーを検出
                if TARGET_TIME_START in txt and time_col_idx < 0:
                    time_col_idx = ci
                    print(f"  [INFO] 時間列(col={ci}): {txt!r}")
                # D面行を検出（全角・半角D、D面○○等も許容）
                if ("D面" in txt or "Ｄ面" in txt) and d_row is None:
                    d_row = row
                    print(f"  [INFO] D面行発見: {txt!r}")

        if time_col_idx >= 0 and d_row is not None:
            d_cells = await d_row.query_selector_all("td, th")
            if time_col_idx < len(d_cells):
                target_cell = d_cells[time_col_idx]
                tc_txt = (await target_cell.inner_text()).strip()
                tc_cls = await target_cell.get_attribute("class") or ""
                tc_style = await target_cell.get_attribute("style") or ""
                tc_on = await target_cell.get_attribute("onclick") or ""
                print(f"  [FOUND-A] D面×{TARGET_TIME_START} text={tc_txt!r} class={tc_cls!r}")
                await target_cell.click()
                clicked = True
                break

    # ─ アプローチB: 赤丸（background-color/クラス）で直接検出 ─
    if not clicked:
        print("  [試行B] 赤丸/クラスで検索...")
        # 赤丸を示す可能性のあるクラス・スタイルパターン
        red_selectors = [
            "td.akamaru", "td.red", "td.r_maru", "td.available_red",
            "td[class*='red']", "td[class*='aka']", "td[class*='maru']",
            "td[style*='red']", "td[style*='#ff']", "td[style*='rgb(255']",
        ]
        for rsel in red_selectors:
            try:
                elems = await page.query_selector_all(rsel)
                for elem in elems:
                    # この赤丸がD面行にあるかチェック
                    row = await elem.evaluate_handle("el => el.closest('tr')")
                    row_elem = row.as_element()
                    if row_elem:
                        row_txt = (await row_elem.inner_text()).strip()
                        if "D面" in row_txt or "Ｄ面" in row_txt:
                            tc_txt = (await elem.inner_text()).strip()
                            print(f"  [FOUND-B] {rsel} text={tc_txt!r}")
                            await elem.click()
                            clicked = True
                            break
            except Exception:
                pass
            if clicked:
                break

    # ─ アプローチC: onclick属性にD面+時間の情報 ─
    if not clicked:
        print("  [試行C] onclick/hrefから探索...")
        all_elems = await page.query_selector_all("[onclick], td > a")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = ""
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                pass
            combined = onclick + href + txt
            if ("D面" in combined or "Ｄ面" in combined) and "16" in combined:
                print(f"  [FOUND-C] text={txt!r} onclick={onclick[:80]!r}")
                await elem.click()
                clicked = True
                break

    # ─ アプローチD: テーブル全走査（行ヘッダーが同行にある場合） ─
    if not clicked:
        print("  [試行D] テーブル全走査...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                texts = [(await c.inner_text()).strip() for c in cells]
                if any("D面" in t or "Ｄ面" in t for t in texts):
                    for i, txt in enumerate(texts):
                        if TARGET_TIME_START in txt or ("16" in txt and "18" in txt):
                            print(f"  [FOUND-D] col={i} text={txt!r}")
                            await cells[i].click()
                            clicked = True
                            break
                if clicked:
                    break
            if clicked:
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        print("\n  [DEBUG] テーブル構造:")
        for ti, table in enumerate(tables[:3]):
            rows = await table.query_selector_all("tr")
            for ri, row in enumerate(rows[:8]):
                cells = await row.query_selector_all("td, th")
                row_info = []
                for cell in cells:
                    ct = (await cell.inner_text()).strip()
                    cc = await cell.get_attribute("class") or ""
                    row_info.append(f"{ct!r}(cls={cc!r})")
                print(f"    T{ti}R{ri}: {' | '.join(row_info[:8])}")
        raise RuntimeError(
            "D面 16:00〜18:00 セルが見つかりません。"
            "screenshots/04_search_results.png を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────
# Step 6: 確定①（料金確認画面へ）
# ──────────────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 6] 確定①クリック（料金確認画面へ）...")
    await save_ss(page, "06a_before_confirm1")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確　定"]',
        'input[value="確 定"]',
        'input[value="確認"]',
        'button:text("確定")',
        'button:text("確認")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'input[value*="料金"]',
        'a:text("確定")',
        'a:text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①", timeout=ELEM_TIMEOUT)

    if not clicked:
        await save_ss(page, "ERROR_confirm1")
        raise RuntimeError("確定①ボタンが見つかりません。screenshots/06a_before_confirm1.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_after_confirm1")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────
# Step 7: 確定②（最終確定）
# ──────────────────────────────────────────────────────
async def step_confirm2(page):
    """
    Tampermonkey で window.confirm を無効化済みの前提。
    万一ダイアログが来た場合は自動承認するフォールバックも設定。
    """
    print("\n[Step 7] 確定②クリック（最終確定）...")
    await save_ss(page, "07a_before_confirm2")

    # ダイアログ自動承認（フォールバック）
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    # JS で confirm を無効化（Tampermonkey が入っていない環境でも安全に動作）
    await page.evaluate("window.confirm = () => true")

    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="確定"]',
        'input[value="確　定"]',
        'button:text("予約確定")',
        'button:text("確定")',
        'input[value*="確定"]',
        'a:text("予約確定")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②", timeout=ELEM_TIMEOUT)

    if not clicked:
        await save_ss(page, "ERROR_confirm2")
        raise RuntimeError("確定②ボタンが見つかりません。screenshots/07a_before_confirm2.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    body = await page.inner_text("body")
    if any(w in body for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了"]):
        print("\n✅ 予約完了！")
    else:
        print("\n⚠️  完了メッセージ未確認。screenshots/07_final_result.png を確認してください。")
    print(f"  本文先頭200字: {body[:200]}")


# ──────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 62)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} / {TARGET_DATE_WAREKI}")
    mode = ("即時実行" if not opts["wait_for_open"] else
            f"時報待ち ({OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d})")
    disp = "ブラウザ表示あり" if not opts["headless"] else "ヘッドレス"
    print(f"モード: {mode} / {disp}")
    print("=" * 62)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,   # 自己署名証明書対応
        )
        page = await context.new_page()

        try:
            # ── 事前処理（5時前に完了させる） ──────────────────
            await step_login(page)
            await step_favorite(page)
            await step_select_date(page)

            # ── 時報待ち（検索ボタン直前） ────────────────────
            if opts["wait_for_open"]:
                await wait_until_open()

            # ── 時報後（最速実行） ────────────────────────────
            await step_click_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)

            print("\n✅ すべてのステップ完了。")

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
