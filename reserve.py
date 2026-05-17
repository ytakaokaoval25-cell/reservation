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
LOGIN_URL   = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID     = "12015873"
PASSWORD    = "0508"

# 予約対象日（令和08年06月19日 = 2026-06-19 で練習。本番は変更）
TARGET_DATE_WAREKI = "令和08年06月19日"   # プルダウンに表示されるテキスト
TARGET_DATE_VALUE  = "20260619"           # value属性が数字形式の場合
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19",
]

# 予約対象コート＆時間
TARGET_FACILITY = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報待ち設定（本番）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト（ミリ秒）
NAV_TIMEOUT = 30_000
ELEM_TIMEOUT = 10_000

# スクリーンショット保存先（デバッグ用）
SS_DIR = "screenshots"
# ──────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位で待機"""
    print("[時報待ち] 朝5:00:00.000 まで待機します...")
    while True:
        now = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
            break
        elif diff_sec > 300:
            # 5分以上前: 30秒ごとにチェック
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            # 10秒～5分前: 1秒ごと
            await asyncio.sleep(1)
        elif diff_sec > 0.1:
            # 100ms～10秒前: 50msごと
            await asyncio.sleep(0.05)
        else:
            # 100ms以内: 1msごと（バスト防止）
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    """スクリーンショット保存（デバッグ用）"""
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_click(page, selectors: list[str], label: str, timeout: int = 5000) -> bool:
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
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


async def try_fill(page, selectors: list[str], value: str, label: str, timeout: int = 5000) -> bool:
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
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


async def step_login(page):
    """Step1: ログイン"""
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号
    await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")

    # パスワード
    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")

    # ログインボタン
    await try_click(page, [
        'input[value="ログイン"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
        'a:text("ログイン")',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


async def step_favorite(page):
    """Step2: お気に入りクリック → 絞り込み画面"""
    print("\n[Step 2] お気に入りをクリック...")
    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        'a:text-matches("お気に入り")',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト検索フォールバック
        elems = await page.query_selector_all("a, button, input[type=button], input[type=submit]")
        for elem in elems:
            txt = (await elem.inner_text()).strip() if await elem.inner_text() else ""
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（フォールバック）: text={txt!r}")
                clicked = True
                break
    if not clicked:
        raise RuntimeError("お気に入りリンクが見つかりません。analyze_site.pyで解析してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


async def step_select_date_and_search(page):
    """Step3: 日付プルダウンで令和08年06月19日を選択して検索（最速）"""
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    # すべてのSELECTを走査
    date_selected = False
    selects = await page.query_selector_all("select")

    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            # テキスト一致 or value一致
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                # select_optionはvalueまたはlabelで指定
                if v:
                    await sel_elem.select_option(value=v)
                else:
                    await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # 分割型（年・月・日が別SELECT）の場合
    if not date_selected:
        print("  [試行] 年月日が分割SELECTの可能性あり...")
        # 令和08年 / 06月 / 19日 をそれぞれ探す
        year_patterns  = ["令和08", "令和8", "08", "2026", "R08", "R8"]
        month_patterns = ["06", "6", "６月", "06月"]
        day_patterns   = ["19", "１９", "19日"]

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p == txt or p == v for p in year_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年選択: {txt!r}")
                    break
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p == txt or p == v for p in month_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月選択: {txt!r}")
                    date_selected = True
                    break
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p == txt or p == v for p in day_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日選択: {txt!r}")
                    break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.pyを実行してセレクターを確認してください。"
        )

    # 検索ボタン
    await try_click(page, [
        'input[value="検索"]',
        'button:text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


async def step_select_slot(page):
    """Step4: D面 16:00〜18:00 の赤丸セルをクリック"""
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    # ── アプローチ①: テキストで直接セルを探す ────────────────
    # D面の行ヘッダーと16:00〜18:00列の交差セルを特定
    clicked = False

    # まずテーブル全体を走査してD面の行を特定
    tables = await page.query_selector_all("table")
    for table in tables:
        rows = await table.query_selector_all("tr")
        for row in rows:
            cells = await row.query_selector_all("td, th")
            cell_texts = []
            for c in cells:
                cell_texts.append((await c.inner_text()).strip())

            # D面の行を特定
            if TARGET_FACILITY in cell_texts:
                d_idx = cell_texts.index(TARGET_FACILITY)
                print(f"  [INFO] D面行発見 cells={cell_texts}")
                # 同じ行で「16:00」または「16:00〜18:00」を含むセルをクリック
                for i, cell in enumerate(cells):
                    txt = cell_texts[i]
                    # 赤丸（○、●、◎）を持つセルかつ時間が一致
                    if TARGET_TIME_START in txt or "16" in txt:
                        cls = await cell.get_attribute("class") or ""
                        onclick = await cell.get_attribute("onclick") or ""
                        print(f"  [FOUND] D面×16:00 セル: text={txt!r} class={cls!r}")
                        await cell.click()
                        clicked = True
                        break
                if clicked:
                    break
        if clicked:
            break

    # ── アプローチ②: ヘッダー行から列インデックスを特定 ──────
    if not clicked:
        print("  [試行] ヘッダーから列インデックスで特定...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            time_col_idx = -1

            # ヘッダー行で16:00〜18:00の列を探す
            for row in rows[:3]:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                        time_col_idx = ci
                        print(f"  [INFO] 16:00〜18:00 列インデックス={ci}")
                        break
                if time_col_idx >= 0:
                    break

            if time_col_idx < 0:
                continue

            # D面の行でそのインデックスのセルをクリック
            for row in rows:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_FACILITY in txt:
                        # D面行が見つかった
                        if time_col_idx < len(cells):
                            target_cell = cells[time_col_idx]
                            tc_txt = (await target_cell.inner_text()).strip()
                            tc_cls = await target_cell.get_attribute("class") or ""
                            print(f"  [FOUND] D面×列{time_col_idx}: text={tc_txt!r} class={tc_cls!r}")
                            await target_cell.click()
                            clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick属性 or href にD面+時間の情報が含まれるリンク ──
    if not clicked:
        print("  [試行] onclick/href からD面16:00を探す...")
        all_elems = await page.query_selector_all("[onclick], a[href]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if ("D面" in combined or "d面" in combined.lower()) and "16" in combined:
                print(f"  [FOUND] onclick={onclick!r} href={href!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。"
            "analyze_site.pyのscreenshotsフォルダを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


async def step_confirm1(page):
    """Step5: 確定①（料金確認画面へ）"""
    print("\n[Step 5] 確定①クリック...")
    clicked = await try_click(page, [
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
    ], "確定①ボタン")

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


async def step_confirm2(page):
    """Step6: 確定②（最終確定）
    Tampermonkey で window.confirm を無効化済みのため
    dialog イベントは発火しない前提
    """
    print("\n[Step 6] 確定②クリック...")

    # 万一 confirm ダイアログが来た場合のフォールバック（自動承認）
    page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'input[value*="確定"]',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not clicked:
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了確認
    body_text = await page.inner_text("body")
    if any(w in body_text for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。スクリーンショットを確認してください。")
    print(f"  最終本文（先頭200字）: {body_text[:200]}")


async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

    # 時報待ち
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
            print(f"\n❌ エラー: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
