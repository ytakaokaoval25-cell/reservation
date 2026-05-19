"""
まんまるよやく2 自動予約スクリプト v3
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト・デバッグ用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備（初回のみ）
  pip install playwright
  playwright install chromium

■ 注意
  このスクリプトは日本国内ネットワークからのみ動作します。
  スクリーンショットは screenshots/ フォルダに保存されます。
  エラー時は screenshots/ERROR_*.png を確認してください。
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────────────────
# 設定値（ここを変更する）
# ──────────────────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日（練習: 令和08年06月19日 = 2026-06-19）
# 本番（07月分）に変えるときは下記を修正
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19",
]

# 予約対象コート＆時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報待ち設定
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# 事前ウォームアップ開始時刻（開始 - この分数前にログインを開始する）
PREWARM_MINUTES = 2

# Chromiumパス（None = playwright install で自動検出）
# クラウド環境用（ローカルWindows/Macでは通常 None でOK）
_LOCAL_CHROMIUM_CANDIDATES = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
]

def _find_chromium():
    for path in _LOCAL_CHROMIUM_CANDIDATES:
        if os.path.exists(path):
            return path
    return None  # Playwrightが自動検出

CHROMIUM_PATH = _find_chromium()

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

SS_DIR = "screenshots"
# ──────────────────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":        "--headful" not in args,
        "wait_for_open":   "--now" not in args,
    }


async def wait_until(target_dt: datetime.datetime):
    """指定datetime（当日）までミリ秒単位で待機"""
    label = target_dt.strftime("%H:%M:%S")
    print(f"[時報待ち] {label} まで待機します...")
    while True:
        now      = datetime.datetime.now()
        diff_sec = (target_dt - now).total_seconds()
        if diff_sec <= 0:
            print(f"[時報] 到達: {now.strftime('%H:%M:%S.%f')}")
            return
        elif diff_sec > 300:
            print(f"  残り {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            await asyncio.sleep(1)
        elif diff_sec > 0.1:
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.001)


def today_at(hour, minute, second, microsecond=0) -> datetime.datetime:
    return datetime.datetime.now().replace(
        hour=hour, minute=minute, second=second, microsecond=microsecond
    )


async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception as e:
        print(f"  [SS失敗] {path}: {e}")


async def dump_page_info(page, label=""):
    """デバッグ用: フォーム要素を標準出力に表示"""
    print(f"\n=== {label} フォーム要素ダンプ ===")
    for inp in await page.query_selector_all("input,select,button"):
        tag = await inp.evaluate("el => el.tagName.toLowerCase()")
        name  = await inp.get_attribute("name") or ""
        id_   = await inp.get_attribute("id") or ""
        type_ = await inp.get_attribute("type") or ""
        val   = await inp.get_attribute("value") or ""
        print(f"  <{tag}> name={name!r} id={id_!r} type={type_!r} value={val!r}")
        if tag == "select":
            for opt in await inp.query_selector_all("option"):
                v = await opt.get_attribute("value") or ""
                t = (await opt.inner_text()).strip()
                print(f"    <option> value={v!r} text={t!r}")
    print(f"  URL: {page.url}")


async def try_click(page, selectors: list, label: str, timeout: int = 5000) -> bool:
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
            print(f"  [SKIP] {label} ({sel!r}): {type(e).__name__}")
    print(f"  [FAIL] {label}: 候補なし")
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
            print(f"  [SKIP] {label} ({sel!r}): {type(e).__name__}")
    print(f"  [FAIL] {label}: 候補なし")
    return False


# ──────────────────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    # JS読み込み完了まで待つ
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except PWTimeout:
        pass
    await save_ss(page, "01_login")

    # 利用者番号
    id_ok = await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid', '#user_id', '#memberNo', '#loginId',
        'input[type="text"]',
    ], USER_ID, "利用者番号")

    if not id_ok:
        # フォーム要素が0件の場合はJSレンダリング待ち不足の可能性
        await dump_page_info(page, "ログインページ")
        raise RuntimeError(
            "利用者番号フィールドが見つかりません。\n"
            f"現在URL: {page.url}\n"
            "screenshots/01_login.png を確認してください。"
        )

    # パスワード
    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        '#passwd', '#password',
    ], PASSWORD, "パスワード")

    # ログインボタン
    await try_click(page, [
        'input[value="ログイン"]',
        'input[value="LOGIN"]',
        'input[value="login"]',
        'button:text("ログイン")',
        'a:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  → URL: {page.url}")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if "エラー" in body or "失敗" in body or "incorrect" in body.lower():
        print(f"  [WARNING] ログイン失敗の可能性あり: {body[:200]}")


# ──────────────────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面
# ──────────────────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'input[value*="お気に入り"]',
        'button:text("お気に入り")',
        'td:text("お気に入り")',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    # テキスト全走査フォールバック
    if not clicked:
        for elem in await page.query_selector_all("a, button, input, td, li"):
            try:
                txt = (await elem.inner_text()).strip()
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    await elem.click()
                    print(f"  [OK] お気に入り（フォールバック）: text={txt!r}")
                    clicked = True
                    break
            except Exception:
                pass

    if not clicked:
        await dump_page_info(page, "お気に入り前")
        raise RuntimeError(
            "お気に入りリンクが見つかりません。\n"
            "screenshots/02_after_login.png を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  → URL: {page.url}")


# ──────────────────────────────────────────────────────────
# Step 3: 日付選択 → 検索
# ──────────────────────────────────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}  検索実行...")

    # SELECT要素をすべて走査して日付を探す
    date_selected = False
    selects = await page.query_selector_all("select")

    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                if v:
                    await sel_elem.select_option(value=v)
                else:
                    await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # 年・月・日が分割SELECT型の場合
    if not date_selected:
        print("  [試行] 年/月/日 分割SELECT型を試みます...")
        # 令和08 = 2026年
        year_targets  = {"令和08", "令和8", "08", "8", "2026", "R08", "R8"}
        month_targets = {"06", "6", "６", "６月", "06月"}
        day_targets   = {"19", "１９", "19日"}
        found = {"year": False, "month": False, "day": False}

        for sel_elem in selects:
            if found["year"] and found["month"] and found["day"]:
                break
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if not found["year"] and (txt in year_targets or v in year_targets):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年選択: {txt!r} value={v!r}")
                    found["year"] = True
                    break
                if not found["month"] and (txt in month_targets or v in month_targets):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月選択: {txt!r} value={v!r}")
                    found["month"] = True
                    break
                if not found["day"] and (txt in day_targets or v in day_targets):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日選択: {txt!r} value={v!r}")
                    found["day"] = True
                    break
        date_selected = found["month"]  # 月が選択できれば成功とみなす

    if not date_selected:
        await dump_page_info(page, "日付選択失敗")
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。\n"
            "screenshots/ERROR_date_not_found.png を確認してください。"
        )

    # 検索ボタン
    await try_click(page, [
        'input[value="検索"]',
        'input[value="空き照会"]',
        'input[value="照会"]',
        'button:text("検索")',
        'button:text("空き照会")',
        'a:text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  → URL: {page.url}")


# ──────────────────────────────────────────────────────────
# Step 4: D面 16:00〜18:00 の赤丸セルをクリック
# ──────────────────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    clicked = False

    # ── アプローチ①: ヘッダー行から列インデックスを特定し、D面行と交差 ──
    tables = await page.query_selector_all("table")
    for table in tables:
        if clicked:
            break
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行（最初の3行）で「16:00〜18:00」列を探す
        for row in rows[:3]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt:
                    time_col_idx = ci
                    print(f"  [INFO] {TARGET_TIME_START} 列インデックス={ci} text={txt!r}")
                    break
            if time_col_idx >= 0:
                break

        # D面の行を探して指定列のセルをクリック
        for row in rows:
            if clicked:
                break
            cells = await row.query_selector_all("td, th")
            row_texts = [(await c.inner_text()).strip() for c in cells]

            if TARGET_FACILITY in row_texts:
                print(f"  [INFO] D面行発見: {row_texts[:6]}")
                # time_col_idx が判明している場合
                if time_col_idx >= 0 and time_col_idx < len(cells):
                    target_cell = cells[time_col_idx]
                    tc_txt = (await target_cell.inner_text()).strip()
                    tc_cls = await target_cell.get_attribute("class") or ""
                    tc_onclick = await target_cell.get_attribute("onclick") or ""
                    print(f"  [FOUND] D面×{TARGET_TIME_START}: text={tc_txt!r} class={tc_cls!r}")
                    await target_cell.click()
                    clicked = True
                else:
                    # D面行内で時間に関するセルを探す
                    for i, cell in enumerate(cells):
                        tc_txt = row_texts[i]
                        if TARGET_TIME_START in tc_txt or (
                            "16" in tc_txt and "18" in tc_txt
                        ):
                            print(f"  [FOUND] D面×時間(row内): idx={i} text={tc_txt!r}")
                            await cell.click()
                            clicked = True
                            break

    # ── アプローチ②: 行ヘッダーが時間、列ヘッダーがD面（転置レイアウト）──
    if not clicked:
        print("  [試行] 転置レイアウト（行=時間・列=コート）を試みます...")
        for table in tables:
            if clicked:
                break
            rows = await table.query_selector_all("tr")
            court_col_idx = -1

            for row in rows[:3]:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_FACILITY in txt:
                        court_col_idx = ci
                        print(f"  [INFO] {TARGET_FACILITY} 列インデックス={ci}")
                        break
                if court_col_idx >= 0:
                    break

            for row in rows:
                if clicked:
                    break
                cells = await row.query_selector_all("td, th")
                row_texts = [(await c.inner_text()).strip() for c in cells]
                if any(TARGET_TIME_START in t for t in row_texts):
                    print(f"  [INFO] {TARGET_TIME_START} 行発見: {row_texts[:6]}")
                    if court_col_idx >= 0 and court_col_idx < len(cells):
                        target_cell = cells[court_col_idx]
                        tc_txt = (await target_cell.inner_text()).strip()
                        print(f"  [FOUND] 時間×D面: text={tc_txt!r}")
                        await target_cell.click()
                        clicked = True

    # ── アプローチ③: onclick/href からD面・16:00含む要素 ──
    if not clicked:
        print("  [試行] onclick/href/text でD面16:00を探します...")
        for elem in await page.query_selector_all("[onclick], a, td, input[type=radio], input[type=checkbox]"):
            try:
                onclick = await elem.get_attribute("onclick") or ""
                href    = await elem.get_attribute("href") or ""
                txt     = (await elem.inner_text()).strip()
                val     = await elem.get_attribute("value") or ""
                combined = " ".join([onclick, href, txt, val])
                d_match = (
                    TARGET_FACILITY in combined
                    or "D_" in combined
                    or "_D_" in combined
                )
                t_match = TARGET_TIME_START in combined or "16" in combined
                if d_match and t_match:
                    print(f"  [FOUND] 候補: text={txt!r} onclick={onclick[:60]!r}")
                    await elem.click()
                    clicked = True
                    break
            except Exception:
                pass

    if not clicked:
        await dump_page_info(page, "スロット選択失敗")
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} が見つかりません。\n"
            "screenshots/04_search_results.png と ERROR_slot_not_found.png を確認してください。"
        )

    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    except PWTimeout:
        pass
    await save_ss(page, "05_slot_selected")
    print(f"  → URL: {page.url}")


# ──────────────────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ──────────────────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①クリック...")

    # ダイアログ自動承認（Tampermonkey非使用時のフォールバック）
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value="予約する"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'input[value*="次へ"]',
        'button:text("確定")',
        'button:text("確認")',
        'button:text("次へ")',
        'a:text("確定")',
        'a:text("確認")',
        'a:text("次へ")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not clicked:
        await dump_page_info(page, "確定①失敗")
        raise RuntimeError(
            "確定①ボタンが見つかりません。\n"
            "screenshots/05_slot_selected.png を確認してください。"
        )

    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    except PWTimeout:
        pass
    await save_ss(page, "06_confirm1")
    print(f"  → URL: {page.url}")


# ──────────────────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# ──────────────────────────────────────────────────────────
async def step_confirm2(page):
    print("\n[Step 6] 確定②クリック（最終確定）...")

    # window.confirm が来た場合は常にOK
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    # window.confirm をJS側でも上書き（Tampermonkeyなしでも確実に抑制）
    await page.add_init_script("window.confirm = () => true; window.alert = () => {};")

    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value*="予約確定"]',
        'input[value*="最終確定"]',
        'input[value*="確定"]',
        'button:text("予約確定")',
        'button:text("最終確定")',
        'button:text("確定")',
        'a:text("予約確定")',
        'a:text("最終確定")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not clicked:
        await dump_page_info(page, "確定②失敗")
        raise RuntimeError(
            "確定②ボタンが見つかりません。\n"
            "screenshots/06_confirm1.png を確認してください。"
        )

    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    except PWTimeout:
        pass
    await save_ss(page, "07_final_result")
    print(f"  → URL: {page.url}")

    # 完了確認
    body_text = await page.inner_text("body")
    keywords = ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました", "ご予約"]
    if any(w in body_text for w in keywords):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。screenshots/07_final_result.png を確認してください。")
    print(f"  最終本文（先頭300字）:\n{body_text[:300]}")


# ──────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト v3")
    print(f"  対象日: {TARGET_DATE_WAREKI}")
    print(f"  施設:   {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"  モード: {'即時実行' if not opts['wait_for_open'] else f'時報待ち({OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d})'}")
    print(f"  Chromium: {CHROMIUM_PATH or '自動検出'}")
    print("=" * 60)

    # ── 事前ウォームアップ待機 ──────────────────────────────
    if opts["wait_for_open"]:
        # 開始 PREWARM_MINUTES 分前にログイン開始
        prewarm_dt = today_at(OPEN_HOUR, OPEN_MINUTE, OPEN_SECOND)
        prewarm_dt -= datetime.timedelta(minutes=PREWARM_MINUTES)
        now = datetime.datetime.now()
        if now < prewarm_dt:
            print(f"\n[事前待機] {prewarm_dt.strftime('%H:%M:%S')} にログイン開始します")
            await wait_until(prewarm_dt)

    launch_opts = {
        "headless": opts["headless"],
        "args":     ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    }
    if CHROMIUM_PATH:
        launch_opts["executable_path"] = CHROMIUM_PATH

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_opts)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,
        )
        # 全ページで window.confirm/alert を無効化
        await context.add_init_script(
            "window.confirm = () => true; window.alert = () => {};"
        )
        page = await context.new_page()

        try:
            # ── ログイン（時報前に完了させる）────────────────
            await step_login(page)
            await step_favorite(page)

            # ── 時報待ち（5:00:00.000 ちょうどまで）─────────
            if opts["wait_for_open"]:
                open_dt = today_at(OPEN_HOUR, OPEN_MINUTE, OPEN_SECOND)
                if datetime.datetime.now() < open_dt:
                    print(f"\n[時報待ち] お気に入り画面で待機中... "
                          f"{open_dt.strftime('%H:%M:%S')} に検索開始します")
                    await wait_until(open_dt)

            # ── 5:00:00 に日付選択・検索を実行 ───────────────
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)
            print("\n✅ すべてのステップが完了しました。")

        except Exception as e:
            try:
                await save_ss(page, "ERROR_final")
            except Exception:
                pass
            print(f"\n❌ エラー発生: {e}")
            print("screenshots/ フォルダのスクリーンショットを確認してください。")
            raise

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
