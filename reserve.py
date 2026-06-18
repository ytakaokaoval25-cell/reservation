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
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日（令和08年06月19日 = 2026-06-19 練習。本番は変更）
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19", "令和８年６月１９日",
]

# 分割型プルダウン用（年・月・日が別々のSELECT）
SPLIT_YEAR_VALUES  = ["令和08", "令和8", "08", "2026", "R08", "R8", "令和08年", "令和8年"]
SPLIT_MONTH_VALUES = ["06", "6", "６", "06月", "６月"]
SPLIT_DAY_VALUES   = ["19", "１９", "19日", "１９日"]

# 予約対象コート＆時間
TARGET_FACILITY    = "D面"
TARGET_TIME_START  = "16:00"
TARGET_TIME_END    = "18:00"

# 時報待ち設定（本番）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# スクリーンショット保存先
SS_DIR = "screenshots"
# ──────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


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
            print(f"[時報] 開始時刻到達: {now.strftime('%H:%M:%S.%f')}")
            break
        elif diff_sec > 300:
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            await asyncio.sleep(1)
        elif diff_sec > 0.1:
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception as e:
        print(f"  [SS 失敗] {e}")


async def page_info(page) -> str:
    try:
        title = await page.title()
        return f"URL={page.url}  TITLE={title!r}"
    except Exception:
        return f"URL={page.url}"


async def try_click(page, selectors: list, label: str, timeout: int = 5000) -> bool:
    """複数セレクターを順番に試してクリック。成功したらTrueを返す"""
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
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: いずれのセレクターにも該当なし")
    return False


async def try_fill(page, selectors: list, value: str, label: str, timeout: int = 5000) -> bool:
    """複数セレクターを順番に試して入力"""
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
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: いずれのセレクターにも該当なし")
    return False


# ──────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")
    print(f"  {await page_info(page)}")

    # 利用者番号（mnetシステムの一般的なname属性を網羅）
    uid_ok = await try_fill(page, [
        'input[name="loginno"]',
        'input[name="riyousyano"]',
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="userno"]',
        'input[name="memberNo"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid', '#loginno', '#riyousyano',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")

    if not uid_ok:
        raise RuntimeError("利用者番号フィールドが見つかりません。analyze_site.py を実行して確認してください。")

    # パスワード
    pw_ok = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        '#passwd', '#password',
    ], PASSWORD, "パスワード")

    if not pw_ok:
        raise RuntimeError("パスワードフィールドが見つかりません。")

    # ログインボタン
    await try_click(page, [
        'input[value="ログイン"]',
        'input[value="　ログイン　"]',
        'input[value="login"]',
        'button:has-text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
        'a:has-text("ログイン")',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  {await page_info(page)}")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if any(w in body for w in ["パスワードが違います", "ログインできません", "認証エラー", "利用者番号が"]):
        raise RuntimeError(f"ログイン失敗: {body[:200]}")


# ──────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面
# ──────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:has-text("お気に入り")',
        'input[value="お気に入り"]',
        'button:has-text("お気に入り")',
        'input[value*="お気に入り"]',
        'a:has-text("お気に入りから選択")',
        'input[value="お気に入りから選択"]',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    # テキスト走査フォールバック
    if not clicked:
        elems = await page.query_selector_all("a, button, input[type=button], input[type=submit]")
        for elem in elems:
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（テキスト走査）: text={txt!r}")
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_favorite_not_found")
        raise RuntimeError("お気に入りリンクが見つかりません。analyze_site.py を実行してメニュー構造を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  {await page_info(page)}")


# ──────────────────────────────────────────────
# Step 3: 日付プルダウンで令和08年06月19日を選択して検索
# ──────────────────────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False
    selects = await page.query_selector_all("select")

    # ── アプローチ①: 日付が1つのSELECT ──────────────────────
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
                print(f"  [OK] 日付選択（一体型）: name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── アプローチ②: 年・月・日が別々のSELECT ───────────────
    if not date_selected:
        print("  [試行] 年月日が分割SELECTの可能性あり...")
        year_set = month_set = day_set = False

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                # 年
                if not year_set and any(p in txt or p == v for p in SPLIT_YEAR_VALUES):
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 年選択: {txt!r} (value={v!r})")
                    year_set = True
                    break

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                # 月（年と別のSELECTを想定）
                if not month_set and any(p == txt or p == v for p in SPLIT_MONTH_VALUES):
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 月選択: {txt!r} (value={v!r})")
                    month_set = True
                    date_selected = True
                    break

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                # 日
                if not day_set and any(p == txt or p == v for p in SPLIT_DAY_VALUES):
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 日選択: {txt!r} (value={v!r})")
                    day_set = True
                    break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.py を実行して OPTION の value/text を確認してください。"
        )

    # 検索ボタン
    await try_click(page, [
        'input[value="検索"]',
        'input[value="　検索　"]',
        'button:has-text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:has-text("検索")',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  {await page_info(page)}")


# ──────────────────────────────────────────────
# Step 4: D面 16:00〜18:00 の赤丸セルをクリック
# ──────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    clicked = False
    tables  = await page.query_selector_all("table")

    # ── アプローチ①: ヘッダー列インデックス → D面行のセルを特定 ────
    #    最も確実。ヘッダー行の時間テキストから列番号を確定し、D面行を探す
    for table in tables:
        rows = await table.query_selector_all("tr")

        # ヘッダー行から「16:00〜18:00」の列インデックスを探す（最初の3行まで）
        time_col_idx = -1
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                # 「16:00〜18:00」「16:00-18:00」「16:00～18:00」などに対応
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_idx = ci
                    print(f"  [INFO] 列インデックス確定: {ci}  ヘッダーテキスト={txt!r}")
                    break
                # 開始時刻のみの場合（例: 列ヘッダーが「16:00」のみ）
                if txt == TARGET_TIME_START or txt.startswith(TARGET_TIME_START):
                    time_col_idx = ci
                    print(f"  [INFO] 列インデックス確定（開始時刻）: {ci}  text={txt!r}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue  # このテーブルには時間ヘッダーなし

        # D面行を探す
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_text = " ".join(
                [(await c.inner_text()).strip() for c in cells]
            )
            if TARGET_FACILITY not in row_text:
                continue

            if time_col_idx < len(cells):
                target_cell = cells[time_col_idx]
                tc_txt = (await target_cell.inner_text()).strip()
                tc_cls = await target_cell.get_attribute("class") or ""
                tc_onc = await target_cell.get_attribute("onclick") or ""
                print(f"  [FOUND] D面×列{time_col_idx}: text={tc_txt!r} class={tc_cls!r}")

                # セル内のリンクがあればリンクをクリック
                inner_link = await target_cell.query_selector("a")
                if inner_link:
                    await inner_link.click()
                    print(f"  [OK] 内部リンクをクリック")
                else:
                    await target_cell.click()
                clicked = True
            break

        if clicked:
            break

    # ── アプローチ②: D面行の全テキストからD面行を確定、16:00含むセルを選ぶ ──
    if not clicked:
        print("  [試行] アプローチ②: D面行を走査して16:00セルを探す...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                cell_texts = [(await c.inner_text()).strip() for c in cells]
                full_row = " ".join(cell_texts)

                if TARGET_FACILITY not in full_row:
                    continue

                print(f"  [INFO] D面行発見: {cell_texts[:8]}")
                for i, cell in enumerate(cells):
                    ct = cell_texts[i]
                    if TARGET_TIME_START in ct:
                        cc = await cell.get_attribute("class") or ""
                        inner_link = await cell.query_selector("a")
                        if inner_link:
                            await inner_link.click()
                        else:
                            await cell.click()
                        print(f"  [OK] D面 {TARGET_TIME_START} セル（アプローチ②）: text={ct!r} class={cc!r}")
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick / href に D面+時刻情報を持つ要素 ─────
    if not clicked:
        print("  [試行] アプローチ③: onclick/href/img alt に D面・16:00 を含む要素を探す...")
        candidates = await page.query_selector_all("[onclick], a[href], input[type=image]")
        for elem in candidates:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            alt     = await elem.get_attribute("alt") or ""
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            combined = " ".join([onclick, href, alt, txt]).lower()
            if ("d面" in combined or "d_men" in combined) and "16" in combined:
                print(f"  [FOUND③] onclick={onclick!r} href={href!r} alt={alt!r}")
                await elem.click()
                clicked = True
                break

    # ── アプローチ④: XPath でテキストが「○」等の予約可能セルを列・行で絞る ──
    if not clicked:
        print("  [試行] アプローチ④: XPath でD面と16:00の交差セルを探す...")
        # D面を含む行の、"16"を含む前の列数と同じインデックスのtdを探す
        try:
            # テーブル内でD面を含む行を取得
            d_row = await page.query_selector(
                f"xpath=//table//tr[td[contains(normalize-space(.), '{TARGET_FACILITY}')] or "
                f"th[contains(normalize-space(.), '{TARGET_FACILITY}')]]"
            )
            if d_row:
                # ヘッダー行（同テーブル最初のtr）で16:00の列位置を取得
                header_cells = await page.query_selector_all(
                    f"xpath=//table//tr[1]/td | //table//tr[1]/th"
                )
                col_idx = -1
                for ci, hc in enumerate(header_cells):
                    ht = (await hc.inner_text()).strip()
                    if TARGET_TIME_START in ht:
                        col_idx = ci
                        break
                if col_idx >= 0:
                    d_cells = await d_row.query_selector_all("td, th")
                    if col_idx < len(d_cells):
                        tc = d_cells[col_idx]
                        link = await tc.query_selector("a")
                        if link:
                            await link.click()
                        else:
                            await tc.click()
                        print(f"  [OK] アプローチ④ (XPath): 列{col_idx}")
                        clicked = True
        except Exception as e:
            print(f"  [アプローチ④失敗] {e}")

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"D面 {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。\n"
            "screenshots/04_search_results.png と analyze_site.py の出力を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  {await page_info(page)}")


# ──────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ──────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①クリック...")
    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="　確定　"]',
        'input[value="確認"]',
        'input[value="申込"]',
        'input[value="予約する"]',
        'input[value="次へ"]',
        'button:has-text("確定")',
        'button:has-text("確認")',
        'button:has-text("申込")',
        'button:has-text("次へ")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'a:has-text("確定")',
        'a:has-text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not clicked:
        await save_ss(page, "ERROR_confirm1_not_found")
        raise RuntimeError("確定①ボタンが見つかりません。screenshots/05_slot_selected.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  {await page_info(page)}")


# ──────────────────────────────────────────────
# Step 6: 確定②（最終確定）
#   Tampermonkey で window.confirm を無効化済みの前提
#   万一ダイアログが来た場合も自動承認するフォールバックを設定
# ──────────────────────────────────────────────
async def step_confirm2(page):
    print("\n[Step 6] 確定②クリック...")

    # window.confirm が発火した場合の自動承認
    async def accept_dialog(dialog):
        print(f"  [DIALOG] type={dialog.type} message={dialog.message!r} → accept")
        await dialog.accept()

    page.on("dialog", accept_dialog)

    # window.confirm をJS側でも強制的に true を返すよう上書き（二重保険）
    await page.evaluate("() => { window.confirm = () => true; }")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="　確定　"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="申込確定"]',
        'button:has-text("確定")',
        'button:has-text("予約確定")',
        'button:has-text("最終確定")',
        'input[value*="確定"]',
        'a:has-text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not clicked:
        await save_ss(page, "ERROR_confirm2_not_found")
        raise RuntimeError("確定②ボタンが見つかりません。screenshots/06_confirm1.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  {await page_info(page)}")

    # 完了判定
    body_text = await page.inner_text("body")
    completion_words = ["予約完了", "受付完了", "受付番号", "予約番号", "申込完了",
                        "完了しました", "受け付けました", "登録しました"]
    if any(w in body_text for w in completion_words):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが確認できません。07_final_result.png を確認してください。")
    print(f"  本文（先頭300字）: {body_text[:300]}")


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00:00)'} / "
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
            print(f"\n❌ エラー発生: {e}")
            print(f"   現在ページ: {await page_info(page)}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
