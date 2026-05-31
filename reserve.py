"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分

■ 使い方
  python reserve.py              # 本番モード：5:00前にログイン完了→5:00:00.000に検索発射
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備（ローカル実行）
  pip install playwright
  playwright install chromium
  python analyze_site.py          # まず解析して正確なセレクターを確認する
  python reserve.py --now --headful  # 動作確認

■ 戦略（先回り方式）
  4:55頃 → ログイン → お気に入りページへ移動して待機
  5:00:00.000 → 日付選択 → 検索 → D面クリック → 確定① → 確定②
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ═══════════════════════════════════════════════════════════════
# 設定値（本番前に必ず analyze_site.py で確認して修正すること）
# ═══════════════════════════════════════════════════════════════
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# ── 予約対象日 ────────────────────────────────────────────────
TARGET_DATE_WAREKI = "令和08年06月19日"   # プルダウン表示テキスト（練習）
# 本番(7月分)に変える場合は下記も一緒に変更
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日",  "2026/06/19",      "R8.6.19",
]
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]

# 分割型（年/月/日 が別SELECT）の場合に使う候補値
TARGET_YEAR_PATTERNS  = ["令和08", "令和8", "令和０８", "08", "2026", "R08", "R8"]
TARGET_MONTH_PATTERNS = ["06", "6", "６", "6月", "06月", "６月"]
TARGET_DAY_PATTERNS   = ["19", "１９", "19日", "１９日"]

# ── 予約対象施設・時間 ────────────────────────────────────────
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# ── 時報設定 ──────────────────────────────────────────────────
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# ── タイムアウト（ms） ────────────────────────────────────────
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

SS_DIR = "screenshots"
# ═══════════════════════════════════════════════════════════════


def parse_args():
    args = sys.argv[1:]
    return {
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


async def wait_until_open():
    """
    朝 5:00:00.000 ぴったりまでミリ秒単位で待機。
    先回り戦略: ログイン・ページ遷移はこの前に済ませておく。
    """
    while True:
        now    = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND,
            microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 発射: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
            return
        elif diff_sec > 300:   # 5分以上前: 30秒ごと
            print(f"[時報待ち] あと {diff_sec/60:.1f}分...")
            await asyncio.sleep(30)
        elif diff_sec > 10:    # 10秒〜5分前: 1秒ごと
            await asyncio.sleep(1)
        elif diff_sec > 0.5:   # 0.5〜10秒前: 50msごと
            await asyncio.sleep(0.05)
        else:                  # 500ms以内: 1msごと（高精度）
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception as e:
        print(f"  [SS ERROR] {path}: {e}")


async def try_click(page, selectors: list[str], label: str, timeout: int = 5000) -> bool:
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.click()
                print(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            continue
        except Exception as e:
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: 候補セレクター全滅")
    return False


async def try_fill(page, selectors: list[str], value: str, label: str, timeout: int = 5000) -> bool:
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.fill(value)
                print(f"  [OK] {label}入力: {sel}")
                return True
        except PWTimeout:
            continue
        except Exception as e:
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: 候補セレクター全滅")
    return False


# ───────────────────────────────────────────────────────────────
# Step 1: ログイン
# ───────────────────────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号フィールド（analyze_site.py の出力で確認してから修正）
    filled = await try_fill(page, [
        'input[name="userid"]',
        'input[name="uid"]',
        'input[name="userno"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid', '#uid', '#userno',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")
    if not filled:
        await save_ss(page, "ERROR_login_userid")
        raise RuntimeError("利用者番号フィールドが見つかりません。analyze_site.pyで確認してください。")

    # パスワードフィールド
    filled = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[name="pw"]',
    ], PASSWORD, "パスワード")
    if not filled:
        await save_ss(page, "ERROR_login_passwd")
        raise RuntimeError("パスワードフィールドが見つかりません。")

    # ログインボタン
    clicked = await try_click(page, [
        'input[value="ログイン"]',
        'input[value="LOGIN"]',
        'input[value="login"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("ログイン")',
    ], "ログインボタン")
    if not clicked:
        await save_ss(page, "ERROR_login_submit")
        raise RuntimeError("ログインボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if "エラー" in body and "パスワード" in body:
        raise RuntimeError("ログイン失敗（ID/パスワード確認）")


# ───────────────────────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面へ移動して待機
# ───────────────────────────────────────────────────────────────
async def step_navigate_to_favorite(page):
    print("\n[Step 2] お気に入りをクリックして絞り込み画面へ...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'a:text-matches("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        '[onclick*="favorite"]',
        '[onclick*="okiniri"]',
        '[href*="favorite"]',
        '[href*="okiniri"]',
        '[class*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    # テキスト全探索フォールバック
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
                print(f"  [OK] お気に入り（テキスト全探索）: {txt!r}")
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_favorite")
        raise RuntimeError(
            "お気に入りリンクが見つかりません。\n"
            "analyze_site.pyで 02_after_login.html を確認してセレクターを修正してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")
    print("  [OK] 絞り込み画面に到達。5:00:00まで待機します...")


# ───────────────────────────────────────────────────────────────
# Step 3: 日付選択 + 検索（5:00:00.000 に発射）
# ───────────────────────────────────────────────────────────────
async def _select_date_from_selects(page) -> bool:
    """全SELECTを走査して対象日を選択。成功でTrue。"""
    selects = await page.query_selector_all("select")
    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or any(v == av for av in TARGET_DATE_ALT_VALUES)):
                sel_name = await sel_elem.get_attribute("name") or "(unknown)"
                await (sel_elem.select_option(value=v) if v
                       else sel_elem.select_option(label=txt))
                print(f"  [OK] 日付選択（一体型）: name={sel_name!r} value={v!r} text={txt!r}")
                return True
    return False


async def _select_date_split(page) -> bool:
    """年・月・日が分割SELECTの場合に対応。成功でTrue。"""
    selects = await page.query_selector_all("select")
    year_done = month_done = day_done = False

    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        opts_data = [(await o.get_attribute("value") or "", (await o.inner_text()).strip())
                     for o in options]
        # 年
        for v, txt in opts_data:
            if any(p in txt or p == v for p in TARGET_YEAR_PATTERNS):
                await sel_elem.select_option(value=v if v else txt)
                print(f"  [OK] 年選択: {txt!r}")
                year_done = True
                break
        # 月
        for v, txt in opts_data:
            if any(p == txt.strip("月") or p == v for p in TARGET_MONTH_PATTERNS):
                await sel_elem.select_option(value=v if v else txt)
                print(f"  [OK] 月選択: {txt!r}")
                month_done = True
                break
        # 日
        for v, txt in opts_data:
            if any(p == txt.strip("日") or p == v for p in TARGET_DAY_PATTERNS):
                await sel_elem.select_option(value=v if v else txt)
                print(f"  [OK] 日選択: {txt!r}")
                day_done = True
                break

    return month_done  # 月が合えば実質OK（年は省略可能なシステムもある）


async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    # 最大3回リトライ（5:00直後はページが更新される場合があるため）
    date_selected = False
    for attempt in range(3):
        # ① 一体型SELECT（例: 「令和08年06月19日」が1つのoption）
        date_selected = await _select_date_from_selects(page)
        if date_selected:
            break

        # ② 分割型SELECT
        date_selected = await _select_date_split(page)
        if date_selected:
            break

        if attempt < 2:
            print(f"  [RETRY {attempt+1}] 日付未発見。ページをリロードして再試行...")
            await page.reload(wait_until="networkidle", timeout=NAV_TIMEOUT)
            await asyncio.sleep(0.3)

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。\n"
            "analyze_site.pyを実行して 03_after_favorite.html のSELECT・OPTIONを確認し、\n"
            "TARGET_DATE_ALT_TEXTS / TARGET_DATE_ALT_VALUES に実際の値を追加してください。"
        )

    # 検索ボタン
    clicked = await try_click(page, [
        'input[value="検索"]',
        'input[value="検　索"]',
        'button:text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ], "検索ボタン")
    if not clicked:
        await save_ss(page, "ERROR_search_button")
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


# ───────────────────────────────────────────────────────────────
# Step 4: D面 16:00〜18:00 の赤丸セルをクリック
# ───────────────────────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")
    clicked = False

    tables = await page.query_selector_all("table")

    # ── アプローチ①: ヘッダーから列インデックスを特定してD面行をクリック ──
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行（先頭3行以内）で 16:00 を含む列を探す
        for row in rows[:4]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt:
                    time_col_idx = ci
                    print(f"  [INFO] {TARGET_TIME_START} 列インデックス={ci} text={txt!r}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行でその列のセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_has_d = False
            for cell in cells:
                txt = (await cell.inner_text()).strip()
                if TARGET_FACILITY in txt:
                    row_has_d = True
                    break

            if not row_has_d:
                continue

            if time_col_idx < len(cells):
                target_cell = cells[time_col_idx]
                tc_txt = (await target_cell.inner_text()).strip()
                tc_cls = await target_cell.get_attribute("class") or ""
                tc_onclick = await target_cell.get_attribute("onclick") or ""
                print(f"  [FOUND] D面×{TARGET_TIME_START} text={tc_txt!r} class={tc_cls!r}")

                # クリック可能かどうか確認（×や満等は避ける）
                skip_words = ["×", "✕", "満", "休", "---", "－", "ー"]
                if any(w in tc_txt for w in skip_words):
                    print(f"  [WARN] 予約不可セルです（{tc_txt!r}）")
                    await save_ss(page, "ERROR_slot_unavailable")
                    raise RuntimeError(f"D面 {TARGET_TIME_START}〜{TARGET_TIME_END} は予約不可 ({tc_txt!r})")

                # セル内リンクがあればそちらをクリック
                inner_link = await target_cell.query_selector("a, input[type=button], input[type=submit]")
                if inner_link:
                    await inner_link.click()
                    print(f"  [OK] セル内リンクをクリック")
                elif tc_onclick:
                    await target_cell.click()
                    print(f"  [OK] onclick付きセルをクリック: {tc_onclick[:60]!r}")
                else:
                    await target_cell.click()
                    print(f"  [OK] セルをクリック")

                clicked = True
                break

        if clicked:
            break

    # ── アプローチ②: onclick/href にD面+時間の情報が含まれる要素 ──
    if not clicked:
        print("  [試行②] onclick/href からD面16:00を探す...")
        all_elems = await page.query_selector_all("[onclick], a[href]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if (TARGET_FACILITY in combined or "d面" in combined.lower()) and "16" in combined:
                print(f"  [FOUND②] onclick={onclick[:60]!r} href={href[:60]!r}")
                await elem.click()
                clicked = True
                break

    # ── アプローチ③: テキスト「○」「◎」が含まれる16:00付近セル ──
    if not clicked:
        print("  [試行③] 赤丸マーク(○◎●)でD面行を探す...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                texts = [(await c.inner_text()).strip() for c in cells]

                if not any(TARGET_FACILITY in t for t in texts):
                    continue

                # D面行の中で ○ や ◎ が含まれるセルを左から走査
                for i, (cell, txt) in enumerate(zip(cells, texts)):
                    if any(m in txt for m in ["○", "◎", "●", "〇"]):
                        cls = await cell.get_attribute("class") or ""
                        print(f"  [FOUND③] D面行 col={i} text={txt!r} class={cls!r}")
                        await cell.click()
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"D面 {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。\n"
            "analysis_output/04_search_results.html でテーブル構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ───────────────────────────────────────────────────────────────
# Step 5: 確定① （料金確認画面へ進む）
# ───────────────────────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①クリック...")
    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value="料金確認"]',
        'button:text("確定")',
        'button:text("確認")',
        'button:text("次へ")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'a:text("確定")',
        'a:text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")
    if not clicked:
        await save_ss(page, "ERROR_confirm1")
        raise RuntimeError("確定①ボタンが見つかりません。05_slot_selected.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


# ───────────────────────────────────────────────────────────────
# Step 6: 確定② （最終確定）
# Tampermonkey で window.confirm 無効化済み前提。
# 万一ダイアログが来た場合のフォールバックも設定済み。
# ───────────────────────────────────────────────────────────────
async def step_confirm2(page):
    print("\n[Step 6] 確定②クリック...")
    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="最終確定"]',
        'input[value="登録"]',
        'button:text("予約確定")',
        'button:text("確定")',
        'input[value*="確定"]',
        'a:text("確定")',
        'a:text("予約確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")
    if not clicked:
        await save_ss(page, "ERROR_confirm2")
        raise RuntimeError("確定②ボタンが見つかりません。06_confirm1.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了確認
    body_text = await page.inner_text("body")
    if any(w in body_text for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。07_final_result.png を確認してください。")
    print(f"  ページ本文（先頭300字）:\n  {body_text[:300]}")


# ───────────────────────────────────────────────────────────────
# メイン
# ───────────────────────────────────────────────────────────────
async def main():
    opts = parse_args()

    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}")
    print(f"施設:   {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    mode_str = ("即時実行" if not opts["wait_for_open"] else "先回り方式（5:00:00.000 発射）")
    disp_str = ("ブラウザ表示あり" if not opts["headless"] else "ヘッドレス")
    print(f"モード: {mode_str} / {disp_str}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
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

        # window.confirm が来ても自動 accept（Tampermonkeyのバックアップ）
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        try:
            # Phase 1: ログイン（5:00前に完了させる）
            await step_login(page)

            # Phase 2: お気に入り → 絞り込み画面へ移動（5:00前に完了させる）
            await step_navigate_to_favorite(page)

            # ★ここで 5:00:00.000 まで待機（先回り方式の核心）
            if opts["wait_for_open"]:
                print("\n[待機] 検索ページで 5:00:00.000 を待ちます...")
                await wait_until_open()

            # Phase 3: 日付選択 + 検索（5:00:00.000 に発射）
            await step_select_date_and_search(page)

            # Phase 4: D面 16:00〜18:00 クリック
            await step_select_slot(page)

            # Phase 5: 確定①
            await step_confirm1(page)

            # Phase 6: 確定②
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
