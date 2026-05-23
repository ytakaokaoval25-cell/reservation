"""
まんまるよやく2 自動予約スクリプト
================================================
対象（練習）: D面 16:00〜18:00 / 令和08年06月19日
本番（5/19朝5時実行）: 令和08年07月分を変更して使用

■ 使い方（ローカルPCで実行 ※日本国内IP必須）
  pip install playwright
  playwright install chromium

  python reserve.py              # 朝5:00:00ぴったり待ちモード
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 事前確認
  analyze_site.py を実行して下記セレクター定数が正しいか検証すること。
  特に SELECT_NAME_DATE / TARGET_DATE_VALUE / SLOT_COL_INDEX の3つが重要。

■ Tampermonkey前提
  window.confirm は Tampermonkey で無効化済みのためダイアログは発火しない。
  万一発火した場合はスクリプト内で自動承認する。
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ══════════════════════════════════════════════════════════
# 【設定値 — analyze_site.py の出力を参考に適宜修正】
# ══════════════════════════════════════════════════════════
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# ── 予約対象日 ──────────────────────────────────────────
# 練習: 令和08年06月19日（2026-06-19）
# 本番: ここを令和08年07月XX日に書き換える
TARGET_DATE_TEXTS = [
    "令和08年06月19日",
    "令和8年6月19日",
    "令和０８年０６月１９日",
    "2026年06月19日",
    "2026/06/19",
]
TARGET_DATE_VALUES = ["20260619", "2026-06-19", "2026/06/19", "260619"]

# ── 予約対象施設・時間 ──────────────────────────────────
TARGET_FACILITY   = "D面"          # 行ヘッダーに表示されるテキスト
TARGET_TIME_START = "16:00"        # 列ヘッダーに表示される開始時刻
TARGET_TIME_END   = "18:00"        # 列ヘッダーに表示される終了時刻

# ── 時報待ち設定 ────────────────────────────────────────
# 本番: 令和08年05月19日 05:00:00 に新予約枠が公開される
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# ── タイムアウト（ms） ──────────────────────────────────
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# ── スクリーンショット保存先 ────────────────────────────
SS_DIR = "screenshots"

# ── Chromium実行パス ────────────────────────────────────
# 通常はNoneのまま（playwright install chromiumで自動解決）
# Windowsの例: r"C:\Users\xxx\AppData\Local\ms-playwright\chromium-xxxx\chrome-win\chrome.exe"
CHROMIUM_PATH: str | None = None

# ══════════════════════════════════════════════════════════


def parse_args() -> dict:
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


# ──────────────────────────────────────────────────────────
# 時報待ちロジック（ミリ秒精度）
# ──────────────────────────────────────────────────────────
async def wait_until_open():
    """朝 OPEN_HOUR:OPEN_MINUTE:OPEN_SECOND ぴったりまで待機（ミリ秒精度）"""
    print(f"[時報待ち] {OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d}.000 まで待機します...")

    while True:
        now    = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0,
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {now.strftime('%H:%M:%S.%f')[:-3]}")
            break
        elif diff_sec > 300:
            # 5分以上前 → 30秒ごとに確認
            print(f"[待機] あと {diff_sec/60:.1f}分 ({diff_sec:.0f}秒)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            # 10秒〜5分前 → 1秒ごと
            await asyncio.sleep(1)
        elif diff_sec > 0.05:
            # 50ms〜10秒前 → 10msごと（精度重視）
            await asyncio.sleep(0.01)
        else:
            # 50ms以内 → 1msごとでスピン待ち
            await asyncio.sleep(0.001)


# ──────────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────────
async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_fill(page, selectors: list[str], value: str, label: str,
                   timeout: int = 5_000) -> bool:
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
    print(f"  [FAIL] {label}: 該当フィールドなし")
    return False


async def try_click(page, selectors: list[str], label: str,
                    timeout: int = 5_000) -> bool:
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


# ──────────────────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号: 最初のtext/tel/number系フィールドに入力
    all_inputs = await page.query_selector_all("input")
    filled = False
    for inp in all_inputs:
        t = (await inp.get_attribute("type") or "text").lower()
        if t in ("text", "tel", "number", "email"):
            name = await inp.get_attribute("name") or ""
            id_  = await inp.get_attribute("id")   or ""
            await inp.fill(USER_ID)
            print(f"  [OK] 利用者番号: type={t!r} name={name!r} id={id_!r}")
            filled = True
            break

    if not filled:
        # フォールバック: name/id にキーワードが含まれるもの
        await try_fill(page, [
            'input[name*="user"]', 'input[name*="id"]', 'input[name*="member"]',
            'input[id*="user"]',   'input[id*="id"]',   'input[id*="member"]',
        ], USER_ID, "利用者番号（フォールバック）")

    # パスワード
    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")

    # ログインボタン
    submitted = False
    # まず input[type=submit] を試す
    sub = await page.query_selector("input[type=submit]")
    if sub:
        val = await sub.get_attribute("value") or ""
        await sub.click()
        print(f"  [OK] ログインボタン（submit）: value={val!r}")
        submitted = True

    if not submitted:
        submitted = await try_click(page, [
            'button[type="submit"]',
            'button:text("ログイン")',
            'input[value="ログイン"]',
            'a:text("ログイン")',
        ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  URL: {page.url}")


# ──────────────────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面
# ──────────────────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
    ], "お気に入り")

    if not clicked:
        # テキストでフォールバック
        elems = await page.query_selector_all(
            "a, button, input[type=submit], input[type=button]"
        )
        for elem in elems:
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = await elem.get_attribute("value") or ""
            if "お気に入り" in txt:
                href = await elem.get_attribute("href") or ""
                print(f"  [OK] お気に入り（フォールバック）: text={txt!r} href={href!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_favorite_not_found")
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行してサイト構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  URL: {page.url}")


# ──────────────────────────────────────────────────────────
# Step 3: 日付選択 + 検索（最速実行）
# ──────────────────────────────────────────────────────────
async def step_select_date_and_search(page):
    """
    日付プルダウンで対象日を選択し検索ボタンを押す。
    時報待ち後に呼ばれるため最速で実行する。
    """
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_TEXTS[0]}")

    # ── アプローチ①: 1つのSELECTで年月日が一体 ──────────
    date_selected = False
    for sel_elem in await page.query_selector_all("select"):
        for opt in await sel_elem.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_TEXTS)
                    or v in TARGET_DATE_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                if v:
                    await sel_elem.select_option(value=v)
                else:
                    await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択: SELECT name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── アプローチ②: 年・月・日が分割SELECTの場合 ────────
    if not date_selected:
        print("  [試行] 年/月/日分割SELECTの可能性あり...")
        year_patterns  = {"令和08", "令和8", "R08", "R8", "2026", "08"}
        month_patterns = {"6", "06", "6月", "06月", "６月"}
        day_patterns   = {"19", "19日", "１９"}

        selects = await page.query_selector_all("select")
        year_done = month_done = day_done = False

        for sel_elem in selects:
            opts = await sel_elem.query_selector_all("option")
            opt_data = [(await o.get_attribute("value") or "", (await o.inner_text()).strip())
                        for o in opts]
            texts = {t for _, t in opt_data}
            values = {v for v, _ in opt_data}

            if not year_done and (year_patterns & (texts | values)):
                for v, t in opt_data:
                    if t in year_patterns or v in year_patterns:
                        await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=t)
                        print(f"  [OK] 年選択: {t!r}")
                        year_done = True
                        break

            elif not month_done and (month_patterns & (texts | values)):
                for v, t in opt_data:
                    if t in month_patterns or v in month_patterns:
                        await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=t)
                        print(f"  [OK] 月選択: {t!r}")
                        month_done = True
                        date_selected = True
                        break

            elif not day_done and (day_patterns & (texts | values)):
                for v, t in opt_data:
                    if t in day_patterns or v in day_patterns:
                        await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=t)
                        print(f"  [OK] 日選択: {t!r}")
                        day_done = True
                        break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_TEXTS[0]!r} がプルダウンに見つかりません。\n"
            "analyze_site.py を実行して analysis_output/03_favorite.html を確認してください。"
        )

    # ── 検索ボタン ──────────────────────────────────────
    searched = False
    for sel in [
        'input[value="検索"]',
        'input[value*="検索"]',
        'button:text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=3_000, state="visible")
            if elem:
                val = await elem.get_attribute("value") or ""
                print(f"  [OK] 検索ボタン: {sel} value={val!r}")
                await elem.click()
                searched = True
                break
        except Exception:
            pass

    if not searched:
        await save_ss(page, "ERROR_search_button_not_found")
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  URL: {page.url}")


# ──────────────────────────────────────────────────────────
# Step 4: D面 16:00〜18:00 セルをクリック
# ──────────────────────────────────────────────────────────
async def step_select_slot(page):
    """
    検索結果テーブルから D面 × 16:00〜18:00 の交差セルをクリックする。

    探索順:
      ① ヘッダー行で「16:00」列インデックスを特定 → D面行のそのセルをクリック
      ② D面行を先に見つけ → 行内で「16:00」テキストを含むセルをクリック
      ③ onclick/href にD面+16時の情報が含まれるリンクをクリック
    """
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    clicked = False
    tables  = await page.query_selector_all("table")

    # ── アプローチ①: ヘッダーで列インデックスを特定 ──────
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # 最初の数行でヘッダー（16:00〜18:00）列を探す
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_idx = ci
                    print(f"  [INFO] 「{TARGET_TIME_START}〜{TARGET_TIME_END}」列インデックス={ci}")
                    break
                # 開始時刻のみのヘッダーの場合
                elif txt == TARGET_TIME_START or txt.startswith(TARGET_TIME_START):
                    time_col_idx = ci
                    print(f"  [INFO] 「{TARGET_TIME_START}」列インデックス={ci}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面行を探してそのインデックスのセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_texts = [(await c.inner_text()).strip() for c in cells]
            if TARGET_FACILITY in row_texts:
                print(f"  [INFO] D面行発見: {row_texts[:6]}")
                if time_col_idx < len(cells):
                    target_cell = cells[time_col_idx]
                    tc_txt = (await target_cell.inner_text()).strip()
                    tc_cls = await target_cell.get_attribute("class")   or ""
                    tc_oc  = await target_cell.get_attribute("onclick") or ""
                    print(f"  [FOUND①] D面×列{time_col_idx}: text={tc_txt!r} class={tc_cls!r}")
                    await target_cell.click()
                    clicked = True
                break
        if clicked:
            break

    # ── アプローチ②: D面行内で時刻テキストを探す ─────────
    if not clicked:
        print("  [試行②] D面行内で時刻テキストを探す...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                row_texts = [(await c.inner_text()).strip() for c in cells]
                if TARGET_FACILITY in row_texts:
                    print(f"  [INFO] D面行: {row_texts[:8]}")
                    for ci, cell in enumerate(cells):
                        txt     = row_texts[ci]
                        cls     = await cell.get_attribute("class")   or ""
                        onclick = await cell.get_attribute("onclick") or ""
                        # 赤丸（○）または予約可能なセルを探す
                        if (TARGET_TIME_START in txt
                                or TARGET_TIME_START in onclick
                                or "○" in txt
                                or "赤" in cls.lower()
                                or "available" in cls.lower()
                                or "yoyaku" in cls.lower()
                                or "reserve" in cls.lower()):
                            print(f"  [FOUND②] D面×{ci}: text={txt!r} class={cls!r}")
                            await cell.click()
                            clicked = True
                            break
                    break
            if clicked:
                break

    # ── アプローチ③: onclick/href でD面+16時 ─────────────
    if not clicked:
        print("  [試行③] onclick/hrefからD面16:00を探す...")
        all_elems = await page.query_selector_all("[onclick], a[href]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href")    or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if (("D面" in combined or "d面" in combined.lower())
                    and ("16" in combined or TARGET_TIME_START in combined)):
                print(f"  [FOUND③] onclick={onclick!r} href={href!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"「{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}」のセルが見つかりません。\n"
            "screenshots/04_search_results.png を確認してセレクターを修正してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  URL: {page.url}")


# ──────────────────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ──────────────────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①（料金確認画面へ）クリック...")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'button:text("確定")',
        'button:text("確認")',
        'a:text("確定")',
        'a:text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキストで全要素を検索
        elems = await page.query_selector_all(
            "input[type=submit], input[type=button], button, a"
        )
        for elem in elems:
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = await elem.get_attribute("value") or ""
            if any(k in txt for k in ["確定", "確認", "次へ", "進む"]):
                print(f"  [OK] 確定①（フォールバック）: text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_confirm1_not_found")
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  URL: {page.url}")


# ──────────────────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# ──────────────────────────────────────────────────────────
async def step_confirm2(page):
    """
    Tampermonkey で window.confirm は無効化済みのためダイアログは発火しない前提。
    万一発火した場合はPlaywright側で自動承認する。
    """
    print("\n[Step 6] 確定②（最終確定）クリック...")

    # 保険: dialogイベントが来たら自動承認
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="最終確定"]',
        'input[value*="確定"]',
        'button:text("予約確定")',
        'button:text("確定")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        elems = await page.query_selector_all(
            "input[type=submit], input[type=button], button, a"
        )
        for elem in elems:
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = await elem.get_attribute("value") or ""
            if any(k in txt for k in ["確定", "予約"]):
                print(f"  [OK] 確定②（フォールバック）: text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_confirm2_not_found")
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  URL: {page.url}")

    # 完了確認
    body_text = await page.inner_text("body")
    keywords = ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました", "受け付けました"]
    if any(w in body_text for w in keywords):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが未確認。screenshots/07_final_result.png を確認してください。")
    print(f"  本文（先頭300字）:\n  {body_text[:300]}")


# ──────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日 : {TARGET_DATE_TEXTS[0]}")
    print(f"施設   : {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード : {'即時実行' if not opts['wait_for_open'] else f'時報待ち({OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d})'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

    # ── 時報待ち ────────────────────────────────────────
    if opts["wait_for_open"]:
        await wait_until_open()

    # ── ブラウザ起動 ────────────────────────────────────
    async with async_playwright() as p:
        launch_opts: dict = {
            "headless": opts["headless"],
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
            "slow_mo": 0,        # 本番は0ms（最速）
        }
        if CHROMIUM_PATH:
            launch_opts["executable_path"] = CHROMIUM_PATH

        browser = await p.chromium.launch(**launch_opts)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,
        )
        page = await ctx.new_page()

        try:
            await step_login(page)
            await step_favorite(page)

            # ── ここで時報待ちを再確認（ログイン処理分のバッファ）──
            # ログイン〜お気に入りクリックまでに時間がかかった場合の補正
            if opts["wait_for_open"]:
                now    = datetime.datetime.now()
                target = now.replace(
                    hour=OPEN_HOUR, minute=OPEN_MINUTE,
                    second=OPEN_SECOND, microsecond=0,
                )
                diff = (target - now).total_seconds()
                if diff > 0:
                    print(f"  [調整待ち] あと {diff:.3f}秒...")
                    await asyncio.sleep(diff)

            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)

            print("\n" + "=" * 60)
            print("✅ すべてのステップ完了！")
            print("=" * 60)

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー: {e}")
            raise

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
