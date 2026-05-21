"""
まんまるよやく2 自動予約スクリプト (v2.1)
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ）
  python reserve.py --prelogin   # ★推奨★ 事前ログイン→5:00に検索（最速）
  python reserve.py --prelogin --headful  # 事前ログイン＋画面表示

■ 最速モード手順（本番）
  1. 4:55頃に「python reserve.py --prelogin」を起動
  2. ログイン・お気に入り画面まで自動移動して待機
  3. 5:00:00.000 ぴったりに自動でリロード→日付選択→検索→予約確定

■ 本番(7月)への切替
  スクリプト冒頭の TARGET_DATE_* を「令和08年07月XX日」に変更する

■ 準備（初回のみ）
  pip install playwright
  playwright install chromium
"""

import asyncio
import datetime
import sys
import os
import time
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────
# 設定値（本番時はここを変更）
# ──────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# ── 練習: 令和08年06月19日 ──
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_VALUE  = "20260619"
TARGET_DATE_ALT_VALUES = ["20260619", "2026-06-19", "2026/06/19", "260619"]
TARGET_DATE_ALT_TEXTS  = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19",
]

# ── 本番(7月)への切替例 ──
# TARGET_DATE_WAREKI = "令和08年07月19日"
# TARGET_DATE_VALUE  = "20260719"
# TARGET_DATE_ALT_VALUES = ["20260719", "2026-07-19", "2026/07/19", "260719"]
# TARGET_DATE_ALT_TEXTS  = [
#     "令和08年07月19日", "令和8年7月19日", "令和０８年０７月１９日",
#     "2026年07月19日", "2026/07/19",
# ]

TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

NAV_TIMEOUT  = 30_000   # ページ遷移タイムアウト（ms）
ELEM_TIMEOUT = 10_000   # 要素待機タイムアウト（ms）

SS_DIR = "screenshots"
# ──────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":      "--headful"  not in args,
        "wait_for_open": "--now"      not in args,
        "prelogin":      "--prelogin" in args,
    }


async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位で待機（段階的スリープ）"""
    print("[時報待ち] 朝5:00:00.000 まで待機します...")
    while True:
        now  = datetime.datetime.now()
        tgt  = now.replace(hour=OPEN_HOUR, minute=OPEN_MINUTE,
                           second=OPEN_SECOND, microsecond=0)
        diff = (tgt - now).total_seconds()

        if diff <= 0:
            print(f"[時報] 到達: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
            break
        elif diff > 300:
            print(f"[時報待ち] あと {diff:.0f}秒 ({diff/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff > 10:
            await asyncio.sleep(1)
        elif diff > 1:
            await asyncio.sleep(0.5)
        elif diff > 0.1:
            await asyncio.sleep(0.05)
        elif diff > 0.01:
            await asyncio.sleep(0.005)
        else:
            # 最後の10ms: ビジーループで精密タイミング
            deadline = time.perf_counter() + diff
            while time.perf_counter() < deadline:
                await asyncio.sleep(0)  # イベントループに最小時間だけ譲渡


async def save_ss(page, name: str):
    """スクリーンショットを保存（デバッグ用・失敗しても処理継続）"""
    os.makedirs(SS_DIR, exist_ok=True)
    try:
        await page.screenshot(path=f"{SS_DIR}/{name}.png", full_page=True)
        print(f"  [SS] {SS_DIR}/{name}.png")
    except Exception:
        pass


async def try_click(page, selectors: list, label: str, timeout: int = 5000) -> bool:
    """複数セレクターを順番に試してクリック。成功したら True を返す"""
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
            print(f"  [SKIP] {sel}: {e}")
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


async def try_fill(page, selectors: list, value: str, label: str, timeout: int = 5000) -> bool:
    """複数セレクターを順番に試して入力。成功したら True を返す"""
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
            print(f"  [SKIP] {sel}: {e}")
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


# ══════════════════════════════════════════════
# ステップ関数
# ══════════════════════════════════════════════

async def step_login(page):
    """Step1: ログイン"""
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号（M-netの主要フィールド名を優先）
    await try_fill(page, [
        'input[name="userid"]',
        'input[name="userno"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
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
    """Step2: お気に入りクリック → 絞り込み画面へ"""
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入り", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全走査フォールバック
        for elem in await page.query_selector_all(
                "a, button, input[type=button], input[type=submit]"):
            txt = (await elem.inner_text()).strip()
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print("  [OK] お気に入り（テキスト走査）")
                clicked = True
                break

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行してセレクターを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_filter_page")
    print(f"  現在URL: {page.url}")


async def step_select_date_and_search(page):
    """Step3: 日付プルダウンで令和08年06月19日を選択して検索（最速）"""
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False
    for sel_elem in await page.query_selector_all("select"):
        for opt in await sel_elem.query_selector_all("option"):
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

    # 分割型（年・月・日が別々のSELECT）のフォールバック
    if not date_selected:
        print("  [試行] 年月日分割SELECTを試みます...")
        year_vals  = ["令和08", "令和8", "08", "2026", "R08", "R8", "8"]
        month_vals = ["06", "6", "６月", "06月", "６"]
        day_vals   = ["19", "１９", "19日"]

        all_selects = await page.query_selector_all("select")
        for target_patterns, label in [
            (year_vals, "年"),
            (month_vals, "月"),
            (day_vals, "日"),
        ]:
            for sel_elem in all_selects:
                for opt in await sel_elem.query_selector_all("option"):
                    txt = (await opt.inner_text()).strip()
                    v   = await opt.get_attribute("value") or ""
                    if any(p == txt or p == v for p in target_patterns):
                        await sel_elem.select_option(value=v if v else txt)
                        print(f"  [OK] {label}選択: {txt!r}")
                        if label == "月":
                            date_selected = True
                        break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.py を実行して実際のoption値を確認してください。"
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
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} を選択...")

    clicked = False

    async def click_cell(cell) -> bool:
        """セル内の子リンク/ボタンを優先してクリック"""
        inner = await cell.query_selector(
            "a, input[type=submit], input[type=button], button")
        if inner:
            await inner.click()
        else:
            await cell.click()
        txt = (await cell.inner_text()).strip()
        print(f"  [OK] セルクリック: text={txt!r}")
        return True

    # ── アプローチ①: ヘッダーから列インデックスを特定 ──────────────
    for table in await page.query_selector_all("table"):
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # 最初の5行でヘッダーを探す
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                # 全角スペース・改行を除去して比較
                txt_clean = txt.replace("　", " ").replace("\n", " ")
                if TARGET_TIME_START in txt_clean:
                    time_col_idx = ci
                    print(f"  [INFO] '{TARGET_TIME_START}' 列インデックス={ci}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行を特定
        for row in rows:
            cells = await row.query_selector_all("td, th")
            if not cells:
                continue

            row_txts = []
            for c in cells:
                row_txts.append((await c.inner_text()).strip())

            if any(TARGET_FACILITY in t for t in row_txts):
                print(f"  [INFO] {TARGET_FACILITY} 行発見")
                if time_col_idx < len(cells):
                    clicked = await click_cell(cells[time_col_idx])
                break

        if clicked:
            break

    # ── アプローチ②: D面行の全セルからTARGET_TIME_STARTを含むセルを探す ─
    if not clicked:
        print("  [試行] アプローチ②: テキスト走査...")
        for table in await page.query_selector_all("table"):
            for row in await table.query_selector_all("tr"):
                cells = await row.query_selector_all("td, th")
                row_txts = []
                for c in cells:
                    row_txts.append((await c.inner_text()).strip())

                if any(TARGET_FACILITY in t for t in row_txts):
                    for cell, txt in zip(cells, row_txts):
                        if TARGET_TIME_START in txt:
                            clicked = await click_cell(cell)
                            break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick/href にD面+16が含まれるリンク ───────────
    if not clicked:
        print("  [試行] アプローチ③: onclick/href 検索...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if ("D面" in combined or "d面" in combined.lower()) and "16" in combined:
                await elem.click()
                print(f"  [OK] アプローチ③: text={txt!r}")
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。"
            "screenshots/04_search_results.png を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


async def step_confirm1(page):
    """Step5: 確定①（料金確認画面へ）"""
    print("\n[Step 5] 確定① クリック（料金確認画面へ）...")

    if not await try_click(page, [
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
    ], "確定①ボタン"):
        raise RuntimeError("確定①ボタンが見つかりません")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


async def step_confirm2(page):
    """Step6: 確定②（最終確定）
    Tampermonkey で window.confirm を無効化済みの前提。
    万一ダイアログが発火した場合に備え自動承認ハンドラを登録。
    """
    print("\n[Step 6] 確定② クリック（最終確定）...")

    async def _accept_dialog(dialog):
        await dialog.accept()

    page.on("dialog", _accept_dialog)

    if not await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'input[value*="確定"]',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン"):
        raise RuntimeError("確定②ボタンが見つかりません")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_complete")
    print(f"  現在URL: {page.url}")

    body = await page.inner_text("body")
    if any(w in body for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。"
              "screenshots/07_complete.png を確認してください。")
    print(f"  本文先頭200字: {body[:200]}")


# ══════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════

async def main():
    opts = parse_args()

    mode_labels = []
    if opts["prelogin"]:      mode_labels.append("事前ログイン（最速）")
    if not opts["wait_for_open"]: mode_labels.append("即時実行")
    else:                         mode_labels.append("時報待ち(05:00:00)")
    if not opts["headless"]:  mode_labels.append("ブラウザ表示")

    print("=" * 62)
    print("まんまるよやく2 自動予約スクリプト v2.1")
    print(f"  対象日  : {TARGET_DATE_WAREKI}")
    print(f"  施設    : {TARGET_FACILITY}  {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"  モード  : {' / '.join(mode_labels)}")
    print("=" * 62)

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
            if opts["prelogin"]:
                # ────────────────────────────────────────────────────
                # 事前ログインモード（推奨）
                #   4:55頃に起動 → ログイン・お気に入りを事前完了
                #   5:00:00 ぴったりにページリロード → 日付選択 → 検索
                # ────────────────────────────────────────────────────
                await step_login(page)
                await step_favorite(page)
                print("\n[待機中] 5:00:00 まで絞り込みページで待機します...")
                if opts["wait_for_open"]:
                    await wait_until_open()
                # 5:00 になったらリロードで最新の日付リストを取得
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S.%f')}] ページリロード開始")
                await page.reload(wait_until="networkidle", timeout=NAV_TIMEOUT)

            else:
                # ────────────────────────────────────────────────────
                # 通常モード（5:00に全ステップ実行）
                # ────────────────────────────────────────────────────
                if opts["wait_for_open"]:
                    await wait_until_open()
                await step_login(page)
                await step_favorite(page)

            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)

            print("\n✅ 全ステップ完了!")

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
