"""
まんまるよやく2 自動予約スクリプト（最適化版）
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方
  python reserve.py              # 朝5:00待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備
  pip install playwright
  playwright install chromium

■ 最速化の仕組み
  ・5:00の1～2分前 → ログイン＋お気に入り画面まで移動
  ・5:00:00直前   → 日付セレクトを設定して待機
  ・5:00:00.000   → 検索ボタンをクリック → 以降は最速処理
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────
# 設定値（本番時は TARGET_DATE_* と OPEN_* を変更）
# ──────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日（令和08年06月19日 = 2026-06-19 は練習用）
# 本番: 令和08年07月XX日 → TARGET_DATE_WAREKI / VALUE を変更
TARGET_DATE_WAREKI    = "令和08年06月19日"
TARGET_DATE_VALUE     = "20260619"
TARGET_DATE_ALT_VALUES = ["20260619", "2026-06-19", "2026/06/19", "260619"]
TARGET_DATE_ALT_TEXTS  = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19",
]

# 予約対象コート＆時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報設定（朝5:00:00.000に検索開始）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# 何秒前からログインを開始するか（事前ログイン戦略）
PRE_LOGIN_SECONDS = 90  # 5:00の1分30秒前からログイン開始

# タイムアウト（ms）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# スクリーンショット保存先
SS_DIR = "screenshots"
# ──────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":      "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


# ─── 時刻ユーティリティ ─────────────────────────────────
def get_open_time_today() -> datetime.datetime:
    now = datetime.datetime.now()
    return now.replace(
        hour=OPEN_HOUR, minute=OPEN_MINUTE,
        second=OPEN_SECOND, microsecond=0
    )


async def wait_until(target: datetime.datetime, label: str = ""):
    """target 時刻まで精密待機（ミリ秒単位）"""
    while True:
        now  = datetime.datetime.now()
        diff = (target - now).total_seconds()
        if diff <= 0:
            print(f"[時刻到達] {label}: {now.strftime('%H:%M:%S.%f')}")
            return
        elif diff > 300:
            print(f"[待機中] {label} まで {diff:.0f}秒 ({diff/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff > 10:
            await asyncio.sleep(1)
        elif diff > 0.05:
            await asyncio.sleep(0.02)   # 20ms
        else:
            await asyncio.sleep(0.001)  # 1ms


# ─── スクリーンショット保存 ──────────────────────────────
async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


# ─── 汎用クリック（複数セレクター試行） ─────────────────
async def try_click(page, selectors: list, label: str,
                    timeout: int = 5000) -> bool:
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


# ─── 汎用入力 ───────────────────────────────────────────
async def try_fill(page, selectors: list, value: str, label: str,
                   timeout: int = 5000) -> bool:
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


# ═══════════════════════════════════════════════
# Step 1: ログイン
# ═══════════════════════════════════════════════
async def step_login(page):
    print("\n[Step 1] ログイン...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # ── 利用者番号 ──────────────────────────────
    await try_fill(page, [
        'input[name="userId"]',
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userId', '#userid',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")

    # ── パスワード ────────────────────────────
    await try_fill(page, [
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[type="password"]',
    ], PASSWORD, "パスワード")

    # ── ログインボタン ────────────────────────
    await try_click(page, [
        'input[value="ログイン"]',
        'input[value="LOGIN"]',
        'input[value="login"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("ログイン")',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


# ═══════════════════════════════════════════════
# Step 2: お気に入り → 絞り込み画面
# ═══════════════════════════════════════════════
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        'a[href*="favorite"]',
        'a[href*="okiniri"]',
        'a[href*="okiniiri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    # テキストスキャン フォールバック
    if not clicked:
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（テキストスキャン）: {txt or val!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。analyze_site.py で確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ═══════════════════════════════════════════════
# Step 3a: 日付プルダウンを設定（検索ボタンは押さない）
# ═══════════════════════════════════════════════
async def step_set_date(page) -> bool:
    """日付セレクトを選択。検索ボタンはまだ押さない。"""
    print(f"\n[Step 3a] 日付プルダウン設定: {TARGET_DATE_WAREKI}")

    # ── 単一SELECT（令和08年06月19日 を含むoption） ────────
    date_selected = False
    for sel_elem in await page.query_selector_all("select"):
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

    # ── 年/月/日 分割SELECT の場合 ───────────────────────
    if not date_selected:
        print("  [試行] 年月日分割SELECT...")
        selects = await page.query_selector_all("select")
        year_done = month_done = day_done = False
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            texts   = [(await o.get_attribute("value") or "", (await o.inner_text()).strip())
                       for o in options]
            # 年
            if not year_done:
                for v, txt in texts:
                    if any(p in txt or p == v for p in
                           ["令和08", "令和8", "08", "2026", "R08", "R8"]):
                        await sel_elem.select_option(value=v or txt)
                        print(f"  [OK] 年選択: {txt!r}")
                        year_done = True
                        break
            # 月
            if not month_done:
                for v, txt in texts:
                    if any(p in txt or p == v for p in
                           ["06", "6", "６月", "06月", "6月"]):
                        await sel_elem.select_option(value=v or txt)
                        print(f"  [OK] 月選択: {txt!r}")
                        month_done = True
                        break
            # 日
            if not day_done:
                for v, txt in texts:
                    if any(p in txt or p == v for p in
                           ["19", "１９", "19日"]):
                        await sel_elem.select_option(value=v or txt)
                        print(f"  [OK] 日選択: {txt!r}")
                        day_done = True
                        break
        if month_done or day_done:
            date_selected = True

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        print(f"  [WARN] 日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
              "（5:00以降に解放される可能性あり）")
    return date_selected


# ═══════════════════════════════════════════════
# Step 3b: 検索ボタンクリック（5:00ちょうどに実行）
# ═══════════════════════════════════════════════
async def step_search(page):
    print(f"\n[Step 3b] 検索ボタンクリック @ {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
    clicked = await try_click(page, [
        'input[value="検索"]',
        'input[value="  検索  "]',
        'button:text("検索")',
        'input[value*="検索"]',
        'input[name="search"]',
        'input[name="btnSearch"]',
        'button[name="search"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ], "検索ボタン", timeout=3000)

    if not clicked:
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


# ═══════════════════════════════════════════════
# Step 4: D面 16:00〜18:00 セル選択
# ═══════════════════════════════════════════════
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} 選択...")
    clicked = False

    tables = await page.query_selector_all("table")

    # ── アプローチ①: ヘッダー行から列インデックスを特定 ────
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行で「16:00〜18:00」または「16:00」の列インデックスを取得
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt:
                    time_col_idx = ci
                    print(f"  [INFO] {TARGET_TIME_START} 列インデックス={ci} (text={txt!r})")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行を探し、time_col_idx列のセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_FACILITY in txt and ci < 2:  # 先頭列付近にD面ラベル
                    if time_col_idx < len(cells):
                        target_cell = cells[time_col_idx]
                        tc_txt = (await target_cell.inner_text()).strip()
                        tc_cls = await target_cell.get_attribute("class") or ""
                        tc_onclick = await target_cell.get_attribute("onclick") or ""
                        print(f"  [FOUND] D面×{TARGET_TIME_START}: "
                              f"text={tc_txt!r} class={tc_cls!r} onclick={tc_onclick[:60]!r}")
                        await target_cell.click()
                        clicked = True
                    break
            if clicked:
                break
        if clicked:
            break

    # ── アプローチ②: D面行のテキストスキャン ───────────────
    if not clicked:
        print("  [試行②] D面行のテキストスキャン...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                cell_texts = [((await c.inner_text()).strip()) for c in cells]
                if TARGET_FACILITY in cell_texts or any(
                        TARGET_FACILITY in t for t in cell_texts):
                    print(f"  [INFO] D面行: {cell_texts[:8]}")
                    for ci, cell in enumerate(cells):
                        txt = cell_texts[ci]
                        if TARGET_TIME_START in txt or "16" in txt:
                            cls     = await cell.get_attribute("class") or ""
                            onclick = await cell.get_attribute("onclick") or ""
                            print(f"  [FOUND②] cell[{ci}] text={txt!r} class={cls!r}")
                            await cell.click()
                            clicked = True
                            break
                    if clicked:
                        break
            if clicked:
                break

    # ── アプローチ③: onclick / href スキャン ────────────────
    if not clicked:
        print("  [試行③] onclick/href スキャン...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if ("D面" in combined or "d面" in combined.lower()) and "16" in combined:
                print(f"  [FOUND③] onclick={onclick[:60]!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    # ── アプローチ④: img の alt や src で赤丸を探す ─────────
    if not clicked:
        print("  [試行④] 赤丸画像スキャン...")
        # 赤丸は通常 img[alt="○"] または class="circle" 等
        for img in await page.query_selector_all("img, td"):
            alt = await img.get_attribute("alt") or ""
            src = await img.get_attribute("src") or ""
            cls = await img.get_attribute("class") or ""
            if any(k in (alt + src + cls).lower() for k in
                   ["red", "maru", "circle", "○", "◎", "●", "open"]):
                # この要素の親rowがD面かチェック
                row = await img.evaluate_handle("el => el.closest('tr')")
                if row:
                    row_txt = await page.evaluate("el => el ? el.innerText : ''", row)
                    if TARGET_FACILITY in row_txt and TARGET_TIME_START in row_txt:
                        print(f"  [FOUND④] 赤丸要素: alt={alt!r} src={src!r}")
                        await img.click()
                        clicked = True
                        break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。"
            "screenshots/ フォルダを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ═══════════════════════════════════════════════
# Step 5: 確定①（料金確認画面へ）
# ═══════════════════════════════════════════════
async def step_confirm1(page):
    print("\n[Step 5] 確定①クリック...")
    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="予約する"]',
        'input[value="次へ"]',
        'input[name="btnYoyaku"]',
        'input[name="btnConfirm"]',
        'input[name="btnNext"]',
        'button:text("確定")',
        'button:text("確認")',
        'button:text("次へ")',
        'input[value*="確定"]',
        'input[value*="予約"]',
        'a:text("確定")',
        'a:text("次へ")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。screenshots/ を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


# ═══════════════════════════════════════════════
# Step 6: 確定②（最終確定）
# Tampermonkey で window.confirm 無効化済みが前提
# Playwright 側でもダイアログを自動承認するフォールバック付き
# ═══════════════════════════════════════════════
async def step_confirm2(page):
    print("\n[Step 6] 確定②クリック...")

    # window.confirm を JS レベルで上書き（二重保険）
    await page.add_init_script("window.confirm = () => true;")
    # Playwright ダイアログハンドラ（フォールバック）
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="申込む"]',
        'input[value="申込"]',
        'input[name="btnFinal"]',
        'input[name="btnKakutei"]',
        'input[name="btnConfirm2"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'button:text("申込む")',
        'input[value*="確定"]',
        'input[value*="申込"]',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        raise RuntimeError("確定②ボタンが見つかりません。screenshots/ を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    body = await page.inner_text("body")
    if any(w in body for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。screenshots/07_final_result.png を確認。")
    print(f"  本文先頭200字: {body[:200]}")


# ═══════════════════════════════════════════════
# メイン処理
# ═══════════════════════════════════════════════
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト（最適化版）")
    print(f"対象: {TARGET_DATE_WAREKI}  {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    mode = ("即時実行" if not opts["wait_for_open"] else "時報待ち(5:00)")
    disp = ("ブラウザ表示あり" if not opts["headless"] else "ヘッドレス")
    print(f"モード: {mode} / {disp}")
    print("=" * 60)

    open_time    = get_open_time_today()
    pre_login_at = open_time - datetime.timedelta(seconds=PRE_LOGIN_SECONDS)

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
        page = await context.new_page()

        # window.confirm を初期スクリプトで上書き（全ページ共通）
        await context.add_init_script("window.confirm = () => true;")

        try:
            if opts["wait_for_open"]:
                # ── 事前ログイン待機 ─────────────────────────────────
                await wait_until(pre_login_at,
                                 f"事前ログイン開始（5:00の{PRE_LOGIN_SECONDS}秒前）")
                await step_login(page)
                await step_favorite(page)

                # ── 日付設定（画面に日付プルダウンが存在すれば） ────
                date_set = await step_set_date(page)

                # ── 5:00:00.000ちょうどまで待機 ──────────────────────
                await wait_until(open_time, "検索ボタン押下（開放時刻）")

                # 日付が未設定の場合は再試行（5:00以降に表示される可能性）
                if not date_set:
                    print("  [再試行] 日付プルダウンを再設定...")
                    await step_set_date(page)

                await step_search(page)

            else:
                # ── 即時実行モード（--now） ─────────────────────────
                await step_login(page)
                await step_favorite(page)
                await step_set_date(page)
                await step_search(page)

            # ── 以降は時刻に関係なく最速処理 ────────────────────────
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
