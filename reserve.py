"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備
  pip install playwright pytz
  playwright install chromium

■ 動作フロー（本番モード）
  ログイン → お気に入り画面 → 日付を事前選択 → 5:00:00ぴったりに検索
  → D面 16:00〜18:00 セルクリック → 確定① → 確定②
"""

import asyncio
import datetime
import sys
import os

try:
    import pytz
    JST = pytz.timezone("Asia/Tokyo")
    def now_jst():
        return datetime.datetime.now(JST)
except ImportError:
    # pytz がなければローカル時刻で代用（PCがJST設定であること）
    def now_jst():
        return datetime.datetime.now()

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日（練習: 令和08年06月19日）
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日",
    "令和０８年０６月１９日", "2026年06月19日", "2026/06/19",
]

# 予約対象コート＆時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報設定（5:00:00.000 JST に検索を実行）
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


# ──────────────────────────────────────────────
# 時報待ちロジック（ミリ秒精度）
# ──────────────────────────────────────────────
async def wait_until_open():
    """JST 5:00:00.000 ぴったりまでミリ秒単位で待機"""
    print("[時報待ち] 朝5:00:00.000 JST まで待機します...")
    while True:
        now = now_jst()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {now_jst().strftime('%H:%M:%S.%f')}")
            return
        elif diff_sec > 300:          # 5分以上前: 30秒ごと
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分) ...")
            await asyncio.sleep(30)
        elif diff_sec > 10:           # 10秒～5分前: 1秒ごと
            await asyncio.sleep(1)
        elif diff_sec > 0.5:          # 500ms～10秒前: 50msごと
            await asyncio.sleep(0.05)
        elif diff_sec > 0.05:         # 50ms～500ms前: 5msごと
            await asyncio.sleep(0.005)
        else:                         # 50ms以内: 1msごと（最終スパート）
            await asyncio.sleep(0.001)


# ──────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────
async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


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
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: 候補なし → スクリーンショットを確認してください")
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
    print(f"  [FAIL] {label}: 候補なし")
    return False


# ──────────────────────────────────────────────
# 各ステップ
# ──────────────────────────────────────────────
async def step_login(page):
    """Step1: ログイン"""
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号入力
    ok = await try_fill(page, [
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
    if not ok:
        await save_ss(page, "ERROR_userid")
        raise RuntimeError("利用者番号フィールドが見つかりません。analyze_site.py で解析してください。")

    # パスワード入力
    ok = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")
    if not ok:
        await save_ss(page, "ERROR_password")
        raise RuntimeError("パスワードフィールドが見つかりません。")

    # ログインボタン
    ok = await try_click(page, [
        'input[value="ログイン"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'button:has-text("ログイン")',
        'a:has-text("ログイン")',
    ], "ログインボタン")
    if not ok:
        await save_ss(page, "ERROR_login_btn")
        raise RuntimeError("ログインボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if any(w in body for w in ["パスワードが違", "ログインできません", "認証エラー", "エラー"]):
        raise RuntimeError(f"ログイン失敗の可能性。ページ内容: {body[:200]}")


async def step_favorite(page):
    """Step2: お気に入りクリック → 絞り込み画面へ"""
    print("\n[Step 2] お気に入りをクリック...")

    # まず通常セレクターで試みる
    clicked = await try_click(page, [
        'a:has-text("お気に入り")',
        'input[value="お気に入り"]',
        'button:has-text("お気に入り")',
        '[onclick*="okiniiri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # フォールバック: 全リンク・ボタンのテキストを走査
        for tag in ["a", "button", "input[type=button]", "input[type=submit]"]:
            elems = await page.query_selector_all(tag)
            for elem in elems:
                txt = (await elem.inner_text()).strip() if await elem.inner_text() else ""
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    await elem.click()
                    print(f"  [OK] お気に入り（フォールバック）: <{tag}> text={txt!r}")
                    clicked = True
                    break
            if clicked:
                break

    if not clicked:
        await save_ss(page, "ERROR_favorite")
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行してページ構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


async def step_preselect_date(page) -> bool:
    """
    Step3a: 時報前に日付プルダウンを選択しておく（検索ボタンは押さない）
    戻り値: True=選択成功, False=プルダウン未発見（検索時に再試行）
    """
    print(f"\n[Step 3a] 日付を事前選択: {TARGET_DATE_WAREKI}")

    date_selected = False
    selects = await page.query_selector_all("select")

    # ── パターン①: 1つのSELECTに日付が全部入っている ──
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

    # ── パターン②: 年・月・日が分割SELECT ──
    if not date_selected:
        print("  [試行] 年月日 分割SELECT パターン...")
        year_hits  = ["令和08", "令和8", "08", "2026", "R08", "R8"]
        month_hits = ["06", "6", "６", "６月", "06月"]
        day_hits   = ["19", "１９", "19日"]

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p in txt or p == v for p in year_hits):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年選択: {txt!r}")
                    break

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p in txt or p == v for p in month_hits):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月選択: {txt!r}")
                    date_selected = True
                    break

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p in txt or p == v for p in day_hits):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日選択: {txt!r}")
                    break

    if not date_selected:
        print(f"  [WARNING] 日付プルダウンに {TARGET_DATE_WAREKI} が見つかりません。"
              "検索後に再確認します。")
    return date_selected


async def step_click_search(page):
    """Step3b: 検索ボタンを押す（時報後に呼ぶ）"""
    print(f"\n[Step 3b] 検索ボタンをクリック（時刻: {now_jst().strftime('%H:%M:%S.%f')}）")
    ok = await try_click(page, [
        'input[value="検索"]',
        'button:has-text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:has-text("検索")',
    ], "検索ボタン")

    if not ok:
        await save_ss(page, "ERROR_search_btn")
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


async def step_select_slot(page):
    """Step4: D面 16:00〜18:00 の赤丸セルをクリック"""
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    clicked = False

    # ── アプローチ①: ヘッダー行から列インデックスを特定 ──────────────
    tables = await page.query_selector_all("table")
    for table in tables:
        rows = await table.query_selector_all("tr")
        if not rows:
            continue

        # ヘッダー行で「16:00〜18:00」を含む列インデックスを探す
        time_col_idx = -1
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_idx = ci
                    print(f"  [INFO] '{txt}' 列インデックス={ci}")
                    break
                # 「16:00」だけの列ヘッダーの場合も対応
                elif TARGET_TIME_START in txt and "18" not in txt:
                    time_col_idx = ci
                    print(f"  [INFO] '{txt}' 列インデックス={ci}（開始時刻のみ一致）")
                    break
            if time_col_idx >= 0:
                break

        # D面行を探してその列をクリック
        if time_col_idx >= 0:
            for row in rows:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_FACILITY in txt:
                        # D面の行発見
                        print(f"  [INFO] D面行発見 行テキスト先頭: {[await c.inner_text() for c in cells[:4]]}")
                        if time_col_idx < len(cells):
                            target_cell = cells[time_col_idx]
                            tc_txt = (await target_cell.inner_text()).strip()
                            tc_cls = await target_cell.get_attribute("class") or ""
                            tc_onclick = await target_cell.get_attribute("onclick") or ""
                            # リンクがあればリンクを、なければセル自体をクリック
                            link = await target_cell.query_selector("a")
                            if link:
                                print(f"  [FOUND] D面×{TARGET_TIME_START}列 リンク: text={tc_txt!r}")
                                await link.click()
                            else:
                                print(f"  [FOUND] D面×{TARGET_TIME_START}列 セル: "
                                      f"text={tc_txt!r} class={tc_cls!r} onclick={tc_onclick!r}")
                                await target_cell.click()
                            clicked = True
                        break
                if clicked:
                    break
        if clicked:
            break

    # ── アプローチ②: D面の行を先に特定してから時間一致セルをクリック ──
    if not clicked:
        print("  [試行] D面行内の時間一致セルを直接探す...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                cell_texts = [(await c.inner_text()).strip() for c in cells]
                if TARGET_FACILITY in cell_texts:
                    print(f"  [INFO] D面行: {cell_texts}")
                    for ci, (cell, txt) in enumerate(zip(cells, cell_texts)):
                        if TARGET_TIME_START in txt:
                            link = await cell.query_selector("a")
                            if link:
                                await link.click()
                            else:
                                await cell.click()
                            print(f"  [OK] D面×{TARGET_TIME_START} セル[{ci}]: {txt!r}")
                            clicked = True
                            break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick / href にD面+時間の情報が含まれる要素 ──
    if not clicked:
        print("  [試行] onclick/href でD面16:00を検索...")
        for selector in ["[onclick]", "a[href]"]:
            elems = await page.query_selector_all(selector)
            for elem in elems:
                onclick = await elem.get_attribute("onclick") or ""
                href    = await elem.get_attribute("href") or ""
                txt     = (await elem.inner_text()).strip()
                combined = onclick + href + txt
                if ("D面" in combined or "d面" in combined.lower()) and "16" in combined:
                    print(f"  [FOUND] onclick={onclick!r} href={href!r} text={txt!r}")
                    await elem.click()
                    clicked = True
                    break
            if clicked:
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。"
            "screenshots/04_search_results.png と analyze_site.py の出力を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


async def step_confirm1(page):
    """Step5: 確定①（料金確認画面へ進む）"""
    print("\n[Step 5] 確定①クリック...")
    ok = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'button:has-text("確定")',
        'button:has-text("確認")',
        'a:has-text("確定")',
        'a:has-text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not ok:
        await save_ss(page, "ERROR_confirm1")
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


async def step_confirm2(page):
    """Step6: 確定②（最終確定）
    ※ Tampermonkey で window.confirm は無効化済み（add_init_script でも上書き済み）
    """
    print("\n[Step 6] 確定②クリック...")
    ok = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="最終確定"]',
        'input[value*="確定"]',
        'button:has-text("予約確定")',
        'button:has-text("確定")',
        'a:has-text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not ok:
        await save_ss(page, "ERROR_confirm2")
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    body_text = await page.inner_text("body")
    if any(w in body_text for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが確認できませんでした。スクリーンショットを確認してください。")
    print(f"  ページ本文（先頭300字）:\n{body_text[:300]}")


# ──────────────────────────────────────────────
# メインフロー
# ──────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00 JST)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

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
        )

        # ─── window.confirm を自動承認（Tampermonkeyと同等の効果）───
        await context.add_init_script("window.confirm = () => true; window.alert = () => {};")

        page = await context.new_page()
        page.set_default_timeout(ELEM_TIMEOUT)

        # ダイアログが万一発火した場合の保険
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        try:
            # ── 5AM前に実行（ログイン〜日付プリセットまで済ませる）──
            await step_login(page)
            await step_favorite(page)
            await step_preselect_date(page)

            # ── 5:00:00.000 ぴったりまで待機 ──
            if opts["wait_for_open"]:
                await wait_until_open()

            # ── 5AM直後に検索ボタンを押す ──
            await step_click_search(page)

            # ── 枠選択・確定 ──
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)

            print("\n✅ 全ステップ完了。")

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー発生: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
