"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備
  pip install playwright
  playwright install chromium

■ セレクター確認
  python analyze_site.py で各ステップのHTMLとスクリーンショットを取得し、
  下記「★要確認セレクター」を実際の値に合わせて修正してください。
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# ── 予約対象 ────────────────────────────────────────────────────────
# 練習：令和08年06月19日  D面 16:00〜18:00
# 本番：令和08年07月**日 に変更
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日",
    "令和8年06月19日",
    "令和８年０６月１９日",
    "令和08年6月19日",
    "2026年06月19日",
    "2026/06/19",
    "R8.6.19",
]
# value属性が数字型の場合の候補（複数形式に対応）
TARGET_DATE_ALT_VALUES = ["20260619", "2026-06-19", "2026/06/19", "260619"]

TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# ── 時報待ち設定 ────────────────────────────────────────────────────
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# ── タイムアウト（ms） ────────────────────────────────────────────
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# ── スクリーンショット保存先 ──────────────────────────────────────
SS_DIR = "screenshots"

# ──────────────────────────────────────────────────────────────────────
# ★ 要確認セレクター（analyze_site.py の出力に合わせて修正）
# ──────────────────────────────────────────────────────────────────────
# analyze_site.py を一度ローカル実行し、各HTMLファイルを確認してください。
# 確認済みなら CONFIRMED_* 変数に実際の値をセットすると優先使用されます。

CONFIRMED_USERID_SEL   = ""   # 例: 'input[name="riyousyaNo"]'
CONFIRMED_PASSWD_SEL   = ""   # 例: 'input[name="passwd"]'
CONFIRMED_SUBMIT_SEL   = ""   # 例: 'input[value="ログイン"]'
CONFIRMED_FAVORITE_SEL = ""   # 例: 'a[href*="okiniri"]'
CONFIRMED_DATE_SEL     = ""   # 例: 'select[name="searchDate"]'
CONFIRMED_SEARCH_SEL   = ""   # 例: 'input[value="検索"]'
# ──────────────────────────────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


# ──────────────────────────────────────────────────────────────────────
# 時報待ちロジック（ミリ秒精度）
# ──────────────────────────────────────────────────────────────────────
async def wait_until_open():
    """朝 OPEN_HOUR:OPEN_MINUTE:OPEN_SECOND.000 ぴったりまでスリープ"""
    print(f"[時報待ち] {OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d}.000 まで待機...")
    while True:
        now    = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
        )
        diff   = (target - now).total_seconds()

        if diff <= 0:
            print(f"[時報] 開始: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
            break
        elif diff > 300:        # 5分超 → 30秒ごとに確認
            print(f"[待機] あと {diff:.0f}秒 ({diff/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff > 10:         # 10秒〜5分 → 1秒ごと
            await asyncio.sleep(1)
        elif diff > 0.100:      # 100ms〜10秒 → 50msごと
            await asyncio.sleep(0.05)
        else:                   # 100ms以内 → 1msごと（精密合わせ）
            await asyncio.sleep(0.001)


# ──────────────────────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────────────────────
async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_click(page, selectors: list[str], label: str,
                    timeout: int = 5000) -> bool:
    """候補セレクターを上から順に試してクリック。成功したら True を返す。"""
    for sel in selectors:
        if not sel:
            continue
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.click()
                print(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: セレクター全滅")
    return False


async def try_fill(page, selectors: list[str], value: str, label: str,
                   timeout: int = 5000) -> bool:
    """候補セレクターを上から順に試して入力。成功したら True を返す。"""
    for sel in selectors:
        if not sel:
            continue
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.fill(value)
                print(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: セレクター全滅")
    return False


# ──────────────────────────────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # ── 利用者番号 ──────────────────────────────────────────────────
    # まんまるよやく2 で確認された name 属性例: riyousyaNo / userid / loginId
    userid_candidates = [
        CONFIRMED_USERID_SEL,
        'input[name="riyousyaNo"]',
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="id"]',
        '#userid',
        '#loginId',
        '#riyousyaNo',
        'input[type="text"]:first-of-type',
    ]
    ok = await try_fill(page, userid_candidates, USER_ID, "利用者番号")
    if not ok:
        raise RuntimeError("利用者番号フィールドが見つかりません。analyze_site.py で確認してください。")

    # ── パスワード ────────────────────────────────────────────────
    passwd_candidates = [
        CONFIRMED_PASSWD_SEL,
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        '#passwd',
        '#password',
    ]
    ok = await try_fill(page, passwd_candidates, PASSWORD, "パスワード")
    if not ok:
        raise RuntimeError("パスワードフィールドが見つかりません。")

    # ── ログインボタン ────────────────────────────────────────────
    submit_candidates = [
        CONFIRMED_SUBMIT_SEL,
        'input[value="ログイン"]',
        'input[value="login"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="btnLogin"]',
        'input[name="login"]',
        'a:text("ログイン")',
    ]
    ok = await try_click(page, submit_candidates, "ログインボタン")
    if not ok:
        raise RuntimeError("ログインボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  ログイン後URL: {page.url}")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if any(w in body for w in ["パスワードが違", "利用者番号が違", "ログインできません", "エラー"]):
        raise RuntimeError(f"ログイン失敗: {body[:200]}")


# ──────────────────────────────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面
# ──────────────────────────────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    fav_candidates = [
        CONFIRMED_FAVORITE_SEL,
        'a:text("お気に入り")',
        'button:text("お気に入り")',
        'input[value="お気に入り"]',
        'a[href*="okiniri"]',
        'a[href*="favorite"]',
        'a[href*="okiniiri"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ]
    clicked = await try_click(page, fav_candidates, "お気に入り", timeout=ELEM_TIMEOUT)

    # フォールバック: ページ全体のテキストで探す
    if not clicked:
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            try:
                txt = (await elem.inner_text()).strip()
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    await elem.click()
                    print(f"  [OK] お気に入り（fallback）: text={txt!r}")
                    clicked = True
                    break
            except Exception:
                pass

    if not clicked:
        await save_ss(page, "ERROR_no_favorite")
        raise RuntimeError("お気に入りが見つかりません。02_after_login.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  絞り込み画面URL: {page.url}")


# ──────────────────────────────────────────────────────────────────────
# Step 3: 日付選択 → 検索（最速）
# ──────────────────────────────────────────────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    # ── CONFIRMED セレクターが設定されている場合は直接選択 ──────────
    if CONFIRMED_DATE_SEL:
        sel_elem = await page.wait_for_selector(CONFIRMED_DATE_SEL, timeout=ELEM_TIMEOUT)
        # テキスト一致で option を選ぶ
        for opt in await sel_elem.query_selector_all("option"):
            txt = (await opt.inner_text()).strip()
            v   = await opt.get_attribute("value") or ""
            if any(t in txt for t in TARGET_DATE_ALT_TEXTS) or v in TARGET_DATE_ALT_VALUES:
                await sel_elem.select_option(value=v if v else txt)
                print(f"  [OK] 日付選択(confirmed): value={v!r} text={txt!r}")
                return await _do_search(page)

    # ── 全 SELECT を走査して日付を探す ────────────────────────────
    date_selected = False
    selects = await page.query_selector_all("select")

    # パターン①: 1つの SELECT に「令和08年06月19日」相当のテキストがある
    for sel_elem in selects:
        for opt in await sel_elem.query_selector_all("option"):
            txt = (await opt.inner_text()).strip()
            v   = await opt.get_attribute("value") or ""
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v if v else txt)
                print(f"  [OK] 日付選択(scan): name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # パターン②: 年・月・日が別 SELECT（例: 年=令和08 / 月=06 / 日=19）
    if not date_selected:
        print("  [試行] 年月日を別SELECTで選択...")
        year_patterns  = ["令和08", "令和8", "令和０８", "08", "2026", "R08", "R8", "R.8"]
        month_patterns = ["06", "6", "６", "06月", "6月"]
        day_patterns   = ["19", "１９", "19日"]

        async def pick_option(patterns):
            for sel_elem in selects:
                for opt in await sel_elem.query_selector_all("option"):
                    txt = (await opt.inner_text()).strip()
                    v   = await opt.get_attribute("value") or ""
                    if any(p == txt.strip() or p == v.strip() for p in patterns):
                        await sel_elem.select_option(value=v if v else txt)
                        return True
            return False

        year_ok  = await pick_option(year_patterns)
        month_ok = await pick_option(month_patterns)
        day_ok   = await pick_option(day_patterns)
        date_selected = year_ok or month_ok or day_ok
        if date_selected:
            print(f"  [OK] 年={year_ok} 月={month_ok} 日={day_ok}")

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンにありません。"
            "analyze_site.py を実行してセレクターを確認してください。"
        )

    await _do_search(page)


async def _do_search(page):
    """検索ボタンをクリックして結果を待つ"""
    search_candidates = [
        CONFIRMED_SEARCH_SEL,
        'input[value="検索"]',
        'button:text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ]
    ok = await try_click(page, search_candidates, "検索ボタン")
    if not ok:
        raise RuntimeError("検索ボタンが見つかりません。")
    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  検索結果URL: {page.url}")


# ──────────────────────────────────────────────────────────────────────
# Step 4: D面 16:00〜18:00（赤丸）セルをクリック
# ──────────────────────────────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} 選択...")

    clicked = False

    # ── アプローチ①: テーブルを走査してD面行×16:00列の交差セルを探す ──
    tables = await page.query_selector_all("table")
    for table in tables:
        rows = await table.query_selector_all("tr")

        # ヘッダー行から「16:00〜18:00」列インデックスを取得
        time_col_idx = -1
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                # "16:00〜18:00" / "16:00～18:00" / "16:00-18:00" のいずれか
                if TARGET_TIME_START in txt and (
                    TARGET_TIME_END in txt
                    or "18" in txt
                ):
                    time_col_idx = ci
                    print(f"  [INFO] 時間列インデックス={ci} (text={txt!r})")
                    break
            if time_col_idx >= 0:
                break

        # D面の行でそのインデックスのセルをクリック
        if time_col_idx >= 0:
            for row in rows:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_FACILITY in txt:
                        # D面行発見 → time_col_idx 列のセルをクリック
                        if time_col_idx < len(cells):
                            target_cell = cells[time_col_idx]
                            tc_txt = (await target_cell.inner_text()).strip()
                            tc_cls = await target_cell.get_attribute("class") or ""
                            onclick = await target_cell.get_attribute("onclick") or ""
                            print(
                                f"  [FOUND] D面×16:00 "
                                f"text={tc_txt!r} class={tc_cls!r} onclick={onclick[:60]!r}"
                            )
                            await target_cell.click()
                            clicked = True
                        break
                if clicked:
                    break
        if clicked:
            break

    # ── アプローチ②: テキストで行ヘッダー＋時間テキスト同時一致を探す ──
    if not clicked:
        print("  [試行] テキスト同時一致で探索...")
        for cell in await page.query_selector_all("td, th"):
            txt = (await cell.inner_text()).strip()
            if TARGET_FACILITY in txt and TARGET_TIME_START in txt:
                cls = await cell.get_attribute("class") or ""
                print(f"  [FOUND] 複合テキスト一致: text={txt!r} class={cls!r}")
                await cell.click()
                clicked = True
                break

    # ── アプローチ③: onclick / href に D面+16 の情報があるリンク ──────
    if not clicked:
        print("  [試行] onclick/href からD面16:00を探索...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            combined = onclick + href
            if ("D面" in combined or "D" in combined) and "16" in combined:
                txt = (await elem.inner_text()).strip()
                print(f"  [FOUND] onclick={onclick[:60]!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    # ── アプローチ④: 赤丸マーク（○/●/◎）を持つセルで16:00付近を探す ──
    if not clicked:
        print("  [試行] 赤丸マーク付きセルで探索...")
        cells_16 = []
        for cell in await page.query_selector_all("td, th"):
            txt = (await cell.inner_text()).strip()
            cls = (await cell.get_attribute("class") or "").lower()
            # 赤丸クラス候補: red / available / circle / maru / open
            has_mark = any(k in cls for k in ["red", "avail", "circle", "maru", "open", "yoyaku"])
            if has_mark:
                cells_16.append(cell)
        print(f"  赤丸候補セル数: {len(cells_16)}")
        # D面の行の中から16:00列にあるセルを探す（行インデックスで判定）
        for cell in cells_16:
            row_elem = await cell.evaluate_handle("el => el.closest('tr')")
            row_cells = await row_elem.query_selector_all("td, th")
            for rc in row_cells:
                rtxt = (await rc.inner_text()).strip()
                if TARGET_FACILITY in rtxt:
                    print(f"  [FOUND] D面行の赤丸セルをクリック")
                    await cell.click()
                    clicked = True
                    break
            if clicked:
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。"
            "04_search_results.png を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  スロット選択後URL: {page.url}")


# ──────────────────────────────────────────────────────────────────────
# Step 5: 確定① （料金確認画面へ）
# ──────────────────────────────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①クリック（料金確認画面へ）...")

    confirm1_candidates = [
        'input[value="確定"]',
        'input[value="確認"]',
        'button:text("確定")',
        'button:text("確認")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'a:text("確定")',
        'a:text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ]
    ok = await try_click(page, confirm1_candidates, "確定①ボタン", timeout=ELEM_TIMEOUT)
    if not ok:
        await save_ss(page, "ERROR_confirm1_not_found")
        raise RuntimeError("確定①ボタンが見つかりません。05_slot_selected.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1_done")
    print(f"  確定①後URL: {page.url}")


# ──────────────────────────────────────────────────────────────────────
# Step 6: 確定② （最終確定）
# ──────────────────────────────────────────────────────────────────────
async def step_confirm2(page):
    print("\n[Step 6] 確定②クリック（最終確定）...")

    # Tampermonkey で window.confirm は無効化済みの前提。
    # 万一 confirm が来た場合は自動承認するフォールバックを設定。
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    confirm2_candidates = [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="最終確定"]',
        'input[value="申込確定"]',
        'button:text("予約確定")',
        'button:text("確定")',
        'input[value*="確定"]',
        'a:text("予約確定")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ]
    ok = await try_click(page, confirm2_candidates, "確定②ボタン", timeout=ELEM_TIMEOUT)
    if not ok:
        await save_ss(page, "ERROR_confirm2_not_found")
        raise RuntimeError("確定②ボタンが見つかりません。06_confirm1_done.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  最終確定後URL: {page.url}")

    # 完了判定
    body = await page.inner_text("body")
    print(f"  画面本文（先頭300字）:\n{body[:300]}")
    if any(w in body for w in ["予約完了", "受付完了", "受付番号", "予約番号", "申込完了", "完了"]):
        print("\n✅  予約完了を確認しました！")
    else:
        print("\n⚠️   完了メッセージが見つかりません。07_final_result.png を確認してください。")


# ──────────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象: {TARGET_DATE_WAREKI}  {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00)'} / "
          f"{'ヘッドレス' if opts['headless'] else 'ブラウザ表示'}")
    print("=" * 60)

    if opts["wait_for_open"]:
        await wait_until_open()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,
        )
        page = await context.new_page()

        try:
            await step_login(page)
            await step_favorite(page)
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)
            print("\n✅  すべてのステップが完了しました。")
        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌  エラー発生: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
