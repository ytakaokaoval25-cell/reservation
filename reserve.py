"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備
  pip install playwright
  playwright install chromium

■ セレクター確認方法
  まず analyze_site.py を --now --headful で実行し、
  analysis_output/ フォルダのHTML・スクリーンショットで実際の構造を確認すること。
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────
LOGIN_URL   = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID     = "12015873"
PASSWORD    = "0508"

# 予約対象日（令和08年06月19日 = 2026-06-19 で練習。本番は変更）
TARGET_DATE_WAREKI = "令和08年06月19日"

# プルダウンに現れうる表記パターン（前方一致・部分一致で試みる）
TARGET_DATE_TEXTS = [
    "令和08年06月19日",
    "令和8年6月19日",
    "令和８年６月１９日",
    "令和０８年０６月１９日",
    "R8.06.19",
    "R08.06.19",
    "2026/06/19",
    "2026年06月19日",
    "2026-06-19",
    "06月19日",  # 月日のみの場合
]
TARGET_DATE_VALUES = [
    "20260619",
    "2026-06-19",
    "2026/06/19",
    "260619",
    "0619",
]

# 年・月・日が分割SELECTの場合の候補
YEAR_TEXTS   = ["令和08", "令和8", "令和０８", "R08", "R8", "2026", "08", "8"]
MONTH_TEXTS  = ["06", "6", "６", "06月", "6月", "６月"]
DAY_TEXTS    = ["19", "１９", "19日", "１９日"]

# 予約対象コート＆時間
TARGET_FACILITY  = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報待ち設定（本番: 朝5:00:00.000）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000
FAST_TIMEOUT = 3_000

# スクリーンショット保存先
SS_DIR = "screenshots"
# ──────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


# ──────────────────────────────────────────────
# 時報待ちロジック（ミリ秒単位）
# ──────────────────────────────────────────────
async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位で待機"""
    print("[時報待ち] 朝5:00:00.000 まで待機します...")
    while True:
        now    = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
            break
        elif diff_sec > 300:       # 5分以上前
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:        # 10秒〜5分前
            await asyncio.sleep(1)
        elif diff_sec > 0.1:       # 100ms〜10秒前
            await asyncio.sleep(0.05)
        else:                      # 100ms以内: 1msごと
            await asyncio.sleep(0.001)


# ──────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────
async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def safe_inner_text(elem) -> str:
    try:
        return (await elem.inner_text()).strip()
    except Exception:
        return ""


async def try_click(page, selectors: list, label: str,
                    timeout: int = FAST_TIMEOUT) -> bool:
    """複数セレクターを順番に試してクリック"""
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
            print(f"  [SKIP] {label} ({sel}): {type(e).__name__}")
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


async def try_fill(page, selectors: list, value: str,
                   label: str, timeout: int = FAST_TIMEOUT) -> bool:
    """複数セレクターを順番に試して値を入力"""
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
            print(f"  [SKIP] {label} ({sel}): {type(e).__name__}")
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


async def select_option_by_text_or_value(sel_elem, texts: list, values: list) -> tuple:
    """SELECTのOPTIONをテキスト/value両方で検索して選択。(成否, value, text)を返す"""
    options = await sel_elem.query_selector_all("option")
    for opt in options:
        v   = await opt.get_attribute("value") or ""
        txt = (await opt.inner_text()).strip()
        if any(t in txt or t == v for t in texts) or v in values:
            if v:
                await sel_elem.select_option(value=v)
            else:
                await sel_elem.select_option(label=txt)
            return (True, v, txt)
    return (False, "", "")


# ──────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号 ── まんまるよやく系は userid / mid / loginid が多い
    filled = await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="mid"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginno"]',
        '#userid',
        '#loginId',
        'form input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")
    if not filled:
        raise RuntimeError("利用者番号フィールドが見つかりません。analyze_site.py を実行してください。")

    # パスワード
    filled = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[name="mpw"]',
        'input[name="loginpass"]',
        '#passwd',
        '#password',
    ], PASSWORD, "パスワード")
    if not filled:
        raise RuntimeError("パスワードフィールドが見つかりません。analyze_site.py を実行してください。")

    # ログインボタン
    await try_click(page, [
        'input[value="ログイン"]',
        'input[value=" ログイン "]',
        'button:has-text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:has-text("ログイン")',
    ], "ログインボタン", timeout=ELEM_TIMEOUT)

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if "エラー" in body or "ログイン" in body and "失敗" in body:
        raise RuntimeError(f"ログイン失敗の可能性あり。スクリーンショット確認: {SS_DIR}/02_after_login.png")


# ──────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面
# ──────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    # Playwright テキストセレクター / 属性ベース 両方試みる
    clicked = await try_click(page, [
        'a:has-text("お気に入り")',
        'button:has-text("お気に入り")',
        'input[value="お気に入り"]',
        'input[value*="お気に入り"]',
        '[onclick*="okiniri"]',
        '[onclick*="okini"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
        '[class*="okiniri"]',
        '[id*="okiniri"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全走査フォールバック
        for tag in ["a", "button", "input"]:
            elems = await page.query_selector_all(tag)
            for elem in elems:
                txt = await safe_inner_text(elem)
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    await elem.click()
                    print(f"  [OK] お気に入り（全走査）: tag={tag} text={txt!r} value={val!r}")
                    clicked = True
                    break
            if clicked:
                break

    if not clicked:
        await save_ss(page, "ERROR_favorite_not_found")
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            f"スクリーンショット {SS_DIR}/02_after_login.png を確認し、"
            "analyze_site.py でメニュー構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 3: 日付プルダウンで「令和08年06月19日」を選択して検索（最速）
# ──────────────────────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False
    selects = await page.query_selector_all("select")

    # ── パターンA: 日付が1つのSELECTにまとまっている ──────────
    for sel_elem in selects:
        ok, v, txt = await select_option_by_text_or_value(
            sel_elem, TARGET_DATE_TEXTS, TARGET_DATE_VALUES
        )
        if ok:
            name = await sel_elem.get_attribute("name") or ""
            print(f"  [OK] 日付選択(単一SELECT): name={name!r} value={v!r} text={txt!r}")
            date_selected = True
            break

    # ── パターンB: 年・月・日が別々のSELECT ──────────────────
    if not date_selected:
        print("  [試行] 年月日分割SELECT パターン...")
        year_ok = month_ok = day_ok = False

        for sel_elem in selects:
            if not year_ok:
                ok, v, txt = await select_option_by_text_or_value(
                    sel_elem, YEAR_TEXTS, []
                )
                if ok:
                    name = await sel_elem.get_attribute("name") or ""
                    print(f"  [OK] 年選択: name={name!r} value={v!r} text={txt!r}")
                    year_ok = True
                    continue

            if not month_ok:
                ok, v, txt = await select_option_by_text_or_value(
                    sel_elem, MONTH_TEXTS, []
                )
                if ok:
                    name = await sel_elem.get_attribute("name") or ""
                    print(f"  [OK] 月選択: name={name!r} value={v!r} text={txt!r}")
                    month_ok = True
                    continue

            if not day_ok:
                ok, v, txt = await select_option_by_text_or_value(
                    sel_elem, DAY_TEXTS, []
                )
                if ok:
                    name = await sel_elem.get_attribute("name") or ""
                    print(f"  [OK] 日選択: name={name!r} value={v!r} text={txt!r}")
                    day_ok = True

        date_selected = year_ok or month_ok or day_ok  # 1つでも成功すれば先に進む

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。\n"
            f"analyze_site.py を実行し、analysis_output/ の内容を確認してください。"
        )

    # 検索ボタン
    await try_click(page, [
        'input[value="検索"]',
        'input[value=" 検索 "]',
        'button:has-text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:has-text("検索")',
    ], "検索ボタン", timeout=ELEM_TIMEOUT)

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 4: D面 16:00〜18:00 の赤丸セルをクリック
# ──────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} (赤丸) 選択...")

    clicked = False
    tables  = await page.query_selector_all("table")

    # ── アプローチ①: ヘッダー行から列インデックスを特定 ──────
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行（最初の3行以内）で時間列を探す
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = await safe_inner_text(cell)
                # 「16:00〜18:00」「16:00-18:00」「16:00～18:00」などのバリエーション
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_idx = ci
                    print(f"  [INFO] 列{ci} = {txt!r}")
                    break
                # 「16:00」「16」だけの場合も考慮
                elif txt == TARGET_TIME_START or txt == "16" or txt == "16時":
                    time_col_idx = ci
                    print(f"  [INFO] 列{ci} = {txt!r} (時間単独)")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行でその列のセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = await safe_inner_text(cell)
                if TARGET_FACILITY in txt:
                    # D面行発見
                    print(f"  [INFO] D面行発見 (列数={len(cells)})")
                    if time_col_idx < len(cells):
                        target_cell = cells[time_col_idx]
                        tc_txt = await safe_inner_text(target_cell)
                        tc_cls = await target_cell.get_attribute("class") or ""
                        print(f"  [FOUND] D面×{TARGET_TIME_START}: "
                              f"text={tc_txt!r} class={tc_cls!r}")
                        # セル内のリンク or 画像を先にクリック試み
                        inner_link = await target_cell.query_selector("a, input[type=button], button")
                        if inner_link:
                            await inner_link.click()
                        else:
                            await target_cell.click()
                        clicked = True
                    break
            if clicked:
                break
        if clicked:
            break

    # ── アプローチ②: D面行から直接テキスト検索 ──────────────
    if not clicked:
        print("  [試行] D面行のテキスト直接検索...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells      = await row.query_selector_all("td, th")
                cell_texts = [await safe_inner_text(c) for c in cells]

                if TARGET_FACILITY in cell_texts or any(TARGET_FACILITY in t for t in cell_texts):
                    print(f"  [INFO] D面行テキスト: {cell_texts[:8]}")
                    for i, (cell, txt) in enumerate(zip(cells, cell_texts)):
                        if TARGET_TIME_START in txt:
                            cls     = await cell.get_attribute("class") or ""
                            onclick = await cell.get_attribute("onclick") or ""
                            print(f"  [FOUND] 列{i}: text={txt!r} class={cls!r}")
                            inner_link = await cell.query_selector("a, input[type=button], button")
                            if inner_link:
                                await inner_link.click()
                            else:
                                await cell.click()
                            clicked = True
                            break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick/href にD面と時間情報が含まれる要素 ──
    if not clicked:
        print("  [試行] onclick/href からD面16:00を探す...")
        all_elems = await page.query_selector_all("[onclick], a[href]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            alt     = await elem.get_attribute("alt") or ""
            txt     = await safe_inner_text(elem)
            combined = onclick + href + alt + txt
            # D面 または コート番号と16:00を含む
            if ("D面" in combined or "D_" in combined or "courtD" in combined.lower()) \
                    and ("16" in combined or "1600" in combined):
                print(f"  [FOUND] onclick={onclick!r} href={href!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    # ── アプローチ④: 赤丸画像(赤=利用可)がある先頭候補 ──────
    if not clicked:
        print("  [試行] 赤丸画像からD面16:00を探す...")
        # 赤丸はimage src に "red"/"aka"/"maru"/"circle" などが含まれることが多い
        imgs = await page.query_selector_all("img[src*='red'], img[src*='aka'], "
                                             "img[src*='maru'], img[src*='circle'], "
                                             "img[alt='○'], img[alt='赤'], img[alt='空']")
        for img in imgs:
            parent_td = await img.evaluate_handle(
                "el => el.closest('td') || el.closest('tr')"
            )
            if parent_td:
                tr = await img.evaluate_handle("el => el.closest('tr')")
                if tr:
                    tds = await tr.query_selector_all("td, th")
                    row_texts = [await safe_inner_text(td) for td in tds]
                    if TARGET_FACILITY in row_texts or any(TARGET_FACILITY in t for t in row_texts):
                        td_parent = await img.evaluate_handle("el => el.closest('td')")
                        if td_parent:
                            td_txt = await safe_inner_text(td_parent.as_element())
                            print(f"  [FOUND] 赤丸img in D面行: cell_text={td_txt!r}")
                            await img.click()
                            clicked = True
                            break
        if clicked:
            pass

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"「{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}」のセルが見つかりません。\n"
            f"{SS_DIR}/04_search_results.png を確認し、analyze_site.py で"
            "テーブル構造を解析してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ──────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①クリック...")
    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value="料金確認"]',
        'button:has-text("確定")',
        'button:has-text("確認")',
        'button:has-text("次へ")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'input[value*="次へ"]',
        'a:has-text("確定")',
        'a:has-text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        await save_ss(page, "ERROR_confirm1_not_found")
        raise RuntimeError("確定①ボタンが見つかりません。スクリーンショットを確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# Tampermonkey で window.confirm を無効化済み前提。
# 万一ダイアログが発火した場合は自動承認するフォールバックも設定。
# ──────────────────────────────────────────────
async def step_confirm2(page):
    print("\n[Step 6] 確定②クリック...")

    # dialog フォールバック（Tampermonkey が無効化していない環境でも動作するように）
    async def handle_dialog(dialog):
        print(f"  [DIALOG] type={dialog.type} message={dialog.message!r} → 自動承認")
        await dialog.accept()

    page.on("dialog", handle_dialog)

    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="確定"]',
        'input[value="予約する"]',
        'button:has-text("予約確定")',
        'button:has-text("最終確定")',
        'button:has-text("確定")',
        'input[value*="確定"]',
        'input[value*="予約"]',
        'a:has-text("確定")',
        'a:has-text("予約確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        await save_ss(page, "ERROR_confirm2_not_found")
        raise RuntimeError("確定②ボタンが見つかりません。スクリーンショットを確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了確認
    body_text = await page.inner_text("body")
    if any(w in body_text for w in ["予約完了", "受付完了", "受付番号", "予約番号", "申込完了", "完了しました"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了キーワードが見つかりません。スクリーンショットで結果を確認してください。")
    print(f"  本文先頭200字: {body_text[:200]}")


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日  : {TARGET_DATE_WAREKI}")
    print(f"施設    : {TARGET_FACILITY}  {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード  : {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00:00)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

    if opts["wait_for_open"]:
        await wait_until_open()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
        )
        page = await context.new_page()

        try:
            await step_login(page)
            await step_favorite(page)
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)
            print("\n✅ すべてのステップが完了しました。")
        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
