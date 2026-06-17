"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）

■ 使い方
  python reserve.py              # 朝5:00:00 JST 時報待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備
  pip install playwright
  playwright install chromium

■ 本番運用時（令和8年7月分予約）
  TARGET_DATE_* と WAIT_UNTIL_* を7月用に変更して実行。
  スクリプトは6月19日 4:00AM JST頃に起動しておくことを推奨。
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ─────────────────────────────────────────────────────────
# ■ 設定値（ここだけ変更すれば本番・練習を切り替えられる）
# ─────────────────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約受付開始日時（JST） ← 練習: 令和08年06月19日 05:00
WAIT_UNTIL = datetime.datetime(2026, 6, 19, 5, 0, 0,
                               tzinfo=datetime.timezone(datetime.timedelta(hours=9)))

# 検索する日付（令和08年06月19日 = 2026-06-19）
TARGET_DATE_WAREKI     = "令和08年06月19日"
TARGET_DATE_ALT_TEXTS  = [
    "令和08年06月19日", "令和8年6月19日",
    "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19",
]
TARGET_DATE_ALT_VALUES = ["20260619", "2026-06-19", "2026/06/19", "260619"]

# 予約対象コート＆時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# スクリーンショット保存先（デバッグ用）
SS_DIR = "screenshots"
# ─────────────────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


async def wait_until_open():
    """WAIT_UNTIL（JST）ぴったりまでミリ秒単位で待機。
    前日から起動しておいても正確に動作する。
    """
    print(f"[時報待ち] {WAIT_UNTIL.strftime('%Y-%m-%d %H:%M:%S')} JST まで待機します...")

    while True:
        now = datetime.datetime.now(tz=WAIT_UNTIL.tzinfo)
        diff_sec = (WAIT_UNTIL - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {now.strftime('%H:%M:%S.%f')[:-3]} JST")
            break
        elif diff_sec > 3600:
            # 1時間以上: 5分ごとにチェック
            print(f"[待機] あと {diff_sec/3600:.1f}時間 ({int(diff_sec//60)}分)...")
            await asyncio.sleep(300)
        elif diff_sec > 300:
            # 5分〜1時間: 30秒ごと
            print(f"[待機] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            # 10秒〜5分: 1秒ごと
            await asyncio.sleep(1)
        elif diff_sec > 0.1:
            # 100ms〜10秒: 50msごと（高精度）
            await asyncio.sleep(0.05)
        else:
            # 100ms以内: 1msごと（最終スパート）
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    """スクリーンショット保存（デバッグ用）"""
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception as e:
        print(f"  [SS-ERR] {path}: {e}")


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
            print(f"  [SKIP] {label} ({sel}): {type(e).__name__}")
    print(f"  [FAIL] {label}: 全セレクター失敗")
    return False


async def try_fill(page, selectors: list, value: str, label: str,
                   timeout: int = 5000) -> bool:
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
            print(f"  [SKIP] {label} ({sel}): {type(e).__name__}")
    print(f"  [FAIL] {label}: 全セレクター失敗")
    return False


async def step_login(page):
    """Step1: ログインページにアクセスしてログイン"""
    print("\n" + "="*60)
    print("[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")
    print(f"  URL: {page.url}")

    # 利用者番号入力
    ok = await try_fill(page, [
        'input[name="userid"]',   'input[name="user_id"]',
        'input[name="memberNo"]', 'input[name="userno"]',
        'input[name="loginId"]',  'input[name="login_id"]',
        'input[name="id"]',       '#userid',
        'input[type="text"]',
    ], USER_ID, "利用者番号")
    if not ok:
        raise RuntimeError("利用者番号フィールドが見つかりません")

    # パスワード入力
    ok = await try_fill(page, [
        'input[type="password"]', 'input[name="passwd"]',
        'input[name="password"]', 'input[name="pass"]',
    ], PASSWORD, "パスワード")
    if not ok:
        raise RuntimeError("パスワードフィールドが見つかりません")

    # ログインボタン
    ok = await try_click(page, [
        'input[value="ログイン"]',    'button:text("ログイン")',
        'input[value="LOGIN"]',      'a:text("ログイン")',
        'input[type="submit"]',      'button[type="submit"]',
    ], "ログインボタン")
    if not ok:
        raise RuntimeError("ログインボタンが見つかりません")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  ログイン後URL: {page.url}")


async def step_favorite(page):
    """Step2: お気に入りをクリックして絞り込み画面へ"""
    print("\n" + "="*60)
    print("[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        'a[href*="okiniri"]',
        'a[href*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
        '[onclick*="favorite"]',
        '[onclick*="okiniri"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全走査フォールバック
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            val = await elem.get_attribute("value") or ""
            txt = ""
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                pass
            if "お気に入り" in txt or "お気に入り" in val:
                print(f"  [OK] お気に入り（フォールバック）: text={txt!r} val={val!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_favorite_not_found")
        raise RuntimeError("お気に入りリンクが見つかりません。analyze_site.py で解析してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  絞り込み画面URL: {page.url}")


async def step_select_date_and_search(page):
    """Step3: 日付プルダウンで対象日を選択して検索（最速）"""
    print("\n" + "="*60)
    print(f"[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    # ── アプローチ①: 1つのSELECTに日付がまとめて入っているパターン ──
    date_selected = False
    selects = await page.query_selector_all("select")

    for sel_elem in selects:
        for opt in await sel_elem.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                await (sel_elem.select_option(value=v) if v
                       else sel_elem.select_option(label=txt))
                print(f"  [OK] 日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── アプローチ②: 年・月・日が別SELECTに分かれているパターン ──
    if not date_selected:
        print("  [試行] 年月日分割SELECTを検索...")

        # 年選択
        year_patterns  = ["令和08", "令和8", "08", "2026", "R08", "R8", "８", "８年"]
        month_patterns = ["06", "6", "６", "06月", "６月"]
        day_patterns   = ["19", "１９", "19日", "１９日"]

        year_found = month_found = day_found = False

        for sel_elem in selects:
            opts = await sel_elem.query_selector_all("option")
            texts = [(await o.get_attribute("value") or "", (await o.inner_text()).strip())
                     for o in opts]
            for v, txt in texts:
                if not year_found and any(p in txt or p == v for p in year_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年選択: {txt!r}")
                    year_found = True
                    break
                if not month_found and any(p == txt or p == v for p in month_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月選択: {txt!r}")
                    month_found = True
                    break
                if not day_found and any(p == txt or p == v for p in day_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日選択: {txt!r}")
                    day_found = True
                    break

        date_selected = month_found or day_found or year_found

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.pyを実行してSELECTのvalue一覧を確認してください。"
        )

    # 検索ボタンクリック
    ok = await try_click(page, [
        'input[value="検索"]',  'button:text("検索")',
        'input[value*="検索"]', 'a:text("検索")',
        'input[type="submit"]', 'button[type="submit"]',
    ], "検索ボタン")
    if not ok:
        raise RuntimeError("検索ボタンが見つかりません")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  検索結果URL: {page.url}")


async def step_select_slot(page):
    """Step4: D面 16:00〜18:00（赤丸）セルをクリック"""
    print("\n" + "="*60)
    print(f"[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    clicked = False
    tables  = await page.query_selector_all("table")

    # ── アプローチ①: ヘッダーから列インデックスを特定してD面行と交差 ──
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # 先頭3行からヘッダーを探す
        for row in rows[:3]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt:
                    time_col_idx = ci
                    print(f"  [INFO] {TARGET_TIME_START} 列インデックス={ci}（テキスト: {txt!r}）")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行を探してその列のセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_has_d = any(
                TARGET_FACILITY in (await c.inner_text()).strip()
                for c in cells
            )
            if not row_has_d:
                continue

            print(f"  [INFO] D面行発見")
            if time_col_idx < len(cells):
                target_cell = cells[time_col_idx]
                tc_txt = (await target_cell.inner_text()).strip()
                tc_cls = await target_cell.get_attribute("class") or ""
                tc_on  = await target_cell.get_attribute("onclick") or ""

                # aタグが内包されていればそちらをクリック
                a_tag  = await target_cell.query_selector("a")
                clicker = a_tag if a_tag else target_cell
                print(
                    f"  [FOUND] D面×{TARGET_TIME_START}: "
                    f"text={tc_txt!r} class={tc_cls!r} onclick={tc_on!r}"
                )
                await clicker.click()
                clicked = True
            break

        if clicked:
            break

    # ── アプローチ②: 全テキストからD面+時間セルを探す ──────────────
    if not clicked:
        print("  [試行] D面の行から直接セルのテキストで探す...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                texts = [(await c.inner_text()).strip() for c in cells]
                if TARGET_FACILITY not in texts and not any(TARGET_FACILITY in t for t in texts):
                    continue
                # D面行：16:00含むセルをクリック
                for ci, cell in enumerate(cells):
                    txt = texts[ci]
                    if TARGET_TIME_START in txt:
                        a   = await cell.query_selector("a")
                        print(f"  [FOUND-T] D面×{TARGET_TIME_START}: text={txt!r}")
                        await (a if a else cell).click()
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick/href にD面+時間の情報が含まれる要素 ────
    if not clicked:
        print("  [試行] onclick/href でD面+16を探す...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = ""
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                pass
            combined = onclick + href + txt
            if (TARGET_FACILITY in combined or "d面" in combined.lower()) and "16" in combined:
                print(f"  [FOUND-O] onclick={onclick!r} href={href!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。"
            f"{SS_DIR}/04_search_results.png を確認してセレクターを特定してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  スロット選択後URL: {page.url}")


async def step_confirm1(page):
    """Step5: 確定①（料金確認画面へ進む）"""
    print("\n" + "="*60)
    print("[Step 5] 確定①クリック...")

    ok = await try_click(page, [
        'input[value="確定"]',    'input[value="確認"]',
        'input[value*="確定"]',   'input[value*="確認"]',
        'button:text("確定")',    'button:text("確認")',
        'a:text("確定")',         'a:text("確認")',
        'input[type="submit"]',  'button[type="submit"]',
    ], "確定①ボタン", timeout=ELEM_TIMEOUT)

    if not ok:
        await save_ss(page, "ERROR_confirm1_not_found")
        raise RuntimeError("確定①ボタンが見つかりません")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1_done")
    print(f"  確定①後URL: {page.url}")


async def step_confirm2(page):
    """Step6: 確定②（最終確定）
    ・Tampermonkey で window.confirm が無効化されている前提
    ・念のため JS 上書き & Playwright のダイアログ自動承認も設定
    """
    print("\n" + "="*60)
    print("[Step 6] 確定②クリック...")

    # window.confirm を JS で上書き（Tampermonkey が無い環境の保険）
    await page.evaluate("window.confirm = () => true; window.alert = () => {};")

    # Playwright レベルでもダイアログを自動承認
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    ok = await try_click(page, [
        'input[value="予約確定"]',  'input[value="確定"]',
        'input[value="最終確定"]',  'input[value*="確定"]',
        'button:text("予約確定")',  'button:text("確定")',
        'a:text("予約確定")',       'a:text("確定")',
        'input[type="submit"]',    'button[type="submit"]',
    ], "確定②ボタン", timeout=ELEM_TIMEOUT)

    if not ok:
        await save_ss(page, "ERROR_confirm2_not_found")
        raise RuntimeError("確定②ボタンが見つかりません")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  確定②後URL: {page.url}")

    # 完了キーワード確認
    body_text = await page.inner_text("body")
    completion_words = ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました", "受付しました"]
    if any(w in body_text for w in completion_words):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。スクリーンショットを確認してください。")
    print(f"  最終本文（先頭300字）: {body_text[:300]!r}")


async def main():
    opts = parse_args()

    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日    : {TARGET_DATE_WAREKI}")
    print(f"施設      : {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    wait_str  = WAIT_UNTIL.strftime("%Y-%m-%d %H:%M:%S JST")
    mode_str  = f"即時実行" if not opts["wait_for_open"] else f"時報待ち({wait_str})"
    disp_str  = "ブラウザ表示あり" if not opts["headless"] else "ヘッドレス"
    print(f"モード    : {mode_str} / {disp_str}")
    print("=" * 60)

    # 時報待ち
    if opts["wait_for_open"]:
        now_jst = datetime.datetime.now(tz=WAIT_UNTIL.tzinfo)
        if now_jst >= WAIT_UNTIL:
            print(f"[INFO] 既に開始時刻を過ぎています。即時実行します。")
        else:
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

            print("\n" + "="*60)
            print("✅ すべてのステップが完了しました。")
            print(f"   スクリーンショット: ./{SS_DIR}/")
            print("=" * 60)

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー発生: {e}")
            print(f"   スクリーンショット: ./{SS_DIR}/ を確認してください。")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
