"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備
  pip install playwright
  playwright install chromium

■ フロー（本番）
  1. スクリプト起動（4:50頃）
  2. ログイン
  3. お気に入りページへ移動
  4. ★ 朝5:00:00.000 ぴったりに検索開始  ← ここで時報待ち
  5. D面 16:00〜18:00 をクリック
  6. 確定① → 確定②
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

# ---- テスト用予約対象日（令和08年06月19日）----
# 本番（07月分）に変更する場合はここを書き換え
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_VALUE  = "20260619"          # value が数字8桁の場合
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
    "06/19", "619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19", "06/19",
    # 曜日付き
    "令和08年06月19日（木）", "令和08年06月19日(木)",
    "令和8年6月19日（木）",
]

# ---- 予約コート＆時間 ----
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# ---- 時報待ち設定 ----
# 本番: 2026年5月19日 05:00:00 に07月分が公開される
# スクリプトをそれより前（例: 04:50）に起動すること
OPEN_YEAR   = 2026
OPEN_MONTH  = 5
OPEN_DAY    = 19
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# ---- タイムアウト（ms）----
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# ---- スクリーンショット保存先 ----
SS_DIR = "screenshots"
# ──────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


def _make_open_target() -> datetime.datetime:
    """本番時報の目標時刻を生成（当日 or 指定日）"""
    now = datetime.datetime.now()
    # 当日が OPEN_YEAR/OPEN_MONTH/OPEN_DAY と一致する場合はその日の5時
    if now.date() == datetime.date(OPEN_YEAR, OPEN_MONTH, OPEN_DAY):
        return now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0
        )
    # それ以外（テスト実行などで日付が違う場合）は今日の5時
    return now.replace(
        hour=OPEN_HOUR, minute=OPEN_MINUTE,
        second=OPEN_SECOND, microsecond=0
    )


async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位で待機"""
    target = _make_open_target()
    print(f"[時報待ち] 目標時刻: {target.strftime('%Y-%m-%d %H:%M:%S')}")

    while True:
        now  = datetime.datetime.now()
        diff = (target - now).total_seconds()

        if diff <= 0:
            print(f"[時報] ★ 開始: {now.strftime('%H:%M:%S.%f')[:-3]}")
            return

        if diff > 300:
            print(f"[時報待ち] あと {int(diff)}秒 ({diff/60:.1f}分)…")
            await asyncio.sleep(30)
        elif diff > 10:
            await asyncio.sleep(1)
        elif diff > 0.5:
            await asyncio.sleep(0.05)
        elif diff > 0.05:
            await asyncio.sleep(0.005)
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


# ────────────────────────────────────────────────────────────────
# Step 1: ログイン
# ────────────────────────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号（camelCase / lowercase / id= など複数候補）
    await try_fill(page, [
        'input[name="userId"]',      # まんまるよやく2 でよく使われる
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userId',
        '#userid',
        'input[type="text"]:first-of-type',
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
        'a:text("ログイン")',
        'input[name="submit"]',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


# ────────────────────────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面
# ────────────────────────────────────────────────────────────────
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

    # フォールバック: テキストスキャン
    if not clicked:
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（テキストスキャン）: {txt!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行してセレクターを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ────────────────────────────────────────────────────────────────
# Step 3: 日付選択 + 検索（5:00ちょうど後に呼ばれる）
# ────────────────────────────────────────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False

    # ── パターン①: 単一 SELECT に全日付が入っている ──────────────
    for sel_elem in await page.query_selector_all("select"):
        for opt in await sel_elem.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                print(f"  [OK] 単一SELECT 日付選択: name={name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── パターン②: 年・月・日が別 SELECT ──────────────────────────
    if not date_selected:
        print("  [試行] 年月日が分割SELECTの可能性あり...")
        year_pats  = ["令和08", "令和8", "令和０８", "08", "8", "2026", "R08", "R8", "R 8"]
        month_pats = ["06", "6", "６", "06月", "6月", "６月"]
        day_pats   = ["19", "１９", "19日", "１９日"]

        selects = await page.query_selector_all("select")

        async def try_select(patterns):
            for sel_elem in selects:
                for opt in await sel_elem.query_selector_all("option"):
                    txt = (await opt.inner_text()).strip()
                    v   = await opt.get_attribute("value") or ""
                    if txt in patterns or v in patterns:
                        await sel_elem.select_option(value=v or txt)
                        print(f"  [OK] 分割SELECT 選択: text={txt!r} value={v!r}")
                        return True
            return False

        yr = await try_select(year_pats)
        mo = await try_select(month_pats)
        dy = await try_select(day_pats)
        if mo or dy:
            date_selected = True

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "screenshots/ または analyze_site.py の出力を確認してください。"
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


# ────────────────────────────────────────────────────────────────
# Step 4: D面 16:00〜18:00（赤丸）セルをクリック
# ────────────────────────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} をクリック...")

    clicked = False
    tables  = await page.query_selector_all("table")

    # ── アプローチ①: 行ヘッダーが施設名、列ヘッダーが時間（横型テーブル）──
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行で「16:00〜18:00」列インデックスを取得
        for header_row in rows[:3]:
            cells = await header_row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_idx = ci
                    print(f"  [INFO] 列インデックス {ci}: {txt!r}")
                    break
                # 「16:00」だけでも
                if TARGET_TIME_START in txt and time_col_idx < 0:
                    time_col_idx = ci
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面 の行を探してそのインデックスのセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_texts = [(await c.inner_text()).strip() for c in cells]
            if any(TARGET_FACILITY in t for t in row_texts):
                print(f"  [INFO] D面行発見: {row_texts}")
                if time_col_idx < len(cells):
                    target_cell = cells[time_col_idx]
                    tc_txt = (await target_cell.inner_text()).strip()
                    tc_cls = await target_cell.get_attribute("class") or ""
                    print(f"  [FOUND] D面×{TARGET_TIME_START}: text={tc_txt!r} class={tc_cls!r}")
                    # セル内のリンク/画像を優先してクリック
                    inner_link = await target_cell.query_selector("a, input[type=image], input[type=submit]")
                    if inner_link:
                        await inner_link.click()
                    else:
                        await target_cell.click()
                    clicked = True
                break
        if clicked:
            break

    # ── アプローチ②: 列ヘッダーが施設名、行ヘッダーが時間（縦型テーブル）──
    if not clicked:
        print("  [試行] 縦型テーブル（列=施設名・行=時間）を探す...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            d_col_idx = -1

            # ヘッダー行で D面 列インデックスを取得
            for header_row in rows[:3]:
                cells = await header_row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    if TARGET_FACILITY in (await cell.inner_text()).strip():
                        d_col_idx = ci
                        print(f"  [INFO] D面 列インデックス={ci}")
                        break
                if d_col_idx >= 0:
                    break

            if d_col_idx < 0:
                continue

            for row in rows:
                cells = await row.query_selector_all("td, th")
                if not cells:
                    continue
                first_txt = (await cells[0].inner_text()).strip()
                if TARGET_TIME_START in first_txt:
                    if d_col_idx < len(cells):
                        target_cell = cells[d_col_idx]
                        tc_txt = (await target_cell.inner_text()).strip()
                        print(f"  [FOUND] {TARGET_TIME_START}行×D面列: text={tc_txt!r}")
                        inner_link = await target_cell.query_selector("a, input[type=image], input[type=submit]")
                        if inner_link:
                            await inner_link.click()
                        else:
                            await target_cell.click()
                        clicked = True
                    break
            if clicked:
                break

    # ── アプローチ③: onclick/href に D面 + 16 の情報が含まれる要素 ──
    if not clicked:
        print("  [試行] onclick/href ベース検索...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if ("D面" in combined or "D " in combined) and "16" in combined:
                print(f"  [FOUND] onclick={onclick!r} href={href!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。"
            "screenshots/04_search_results.png を確認し、"
            "テーブル構造に合わせてセレクターを調整してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ────────────────────────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ────────────────────────────────────────────────────────────────
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
        await save_ss(page, "ERROR_confirm1")
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


# ────────────────────────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# window.confirm は Tampermonkey で無効化済みを前提とするが、
# 万一 dialog が来た場合は自動 accept する
# ────────────────────────────────────────────────────────────────
async def step_confirm2(page):
    print("\n[Step 6] 確定②クリック...")

    # Playwright 側でも dialog を自動承認（二重保険）
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

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
        await save_ss(page, "ERROR_confirm2")
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    body_text = await page.inner_text("body")
    if any(w in body_text for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが未確認です。07_final_result.png を確認してください。")
    print(f"  本文（先頭300字）: {body_text[:300]}")


# ────────────────────────────────────────────────────────────────
# メイン
# ────────────────────────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  "
          f"施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
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
        )
        page = await context.new_page()

        try:
            # ① ログイン（5時前に実施済みにする）
            await step_login(page)

            # ② お気に入りページへ移動（5時前に実施済みにする）
            await step_favorite(page)

            # ③ ★ 5:00:00.000 ちょうどまで待機 ★
            #    ここで待機することで、ログイン・ナビはすでに完了しており
            #    5時ちょうどに最速で検索を開始できる
            if opts["wait_for_open"]:
                await wait_until_open()
            else:
                print("\n[時報待ち] スキップ（--now モード）")

            # ④ 日付選択 → 検索
            await step_select_date_and_search(page)

            # ⑤ コマ選択
            await step_select_slot(page)

            # ⑥ 確定①
            await step_confirm1(page)

            # ⑦ 確定②
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
