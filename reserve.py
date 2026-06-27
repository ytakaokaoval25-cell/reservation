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
import re
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────
# 設定値（本番切り替え時はここを変更）
# ──────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 練習: 令和08年06月19日 / 本番: 令和08年07月XX日 に書き換え
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_VALUE  = "20260619"
TARGET_DATE_ALT_VALUES = ["20260619", "2026-06-19", "2026/06/19", "260619", "0619"]
TARGET_DATE_ALT_TEXTS  = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19", "06/19", "06月19日",
]

# 予約対象
TARGET_FACILITY  = "D面"
TARGET_TIME_FROM = "16:00"
TARGET_TIME_TO   = "18:00"

# 時報設定（本番: 朝5:00ちょうど）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

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
        "wait_for_open": "--now"     not in args,
    }


async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位で待機するループ"""
    print("[時報待ち] 朝5:00:00.000 まで待機します...")
    while True:
        now    = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0,
        )
        diff = (target - now).total_seconds()

        if diff <= 0:
            print(f"[時報] 開始: {now.strftime('%H:%M:%S.%f')}")
            return
        elif diff > 300:
            print(f"[時報待ち] あと {diff:.0f}秒 ({diff/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff > 10:
            await asyncio.sleep(1)
        elif diff > 0.1:
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.001)


async def ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    await page.screenshot(path=f"{SS_DIR}/{name}.png", full_page=True)
    print(f"  [SS] {SS_DIR}/{name}.png")


# ───────────────────────── ヘルパー ──────────────────────────

async def try_fill(page, selectors: list, value: str, label: str,
                   timeout: int = ELEM_TIMEOUT) -> bool:
    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                await el.fill(value)
                print(f"  [OK] {label} 入力: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: 入力フィールドが見つかりません")
    return False


async def try_click(page, selectors: list, label: str,
                    timeout: int = ELEM_TIMEOUT) -> bool:
    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                await el.click()
                print(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: 要素が見つかりません")
    return False


# ─────────────────────────── Steps ───────────────────────────

async def step_login(page):
    """Step1: ログイン"""
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "01_login")
    print(f"  URL: {page.url}")

    # 利用者番号 — mnet系で使われる可能性の高い順
    await try_fill(page, [
        'input[name="userno"]',
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userno', '#userid', '#user_id',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")

    await try_fill(page, [
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[type="password"]',
    ], PASSWORD, "パスワード")

    await try_click(page, [
        'input[value="ログイン"]',
        'input[value="LOGIN"]',
        'input[value="login"]',
        'input[value="ログイン "]',      # 末尾スペースあり版
        'button:has-text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "02_after_login")
    print(f"  URL: {page.url}")


async def step_favorite(page):
    """Step2: お気に入りリンクをクリックして絞り込み画面へ"""
    print("\n[Step 2] お気に入りをクリック...")

    # まずすべてのリンク・ボタンを走査してデバッグ出力
    all_elems = await page.query_selector_all("a, button, input[type=button], input[type=submit]")
    for el in all_elems:
        try:
            txt = (await el.inner_text()).strip()
        except Exception:
            txt = ""
        val  = await el.get_attribute("value")  or ""
        href = await el.get_attribute("href")   or ""
        onclick = await el.get_attribute("onclick") or ""
        if txt or val:
            print(f"  ELEM text={txt!r} val={val!r} href={href!r} onclick={onclick!r}")

    clicked = False
    # テキストで直接探す
    for el in all_elems:
        try:
            txt = (await el.inner_text()).strip()
        except Exception:
            txt = ""
        val = await el.get_attribute("value") or ""
        if "お気に入り" in txt or "お気に入り" in val:
            await el.click()
            print(f"  [OK] お気に入りクリック: text={txt!r} val={val!r}")
            clicked = True
            break

    if not clicked:
        # セレクター候補でも試す
        clicked = await try_click(page, [
            'a:has-text("お気に入り")',
            'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
            '[onclick*="okiniri"]',
            '[onclick*="okini"]',
            '[href*="okiniri"]',
            '[href*="okini"]',
            '[href*="favorite"]',
            '[class*="favorite"]',
            '[id*="favorite"]',
        ], "お気に入りリンク", timeout=5000)

    if not clicked:
        await ss(page, "ERROR_no_favorite")
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            f"screenshots/02_after_login.png を確認してください。\n"
            "ページ上の実際のリンクテキストを確認し、このスクリプトのselectors を修正してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "03_favorite_filter")
    print(f"  URL: {page.url}")


async def step_select_date_and_search(page):
    """Step3: 日付プルダウンで TARGET_DATE を選択して検索（最速実行）"""
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    # ── まずすべてのSELECTとOPTIONをデバッグ出力 ──
    selects = await page.query_selector_all("select")
    print(f"  SELECTタグ数: {len(selects)}")
    for sel_el in selects:
        name = await sel_el.get_attribute("name") or ""
        id_  = await sel_el.get_attribute("id")   or ""
        opts = await sel_el.query_selector_all("option")
        print(f"  SELECT name={name!r} id={id_!r} ({len(opts)} options)")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            print(f"    OPTION value={v!r} text={txt!r}")

    # ── ① 単一プルダウンに日付が入っているパターン ──
    date_selected = False
    for sel_el in selects:
        opts = await sel_el.query_selector_all("option")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_el.get_attribute("name") or ""
                if v:
                    await sel_el.select_option(value=v)
                else:
                    await sel_el.select_option(label=txt)
                print(f"  [OK] 日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── ② 年/月/日が別々のSELECTに分かれているパターン ──
    if not date_selected:
        print("  [試行] 年・月・日 分割SELECTを探します...")
        year_hits  = ["令和08", "令和8", "08", "2026", "R08", "R8", "８"]
        month_hits = ["06", "6", "６", "06月", "6月", "６月"]
        day_hits   = ["19", "１９", "19日", "１９日"]

        def _match(txt, v, patterns):
            return any(p == txt or p == v or txt.startswith(p) for p in patterns)

        for sel_el in selects:
            opts = await sel_el.query_selector_all("option")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if _match(txt, v, year_hits):
                    await sel_el.select_option(value=v or txt)
                    print(f"  [OK] 年選択: {txt!r} (value={v!r})")
                    break

        for sel_el in selects:
            opts = await sel_el.query_selector_all("option")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if _match(txt, v, month_hits):
                    await sel_el.select_option(value=v or txt)
                    print(f"  [OK] 月選択: {txt!r} (value={v!r})")
                    date_selected = True
                    break

        for sel_el in selects:
            opts = await sel_el.query_selector_all("option")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if _match(txt, v, day_hits):
                    await sel_el.select_option(value=v or txt)
                    print(f"  [OK] 日選択: {txt!r} (value={v!r})")
                    break

    if not date_selected:
        await ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。\n"
            "screenshots/03_favorite_filter.png と上記の SELECT/OPTION 出力を確認し、\n"
            "TARGET_DATE_ALT_VALUES / TARGET_DATE_ALT_TEXTS を修正してください。"
        )

    # 検索ボタン
    await try_click(page, [
        'input[value="検索"]',
        'input[value="検　索"]',
        'input[value="検 索"]',
        'button:has-text("検索")',
        'a:has-text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "04_search_results")
    print(f"  URL: {page.url}")


async def step_select_slot(page):
    """Step4: D面 16:00〜18:00 の赤丸セルをクリック"""
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_FROM}〜{TARGET_TIME_TO} セルを選択...")

    # ── デバッグ: テーブル全体を出力 ──
    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")
    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                cls = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                a_el = await cell.query_selector("a")
                href = (await a_el.get_attribute("href") or "") if a_el else ""
                if txt:
                    row_info.append(
                        f"[{ci}]{txt!r}(cls={cls!r} onclick={onclick!r} href={href!r})"
                    )
            if row_info:
                print(f"  T{ti}R{ri}: {' | '.join(row_info)}")

    clicked = False

    # ── アプローチ①: ヘッダーから列インデックスを特定 → D面行の当該セルをクリック ──
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行（最初の3行）で「16:00〜18:00」または「16:00」列を探す
        for row in rows[:4]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                # 様々な表記に対応
                normalized = txt.replace("〜", "～").replace(" ", "").replace("\n", "")
                if (TARGET_TIME_FROM in normalized and TARGET_TIME_TO in normalized) or \
                   normalized == TARGET_TIME_FROM or \
                   f"{TARGET_TIME_FROM}～{TARGET_TIME_TO}" in normalized:
                    time_col_idx = ci
                    print(f"  [INFO] 時間列インデックス={ci} (text={txt!r})")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行を探して、time_col_idx の列のセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            is_d_row = False
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_FACILITY in txt and ci <= 2:  # 行ヘッダーはたいてい左端
                    is_d_row = True
                    break

            if is_d_row and time_col_idx < len(cells):
                target_cell = cells[time_col_idx]
                tc_txt = (await target_cell.inner_text()).strip()
                tc_cls = await target_cell.get_attribute("class") or ""
                tc_onclick = await target_cell.get_attribute("onclick") or ""

                # アンカーが中にある場合はアンカーをクリック
                a_el = await target_cell.query_selector("a")
                if a_el:
                    a_href = await a_el.get_attribute("href") or ""
                    print(f"  [FOUND①] D面×16:00〜18:00 アンカー href={a_href!r}")
                    await a_el.click()
                else:
                    print(f"  [FOUND①] D面×16:00〜18:00 セル text={tc_txt!r} cls={tc_cls!r}")
                    await target_cell.click()
                clicked = True
                break
        if clicked:
            break

    # ── アプローチ②: D面の行でテキストに「16」を含む、かつ赤丸クラスのセルをクリック ──
    if not clicked:
        print("  [試行②] テキスト/クラスベースで赤丸セルを探します...")
        red_classes = ["maru", "akamaru", "red", "available", "yoyaku", "circle", "○"]
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                cell_texts = [
                    (await c.inner_text()).strip() for c in cells
                ]
                # D面の行かチェック
                if not any(TARGET_FACILITY in t for t in cell_texts[:3]):
                    continue

                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    cls = (await cell.get_attribute("class") or "").lower()
                    # 赤丸 = 16:00 + (red系クラス or ○テキスト)
                    if "16" in txt and (
                        any(rc in cls for rc in red_classes) or "○" in txt
                    ):
                        print(f"  [FOUND②] text={txt!r} cls={cls!r}")
                        a_el = await cell.query_selector("a")
                        await (a_el or cell).click()
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick / href の文字列からD面+時間コードを探す ──
    if not clicked:
        print("  [試行③] onclick/href からD面16:00を探します...")
        all_els = await page.query_selector_all("td a, td[onclick], a[href]")
        for el in all_els:
            onclick = await el.get_attribute("onclick") or ""
            href    = await el.get_attribute("href")    or ""
            txt     = (await el.inner_text()).strip()
            combined = onclick + href + txt

            # D面を示すコード + 16:00 付近の数値
            has_d    = "D面" in combined or re.search(r'[Dd]men|d_men|dmen|[Dd]side', combined)
            has_time = "16" in combined or "1600" in combined
            if has_d and has_time:
                print(f"  [FOUND③] onclick={onclick!r} href={href!r} text={txt!r}")
                await el.click()
                clicked = True
                break

    # ── アプローチ④: 全セルのテキストを「○」「◎」で探してD面行に絞る ──
    if not clicked:
        print("  [試行④] ○記号セル全走査...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                cell_txts = [(await c.inner_text()).strip() for c in cells]
                if not any(TARGET_FACILITY in t for t in cell_txts[:3]):
                    continue
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if "○" in txt or "◎" in txt or "●" in txt:
                        a_el = await cell.query_selector("a")
                        print(f"  [FOUND④] col={ci} text={txt!r}")
                        await (a_el or cell).click()
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    if not clicked:
        await ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_FROM}〜{TARGET_TIME_TO} セルが見つかりません。\n"
            "screenshots/04_search_results.png と上記テーブルダンプを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "05_slot_selected")
    print(f"  URL: {page.url}")


async def step_confirm1(page):
    """Step5: 確定① — 料金確認画面へ進む"""
    print("\n[Step 5] 確定①クリック...")

    # デバッグ: ページ上の全ボタン・リンク
    els = await page.query_selector_all("input[type=submit], input[type=button], button, a")
    for el in els:
        try:
            txt = (await el.inner_text()).strip()
        except Exception:
            txt = ""
        val  = await el.get_attribute("value")  or ""
        href = await el.get_attribute("href")   or ""
        if txt or val:
            print(f"  BTN/LINK text={txt!r} val={val!r} href={href!r}")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確　定"]',
        'input[value="予約確認"]',
        'input[value="次へ"]',
        'input[value="次 へ"]',
        'button:has-text("確定")',
        'button:has-text("次へ")',
        'a:has-text("確定")',
        'a:has-text("次へ")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not clicked:
        await ss(page, "ERROR_confirm1")
        raise RuntimeError("確定①ボタンが見つかりません。screenshots/05_slot_selected.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "06_confirm1")
    print(f"  URL: {page.url}")


async def step_confirm2(page):
    """Step6: 確定② — 最終確定
    Tampermonkeyで window.confirm が無効化済みの前提。
    念のため dialog イベントは自動承認しておく。
    """
    print("\n[Step 6] 確定②クリック...")

    # ダイアログ自動承認（Tampermonkey無効化済みでも念のため）
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    # デバッグ: ページ上の全ボタン・リンク
    els = await page.query_selector_all("input[type=submit], input[type=button], button, a")
    for el in els:
        try:
            txt = (await el.inner_text()).strip()
        except Exception:
            txt = ""
        val  = await el.get_attribute("value")  or ""
        href = await el.get_attribute("href")   or ""
        if txt or val:
            print(f"  BTN/LINK text={txt!r} val={val!r} href={href!r}")

    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="確　定"]',
        'input[value="最終確定"]',
        'input[value="予約する"]',
        'button:has-text("予約確定")',
        'button:has-text("確定")',
        'button:has-text("予約する")',
        'a:has-text("予約確定")',
        'a:has-text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not clicked:
        await ss(page, "ERROR_confirm2")
        raise RuntimeError("確定②ボタンが見つかりません。screenshots/06_confirm1.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "07_final_result")
    print(f"  URL: {page.url}")

    # 完了確認
    body = await page.inner_text("body")
    keywords = ["予約完了", "受付完了", "受付番号", "予約番号", "予約を受け付けました", "完了しました"]
    if any(k in body for k in keywords):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了キーワードが見つかりません。screenshots/07_final_result.png を確認してください。")
    print(f"  ページ本文（先頭300字）: {body[:300]}")


# ───────────────────────── main ─────────────────────────────

async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象: {TARGET_DATE_WAREKI}  {TARGET_FACILITY} {TARGET_TIME_FROM}〜{TARGET_TIME_TO}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00)'}"
          f" / {'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

    if opts["wait_for_open"]:
        await wait_until_open()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await ctx.new_page()

        try:
            await step_login(page)
            await step_favorite(page)
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)
            print("\n✅ すべてのステップが完了しました。")
        except Exception as e:
            await ss(page, "ERROR_final")
            print(f"\n❌ エラー: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
