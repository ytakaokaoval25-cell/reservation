"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 動作の流れ（最速化）
  [5:00AM より前] ログイン → お気に入り → 日付選択（検索はまだ）
  [5:00:00.000AM] 検索ボタンをクリック
  [直後]          D面 16:00〜18:00 の○セルをクリック → 確定① → 確定②

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
# 設定値（本番時はここを変更）
# ──────────────────────────────────────────────
LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"

# ★本番は TARGET_DATE_WAREKI = "令和08年07月XX日" に書き換えること
TARGET_DATE_WAREKI = "令和08年06月19日"   # プルダウン表示テキスト
TARGET_DATE_VALUE  = "20260619"           # valueが数字形式の場合

# 複数フォーマットを許容（プルダウンの実際のvalue/textに合わせて自動マッチ）
TARGET_DATE_ALT_VALUES = ["20260619", "2026-06-19", "2026/06/19", "260619"]
TARGET_DATE_ALT_TEXTS  = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19",
]

TARGET_FACILITY  = "D面"
TARGET_TIME_TEXT = "16:00"  # 列ヘッダーまたはセルに含まれる文字列

# 時報設定
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

SS_DIR = "screenshots"
# ──────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


# ────────────────────────────────────────────────────────────────
# 時報待ちロジック
# ────────────────────────────────────────────────────────────────
async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位で待機する"""
    print(f"[時報待ち] {OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d} まで待機します...")
    while True:
        now = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {now.strftime('%H:%M:%S.%f')}")
            return
        elif diff_sec > 300:
            print(f"[時報待ち] あと {int(diff_sec//60)}分{int(diff_sec%60)}秒 ...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            await asyncio.sleep(1)
        elif diff_sec > 0.5:
            await asyncio.sleep(0.2)
        elif diff_sec > 0.05:
            await asyncio.sleep(0.01)
        else:
            await asyncio.sleep(0.001)


def seconds_to_open() -> float:
    """現在から開放時刻までの秒数（負なら過ぎている）"""
    now = datetime.datetime.now()
    target = now.replace(
        hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
    )
    return (target - now).total_seconds()


# ────────────────────────────────────────────────────────────────
# ユーティリティ
# ────────────────────────────────────────────────────────────────
async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_click(page, selectors: list, label: str, timeout: int = 5000) -> bool:
    """複数セレクターを順番に試してクリック。成功したらTrueを返す"""
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
    print(f"  [FAIL] {label}: 該当セレクターなし {selectors}")
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
    print(f"  [FAIL] {label}: 該当フィールドなし")
    return False


# ────────────────────────────────────────────────────────────────
# 各ステップ
# ────────────────────────────────────────────────────────────────
async def step_login(page):
    """Step1: ログイン"""
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")
    print(f"  URL: {page.url}")

    # 利用者番号
    filled = await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid', '#loginId', '#user_id',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")
    if not filled:
        raise RuntimeError("利用者番号フィールドが見つかりません。analyze_site.py で解析してください。")

    # パスワード
    filled = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        '#passwd', '#password',
    ], PASSWORD, "パスワード")
    if not filled:
        raise RuntimeError("パスワードフィールドが見つかりません。")

    # ログインボタン
    clicked = await try_click(page, [
        'input[value="ログイン"]',
        'input[value="LOGIN"]',
        'input[value="login"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
        'a:text("ログイン")',
    ], "ログインボタン")
    if not clicked:
        raise RuntimeError("ログインボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if any(w in body for w in ["ログインに失敗", "パスワードが違", "該当しません", "エラー"]):
        raise RuntimeError(f"ログイン失敗の可能性があります。ページ内容: {body[:200]}")


async def step_favorite(page):
    """Step2: お気に入りをクリックして絞り込み画面へ"""
    print("\n[Step 2] お気に入りをクリック...")

    # まずテキストで探す
    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[href*="favorite"]',
        '[href*="okiniri"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入り", timeout=ELEM_TIMEOUT)

    # テキスト部分一致フォールバック
    if not clicked:
        for elem in await page.query_selector_all("a, input[type=button], input[type=submit], button"):
            try:
                txt = (await elem.inner_text()).strip()
                val = (await elem.get_attribute("value") or "").strip()
                if "お気に入り" in txt or "お気に入り" in val:
                    await elem.click()
                    print(f"  [OK] お気に入り（フォールバック）: text={txt!r} val={val!r}")
                    clicked = True
                    break
            except Exception:
                pass

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。\n"
            "analyze_site.py を実行して02_after_login.html を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


async def step_select_date(page):
    """Step3: 日付プルダウンで対象日を選択（検索はまだ押さない）"""
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False

    # ── パターンA: 日付が1つのSELECTに集約されている ──
    for sel_elem in await page.query_selector_all("select"):
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = (await opt.get_attribute("value") or "").strip()
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                name = await sel_elem.get_attribute("name") or "(no name)"
                # value が空でないなら value で選択、なければ label で選択
                if v:
                    await sel_elem.select_option(value=v)
                else:
                    await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択(単一): name={name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── パターンB: 年・月・日が分割SELECTの場合 ──
    if not date_selected:
        print("  [試行] 年月日分割SELECTを検索...")
        year_patterns  = ["令和08", "令和8", "08", "8", "2026", "R08", "R8"]
        month_patterns = ["06", "6", "６", "06月", "6月"]
        day_patterns   = ["19", "１９", "19日"]

        selects = await page.query_selector_all("select")
        for i, sel_elem in enumerate(selects):
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = (await opt.get_attribute("value") or "").strip()
                if any(p == txt.strip("年号") or p == v for p in year_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年SELECT[{i}]: {txt!r}")
                    break
        for i, sel_elem in enumerate(selects):
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = (await opt.get_attribute("value") or "").strip()
                if any(p == txt.rstrip("月") or p == v for p in month_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月SELECT[{i}]: {txt!r}")
                    date_selected = True
                    break
        for i, sel_elem in enumerate(selects):
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = (await opt.get_attribute("value") or "").strip()
                if any(p == txt.rstrip("日") or p == v for p in day_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日SELECT[{i}]: {txt!r}")
                    break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。\n"
            "analyze_site.py → 03_after_favorite.html でSELECT要素を確認してください。"
        )

    print(f"  [OK] 日付選択完了 ({TARGET_DATE_WAREKI})")


async def step_search_at_open(page, wait_for_open: bool):
    """Step4: ★ここが時報ポイント★ 5:00:00 ちょうどに検索ボタンを押す"""
    if wait_for_open:
        await wait_until_open()

    print(f"\n[Step 4] 検索ボタンをクリック... ({datetime.datetime.now().strftime('%H:%M:%S.%f')})")

    clicked = await try_click(page, [
        'input[value="検索"]',
        'input[value="絞込み検索"]',
        'input[value="空き照会"]',
        'button:text("検索")',
        'button:text("空き照会")',
        'a:text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "検索ボタン", timeout=3000)

    if not clicked:
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")
    print(f"  検索完了: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")


async def step_select_slot(page):
    """Step5: D面 16:00〜18:00 の空きセル（○）をクリック"""
    print(f"\n[Step 5] {TARGET_FACILITY} {TARGET_TIME_TEXT}〜18:00 の空きセルを選択...")

    clicked = False

    # ── アプローチA: ヘッダー行から列インデックスを特定し、D面行と交差 ──
    tables = await page.query_selector_all("table")
    for table in tables:
        rows = await table.query_selector_all("tr")
        if len(rows) < 2:
            continue

        # ヘッダー行で「16:00」を含む列インデックスを探す
        time_col_idx = -1
        for row in rows[:4]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_TEXT in txt:
                    time_col_idx = ci
                    print(f"  [INFO] 16:00列インデックス={ci} (text={txt!r})")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行を探してそのインデックスのセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_has_d = any(
                TARGET_FACILITY in (await c.inner_text()).strip()
                for c in cells
            )
            if not row_has_d:
                continue

            print(f"  [INFO] D面行発見, 列数={len(cells)}")
            if time_col_idx >= len(cells):
                print(f"  [WARN] 列インデックス={time_col_idx} が範囲外 (列数={len(cells)})")
                continue

            target_cell = cells[time_col_idx]
            tc_txt  = (await target_cell.inner_text()).strip()
            tc_cls  = (await target_cell.get_attribute("class") or "").strip()
            tc_on   = (await target_cell.get_attribute("onclick") or "").strip()
            tc_bg   = (await target_cell.get_attribute("bgcolor") or "").strip()
            print(f"  [TARGET CELL] text={tc_txt!r} class={tc_cls!r} onclick={tc_on!r} bgcolor={tc_bg!r}")

            # 利用可能かチェック（○ がある、または class に "open"/"available" 系が含まれる）
            available_marks = ["○", "◯", "〇", "空き", "予約可"]
            forbidden_marks = ["×", "✕", "✗", "×", "満", "不可", "休"]
            if any(m in tc_txt for m in forbidden_marks):
                print(f"  [WARN] このセルは予約不可 ({tc_txt!r})")
                await save_ss(page, "ERROR_slot_unavailable")
                raise RuntimeError(f"D面 16:00〜18:00 は予約不可です ({tc_txt!r})。スクリーンショットを確認。")

            await target_cell.click()
            print(f"  [OK] セルクリック完了")
            clicked = True
            break

        if clicked:
            break

    # ── アプローチB: D面行のセルを全走査して16:00を探す ──
    if not clicked:
        print("  [試行B] D面行の全セルを走査...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                row_texts = [(await c.inner_text()).strip() for c in cells]
                if TARGET_FACILITY not in row_texts:
                    continue
                for ci, cell in enumerate(cells):
                    txt = row_texts[ci]
                    if TARGET_TIME_TEXT in txt or (ci > 0 and "16" in txt):
                        print(f"  [FOUND-B] D面×16:00 cell[{ci}] text={txt!r}")
                        await cell.click()
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチC: onclick/href に "D" + "16" が含まれるリンク ──
    if not clicked:
        print("  [試行C] onclick/href から D面16:00を探す...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            onclick = (await elem.get_attribute("onclick") or "").lower()
            href    = (await elem.get_attribute("href") or "").lower()
            txt     = (await elem.inner_text()).strip().lower()
            combined = onclick + href + txt
            if ("d面" in combined or "'d'" in combined or '"d"' in combined) and "16" in combined:
                print(f"  [FOUND-C] {combined[:100]!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。\n"
            f"  04_search_results.png / .html を確認してください。\n"
            f"  フォルダ: {os.path.abspath(SS_DIR)}"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


async def step_confirm1(page):
    """Step6: 確定①（料金確認画面へ進む）"""
    print("\n[Step 6] 確定①クリック（料金確認）...")

    clicked = await try_click(page, [
        # mNetで多いパターン
        'input[value="確定"]',
        'input[value="次へ"]',
        'input[value="料金確認"]',
        'input[value="予約確認"]',
        'button:text("確定")',
        'button:text("次へ")',
        'a:text("確定")',
        'a:text("次へ")',
        'input[value*="確定"]',
        'input[value*="次へ"]',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        # フォールバック: ページ内のすべてのsubmit/button を探して「確定」系を選ぶ
        for elem in await page.query_selector_all("input[type=submit], input[type=button], button"):
            val = (await elem.get_attribute("value") or "").strip()
            txt = (await elem.inner_text()).strip() if await elem.inner_text() else ""
            combined = val + txt
            if any(w in combined for w in ["確定", "次へ", "確認", "予約"]):
                await elem.click()
                print(f"  [OK] 確定①（フォールバック）: {combined!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。05_slot_selected.html を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1_result")
    print(f"  現在URL: {page.url}")


async def step_confirm2(page):
    """Step7: 確定②（最終確定）
    Tampermonkeyでwindow.confirmが無効化されている前提。
    念のためPlaywrightのdialogハンドラも設定しておく。
    """
    print("\n[Step 7] 確定②クリック（最終確定）...")

    # window.confirm が発火した場合のフォールバック（自動accept）
    async def handle_dialog(dialog):
        print(f"  [DIALOG] {dialog.type}: {dialog.message!r} → accept")
        await dialog.accept()
    page.on("dialog", handle_dialog)

    # 確定②のボタンを探す
    # 確定①のページと同様のボタンが出ることが多いが、URL/ページが変わっているはず
    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="最終確定"]',
        'input[value="決定"]',
        'button:text("予約確定")',
        'button:text("確定")',
        'button:text("決定")',
        'a:text("確定")',
        'a:text("予約確定")',
        'input[value*="確定"]',
        'input[value*="決定"]',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        for elem in await page.query_selector_all("input[type=submit], input[type=button], button"):
            val = (await elem.get_attribute("value") or "").strip()
            txt = (await elem.inner_text()).strip() if await elem.inner_text() else ""
            combined = val + txt
            if any(w in combined for w in ["確定", "決定", "予約"]):
                await elem.click()
                print(f"  [OK] 確定②（フォールバック）: {combined!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError("確定②ボタンが見つかりません。06_confirm1_result.html を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了確認
    body = await page.inner_text("body")
    if any(w in body for w in ["予約完了", "受付完了", "受付番号", "予約番号", "申込番号", "完了しました"]):
        print("\n" + "=" * 60)
        print("✅  予約完了！")
        print("=" * 60)
    else:
        print("\n⚠️  完了メッセージが見つかりません。07_final_result.png を確認してください。")

    print(f"  完了時刻: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
    print(f"  ページ本文（先頭300字）:\n{body[:300]}")


# ────────────────────────────────────────────────────────────────
# メイン処理
# ────────────────────────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("  まんまるよやく2 自動予約スクリプト")
    print(f"  対象: {TARGET_DATE_WAREKI}  {TARGET_FACILITY} {TARGET_TIME_TEXT}〜18:00")
    print(f"  モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00)'}")
    print(f"  表示: {'ブラウザあり' if not opts['headless'] else 'ヘッドレス'}")
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
            # ── 5:00AM前に完了しておく処理 ──────────────────────
            await step_login(page)
            await step_favorite(page)
            await step_select_date(page)

            # ── 5:00:00.000 ぴったりに検索 ───────────────────────
            await step_search_at_open(page, opts["wait_for_open"])

            # ── 検索後の選択・確定 ────────────────────────────────
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)

            print("\n✅ すべてのステップが完了しました。")

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー発生: {e}")
            print(f"   スクリーンショット: {os.path.abspath(SS_DIR)}/")
            raise

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
