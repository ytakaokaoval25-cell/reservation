"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方
  python reserve.py              # 本番モード: 5時前にログイン待機、5:00:00ちょうどに検索
  python reserve.py --now        # 即時実行（テスト用・5時待機スキップ）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備
  pip install playwright
  playwright install chromium

■ タイミング設計（本番時）
  04:50頃 スクリプト起動 → ログイン → お気に入り → 日付選択（事前準備）
  05:00:00.000 ← ここで検索ボタンをクリック（ミリ秒精度で待機）
  05:00:00.xxx  D面16:00〜18:00を選択 → 確定① → 確定②
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

# 予約対象日（練習: 令和08年06月19日。本番は変更）
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026年6月19日", "2026/06/19",
]
TARGET_YEAR_VALUES  = ["令和08", "令和8", "08", "8", "2026", "R08", "R8"]
TARGET_MONTH_VALUES = ["06", "6", "６", "６月", "06月", "6月"]
TARGET_DAY_VALUES   = ["19", "１９", "19日"]

# 予約対象コート＆時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 予約受付開始時刻（本番: 朝5:00:00）
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
        "headless":      "--headful" not in args,
        "wait_for_open": "--now"     not in args,
    }


async def wait_until_open():
    """
    朝5:00:00.000 ぴったりまでミリ秒単位で待機する。
    ログイン・画面遷移は事前に完了し、検索ボタン直前でこの関数を呼ぶ。
    """
    while True:
        now    = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0,
        )
        diff = (target - now).total_seconds()

        if diff <= 0:
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")
            print(f"[時報] 開始時刻到達: {ts}")
            return

        if diff > 300:        # 5分以上前 → 30秒おき
            print(f"[時報待ち] あと {diff:.0f}秒 ({diff/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff > 10:       # 10秒〜5分前 → 1秒おき
            await asyncio.sleep(1)
        elif diff > 0.1:      # 100ms〜10秒前 → 50msおき
            await asyncio.sleep(0.05)
        else:                 # 100ms以内 → 1msごとのビジーウェイト
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_click(page, selectors: list, label: str, timeout: int = 5_000) -> bool:
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


async def try_fill(page, selectors: list, value: str, label: str, timeout: int = 5_000) -> bool:
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


# ──────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────
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
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")

    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")

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


# ──────────────────────────────────────────────
# Step 2: お気に入りクリック
# ──────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        '[onclick*="favorite"]',
        '[onclick*="okiniri"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全走査フォールバック
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
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
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行してメニュー構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 3: 日付選択（5時前に完了）＋ 時報待ち ＋ 検索
# ──────────────────────────────────────────────
async def step_select_date_and_search(page, wait_for_open: bool):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False
    selects = await page.query_selector_all("select")

    # ── アプローチ①: 単一SELECTに日付テキスト/valueが含まれる場合 ──
    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択 (単一): name={name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── アプローチ②: 年・月・日が別々のSELECTに分かれている場合 ──
    if not date_selected:
        print("  [試行] 年月日が分割SELECTの可能性あり...")
        year_done = month_done = day_done = False

        for sel_elem in selects:
            opts = await sel_elem.query_selector_all("option")
            opt_texts  = [(await o.inner_text()).strip() for o in opts]
            opt_values = [await o.get_attribute("value") or "" for o in opts]

            for i, (ot, ov) in enumerate(zip(opt_texts, opt_values)):
                if not year_done and any(p in ot or p == ov for p in TARGET_YEAR_VALUES):
                    await sel_elem.select_option(index=i)
                    print(f"  [OK] 年選択: {ot!r}")
                    year_done = True
                    break
                if not month_done and any(p == ot or p == ov for p in TARGET_MONTH_VALUES):
                    await sel_elem.select_option(index=i)
                    print(f"  [OK] 月選択: {ot!r}")
                    month_done = True
                    break
                if not day_done and any(p == ot or p == ov for p in TARGET_DAY_VALUES):
                    await sel_elem.select_option(index=i)
                    print(f"  [OK] 日選択: {ot!r}")
                    day_done = True
                    break

        date_selected = year_done or month_done or day_done

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.py でプルダウン構造を確認してください。"
        )

    await save_ss(page, "03b_date_selected")

    # ── 5:00:00 ちょうどまで待機（ここが時報待ちポイント）──
    if wait_for_open:
        print(f"\n[時報待ち] 日付選択完了。朝{OPEN_HOUR}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d} まで待機...")
        await wait_until_open()
    else:
        print("  [即時] 時報待ちスキップ（--now モード）")

    # ── 検索ボタンを即クリック（5:00:00.xxx） ──
    clicked = await try_click(page, [
        'input[value="検索"]',
        'button:text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ], "検索ボタン")

    if not clicked:
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 4: D面 16:00〜18:00 の赤丸セルをクリック
# ──────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")
    clicked = False

    tables = await page.query_selector_all("table")

    # ── アプローチ①: D面行を探し、その行の16:00セルをクリック ──
    for table in tables:
        rows = await table.query_selector_all("tr")
        for row in rows:
            cells = await row.query_selector_all("td, th")
            cell_texts = [(await c.inner_text()).strip() for c in cells]

            if TARGET_FACILITY not in cell_texts:
                continue

            print(f"  [INFO] D面行発見: {cell_texts}")
            for i, cell in enumerate(cells):
                txt = cell_texts[i]
                if TARGET_TIME_START in txt:
                    cls  = await cell.get_attribute("class") or ""
                    onclick = await cell.get_attribute("onclick") or ""
                    print(f"  [FOUND①] D面×{TARGET_TIME_START}: text={txt!r} class={cls!r}")
                    await cell.click()
                    clicked = True
                    break

                # onclick/aタグが埋め込まれているケース
                a = await cell.query_selector("a")
                if a:
                    a_txt = (await a.inner_text()).strip()
                    if TARGET_TIME_START in a_txt or str(i) in onclick:
                        print(f"  [FOUND①-a] D面リンク: {a_txt!r}")
                        await a.click()
                        clicked = True
                        break
            if clicked:
                break
        if clicked:
            break

    # ── アプローチ②: ヘッダー行から列インデックスを特定 ──
    if not clicked:
        print("  [試行②] ヘッダーから列インデックスを特定...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            time_col_idx = -1

            for row in rows[:4]:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                        time_col_idx = ci
                        print(f"  [INFO] 16:00〜18:00 列={ci}")
                        break
                if time_col_idx >= 0:
                    break

            if time_col_idx < 0:
                continue

            for row in rows:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_FACILITY in txt and time_col_idx < len(cells):
                        target_cell = cells[time_col_idx]
                        tc_txt = (await target_cell.inner_text()).strip()
                        tc_cls = await target_cell.get_attribute("class") or ""
                        print(f"  [FOUND②] D面×列{time_col_idx}: text={tc_txt!r} class={tc_cls!r}")
                        await target_cell.click()
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick/href にD面+時間が含まれる要素 ──
    if not clicked:
        print("  [試行③] onclick/href/text からD面16:00を探す...")
        for elem in await page.query_selector_all("[onclick], a[href], input[type=image]"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href")    or ""
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            combined = onclick + href + txt
            if ("D面" in combined or "d面" in combined.lower()) and "16" in combined:
                print(f"  [FOUND③] onclick={onclick[:60]!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。"
            "screenshots/04_search_results.png でテーブル構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ──────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①クリック...")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="予約確認"]',
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


# ──────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# ──────────────────────────────────────────────
async def step_confirm2(page):
    """
    window.confirm はページ読み込み時に add_init_script で無効化済み。
    念のため dialog イベントでも自動承認する。
    """
    print("\n[Step 6] 確定②クリック...")

    # dialogイベントハンドラ（二重の保険）
    page.on("dialog", lambda dlg: asyncio.ensure_future(dlg.accept()))

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
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。スクリーンショットを確認してください。")
    print(f"  最終本文（先頭200字）: {body_text[:200]}")


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    mode_str = "即時実行" if not opts["wait_for_open"] else f"時報待ち({OPEN_HOUR}:00)"
    head_str = "ブラウザ表示あり" if not opts["headless"] else "ヘッドレス"
    print(f"モード: {mode_str} / {head_str}")
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
            ignore_https_errors=True,
        )

        # window.confirm / alert / prompt を全ページで無効化
        # （Tampermonkeyが有効でないPlaywright環境でも動作するよう二重対策）
        await context.add_init_script(
            "window.confirm = () => true; "
            "window.alert  = () => {}; "
            "window.prompt = () => null;"
        )

        page = await context.new_page()

        try:
            # ── ログイン・ナビゲート（5時前に完了させる） ──
            await step_login(page)
            await step_favorite(page)

            # ── 日付選択 → 時報待ち → 検索（5:00:00ちょうど） ──
            await step_select_date_and_search(page, opts["wait_for_open"])

            # ── スロット選択・確定（全速） ──
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
