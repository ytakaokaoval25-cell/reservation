"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方（ローカルPCで実行）
  python reserve.py              # 朝5:00:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備（ローカルPC）
  pip install playwright
  playwright install chromium

■ 注意
  ・このスクリプトはローカルPCから実行してください
  ・サーバーがクラウド環境のIPをブロックするため、クラウド上では動作しません
  ・window.confirm は Playwright の dialog ハンドラで自動承認します
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

# 予約対象日（令和08年06月19日 = 2026-06-19 で練習。本番: 07月分に変更）
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日",
    "令和8年6月19日",
    "令和０８年０６月１９日",
    "2026年06月19日",
    "2026/06/19",
    "2026-06-19",
]
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]

# 予約対象コート＆時間
TARGET_FACILITY  = "D面"
TARGET_TIME_FROM = "16:00"
TARGET_TIME_TO   = "18:00"

# 時報待ち設定（本番）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# スクリーンショット保存先（デバッグ用）
SS_DIR = "screenshots"
# ──────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位で待機するループ"""
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
        elif diff_sec > 300:      # 5分以上前: 30秒ごと
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:       # 10秒〜5分前: 1秒ごと
            await asyncio.sleep(1)
        elif diff_sec > 0.1:      # 0.1秒〜10秒前: 50msごと
            await asyncio.sleep(0.05)
        else:                     # 0.1秒以内: 1msごと（精密待ち）
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_click(page, selectors: list, label: str, timeout: int = 5000) -> bool:
    """複数セレクターを順番に試してクリック（最初に成功したものを採用）"""
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
    print(f"  [FAIL] {label}: 全セレクターで要素なし")
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
    print(f"  [FAIL] {label}: 全セレクターで要素なし")
    return False


# ──────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号フィールド（候補セレクター優先順）
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

    # パスワードフィールド
    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")

    # ログインボタン
    await try_click(page, [
        'input[value="ログイン"]',
        'input[value="login"]',
        'input[value="LOGIN"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面
# ──────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'button:text("お気に入り")',
        'input[value="お気に入り"]',
        'input[value*="お気に入り"]',
        'a:text-matches("お気に入り")',
        '[onclick*="okiniri"]',
        '[onclick*="okiniiri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    # テキスト検索フォールバック
    if not clicked:
        for tag in ["a", "button", "input"]:
            elems = await page.query_selector_all(tag)
            for elem in elems:
                try:
                    txt = (await elem.inner_text()).strip()
                    val = await elem.get_attribute("value") or ""
                    if "お気に入り" in txt or "お気に入り" in val:
                        await elem.click()
                        print(f"  [OK] お気に入り（フォールバック）: tag={tag} text={txt!r}")
                        clicked = True
                        break
                except Exception:
                    pass
            if clicked:
                break

    if not clicked:
        raise RuntimeError("お気に入りリンクが見つかりません。--headful でブラウザを確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 3: 日付プルダウンで令和08年06月19日を選択 → 検索
# ──────────────────────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: 令和08年06月19日")

    date_selected = False

    # ── アプローチ①: 1つのSELECTで完全な日付テキスト/valueを探す ──
    selects = await page.query_selector_all("select")
    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択（単一SELECT）: name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── アプローチ②: 年・月・日が分割SELECT ──
    if not date_selected:
        print("  [試行] 年月日が分割SELECTの可能性あり...")
        year_matches  = {"令和08", "令和8", "R08", "R8", "2026", "08"}
        month_matches = {"06", "6", "６月", "06月", "6月"}
        day_matches   = {"19", "１９", "19日"}

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if txt in year_matches or v in year_matches:
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年選択: {txt!r} / {v!r}")
                    break
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if txt in month_matches or v in month_matches:
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月選択: {txt!r} / {v!r}")
                    date_selected = True
                    break
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if txt in day_matches or v in day_matches:
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日選択: {txt!r} / {v!r}")
                    break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            "令和08年06月19日 がプルダウンに見つかりません。"
            "--headful で確認し、実際のoption value/textを確認してください。"
        )

    # 検索ボタン
    await try_click(page, [
        'input[value="検索"]',
        'input[value*="検索"]',
        'button:text("検索")',
        'a:text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 4: D面 16:00〜18:00（赤丸）セルをクリック
# ──────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_FROM}〜{TARGET_TIME_TO} セル選択...")

    clicked = False

    # ── アプローチ①: ヘッダー行から「16:00〜18:00」列インデックスを特定 ──
    tables = await page.query_selector_all("table")
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行（最初の3行以内）から時間列を特定
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip().replace("\n", "").replace(" ", "")
                # 「16:00」と「18:00」が同じセルに含まれる
                if TARGET_TIME_FROM in txt and TARGET_TIME_TO in txt:
                    time_col_idx = ci
                    print(f"  [INFO] 列{ci} = {TARGET_TIME_FROM}〜{TARGET_TIME_TO}: {txt!r}")
                    break
                # または「16:00」だけの場合（後続セルで18:00を確認）
                elif TARGET_TIME_FROM in txt and time_col_idx < 0:
                    time_col_idx = ci
                    print(f"  [INFO] 列{ci} = {TARGET_TIME_FROM}: {txt!r}")
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行を探してその列のセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            first_cell_txt = (await cells[0].inner_text()).strip() if cells else ""
            if TARGET_FACILITY in first_cell_txt:
                print(f"  [INFO] D面行発見: 先頭セル={first_cell_txt!r}")
                if time_col_idx < len(cells):
                    target_cell = cells[time_col_idx]
                    tc_txt = (await target_cell.inner_text()).strip()
                    tc_cls = await target_cell.get_attribute("class") or ""
                    tc_onclick = await target_cell.get_attribute("onclick") or ""
                    print(f"  [FOUND] D面×{TARGET_TIME_FROM} セル: text={tc_txt!r} class={tc_cls!r}")

                    # セル内のリンク（<a>タグ）を優先クリック
                    inner_link = await target_cell.query_selector("a")
                    if inner_link:
                        await inner_link.click()
                        print(f"  [OK] セル内 <a> をクリック")
                    else:
                        await target_cell.click()
                        print(f"  [OK] セル直接クリック")
                    clicked = True
                break
        if clicked:
            break

    # ── アプローチ②: D面の行にある全セルをテキストで走査 ──
    if not clicked:
        print("  [試行] D面行の全セルをテキスト走査...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                texts = []
                for c in cells:
                    texts.append((await c.inner_text()).strip())

                if any(TARGET_FACILITY in t for t in texts):
                    print(f"  [INFO] D面行テキスト: {texts[:10]}")
                    for i, cell in enumerate(cells):
                        txt = texts[i]
                        if TARGET_TIME_FROM in txt or TARGET_TIME_FROM.replace(":", "") in txt:
                            inner_link = await cell.query_selector("a")
                            if inner_link:
                                await inner_link.click()
                            else:
                                await cell.click()
                            print(f"  [OK] アプローチ②: index={i} text={txt!r}")
                            clicked = True
                            break
                    if clicked:
                        break
            if clicked:
                break

    # ── アプローチ③: onclick/href でD面+16:00の組み合わせを探す ──
    if not clicked:
        print("  [試行] onclick/href + テキストでD面16:00を探す...")
        all_elems = await page.query_selector_all("a[href], [onclick]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href")    or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if (TARGET_FACILITY in combined) and (TARGET_TIME_FROM.replace(":", "") in combined
                                                   or TARGET_TIME_FROM in combined):
                print(f"  [FOUND] アプローチ③: text={txt!r} onclick={onclick!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_FROM}〜{TARGET_TIME_TO} セルが見つかりません。"
            " screenshots/04_search_results.png を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ進む）
# ──────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①クリック（料金確認画面へ）...")

    # ダイアログが来た場合のフォールバック自動承認
    page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
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
    ], "確定①ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        await save_ss(page, "ERROR_confirm1")
        raise RuntimeError("確定①ボタンが見つかりません。screenshots/05_slot_selected.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# ──────────────────────────────────────────────
async def step_confirm2(page):
    """
    最終確定ボタンをクリックする。
    Playwright の dialog ハンドラで window.confirm を自動承認するため、
    Tampermonkey の無効化スクリプトは不要だが共存可能。
    """
    print("\n[Step 6] 確定②クリック（最終確定）...")

    # window.confirm / window.alert を自動承認
    page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))

    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="最終確定"]',
        'input[value*="確定"]',
        'button:text("予約確定")',
        'button:text("確定")',
        'button:text("最終確定")',
        'a:text("予約確定")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        await save_ss(page, "ERROR_confirm2")
        raise RuntimeError("確定②ボタンが見つかりません。screenshots/06_confirm1.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了確認
    body_text = await page.inner_text("body")
    completion_words = ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました", "完了"]
    if any(w in body_text for w in completion_words):
        print("\n[SUCCESS] 予約完了を確認しました！")
    else:
        print("\n[WARNING] 完了メッセージが見つかりません。screenshots/07_final_result.png を確認してください。")
    print(f"  最終本文（先頭300字）: {body_text[:300]}")


# ──────────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: 令和08年06月19日  施設: {TARGET_FACILITY} {TARGET_TIME_FROM}〜{TARGET_TIME_TO}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00:00)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

    if opts["wait_for_open"]:
        await wait_until_open()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,  # SSL証明書エラーを無視
        )
        page = await context.new_page()

        try:
            await step_login(page)
            await step_favorite(page)
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
