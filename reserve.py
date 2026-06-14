"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 動作フロー
  [～4:59] ログイン → お気に入り → 絞り込み画面へ → 日付選択（待機）
  [5:00:00.000] 検索ボタンをクリック
  [5:00直後]  D面 16:00〜18:00 の赤丸セルをクリック → 確定① → 確定②

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

# 予約対象日（令和08年06月19日 = 2026-06-19 で練習）
# 本番（令和08年07月分）に変更する場合はここを書き換える
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19", "06月19日",
]
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619", "0619",
]
TARGET_DATE_YEAR_PATTERNS  = ["令和08", "令和8", "08", "2026", "R08", "R8"]
TARGET_DATE_MONTH_PATTERNS = ["06", "6", "６", "06月", "6月"]
TARGET_DATE_DAY_PATTERNS   = ["19", "１９", "19日"]

# 予約対象コート＆時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報待ち設定（新規枠が公開される時刻）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト
NAV_TIMEOUT  = 30_000   # ページ遷移待機 (ms)
ELEM_TIMEOUT = 10_000   # 要素待機 (ms)

# スクリーンショット保存先
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
    """
    朝 OPEN_HOUR:OPEN_MINUTE:OPEN_SECOND.000 ぴったりまで待機。
    段階的にスリープ間隔を短くしてオーバーシュートを最小化する。
    """
    print(f"[時報待ち] {OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d}.000 まで待機中...")

    while True:
        now = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0,
        )
        diff = (target - now).total_seconds()

        if diff <= 0:
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")
            print(f"[時報] 開始時刻到達: {ts}")
            return

        if diff > 300:          # 5分超 → 30秒ごと
            remain_min = diff / 60
            print(f"[時報待ち] あと {remain_min:.1f} 分...")
            await asyncio.sleep(30)
        elif diff > 30:         # 30秒超 → 1秒ごと
            await asyncio.sleep(1)
        elif diff > 5:          # 5秒超 → 100msごと
            await asyncio.sleep(0.1)
        elif diff > 0.5:        # 0.5秒超 → 20msごと
            await asyncio.sleep(0.02)
        elif diff > 0.1:        # 100ms超 → 5msごと
            await asyncio.sleep(0.005)
        else:
            # ラスト100ms: 1ms精密ループ
            while datetime.datetime.now() < target:
                await asyncio.sleep(0.001)
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")
            print(f"[時報] 開始時刻到達: {ts}")
            return


# ──────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────
async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_click(page, selectors: list[str], label: str,
                    timeout: int = 5000) -> bool:
    """複数セレクターを順に試してクリック。成功したら True を返す。"""
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
    print(f"  [FAIL] {label}: 候補要素が見つかりません")
    return False


async def try_fill(page, selectors: list[str], value: str,
                   label: str, timeout: int = 5000) -> bool:
    """複数セレクターを順に試してテキスト入力。成功したら True を返す。"""
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
    print(f"  [FAIL] {label}: 候補要素が見つかりません")
    return False


# ──────────────────────────────────────────────
# ステップ実装
# ──────────────────────────────────────────────
async def step_login(page):
    """Step 1: ログインページへ移動してログイン"""
    print("\n[Step 1] ログイン...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号
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
    ], USER_ID, "利用者番号", timeout=ELEM_TIMEOUT)
    if not ok:
        raise RuntimeError("利用者番号フィールドが見つかりません。analyze_site.py を実行してください。")

    # パスワード
    ok = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード", timeout=ELEM_TIMEOUT)
    if not ok:
        raise RuntimeError("パスワードフィールドが見つかりません。")

    # ログインボタン
    ok = await try_click(page, [
        'input[value="ログイン"]',
        'input[value="ﾛｸﾞｲﾝ"]',
        'button:text("ログイン")',
        'a:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
    ], "ログインボタン", timeout=ELEM_TIMEOUT)
    if not ok:
        raise RuntimeError("ログインボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


async def step_favorite(page):
    """Step 2: お気に入りリンクをクリックして絞り込み画面へ"""
    print("\n[Step 2] お気に入りクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        '[onclick*="okiniiri"]',
        '[onclick*="favorite"]',
        'a[href*="okiniiri"]',
        'a[href*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    # テキスト完全一致によるフォールバック
    if not clicked:
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            try:
                txt = (await elem.inner_text()).strip()
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    await elem.click()
                    print(f"  [OK] お気に入り（フォールバック）: text={txt!r}")
                    clicked = True
                    break
            except Exception:
                pass

    if not clicked:
        raise RuntimeError("お気に入りリンクが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


async def step_select_date(page):
    """
    Step 3: 絞り込み画面で「令和08年06月19日」を選択する。
    検索ボタンは押さない（5:00ちょうどに押すため）。
    """
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}（検索はまだ押さない）")
    await save_ss(page, "04_before_date_select")

    selects = await page.query_selector_all("select")
    date_selected = False

    # ─ パターン①: 1つのSELECTに日付全体が入っている ─────────
    for sel_elem in selects:
        sel_name = await sel_elem.get_attribute("name") or ""
        options  = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                try:
                    if v:
                        await sel_elem.select_option(value=v)
                    else:
                        await sel_elem.select_option(label=txt)
                    print(f"  [OK] 日付選択(単体): name={sel_name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
                except Exception as e:
                    print(f"  [WARN] select_option失敗: {e}")
        if date_selected:
            break

    # ─ パターン②: 年・月・日が別々のSELECT ─────────────────
    if not date_selected:
        print("  [試行] 年/月/日 分割SELECTパターンを試みます...")
        year_sel = month_sel = day_sel = None
        year_v = month_v = day_v = ""

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                combined = txt + v
                if any(p in combined for p in TARGET_DATE_YEAR_PATTERNS) and year_sel is None:
                    year_sel = sel_elem
                    year_v   = v
                    print(f"  [INFO] 年SELECT候補: {txt!r} ({v!r})")
                    break
                if any(p in combined for p in TARGET_DATE_MONTH_PATTERNS) and month_sel is None:
                    month_sel = sel_elem
                    month_v   = v
                    print(f"  [INFO] 月SELECT候補: {txt!r} ({v!r})")
                    break
                if any(p in combined for p in TARGET_DATE_DAY_PATTERNS) and day_sel is None:
                    day_sel = sel_elem
                    day_v   = v
                    print(f"  [INFO] 日SELECT候補: {txt!r} ({v!r})")
                    break

        for sel_obj, val, label in [
            (year_sel,  year_v,  "年"),
            (month_sel, month_v, "月"),
            (day_sel,   day_v,   "日"),
        ]:
            if sel_obj and val:
                try:
                    await sel_obj.select_option(value=val)
                    print(f"  [OK] {label}選択: {val!r}")
                    await asyncio.sleep(0.3)  # onChange JS が走る場合の待機
                    date_selected = True
                except Exception as e:
                    print(f"  [WARN] {label}選択失敗: {e}")

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.py を実行してセレクターを確認してください。"
        )

    await save_ss(page, "05_date_selected")
    print(f"  日付選択完了。次は5:00ちょうどに検索ボタンを押します。")


async def step_click_search(page):
    """
    Step 4: 5:00:00 ぴったりに検索ボタンをクリック。
    この関数は wait_until_open() の直後に呼ぶこと。
    """
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")
    print(f"\n[Step 4] 検索ボタンクリック ({ts})")

    ok = await try_click(page, [
        'input[value="検索"]',
        'input[value="検　索"]',
        'button:text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ], "検索ボタン", timeout=ELEM_TIMEOUT)

    if not ok:
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_search_results")
    print(f"  現在URL: {page.url}")


async def step_select_slot(page):
    """
    Step 5: D面 16:00〜18:00 の赤丸（○）セルをクリック。

    まんまるよやく2の典型的なテーブル構造:
      列ヘッダー: コート名 | 時間1 | 時間2 | ... | 16:00〜18:00 | ...
      各行:       D面      | ×    | ○    | ... | ○（赤丸）   | ...
    """
    print(f"\n[Step 5] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")
    clicked = False

    tables = await page.query_selector_all("table")

    # ─ アプローチ A: ヘッダー列インデックス法 ─────────────────
    # ヘッダー行で "16:00〜18:00" の列番号を取得し、D面行のその列をクリック
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行（先頭3行以内）から対象時間の列を探す
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip().replace("　", " ").replace("\n", "")
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_idx = ci
                    print(f"  [INFO] {TARGET_TIME_START}〜{TARGET_TIME_END} 列インデックス={ci}")
                    break
                # 列に時間だけ書かれているケース（例: "16:00"）
                if txt == TARGET_TIME_START:
                    time_col_idx = ci
                    print(f"  [INFO] {TARGET_TIME_START} 列インデックス={ci}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面行でその列のセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_FACILITY in txt:
                    if time_col_idx < len(cells):
                        target_cell = cells[time_col_idx]
                        tc_txt = (await target_cell.inner_text()).strip()
                        tc_cls = await target_cell.get_attribute("class") or ""
                        print(f"  [FOUND-A] D面×列{time_col_idx}: text={tc_txt!r} class={tc_cls!r}")

                        # セル内のリンクを優先してクリック
                        links = await target_cell.query_selector_all("a")
                        if links:
                            await links[0].click()
                        else:
                            await target_cell.click()
                        clicked = True
                    break
            if clicked:
                break
        if clicked:
            break

    # ─ アプローチ B: D面行を走査して16:00を含むセルを探す ─────
    if not clicked:
        print("  [試行B] D面行を直接走査...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                row_txt = (await row.inner_text()).strip()
                if TARGET_FACILITY not in row_txt:
                    continue
                print(f"  [INFO] D面行テキスト（先頭100字）: {row_txt[:100]!r}")
                cells = await row.query_selector_all("td, th")
                for cell in cells:
                    cell_txt = (await cell.inner_text()).strip()
                    cell_cls = await cell.get_attribute("class") or ""
                    # 「○」かつ赤色・maru系クラスを持つセルを優先
                    is_circle = "○" in cell_txt or "◯" in cell_txt or "●" in cell_txt
                    is_red    = "red" in cell_cls or "maru" in cell_cls or "aki" in cell_cls
                    if is_circle and is_red:
                        print(f"  [FOUND-B] 赤丸セル: text={cell_txt!r} class={cell_cls!r}")
                        links = await cell.query_selector_all("a")
                        if links:
                            await links[0].click()
                        else:
                            await cell.click()
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ─ アプローチ C: onclick/href 属性でD面+時刻情報を含む要素を探す ──
    if not clicked:
        print("  [試行C] onclick/href からD面+16:00を探す...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            try:
                onclick = await elem.get_attribute("onclick") or ""
                href    = await elem.get_attribute("href") or ""
                parent_txt = ""
                parent = await elem.evaluate_handle("el => el.closest('tr')")
                if parent:
                    parent_txt = await page.evaluate("el => el ? el.innerText : ''", parent)
                combined = onclick + href + parent_txt
                if (TARGET_FACILITY in combined and "16" in combined):
                    print(f"  [FOUND-C] onclick={onclick[:60]!r}")
                    await elem.click()
                    clicked = True
                    break
            except Exception:
                pass

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。"
            "screenshots/ のスクリーンショットを確認してセレクターを調整してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_slot_selected")
    print(f"  現在URL: {page.url}")


async def step_confirm1(page):
    """Step 6: 確定① ― 料金確認画面への進捗ボタン"""
    print("\n[Step 6] 確定①クリック...")
    await save_ss(page, "08_confirm1_page")

    ok = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value="予約確定"]',
        'button:text("確定")',
        'button:text("確認")',
        'button:text("次へ")',
        'a:text("確定")',
        'a:text("次へ")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン", timeout=ELEM_TIMEOUT)

    if not ok:
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "09_after_confirm1")
    print(f"  現在URL: {page.url}")


async def step_confirm2(page):
    """
    Step 7: 確定② ― 最終確定。
    Tampermonkey で window.confirm は無効化済み前提だが、
    念のため Playwright 側でも自動承認ハンドラを設定する。
    """
    print("\n[Step 7] 確定②クリック...")
    await save_ss(page, "10_confirm2_page")

    # window.confirm を強制 true にする（二重保険）
    await page.add_init_script("window.confirm = () => true; window.alert = () => {};")
    # ダイアログイベントのフォールバック
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    ok = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="登録"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'button:text("最終確定")',
        'a:text("確定")',
        'input[value*="確定"]',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン", timeout=ELEM_TIMEOUT)

    if not ok:
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "11_final_result")
    print(f"  現在URL: {page.url}")

    # 予約完了の確認
    body = await page.inner_text("body")
    keywords = ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました"]
    if any(kw in body for kw in keywords):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが確認できません。スクリーンショット 11_final_result.png を確認してください。")
    print(f"  本文（先頭300字）: {body[:300]}")


# ──────────────────────────────────────────────
# メインフロー
# ──────────────────────────────────────────────
async def main():
    opts = parse_args()

    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象: {TARGET_DATE_WAREKI} / {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行(--now)' if not opts['wait_for_open'] else '時報待ち(5:00)'}"
          f" / {'ブラウザ表示あり(--headful)' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

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
            timezone_id="Asia/Tokyo",
        )
        # window.confirm を常に true に（Tampermonkey の補完）
        await context.add_init_script(
            "window.confirm = () => true; window.alert = () => {};"
        )
        page = await context.new_page()

        try:
            # ── 事前準備フェーズ（5:00前に完了させる） ──────────
            await step_login(page)
            await step_favorite(page)
            await step_select_date(page)   # 日付を選択して待機

            # ── 5:00:00 ぴったりに検索 ──────────────────────────
            if opts["wait_for_open"]:
                await wait_until_open()

            await step_click_search(page)  # ← ここが5:00に実行される

            # ── 予約確定フェーズ ────────────────────────────────
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)

            print("\n✅ すべてのステップが完了しました。")

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラーが発生しました: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
