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
# タイムゾーン（日本標準時 JST = UTC+9）
# ──────────────────────────────────────────────
JST = datetime.timezone(datetime.timedelta(hours=9))

# ──────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────
LOGIN_URL   = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID     = "12015873"
PASSWORD    = "0508"

# ── 練習用: 令和08年06月19日（2026-06-19）──
# ── 本番用: 令和08年07月19日（2026-07-19）に下記を書き換える ──
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日",
    "令和０８年０６月１９日", "令和08年06月19日",
    "2026年06月19日", "2026/06/19",
]

# 予約対象コート＆時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

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
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


async def wait_until_open():
    """朝5:00:00.000 JST ぴったりまでミリ秒単位で待機"""
    now = datetime.datetime.now(JST)
    target = now.replace(
        hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
    )
    if now >= target:
        print(f"[時報] すでに {OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d} を過ぎています。即時実行します。")
        print(f"  現在JST: {now.strftime('%H:%M:%S.%f')}")
        return

    print(f"[時報待ち] {OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d} JST まで待機します...")
    print(f"  現在JST: {now.strftime('%H:%M:%S.%f')}")
    print(f"  目標JST: {target.strftime('%H:%M:%S.%f')}")

    while True:
        now = datetime.datetime.now(JST)
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            break
        elif diff_sec > 300:
            # 5分以上前: 30秒ごとにログを出しながら待機
            print(f"  あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)... [{now.strftime('%H:%M:%S')} JST]")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            # 10秒〜5分前: 1秒ごと
            await asyncio.sleep(1)
        elif diff_sec > 0.1:
            # 100ms〜10秒前: 50msごと（精密フェーズ）
            await asyncio.sleep(0.05)
        else:
            # 最後の100ms: 1msビジーウェイト（最高精度）
            await asyncio.sleep(0.001)

    print(f"[時報] 開始！ {datetime.datetime.now(JST).strftime('%H:%M:%S.%f')} JST")


async def save_ss(page, name: str):
    """スクリーンショット保存"""
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_click(page, selectors: list, label: str, timeout: int = 5000) -> bool:
    """複数セレクターを順番に試してクリック（Playwright拡張CSS対応）"""
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
    print(f"  [FAIL] {label}: 該当要素なし（全セレクター失敗）")
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
    print(f"  [FAIL] {label}: 該当要素なし（全セレクター失敗）")
    return False


async def step_login(page):
    """Step1: ログイン"""
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号（実サイトで analyze_site.py 実行後にname値を確認して先頭に追加）
    await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid',
        'input[type="text"]',
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
        'input[value="LOGIN"]',
        'input[value="ログ イン"]',
        'button:has-text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
        'a:has-text("ログイン")',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


async def step_favorite(page):
    """Step2: お気に入りクリック → 絞り込み画面"""
    print("\n[Step 2] お気に入りをクリック...")

    # セレクターを優先度順に試す
    clicked = await try_click(page, [
        'a:has-text("お気に入り")',
        'input[value="お気に入り"]',
        'button:has-text("お気に入り")',
        '[class*="favorite"]',
        '[id*="favorite"]',
        '[onclick*="favorite"]',
        '[onclick*="okiniri"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全文検索フォールバック
        for selector in ["a", "button", "input[type=button]", "input[type=submit]"]:
            elems = await page.query_selector_all(selector)
            for elem in elems:
                try:
                    if selector == "a" or selector == "button":
                        txt = (await elem.inner_text()).strip()
                    else:
                        txt = (await elem.get_attribute("value") or "").strip()
                    if "お気に入り" in txt:
                        await elem.click()
                        print(f"  [OK] お気に入り（フォールバック）: selector={selector} text={txt!r}")
                        clicked = True
                        break
                except Exception:
                    pass
            if clicked:
                break

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行してセレクターを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


async def step_select_date_and_search(page):
    """Step3: 日付プルダウンで令和08年06月19日を選択して検索（最速）"""
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False
    selects = await page.query_selector_all("select")

    # ── パターンA: 1つのSELECTに完全な日付文字列がある ─────────
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
                print(f"  [OK] 日付選択(完全): name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── パターンB: 年・月・日が別SELECTに分かれている ───────────
    if not date_selected:
        print("  [試行] 年月日が分割SELECTの可能性あり...")
        year_patterns  = ["令和08", "令和8", "08", "8", "2026", "R08", "R8"]
        month_patterns = ["06", "6", "６", "６月", "06月", "6月"]
        day_patterns   = ["19", "１９", "19日", "１９日"]

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if txt in year_patterns or v in year_patterns:
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年選択: value={v!r} text={txt!r}")
                    break

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if txt in month_patterns or v in month_patterns:
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月選択: value={v!r} text={txt!r}")
                    date_selected = True
                    break

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if txt in day_patterns or v in day_patterns:
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日選択: value={v!r} text={txt!r}")
                    break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.py を実行してセレクターを確認してください。"
        )

    # 検索ボタン
    await try_click(page, [
        'input[value="検索"]',
        'input[value*="検索"]',
        'button:has-text("検索")',
        'a:has-text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


async def step_select_slot(page):
    """Step4: D面 16:00〜18:00 の赤丸セルをクリック

    テーブル構造パターン:
      A) 行ヘッダー=施設名、列ヘッダー=時間帯
      B) 行ヘッダー=時間帯、列ヘッダー=施設名
    セル内には <a> リンクまたは onclick 付き <td> がある。
    """
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    clicked = False
    tables = await page.query_selector_all("table")

    # ── アプローチ①: D面が行ヘッダーの場合 ──────────────────────
    for table in tables:
        rows = await table.query_selector_all("tr")

        # ヘッダー行から 16:00〜18:00 の列インデックスを取得
        time_col_idx = -1
        for row in rows[:4]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_idx = ci
                    print(f"  [INFO] 列ヘッダー発見: 列{ci} = {txt!r}")
                    break
                # 「16:00」だけのヘッダーの場合
                if txt == TARGET_TIME_START or txt.startswith(TARGET_TIME_START):
                    time_col_idx = ci
                    print(f"  [INFO] 列ヘッダー発見(開始時刻のみ): 列{ci} = {txt!r}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行を探し、該当列のセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_has_d_men = any(
                TARGET_FACILITY in (await c.inner_text()).strip()
                for c in cells
            )
            if not row_has_d_men:
                continue

            if time_col_idx >= len(cells):
                print(f"  [WARN] D面行の列数({len(cells)})が時間列インデックス({time_col_idx})より少ない")
                continue

            target_cell = cells[time_col_idx]
            tc_txt = (await target_cell.inner_text()).strip()
            tc_cls = await target_cell.get_attribute("class") or ""
            print(f"  [FOUND] D面×16:00セル: text={tc_txt!r} class={tc_cls!r}")

            # セル内の <a> リンクを優先してクリック
            link = await target_cell.query_selector("a")
            if link:
                await link.click()
                print(f"  [OK] セル内リンクをクリック")
            else:
                await target_cell.click()
                print(f"  [OK] セル自体をクリック")
            clicked = True
            break

        if clicked:
            break

    # ── アプローチ②: 時間帯が行ヘッダーの場合（行列転置） ───────
    if not clicked:
        print("  [試行] 時間帯が行ヘッダーのパターンで再挑戦...")
        for table in tables:
            rows = await table.query_selector_all("tr")

            # ヘッダー行からD面の列インデックスを取得
            d_col_idx = -1
            for row in rows[:4]:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_FACILITY in txt:
                        d_col_idx = ci
                        print(f"  [INFO] D面列ヘッダー発見: 列{ci} = {txt!r}")
                        break
                if d_col_idx >= 0:
                    break

            if d_col_idx < 0:
                continue

            # 16:00〜18:00 の行を探す
            for row in rows:
                cells = await row.query_selector_all("td, th")
                row_has_time = any(
                    TARGET_TIME_START in (await c.inner_text()).strip()
                    for c in cells
                )
                if not row_has_time:
                    continue

                if d_col_idx >= len(cells):
                    continue

                target_cell = cells[d_col_idx]
                tc_txt = (await target_cell.inner_text()).strip()
                print(f"  [FOUND] 16:00行×D面列: text={tc_txt!r}")

                link = await target_cell.query_selector("a")
                if link:
                    await link.click()
                    print(f"  [OK] セル内リンクをクリック")
                else:
                    await target_cell.click()
                    print(f"  [OK] セル自体をクリック")
                clicked = True
                break

            if clicked:
                break

    # ── アプローチ③: onclick/href にD面+時間情報を含む要素を探す ──
    if not clicked:
        print("  [試行] onclick/href からD面16:00を探す...")
        all_elems = await page.query_selector_all("[onclick], a[href]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            # D面かつ16時を示す文字列を含む
            if ("D面" in combined or "D" in combined) and (
                "16" in combined or "1600" in combined
            ):
                print(f"  [FOUND] onclick={onclick[:80]!r} href={href[:80]!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。"
            "screenshots/04_search_results.png を確認してください。"
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
        'input[value="次へ"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'button:has-text("確定")',
        'button:has-text("確認")',
        'button:has-text("次へ")',
        'a:has-text("確定")',
        'a:has-text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。screenshots/05_slot_selected.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


async def step_confirm2(page):
    """Step6: 確定②（最終確定）

    Tampermonkey で window.confirm を無効化済み前提だが、
    Playwright 側でも dialog を自動承認しておく。
    """
    print("\n[Step 6] 確定②クリック...")

    # ダイアログが来た場合の自動承認（フォールバック）
    async def handle_dialog(dialog):
        print(f"  [DIALOG] type={dialog.type} message={dialog.message!r} → 承認")
        await dialog.accept()

    page.on("dialog", handle_dialog)

    # JS でも確認ダイアログを無効化（二重保険）
    await page.evaluate("window.confirm = () => true; window.alert = () => {};")

    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="最終確定"]',
        'input[value*="確定"]',
        'button:has-text("予約確定")',
        'button:has-text("確定")',
        'a:has-text("確定")',
        'a:has-text("予約確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not clicked:
        raise RuntimeError("確定②ボタンが見つかりません。screenshots/06_confirm1.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了確認
    body_text = await page.inner_text("body")
    keywords = ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました", "完了"]
    if any(w in body_text for w in keywords):
        print("\n[SUCCESS] 予約完了を確認しました！")
    else:
        print("\n[WARNING] 完了メッセージが見つかりません。screenshots/07_final_result.png を確認してください。")
    print(f"  本文先頭300字: {body_text[:300]}")


async def main():
    opts = parse_args()
    now_jst = datetime.datetime.now(JST)
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"現在JST: {now_jst.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00 JST)'} / "
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
            # ── ここからが時間勝負 ──
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)
            print("\n[DONE] すべてのステップが完了しました。")
        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n[ERROR] {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
