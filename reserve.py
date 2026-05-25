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

# 予約対象日（練習: 令和08年06月19日 / 本番: 令和08年07月19日 等に変更）
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_VALUE  = "20260619"           # value属性が数字形式の場合

# 予約対象コート＆時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報待ち設定（本番: 毎月19日 05:00:00 JST）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# スクリーンショット保存先（デバッグ用）
SS_DIR = "screenshots"

# 日付の代替フォーマット（プルダウン検索に使用）
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日",
    "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19", "2026-06-19",
]
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19",
    "260619", "060619",
]
# ──────────────────────────────────────────────


def _jst_now() -> datetime.datetime:
    """JST現在時刻を返す（zoneinfo/pytz どちらにも対応）"""
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Asia/Tokyo"))
    except ImportError:
        import pytz
        return datetime.datetime.now(pytz.timezone("Asia/Tokyo"))


def parse_args() -> dict:
    args = sys.argv[1:]
    return {
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


async def wait_until_open():
    """
    朝5:00:00.000 JST ぴったりまでミリ秒単位で待機。
    段階的スリープで CPU 使用率を抑えつつ精度を確保。
    """
    while True:
        now = _jst_now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0,
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {_jst_now().strftime('%H:%M:%S.%f')} JST")
            return
        elif diff_sec > 300:
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分) ...")
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
    print(f"  [FAIL] {label}: 該当要素なし")
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
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


async def get_active_page(context, page):
    """iframeが存在する場合はメインフレームを返す"""
    # フレームセット構成の場合
    frames = page.frames
    if len(frames) > 1:
        for frame in frames:
            if frame.url and frame.url != "about:blank":
                print(f"  [FRAME] {frame.url}")
    return page


# ─────────────────────────────────────────────────────────
# Step 1: ログイン
# ─────────────────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号（Mnet系で実績のある name 属性を優先）
    await try_fill(page, [
        'input[name="riyousya_bango"]',   # Mnet 標準
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
        'input[name="passwd"]',           # Mnet 標準
        'input[type="password"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")

    # ログインボタン
    await try_click(page, [
        'input[value="ログイン"]',
        'input[value="LOGIN"]',
        'input[value="login"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


# ─────────────────────────────────────────────────────────
# Step 2: お気に入りクリック
# ─────────────────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")
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
        # テキスト全走査フォールバック
        elems = await page.query_selector_all("a, button, input[type=button], input[type=submit]")
        for elem in elems:
            txt = (await elem.inner_text()).strip()
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（フォールバック）: text={txt!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行してページ構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ─────────────────────────────────────────────────────────
# Step 3: 日付選択 + 検索（時報待ち後に実行）
# ─────────────────────────────────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False
    selects = await page.query_selector_all("select")

    # ── パターンA: 単一SELECT（一体型日付）──────────────────
    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v if v else txt)
                print(f"  [OK] 日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── パターンB: 年・月・日が分割SELECTの場合 ─────────────
    if not date_selected:
        print("  [試行] 年月日分割SELECTの可能性...")
        year_pats  = ["令和08", "令和8", "08", "2026", "R08", "R8", "08年"]
        month_pats = ["06", "6", "６", "06月", "6月"]
        day_pats   = ["19", "１９", "19日"]

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p == txt.strip() or p == v for p in year_pats):
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 年選択: {txt!r}")
                    break
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p == txt.strip() or p == v for p in month_pats):
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 月選択: {txt!r}")
                    date_selected = True
                    break
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(p == txt.strip() or p == v for p in day_pats):
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 日選択: {txt!r}")
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
        'button:text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


# ─────────────────────────────────────────────────────────
# Step 4: D面 16:00〜18:00 セルをクリック
# ─────────────────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    # ── 方法①: JavaScriptでテーブル構造を解析してクリック ──
    # 最も確実。行=D面・列=時間帯 と 行=時間帯・列=D面 両方に対応。
    clicked = await page.evaluate("""
        ([facility, timeStart, timeEnd]) => {
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const rows = Array.from(table.querySelectorAll('tr'));

                // ── ケースA: 行ヘッダー=施設名、列ヘッダー=時間帯 ──
                // 1) ヘッダー行から「16:00」列インデックスを探す
                let timeColIdx = -1;
                for (const row of rows.slice(0, 4)) {
                    const cells = Array.from(row.querySelectorAll('td,th'));
                    for (let i = 0; i < cells.length; i++) {
                        const t = cells[i].innerText.trim();
                        if (t.includes(timeStart) || t.includes('16時')) {
                            timeColIdx = i;
                            break;
                        }
                    }
                    if (timeColIdx >= 0) break;
                }
                if (timeColIdx >= 0) {
                    for (const row of rows) {
                        const cells = Array.from(row.querySelectorAll('td,th'));
                        if (cells.length > 0 && cells[0].innerText.trim().includes(facility)) {
                            const tc = cells[timeColIdx];
                            if (tc) {
                                const link = tc.querySelector('a');
                                (link || tc).click();
                                return true;
                            }
                        }
                    }
                }

                // ── ケースB: 行ヘッダー=時間帯、列ヘッダー=施設名 ──
                let facColIdx = -1;
                for (const row of rows.slice(0, 4)) {
                    const cells = Array.from(row.querySelectorAll('td,th'));
                    for (let i = 0; i < cells.length; i++) {
                        if (cells[i].innerText.trim().includes(facility)) {
                            facColIdx = i;
                            break;
                        }
                    }
                    if (facColIdx >= 0) break;
                }
                if (facColIdx >= 0) {
                    for (const row of rows) {
                        const cells = Array.from(row.querySelectorAll('td,th'));
                        if (cells.length > 0) {
                            const t = cells[0].innerText.trim();
                            if (t.includes(timeStart) || t.includes('16時')) {
                                const tc = cells[facColIdx];
                                if (tc) {
                                    const link = tc.querySelector('a');
                                    (link || tc).click();
                                    return true;
                                }
                            }
                        }
                    }
                }
            }
            return false;
        }
    """, [TARGET_FACILITY, TARGET_TIME_START, TARGET_TIME_END])

    if clicked:
        print("  [OK] D面×16:00セル（JavaScript）")
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
        await save_ss(page, "05_slot_selected")
        print(f"  現在URL: {page.url}")
        return

    # ── 方法②: Playwright locator API（Pythonテーブル走査）──
    print("  [試行] Pythonテーブル走査...")
    tables = await page.query_selector_all("table")
    for table in tables:
        rows = await table.query_selector_all("tr")

        # 時間帯列インデックスを探す
        time_col_idx = -1
        for row in rows[:4]:
            cells = await row.query_selector_all("td,th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt or "16時" in txt:
                    time_col_idx = ci
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        for row in rows:
            cells = await row.query_selector_all("td,th")
            if not cells:
                continue
            first_txt = (await cells[0].inner_text()).strip()
            if TARGET_FACILITY in first_txt and time_col_idx < len(cells):
                target_cell = cells[time_col_idx]
                link = await target_cell.query_selector("a")
                elem_to_click = link if link else target_cell
                tc_txt = (await target_cell.inner_text()).strip()
                print(f"  [OK] D面×16:00セル（Python走査）: text={tc_txt!r}")
                await elem_to_click.click()
                clicked = True
                break
        if clicked:
            break

    # ── 方法③: onclick/href フォールバック ──────────────────
    if not clicked:
        print("  [試行] onclick/href フォールバック...")
        all_elems = await page.query_selector_all("[onclick], a[href]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href")   or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if (TARGET_FACILITY in combined) and "16" in combined:
                print(f"  [OK] onclick/href: onclick={onclick!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。"
            f"{SS_DIR}/04_search_results.png を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ─────────────────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ─────────────────────────────────────────────────────────
async def step_confirm1(page):
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


# ─────────────────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# Tampermonkey で window.confirm を無効化済みの前提。
# 念のため dialog イベントも自動承認。
# ─────────────────────────────────────────────────────────
async def step_confirm2(page):
    print("\n[Step 6] 確定②クリック...")

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

    body_text = await page.inner_text("body")
    if any(w in body_text for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了"]):
        print("\n✅  予約完了を確認しました！")
    else:
        print("\n⚠️   完了メッセージが見つかりません。スクリーンショットを確認してください。")
    print(f"  本文（先頭200字）: {body_text[:200]}")


# ─────────────────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
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
            timezone_id="Asia/Tokyo",
        )
        page = await context.new_page()

        try:
            await step_login(page)
            await step_favorite(page)
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)
            print("\n✅  すべてのステップが完了しました。")
        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌  エラー: {e}")
            raise
        finally:
            if not opts["headless"]:
                input("\nEnterキーでブラウザを閉じます...")
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
