"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00

■ 使い方
  python reserve.py              # 時報待ちモード（本番: 朝5:00ぴったりに検索実行）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 推奨起動タイミング
  朝 4:57〜4:59 に起動してください。
  スクリプトはログイン→お気に入り→日付選択まで事前に済ませ、
  5:00:00.000 ぴったりに「検索」ボタンを押します。

■ 準備
  pip install playwright
  playwright install chromium

■ 本番（7月予約）への切り替え
  TARGET_DATE_WAREKI / TARGET_DATE_VALUE を
  「令和08年07月19日」/ 「20260719」に変更してください。
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────
# 設定値（本番時はここを変更）
# ──────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# ---- 練習: 令和08年06月19日 ----
# ---- 本番: 令和08年07月19日 に変更 ----
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_VALUE  = "20260619"

# 予約対象コート＆時間
TARGET_FACILITY  = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報設定（毎月19日 朝5:00:00 に開放）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# スクリーンショット保存先（空文字でスキップ）
SS_DIR = "screenshots"

# valueに使われる可能性のある形式を列挙
TARGET_DATE_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619", "060619",
]
TARGET_DATE_TEXTS = [
    "令和08年06月19日", "令和8年6月19日",
    "令和０８年０６月１９日", "令和08年6月19日",
    "2026年06月19日", "2026/06/19", "2026-06-19",
]
# ──────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


# ─── 時報待ちロジック ─────────────────────────────────────────────────────────

async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位で待機。
    ログイン・ナビゲートが完了した後に呼ぶことで、
    フライングを防ぎつつネットワーク遅延分を吸収する。
    """
    print("[時報待ち] 朝5:00:00.000 まで待機します...")
    while True:
        now = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0,
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
            break
        elif diff_sec > 300:       # 5分以上 → 30秒ごと
            m, s = divmod(int(diff_sec), 60)
            print(f"[時報待ち] あと {m}分{s}秒...")
            await asyncio.sleep(30)
        elif diff_sec > 10:        # 10秒〜5分 → 1秒ごと
            await asyncio.sleep(1)
        elif diff_sec > 0.1:       # 100ms〜10秒 → 50msごと
            await asyncio.sleep(0.05)
        else:                       # 〜100ms → 1msごと（精密待ち）
            await asyncio.sleep(0.001)


# ─── ユーティリティ ──────────────────────────────────────────────────────────

async def save_ss(page, name: str):
    if not SS_DIR:
        return
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception:
        pass


async def try_click(page, selectors: list[str], label: str,
                    timeout: int = 5000) -> bool:
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


async def try_fill(page, selectors: list[str], value: str, label: str,
                   timeout: int = 5000) -> bool:
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


# ─── 各ステップ ───────────────────────────────────────────────────────────────

async def step_login(page):
    """Step 1: ログイン"""
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
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
        'input[value="ログイン　"]',
        'button:has-text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:has-text("ログイン")',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


async def step_favorite(page):
    """Step 2: お気に入りクリック → 絞り込み画面"""
    print("\n[Step 2] お気に入りをクリック...")

    # まず通常セレクターを試す
    clicked = await try_click(page, [
        'a:has-text("お気に入り")',
        'input[value="お気に入り"]',
        'button:has-text("お気に入り")',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全探索フォールバック
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（全探索）: text={txt!r} val={val!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError("お気に入りリンクが見つかりません。analyze_site.py で解析してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


async def step_set_date(page):
    """Step 3a: 日付プルダウンで対象日を選択（検索は押さない）"""
    print(f"\n[Step 3a] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False
    selects = await page.query_selector_all("select")

    # ── アプローチA: 1つのSELECTに「令和08年06月19日」形式の日付 ──
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
                print(f"  [OK] 日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── アプローチB: 年・月・日が別々のSELECT ──
    if not date_selected:
        print("  [試行] 年/月/日 分割SELECT...")
        year_cands  = ["令和08", "令和8", "08", "2026", "R08", "R8", "令和08年"]
        month_cands = ["06", "6", "６", "06月", "6月"]
        day_cands   = ["19", "１９", "19日"]

        found_year = found_month = found_day = False
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if not found_year and any(c == txt or c == v or c in txt for c in year_cands):
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 年選択: {txt!r}")
                    found_year = True
                    break
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if not found_month and any(c == txt or c == v for c in month_cands):
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 月選択: {txt!r}")
                    found_month = True
                    break
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if not found_day and any(c == txt or c == v for c in day_cands):
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 日選択: {txt!r}")
                    found_day = True
                    break
        date_selected = found_year or found_month or found_day

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.py を実行してセレクターを確認してください。"
        )

    await save_ss(page, "03b_date_set")
    print("  [OK] 日付セット完了。検索は時報後に実行します。")


async def step_click_search(page):
    """Step 3b: 検索ボタンをクリック（時報後に呼ぶ）"""
    print(f"\n[Step 3b] 検索ボタンクリック @ {datetime.datetime.now().strftime('%H:%M:%S.%f')}")

    clicked = await try_click(page, [
        'input[value="検索"]',
        'button:has-text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:has-text("検索")',
    ], "検索ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


async def step_select_slot(page):
    """Step 4: D面 16:00〜18:00 セルをクリック"""
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    tables = await page.query_selector_all("table")
    clicked = False

    for table in tables:
        rows = await table.query_selector_all("tr")

        # ── ヘッダー行から 16:00〜18:00 の列インデックスを特定 ──
        time_col_idx = -1
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                # "16:00" と "18:00" が同じセルに含まれる（例: "16:00〜18:00"）
                # または "16:00" だけ含む列ヘッダーでも可
                hit = (TARGET_TIME_START in txt and TARGET_TIME_END in txt)
                if not hit:
                    # "16:00" のみ（区切り文字違い対応）
                    hit = (TARGET_TIME_START in txt and "18" in txt)
                if not hit:
                    # 全角対応: "１６：００〜１８：００" 等
                    hit = ("16" in txt and "18" in txt and (":" in txt or "：" in txt))
                if hit:
                    time_col_idx = ci
                    print(f"  [INFO] 時間列: col={ci} text={txt!r}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue  # このテーブルには時間ヘッダーなし

        # ── D面の行を探してそのインデックスのセルをクリック ──
        for row in rows:
            cells = await row.query_selector_all("td, th")
            d_col_idx = -1
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_FACILITY in txt or txt == TARGET_FACILITY:
                    d_col_idx = ci
                    break
            if d_col_idx < 0:
                continue

            # D面行が見つかった → 時間列のセルをクリック
            if time_col_idx < len(cells):
                target_cell = cells[time_col_idx]
                tc_txt = (await target_cell.inner_text()).strip()
                tc_cls = await target_cell.get_attribute("class") or ""
                tc_id  = await target_cell.get_attribute("id") or ""
                tc_onclick = await target_cell.get_attribute("onclick") or ""
                print(f"  [FOUND] D面×{TARGET_TIME_START} セル:"
                      f" text={tc_txt!r} class={tc_cls!r} id={tc_id!r}"
                      f" onclick={tc_onclick!r[:80]}")

                # 予約不可（×など）でないか確認
                ng_marks = ["×", "✕", "ー", "－", "−", "休", "休館", "不可"]
                if any(m in tc_txt for m in ng_marks) and "○" not in tc_txt:
                    print(f"  [WARNING] このセルは予約不可の可能性: {tc_txt!r}")
                    # それでもクリック（サーバー側でエラーが出る）
                await target_cell.click()
                clicked = True
                break

        if clicked:
            break

    # ── フォールバック: onclick/href にD面+時間情報を含む要素 ──
    if not clicked:
        print("  [試行] onclick/href からD面16:00を探す...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if (("D面" in combined or "d面" in combined.lower())
                    and "16" in combined):
                print(f"  [FOUND] onclick={onclick!r[:80]} href={href!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。"
            "screenshots/04_search_results.png を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


async def step_confirm1(page):
    """Step 5: 確定①（料金確認画面へ）"""
    print("\n[Step 5] 確定①クリック...")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="予約確認"]',
        'button:has-text("確定")',
        'button:has-text("確認")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'a:has-text("確定")',
        'a:has-text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


async def step_confirm2(page):
    """Step 6: 確定②（最終確定）
    Tampermonkey で window.confirm が無効化されている前提。
    万一ダイアログが来た場合は自動承認する。
    """
    print("\n[Step 6] 確定②クリック...")

    # window.confirm を JS で上書き（Tampermonkey 未導入環境でも動くよう保険）
    await page.evaluate("window.confirm = () => true;")

    # ダイアログイベントフォールバック
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="最終確定"]',
        'button:has-text("予約確定")',
        'button:has-text("確定")',
        'input[value*="確定"]',
        'a:has-text("確定")',
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
        print("\n⚠️   完了メッセージが見つかりません。07_final_result.png を確認してください。")
    print(f"  本文（先頭300字）: {body_text[:300]}")


# ─── メイン ──────────────────────────────────────────────────────────────────

async def main():
    opts = parse_args()

    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象: {TARGET_DATE_WAREKI}  {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00)'}"
          f" / {'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
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
        page = await context.new_page()

        try:
            # ── Phase 1: 事前準備（5:00前に完了させる） ──
            await step_login(page)
            await step_favorite(page)
            await step_set_date(page)

            # ── 時報待ち（検索直前で5:00:00.000まで待機） ──
            if opts["wait_for_open"]:
                await wait_until_open()

            # ── Phase 2: 5:00ちょうどに検索実行 ──
            await step_click_search(page)

            # ── Phase 3: セル選択・予約確定 ──
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)

            print("\n✅  すべてのステップが完了しました。")

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌  エラー: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
