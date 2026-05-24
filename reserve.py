"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備
  pip install playwright==1.56.0
  playwright install chromium   # ブラウザが未インストールの場合

■ 本番運用時の変更点
  TARGET_DATE_WAREKI を "令和08年07月19日" に変更（07月分予約開始時）
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────
# 設定値（ここだけ変更すれば対応できる）
# ──────────────────────────────────────────────
LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"

# 練習: 令和08年06月19日 / 本番(07月分): 令和08年07月19日 に変更
TARGET_DATE_WAREKI = "令和08年06月19日"

# 予約対象コート＆時間
TARGET_FACILITY    = "D面"
TARGET_TIME_START  = "16:00"
TARGET_TIME_END    = "18:00"

# 時報待ち設定
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# スクリーンショット保存先
SS_DIR = "screenshots"
# ──────────────────────────────────────────────

# 日付の表記ゆれ対応
_TARGET_DATE_VALUE_CANDIDATES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
_TARGET_DATE_TEXT_CANDIDATES = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19",
]


def parse_args():
    args = sys.argv[1:]
    return {
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位でビジーウェイト"""
    print("[時報待ち] 朝5:00:00.000 まで待機します...")
    while True:
        now = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0,
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
            break
        elif diff_sec > 300:
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            await asyncio.sleep(1)
        elif diff_sec > 0.1:
            await asyncio.sleep(0.05)   # 50ms
        else:
            await asyncio.sleep(0.001)  # 1ms


async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
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
            print(f"  [SKIP] {label} ({sel}): {e}")
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
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


# ─────────────────────────────────────────────────────────────────────
# Step 1: ログイン
# ─────────────────────────────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # ページHTMLをダンプしてフォーム要素確認（デバッグ用）
    html = await page.content()
    print(f"  [HTML] 先頭500文字: {html[:500]!r}")

    # 利用者番号 — まんまるよやく系でよく使われるname属性を網羅
    filled = await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="userno"]',
        'input[name="memberNo"]',
        'input[name="member_no"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        'input[name="login"]',
        '#userid', '#user_id', '#userno', '#memberNo', '#loginId',
        'input[type="text"]',
    ], USER_ID, "利用者番号")

    if not filled:
        # JS描画待ちを追加してリトライ
        await asyncio.sleep(2)
        await try_fill(page, ['input[type="text"]', 'input:not([type="hidden"])'],
                       USER_ID, "利用者番号(リトライ)")

    # パスワード
    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[name="pw"]',
        '#passwd', '#password',
    ], PASSWORD, "パスワード")

    # ログインボタン
    await try_click(page, [
        'input[value="ログイン"]',
        'input[value="　ログイン　"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
        'a:text("ログイン")',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


# ─────────────────────────────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面
# ─────────────────────────────────────────────────────────────────────
async def step_favorite(page):
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
        '[class*="okini"]',
        '[id*="okini"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全走査フォールバック
        elems = await page.query_selector_all("a, button, input[type=button], input[type=submit]")
        for elem in elems:
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（フォールバック）: text={txt!r}")
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_no_favorite")
        raise RuntimeError(
            "お気に入りリンクが見つかりません。screenshots/ERROR_no_favorite.png を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ─────────────────────────────────────────────────────────────────────
# Step 3: 日付プルダウン選択 → 検索
# ─────────────────────────────────────────────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    # すべてのSELECTを走査して日付を選択
    date_selected = False
    selects = await page.query_selector_all("select")
    print(f"  [INFO] SELECT要素数: {len(selects)}")

    for sel_elem in selects:
        name = await sel_elem.get_attribute("name") or ""
        id_  = await sel_elem.get_attribute("id") or ""
        options = await sel_elem.query_selector_all("option")
        print(f"  SELECT name={name!r} id={id_!r} options={len(options)}件")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            # テキスト一致 or value一致
            if (any(t in txt for t in _TARGET_DATE_TEXT_CANDIDATES)
                    or v in _TARGET_DATE_VALUE_CANDIDATES):
                if v:
                    await sel_elem.select_option(value=v)
                else:
                    await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択: name={name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # 年・月・日が分割SELECTになっているパターン
    if not date_selected:
        print("  [試行] 年月日が分割SELECTの可能性...")
        year_patterns  = ["令和08", "令和8", "R08", "R8", "2026"]
        month_patterns = ["06", "6", "6月", "06月"]
        day_patterns   = ["19", "19日"]

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p in txt or p == v for p in year_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年選択: {txt!r}")
                    break

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p in txt or p == v for p in month_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月選択: {txt!r}")
                    date_selected = True
                    break

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p in txt or p == v for p in day_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日選択: {txt!r}")
                    break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        # 全SELECTの内容を出力してデバッグ
        for sel_elem in selects:
            name = await sel_elem.get_attribute("name") or ""
            options = await sel_elem.query_selector_all("option")
            print(f"  [DUMP] SELECT name={name!r}")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r} text={txt!r}")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "screenshots/ フォルダのスクリーンショットとDUMPログを確認してください。"
        )

    # 検索ボタン
    await try_click(page, [
        'input[value="検索"]',
        'input[value*="検索"]',
        'button:text("検索")',
        'button:text-matches("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


# ─────────────────────────────────────────────────────────────────────
# Step 4: D面 16:00〜18:00（赤丸）セルをクリック
# ─────────────────────────────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    clicked = False

    # ── アプローチ①: ヘッダー行から時間列インデックスを特定し、D面行と交差するセルをクリック
    tables = await page.query_selector_all("table")
    print(f"  [INFO] テーブル数: {len(tables)}")

    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行（最初の3行以内）から時間列を特定
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt:
                    time_col_idx = ci
                    print(f"  [INFO] 時間列インデックス={ci} (text={txt!r})")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面行を探して該当列セルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_texts = [(await c.inner_text()).strip() for c in cells]
            if TARGET_FACILITY in row_texts:
                print(f"  [INFO] D面行発見: {row_texts}")
                if time_col_idx < len(cells):
                    target_cell = cells[time_col_idx]
                    tc_txt = (await target_cell.inner_text()).strip()
                    tc_cls = await target_cell.get_attribute("class") or ""
                    print(f"  [FOUND] D面×{TARGET_TIME_START}列: text={tc_txt!r} class={tc_cls!r}")
                    await target_cell.click()
                    clicked = True
                break
        if clicked:
            break

    # ── アプローチ②: D面行の全セルを走査してテキスト/属性で一致するものを探す
    if not clicked:
        print("  [試行] D面行の全セル走査...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                row_texts = [(await c.inner_text()).strip() for c in cells]
                if TARGET_FACILITY in row_texts:
                    for i, cell in enumerate(cells):
                        txt = row_texts[i]
                        cls = await cell.get_attribute("class") or ""
                        onclick = await cell.get_attribute("onclick") or ""
                        combined = txt + cls + onclick
                        if TARGET_TIME_START in combined or "1600" in combined:
                            print(f"  [FOUND] D面行 cell[{i}]: text={txt!r} class={cls!r}")
                            await cell.click()
                            clicked = True
                            break
                    if clicked:
                        break
            if clicked:
                break

    # ── アプローチ③: onclick / href にD面+16が含まれる要素を探す
    if not clicked:
        print("  [試行] onclick/hrefからD面+16:00を探す...")
        all_elems = await page.query_selector_all("[onclick], a[href]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if ("D面" in combined or "d面" in combined.lower()) and "16" in combined:
                print(f"  [FOUND] onclick={onclick[:80]!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    # ── アプローチ④: 全セルをダンプしてデバッグ情報を出力
    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        all_cells = await page.query_selector_all("td")
        print(f"\n  [DEBUG] 全td要素数: {len(all_cells)}")
        for i, c in enumerate(all_cells[:60]):
            txt = (await c.inner_text()).strip()
            cls = await c.get_attribute("class") or ""
            onclick = await c.get_attribute("onclick") or ""
            if txt or onclick:
                print(f"  td[{i}] cls={cls!r} onclick={onclick[:60]!r} text={txt[:40]!r}")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。"
            "screenshots/ERROR_slot_not_found.png とダンプログを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ─────────────────────────────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ─────────────────────────────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①クリック...")
    await save_ss(page, "05b_before_confirm1")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value="予約確認"]',
        'button:text("確定")',
        'button:text("確認")',
        'button:text("次へ")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'a:text("確定")',
        'a:text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        await save_ss(page, "ERROR_confirm1")
        raise RuntimeError("確定①ボタンが見つかりません。screenshots/ERROR_confirm1.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


# ─────────────────────────────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# window.confirm は Tampermonkey で無効化済みの前提
# 万一ダイアログが発生した場合は自動承認する
# ─────────────────────────────────────────────────────────────────────
async def step_confirm2(page):
    print("\n[Step 6] 確定②クリック...")
    await save_ss(page, "06b_before_confirm2")

    # ダイアログ自動承認（Tampermonkeyで無効化されていても念のため設定）
    page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="予約する"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'button:text("予約する")',
        'input[value*="確定"]',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        await save_ss(page, "ERROR_confirm2")
        raise RuntimeError("確定②ボタンが見つかりません。screenshots/ERROR_confirm2.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了確認
    body_text = await page.inner_text("body")
    keywords = ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました", "受付しました"]
    if any(w in body_text for w in keywords):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。スクリーンショットを確認してください。")
    print(f"  本文（先頭300字）: {body_text[:300]}")


# ─────────────────────────────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00)'}  "
          f"ブラウザ: {'表示あり' if not opts['headless'] else 'ヘッドレス'}")
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
            ignore_https_errors=True,   # SSL証明書エラーを無視
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
