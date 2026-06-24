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
LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"

# 予約対象日（令和08年06月19日 = 2026-06-19 で練習。本番は変更）
# プルダウンのテキスト候補（サイトの表示形式に合わせて複数用意）
TARGET_DATE_TEXTS = [
    "令和08年06月19日",
    "令和8年6月19日",
    "令和０８年０６月１９日",
    "2026年06月19日",
    "2026/06/19",
    "R08.06.19",
]
# プルダウンのvalue属性候補
TARGET_DATE_VALUES = [
    "20260619",
    "2026-06-19",
    "2026/06/19",
    "260619",
    "0619",
]

# 予約対象コート＆時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報待ち設定（本番: 朝5時ぴったり）
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
            # 10秒〜5分前: 1秒ごと
            await asyncio.sleep(1)
        elif diff_sec > 0.05:
            # 50ms〜10秒前: 50msごと
            await asyncio.sleep(0.05)
        else:
            # 50ms以内: 1msごと（ビジーウェイト）
            await asyncio.sleep(0.001)


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


# ── Step1: ログイン ────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

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

    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")

    await try_click(page, [
        'input[value="ログイン"]',
        'input[value*="ログイン"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


# ── Step2: お気に入りクリック → 絞り込み画面 ──────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    # テキスト/value属性でお気に入りを探す
    all_elems = await page.query_selector_all(
        "a, button, input[type=button], input[type=submit]"
    )
    clicked = False
    for elem in all_elems:
        txt = ""
        try:
            txt = (await elem.inner_text()).strip()
        except Exception:
            pass
        val = await elem.get_attribute("value") or ""
        if "お気に入り" in txt or "お気に入り" in val:
            print(f"  [OK] お気に入り要素発見: text={txt!r} value={val!r}")
            await elem.click()
            clicked = True
            break

    if not clicked:
        # セレクター候補で再試行
        clicked = await try_click(page, [
            'a:text("お気に入り")',
            'input[value="お気に入り"]',
            'button:text("お気に入り")',
            '[onclick*="okiniri"]',
            '[onclick*="favorite"]',
            '[class*="favorite"]',
            '[id*="favorite"]',
        ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        await save_ss(page, "ERROR_favorite_not_found")
        raise RuntimeError("お気に入りリンクが見つかりません。analyze_site.pyで解析してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ── Step3: 日付選択 → 検索（最速）──────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_TEXTS[0]}")

    date_selected = False
    selects = await page.query_selector_all("select")

    # パターンA: 統合SELECT（令和08年06月19日 がひとつのSELECTに入っている）
    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_TEXTS)
                    or v in TARGET_DATE_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                if v:
                    await sel_elem.select_option(value=v)
                else:
                    await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択（統合型）: name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # パターンB: 年・月・日が別々のSELECT
    if not date_selected:
        print("  [試行] 年月日が分割SELECTの可能性...")
        YEAR_PATTERNS  = ["令和08", "令和8", "08", "R08", "R8", "2026", "8"]
        MONTH_PATTERNS = ["06", "6", "06月", "６月"]
        DAY_PATTERNS   = ["19", "１９", "19日"]

        # 年を選択
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p == txt.strip() or p == v.strip() for p in YEAR_PATTERNS):
                    sel_name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年選択: name={sel_name!r} value={v!r} text={txt!r}")
                    break

        # 月を選択
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p == txt.strip() or p == v.strip() for p in MONTH_PATTERNS):
                    sel_name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月選択: name={sel_name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break

        # 日を選択
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p == txt.strip() or p == v.strip() for p in DAY_PATTERNS):
                    sel_name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日選択: name={sel_name!r} value={v!r} text={txt!r}")
                    break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_TEXTS[0]} がプルダウンに見つかりません。"
            "analyze_site.pyを実行してセレクターを確認してください。"
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


# ── Step4: D面 16:00〜18:00 の赤丸セルをクリック ──────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    clicked = False

    # アプローチ①: テーブルを走査してD面行 × 16:00列を特定
    tables = await page.query_selector_all("table")

    for table in tables:
        rows = await table.query_selector_all("tr")

        # ヘッダー行から「16:00〜18:00」の列インデックスを取得
        time_col_idx = -1
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_idx = ci
                    print(f"  [INFO] 列インデックス取得: {TARGET_TIME_START}〜{TARGET_TIME_END} → col={ci}")
                    break
                # 16:00 のみのヘッダーも考慮
                elif txt == TARGET_TIME_START or txt.startswith(TARGET_TIME_START):
                    time_col_idx = ci
                    print(f"  [INFO] 列インデックス取得: {TARGET_TIME_START} → col={ci}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行を特定してそのインデックスのセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_texts = [((await c.inner_text()).strip()) for c in cells]

            if any(TARGET_FACILITY in t for t in row_texts):
                print(f"  [INFO] D面行発見: {row_texts[:6]}")
                if time_col_idx < len(cells):
                    target_cell = cells[time_col_idx]
                    tc_txt = (await target_cell.inner_text()).strip()
                    tc_cls = await target_cell.get_attribute("class") or ""
                    tc_onclick = await target_cell.get_attribute("onclick") or ""

                    # 子要素のAタグ経由でクリック（予約可能な場合はAタグが存在することが多い）
                    a_child = await target_cell.query_selector("a")
                    if a_child:
                        a_txt = (await a_child.inner_text()).strip()
                        print(f"  [CLICK] A要素でクリック: text={a_txt!r}")
                        await a_child.click()
                    else:
                        print(f"  [CLICK] セル直接クリック: text={tc_txt!r} class={tc_cls!r}")
                        await target_cell.click()

                    clicked = True
                break

        if clicked:
            break

    # アプローチ②: D面が行テキストに含まれる行を探して16:00セルをクリック
    if not clicked:
        print("  [試行②] テキスト走査でD面+16:00を特定...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                row_texts = [((await c.inner_text()).strip()) for c in cells]
                combined_row = " ".join(row_texts)

                if TARGET_FACILITY in combined_row:
                    for ci, cell in enumerate(cells):
                        txt = (await cell.inner_text()).strip()
                        cls = await cell.get_attribute("class") or ""
                        # 予約可能なセルは ○、●、赤丸 などのマークを持つ
                        if (TARGET_TIME_START in txt
                                or "○" in txt or "●" in txt or "◎" in txt
                                or "赤" in cls.lower() or "red" in cls.lower()
                                or "kano" in cls.lower() or "ok" in cls.lower()):
                            a_child = await cell.query_selector("a")
                            if a_child:
                                print(f"  [CLICK②] A要素クリック: col={ci} text={txt!r}")
                                await a_child.click()
                            else:
                                print(f"  [CLICK②] セルクリック: col={ci} text={txt!r}")
                                await cell.click()
                            clicked = True
                            break
                if clicked:
                    break
            if clicked:
                break

    # アプローチ③: onclick / href にD面+時間の情報が含まれる要素
    if not clicked:
        print("  [試行③] onclick/hrefからD面16:00を探す...")
        all_elems = await page.query_selector_all("[onclick], a[href]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if (("D面" in combined or "d" in combined.lower())
                    and "16" in combined):
                print(f"  [CLICK③] text={txt!r} onclick={onclick!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。"
            "analyze_site.py のスクリーンショットを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ── Step5: 確定①（料金確認画面へ）───────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①クリック...")

    # ダイアログが来た場合の自動承認（Tampermonkey無効化済み前提だがフォールバック）
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'button:text("確定")',
        'button:text("確認")',
        'button:text("次へ")',
        'a:text("確定")',
        'a:text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。スクリーンショットを確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


# ── Step6: 確定②（最終確定）──────────────────────────────────────
async def step_confirm2(page):
    """最終確定。Tampermonkey で window.confirm 無効化済み前提。"""
    print("\n[Step 6] 確定②クリック（最終確定）...")

    # window.confirm を JavaScript で強制的に true を返すよう上書き
    # （Tampermonkey 無効化済みの場合はこの上書きも問題なし）
    await page.add_init_script("window.confirm = () => true;")

    # ダイアログが来た場合の自動承認（二重のフォールバック）
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    # ページ遷移後にも同様のセレクターを試みる
    # （確定①と②でボタンのvalueが同じ「確定」の場合あり）
    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="確定"]',
        'input[value*="確定"]',
        'button:text("予約確定")',
        'button:text("最終確定")',
        'button:text("確定")',
        'a:text("予約確定")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not clicked:
        raise RuntimeError("確定②ボタンが見つかりません。スクリーンショットを確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了確認
    body_text = await page.inner_text("body")
    completion_keywords = ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました", "完了"]
    if any(w in body_text for w in completion_keywords):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。スクリーンショットを確認してください。")
    print(f"  最終本文（先頭300字）:\n{body_text[:300]}")


# ── メイン ────────────────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_TEXTS[0]}")
    print(f"施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

    # ── 時報待ち ──────────────────────────────────────────────
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
        # window.confirm を常に true に上書き（全ページで有効）
        await context.add_init_script("window.confirm = () => true;")
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
