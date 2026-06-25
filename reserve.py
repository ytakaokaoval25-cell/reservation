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
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日（令和08年06月19日 = 2026-06-19 で練習。本番は変更）
TARGET_DATE_WAREKI = "令和08年06月19日"   # プルダウンに表示されるテキスト
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19",
]

# 予約対象コート＆時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報待ち設定（本番）
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
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位で待機"""
    print("[時報待ち] 朝5:00:00.000 まで待機します...")
    while True:
        now = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {now.strftime('%H:%M:%S.%f')}")
            break
        elif diff_sec > 300:
            # 5分以上前: 30秒ごとにチェック
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            # 10秒～5分前: 1秒ごと
            await asyncio.sleep(1)
        elif diff_sec > 0.1:
            # 100ms～10秒前: 50msごと
            await asyncio.sleep(0.05)
        else:
            # 100ms以内: 1msごと（精密追い込み）
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    """スクリーンショット保存（デバッグ用）"""
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception as e:
        print(f"  [SS ERROR] {path}: {e}")


async def try_click(page, selectors: list, label: str, timeout: int = 5000) -> bool:
    """複数セレクターを順番に試してクリック（Playwright has-text 構文対応）"""
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
    # フォールバック: テキストマッチによる全要素検索
    print(f"  [FAIL] {label}: セレクターで発見できず")
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


async def step_login(page):
    """Step1: ログイン"""
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号（複数セレクター候補を順番に試す）
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
        raise RuntimeError("利用者番号フィールドが見つかりません。analyze_site.py を実行して確認してください。")

    # パスワード
    ok = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")
    if not ok:
        raise RuntimeError("パスワードフィールドが見つかりません。")

    # ログインボタン
    ok = await try_click(page, [
        'input[value="ログイン"]',
        'input[value*="ログイン"]',
        'button:has-text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
        'a:has-text("ログイン")',
    ], "ログインボタン")
    if not ok:
        raise RuntimeError("ログインボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if "パスワード" in body and ("誤り" in body or "違います" in body or "正しく" in body):
        raise RuntimeError(f"ログイン失敗: パスワードまたはIDが正しくありません。")


async def step_favorite(page):
    """Step2: お気に入りをクリック → 絞り込み画面"""
    print("\n[Step 2] お気に入りをクリック...")

    # Playwrightの正しい構文: :has-text()
    ok = await try_click(page, [
        'a:has-text("お気に入り")',
        'input[value="お気に入り"]',
        'input[value*="お気に入り"]',
        'button:has-text("お気に入り")',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not ok:
        # テキスト全要素フォールバック
        for tag in ["a", "button", "input"]:
            elems = await page.query_selector_all(tag)
            for elem in elems:
                try:
                    txt = await elem.inner_text() or ""
                    val = await elem.get_attribute("value") or ""
                    if "お気に入り" in txt.strip() or "お気に入り" in val:
                        await elem.click()
                        print(f"  [OK] お気に入り（フォールバック/{tag}）: text={txt.strip()!r}")
                        ok = True
                        break
                except Exception:
                    pass
            if ok:
                break

    if not ok:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。analyze_site.py を実行して"
            "ログイン後のメニュー構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


async def step_select_date_and_search(page):
    """Step3: 日付プルダウンで令和08年06月19日を選択して検索（最速）"""
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False

    # ── アプローチ①: 結合型SELECT（1つのSelectに全日付が入る場合）──
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

    # ── アプローチ②: 分割型SELECT（年/月/日が別々のSelectの場合）──
    if not date_selected:
        print("  [試行] 年月日分割SELECTパターン...")
        # 令和08年 / 06月 / 19日 をそれぞれ別のSELECTに入力
        year_keywords  = ["令和08", "令和8", "R08", "R8", "2026"]
        month_keywords = ["06月", "6月", "06", "6"]
        day_keywords   = ["19日", "19"]

        matched_year  = False
        matched_month = False
        matched_day   = False

        for sel_elem in await page.query_selector_all("select"):
            options = await sel_elem.query_selector_all("option")
            opt_texts = [(await o.get_attribute("value") or "", (await o.inner_text()).strip())
                         for o in options]

            # 年SELECTか判定（令和や年が含まれるoption群）
            if not matched_year and any(
                any(k in v or k in t for k in year_keywords) for v, t in opt_texts
            ):
                for v, t in opt_texts:
                    if any(k in t or k in v for k in year_keywords):
                        await sel_elem.select_option(value=v)
                        print(f"  [OK] 年選択: value={v!r} text={t!r}")
                        matched_year = True
                        break

            # 月SELECTか判定
            elif not matched_month and any(
                any(k == v or k == t or k in t for k in month_keywords) for v, t in opt_texts
            ):
                for v, t in opt_texts:
                    if any(k == v or k == t or k in t for k in month_keywords):
                        await sel_elem.select_option(value=v)
                        print(f"  [OK] 月選択: value={v!r} text={t!r}")
                        matched_month = True
                        break

            # 日SELECTか判定
            elif not matched_day and any(
                any(k == v or k == t or k in t for k in day_keywords) for v, t in opt_texts
            ):
                for v, t in opt_texts:
                    if any(k == v or k == t or k in t for k in day_keywords):
                        await sel_elem.select_option(value=v)
                        print(f"  [OK] 日選択: value={v!r} text={t!r}")
                        matched_day = True
                        break

        if matched_year or matched_month or matched_day:
            date_selected = True

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。\n"
            "analyze_site.py を実行して screenshots/ を確認し、\n"
            "TARGET_DATE_ALT_VALUES / TARGET_DATE_ALT_TEXTS を修正してください。"
        )

    # 検索ボタン
    ok = await try_click(page, [
        'input[value="検索"]',
        'input[value*="検索"]',
        'button:has-text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:has-text("検索")',
    ], "検索ボタン")
    if not ok:
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


async def step_select_slot(page):
    """Step4: D面 16:00〜18:00 の赤丸セルをクリック"""
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    clicked = False
    tables = await page.query_selector_all("table")

    # ── アプローチ①: ヘッダー行から列インデックスを特定し、D面行と交差セルをクリック ──
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行（上位3行）で 16:00〜18:00 の列インデックスを探す
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                # 「16:00」と「18:00」が同一セル内にある、または「16:00」だけの列
                if TARGET_TIME_START in txt:
                    time_col_idx = ci
                    print(f"  [INFO] {TARGET_TIME_START} 列インデックス={ci} テキスト={txt!r}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行を探し、time_col_idx のセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            first_cell_txt = (await cells[0].inner_text()).strip() if cells else ""
            if TARGET_FACILITY in first_cell_txt:
                print(f"  [INFO] D面行発見 (先頭セル={first_cell_txt!r}), 列{time_col_idx}をクリック")
                if time_col_idx < len(cells):
                    target_cell = cells[time_col_idx]
                    tc_txt = (await target_cell.inner_text()).strip()
                    tc_cls = await target_cell.get_attribute("class") or ""
                    tc_onclick = await target_cell.get_attribute("onclick") or ""
                    print(f"  [FOUND] セル: text={tc_txt!r} class={tc_cls!r} onclick={tc_onclick[:80]!r}")
                    # セル内にリンクがあればリンクをクリック、なければセルをクリック
                    link = await target_cell.query_selector("a")
                    if link:
                        await link.click()
                    else:
                        await target_cell.click()
                    clicked = True
                break
        if clicked:
            break

    # ── アプローチ②: 全セル走査でD面かつ16:00が同一行に存在するパターン ──
    if not clicked:
        print("  [試行] 全テーブルのD面行×16:00列を直接走査...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                row_texts = [(await c.inner_text()).strip() for c in cells]

                if TARGET_FACILITY in row_texts:
                    # D面が存在する行 — 16:00 を含むセルを探す
                    for ci, txt in enumerate(row_texts):
                        if TARGET_TIME_START in txt:
                            cell = cells[ci]
                            tc_cls = await cell.get_attribute("class") or ""
                            print(f"  [FOUND②] D面行×16:00セル ci={ci} text={txt!r} class={tc_cls!r}")
                            link = await cell.query_selector("a")
                            if link:
                                await link.click()
                            else:
                                await cell.click()
                            clicked = True
                            break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick / href にD面かつ16に関する文字列を持つ要素 ──
    if not clicked:
        print("  [試行] onclick/href でD面+16:00を検索...")
        all_elems = await page.query_selector_all("td[onclick], a[href], input[onclick]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            combined = onclick + href
            # D面 + 16時間帯が含まれるか（URLパラメータ等）
            if ("D" in combined or "d面" in combined.lower()) and "16" in combined:
                txt = (await elem.inner_text()).strip()
                print(f"  [FOUND③] onclick={onclick[:80]!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    # ── アプローチ④: 赤丸画像を含むセルを行・列で特定 ──
    if not clicked:
        print("  [試行] 画像（赤丸）を含むセルを検索...")
        # D面行の赤丸（img alt=○ など）を持つセルを探す
        # まずD面行のtrを特定
        d_row = None
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                if cells:
                    first_txt = (await cells[0].inner_text()).strip()
                    if TARGET_FACILITY in first_txt:
                        d_row = row
                        break
            if d_row:
                break

        if d_row:
            cells = await d_row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                # imgがあるか / 赤い背景か / ○印か確認
                imgs = await cell.query_selector_all("img")
                txt  = (await cell.inner_text()).strip()
                cls  = await cell.get_attribute("class") or ""
                style = await cell.get_attribute("style") or ""
                if imgs or "○" in txt or "◎" in txt or "red" in cls.lower() or "red" in style.lower():
                    for img in imgs:
                        alt = await img.get_attribute("alt") or ""
                        src = await img.get_attribute("src") or ""
                        print(f"  [INFO] img alt={alt!r} src={src!r} ci={ci}")
                    print(f"  [FOUND④] D面×ci={ci} text={txt!r} class={cls!r}")
                    link = await cell.query_selector("a")
                    if link:
                        await link.click()
                    else:
                        await cell.click()
                    clicked = True
                    break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。\n"
            "screenshots/ERROR_slot_not_found.png と analyze_site.py の出力を確認してください。"
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
        'input[value="次へ"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'button:has-text("確定")',
        'button:has-text("確認")',
        'button:has-text("次へ")',
        'a:has-text("確定")',
        'a:has-text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not ok:
        await save_ss(page, "ERROR_confirm1_not_found")
        raise RuntimeError("確定①ボタンが見つかりません。screenshots/ERROR_confirm1_not_found.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


async def step_confirm2(page):
    """Step6: 確定②（最終確定）
    Tampermonkey で window.confirm を無効化済みのため通常はダイアログ不発。
    念のため page.on("dialog") を事前登録して自動承認する。
    """
    print("\n[Step 6] 確定②クリック...")

    ok = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="確定"]',
        'input[value*="確定"]',
        'button:has-text("予約確定")',
        'button:has-text("最終確定")',
        'button:has-text("確定")',
        'a:has-text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not ok:
        await save_ss(page, "ERROR_confirm2_not_found")
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了確認
    body_text = await page.inner_text("body")
    success_keywords = ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました", "予約が完了"]
    if any(w in body_text for w in success_keywords):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。screenshots/07_final_result.png を確認してください。")
    print(f"  最終本文（先頭300字）: {body_text[:300]}")


async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00)'} / "
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
        )
        page = await context.new_page()

        # confirmダイアログを事前に自動承認登録
        # (Tampermonkeyで無効化済みでも念のため)
        page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))

        try:
            await step_login(page)
            await step_favorite(page)
            await step_select_date_and_search(page)
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
