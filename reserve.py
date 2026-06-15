"""
まんまるよやく2 自動予約スクリプト
===================================
対象  : D面 16:00〜18:00
練習日: 令和08年06月19日 (2026-06-19)
本番日: 令和08年07月XX日 (reserve.pyの TARGET_DATE_* を変更)

■ 使い方
  python reserve.py              # 朝5:00:00ちょうど待ちモード（本番）
  python reserve.py --now        # 即時実行（動作確認用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 前提
  pip install playwright
  playwright install chromium

■ Tampermonkey前提
  window.confirm は Tampermonkey で無効化済み（自動 true 返却）を前提とする。
  Playwrightのdialogハンドラーでも自動承認するため二重対策済み。
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ============================================================
# ★★★ 設定値（本番時はここを変更） ★★★
# ============================================================
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日 ─ テキスト候補（プルダウン表示形式ごとに対応）
TARGET_DATE_TEXTS = [
    "令和08年06月19日",
    "令和8年6月19日",
    "令和０８年０６月１９日",
    "2026年06月19日",
    "2026/06/19",
    "2026-06-19",
]
# 予約対象日 ─ value候補（value属性が数値形式の場合）
TARGET_DATE_VALUES = ["20260619", "2026-06-19", "260619"]

# 年・月・日が別々のSELECTになっている場合の候補
TARGET_YEAR_TEXTS  = ["令和08年", "令和8年", "令和０８年", "2026年", "2026", "08", "8"]
TARGET_MONTH_TEXTS = ["06月", "6月", "０６月", "6", "06"]
TARGET_DAY_TEXTS   = ["19日", "１９日", "19"]

# 予約対象コート＆時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 開場時刻（朝5:00:00.000 ぴったりに検索を実行）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト
NAV_TIMEOUT  = 30_000   # ページ遷移
ELEM_TIMEOUT = 10_000   # 要素待機

# スクリーンショット保存フォルダ（デバッグ用）
SS_DIR = "screenshots"
# ============================================================


# ──────────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────────

def parse_args() -> dict:
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


async def wait_until_open():
    """
    朝5:00:00.000 ぴったりまでミリ秒単位で待機するループ。

    段階的スリープ戦略:
      5分以上前  → 30秒ごとに残り時間を表示
      10秒〜5分前 → 1秒ごと
      100ms〜10秒前 → 50ms ごと
      100ms以内   → 1ms ごと（精密ループ）
    """
    print("[時報待ち] 朝5:00:00.000 まで待機します...")

    while True:
        now    = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")
            print(f"[時報！] 開始: {ts}")
            return

        if diff_sec > 300:
            print(f"  あと {diff_sec:.0f} 秒 ({diff_sec/60:.1f} 分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            await asyncio.sleep(1)
        elif diff_sec > 0.1:
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.001)


async def ss(page, name: str):
    """スクリーンショットを保存"""
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_click(page, selectors: list[str], label: str,
                    timeout: int = ELEM_TIMEOUT) -> bool:
    """複数セレクターを順番に試してクリック。全失敗時はテキスト検索"""
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
            print(f"  [skip] {sel}: {e}")

    # フォールバック: ボタン・リンクをテキストで探す
    for elem in await page.query_selector_all(
        "a, button, input[type=submit], input[type=button]"
    ):
        try:
            txt = (await elem.inner_text()).strip()
            val = await elem.get_attribute("value") or ""
            key = label.split("（")[0].split("(")[0].strip()
            if key and (key in txt or key in val):
                await elem.click()
                print(f"  [OK] {label} (テキスト検索): {txt!r}")
                return True
        except Exception:
            pass

    print(f"  [FAIL] {label}")
    return False


async def try_fill(page, selectors: list[str], value: str,
                   label: str, timeout: int = ELEM_TIMEOUT) -> bool:
    """複数セレクターを順番に試して入力"""
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.fill(value)
                print(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            print(f"  [skip] {sel}: {e}")
    print(f"  [FAIL] {label}")
    return False


# ──────────────────────────────────────────────────────────
# 各ステップ
# ──────────────────────────────────────────────────────────

async def step_login(page):
    """Step 1: ログイン"""
    print("\n[Step 1] ログイン...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "01_login")

    ok = await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        '#userid',
        'input[type="text"]',
    ], USER_ID, "利用者番号")
    if not ok:
        raise RuntimeError("利用者番号フィールドが見つかりません。analyze_site.py で確認してください。")

    ok = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")
    if not ok:
        raise RuntimeError("パスワードフィールドが見つかりません。")

    ok = await try_click(page, [
        'input[value="ログイン"]',
        'button:has-text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
        'a:has-text("ログイン")',
    ], "ログインボタン")
    if not ok:
        raise RuntimeError("ログインボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "02_after_login")
    print(f"  URL: {page.url}")


async def step_favorite(page):
    """Step 2: お気に入り → 絞り込み画面"""
    print("\n[Step 2] お気に入りをクリック...")

    # セレクターリスト
    ok = await try_click(page, [
        'a:has-text("お気に入り")',
        'input[value="お気に入り"]',
        'input[value*="お気に入り"]',
        'button:has-text("お気に入り")',
        '[onclick*="okiniiri"]',
        '[onclick*="favorite"]',
        '[href*="okiniiri"]',
        '[href*="favorite"]',
        '[id*="favorite"]',
        '[class*="favorite"]',
    ], "お気に入り")

    if not ok:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行して 02_after_login.html を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "03_after_favorite")
    print(f"  URL: {page.url}")


async def _select_by_options(page, target_texts: list[str],
                              target_values: list[str]) -> bool:
    """ページ内の全SELECTからテキスト/valueが一致するoptionを選択"""
    for sel_elem in await page.query_selector_all("select"):
        for opt in await sel_elem.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in target_texts) or v in target_values):
                name = await sel_elem.get_attribute("name") or ""
                if v:
                    await sel_elem.select_option(value=v)
                else:
                    await sel_elem.select_option(label=txt)
                print(f"  [OK] SELECT name={name!r} value={v!r} text={txt!r}")
                return True
    return False


async def step_select_date_and_search(page):
    """
    Step 3: 日付プルダウンで令和08年06月19日を選択して検索。

    対応パターン:
      パターンA: 1つのSELECTに「令和08年06月19日」の形で日付が並ぶ
      パターンB: 年・月・日が別々のSELECT
    """
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_TEXTS[0]}")
    await ss(page, "03b_search_form")

    # ── パターンA: 単一SELECTで日付を選択 ───────────────
    date_set = await _select_by_options(page, TARGET_DATE_TEXTS, TARGET_DATE_VALUES)

    # ── パターンB: 年月日が別々のSELECT ─────────────────
    if not date_set:
        print("  [試行] 年月日が分割SELECTの可能性あり...")
        year_set  = await _select_by_options(page, TARGET_YEAR_TEXTS,  [])
        month_set = await _select_by_options(page, TARGET_MONTH_TEXTS, [])
        day_set   = await _select_by_options(page, TARGET_DAY_TEXTS,   [])
        date_set  = year_set and month_set and day_set

    if not date_set:
        await ss(page, "ERROR_date_select")
        raise RuntimeError(
            f"日付 {TARGET_DATE_TEXTS[0]} のオプションが見つかりません。\n"
            "analyze_site.py を実行して 03_after_favorite.html の SELECT を確認してください。"
        )

    # 検索ボタン
    ok = await try_click(page, [
        'input[value="検索"]',
        'input[value*="検索"]',
        'button:has-text("検索")',
        'a:has-text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "検索ボタン")
    if not ok:
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "04_search_results")
    print(f"  URL: {page.url}")


async def step_select_slot(page):
    """
    Step 4: D面 16:00〜18:00（赤丸）のセルをクリック。

    アプローチ①: テーブルの行をスキャンしてD面を含む行の16:00列セルをクリック
    アプローチ②: ヘッダー行から16:00〜18:00の列インデックスを特定 → D面行のそのセル
    アプローチ③: onclick/href にD面・16:00の情報が含まれる要素を探す
    """
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セルをクリック...")

    clicked = False
    tables  = await page.query_selector_all("table")

    # ── アプローチ①: 行スキャン（D面を含む行の16:00セル）──────
    for table in tables:
        rows = await table.query_selector_all("tr")
        for row in rows:
            cells     = await row.query_selector_all("td, th")
            row_texts = []
            for c in cells:
                try:
                    row_texts.append((await c.inner_text()).strip().replace("\n", " "))
                except Exception:
                    row_texts.append("")

            # D面を含む行か判定
            if not any(TARGET_FACILITY in t for t in row_texts):
                continue

            print(f"  [INFO] D面行: {row_texts[:8]}")

            # 16:00 を含むセルをクリック
            for i, cell in enumerate(cells):
                txt = row_texts[i]
                if TARGET_TIME_START in txt:
                    cls     = await cell.get_attribute("class")   or ""
                    onclick = await cell.get_attribute("onclick") or ""
                    print(f"  [FOUND①] D面×16:00 text={txt!r} class={cls!r} onclick={onclick!r}")
                    # セル内リンクがあればそちらをクリック
                    child = await cell.query_selector("a, input[type=button], input[type=submit]")
                    if child:
                        await child.click()
                    else:
                        await cell.click()
                    clicked = True
                    break
            if clicked:
                break
        if clicked:
            break

    # ── アプローチ②: ヘッダーから列インデックスを特定 ──────────
    if not clicked:
        print("  [試行②] ヘッダーから列インデックスで特定...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            time_col = -1

            for row in rows[:5]:  # 最初の5行でヘッダー探索
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                        time_col = ci
                        print(f"  [INFO] 16:00〜18:00 列={ci}")
                        break
                if time_col >= 0:
                    break

            if time_col < 0:
                continue

            for row in rows:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_FACILITY in txt and time_col < len(cells):
                        target = cells[time_col]
                        tc_txt = (await target.inner_text()).strip()
                        tc_cls = await target.get_attribute("class") or ""
                        print(f"  [FOUND②] D面行col{time_col}: {tc_txt!r} class={tc_cls!r}")
                        child = await target.query_selector("a, input[type=button], input[type=submit]")
                        if child:
                            await child.click()
                        else:
                            await target.click()
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick/href でD面+16を探す ──────────────
    if not clicked:
        print("  [試行③] onclick/href でD面+16:00を探す...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            try:
                onclick = await elem.get_attribute("onclick") or ""
                href    = await elem.get_attribute("href")    or ""
                txt     = (await elem.inner_text()).strip()
                combined = onclick + href + txt
                if ("D面" in combined or "d面" in combined.lower()) and "16" in combined:
                    print(f"  [FOUND③] onclick={onclick!r} href={href!r} text={txt!r}")
                    await elem.click()
                    clicked = True
                    break
            except Exception:
                pass

    if not clicked:
        await ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。\n"
            "analyze_site.py を実行して 04_search_results.html のテーブル構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "05_slot_selected")
    print(f"  URL: {page.url}")


async def step_confirm1(page):
    """Step 5: 確定①（料金確認画面へ進む）"""
    print("\n[Step 5] 確定①...")
    ok = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'button:has-text("確定")',
        'button:has-text("確認")',
        'a:has-text("確定")',
        'a:has-text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①")
    if not ok:
        await ss(page, "ERROR_confirm1")
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "06_confirm1")
    print(f"  URL: {page.url}")


async def step_confirm2(page):
    """
    Step 6: 確定②（最終確定）

    Tampermonkey で window.confirm が無効化（常にtrue返却）されているため
    confirm ダイアログは発火しない前提。
    Playwright の dialog ハンドラーで万が一の場合も自動承認する。
    """
    print("\n[Step 6] 確定②（最終確定）...")

    # 万一 window.confirm が発火した場合の自動承認
    def _accept_dialog(dialog):
        print(f"  [dialog] {dialog.type}: {dialog.message!r} → 自動承認")
        asyncio.ensure_future(dialog.accept())

    page.on("dialog", _accept_dialog)

    ok = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value*="確定"]',
        'button:has-text("確定")',
        'button:has-text("予約確定")',
        'a:has-text("確定")',
        'a:has-text("予約確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②")
    if not ok:
        await ss(page, "ERROR_confirm2")
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "07_final")
    print(f"  URL: {page.url}")

    # 完了判定
    body = await page.inner_text("body")
    if any(w in body for w in ["予約完了", "受付完了", "受付番号", "予約番号", "ご予約"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。screenshots/07_final.png を確認してください。")
    print(f"  ページ冒頭200文字: {body[:200]!r}")


# ──────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────

async def main():
    opts = parse_args()
    mode_label = ("即時実行" if not opts["wait_for_open"] else "時報待ち(5:00)")
    ui_label   = ("ブラウザ表示あり" if not opts["headless"]      else "ヘッドレス")
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"  対象  : {TARGET_DATE_TEXTS[0]} {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"  モード : {mode_label} / {ui_label}")
    print("=" * 60)

    # 時報待ち
    if opts["wait_for_open"]:
        await wait_until_open()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,   # ★ SSL証明書エラーを無視
        )
        page = await ctx.new_page()

        try:
            await step_login(page)
            await step_favorite(page)
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)
            print("\n✅ 全ステップ完了。")
        except Exception as e:
            await ss(page, "ERROR_fatal")
            print(f"\n❌ エラー: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
