"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は令和08年07月分に変更

■ 正しい実行フロー
  1. スクリプト起動（朝4:55頃推奨）
  2. ログイン → お気に入り絞り込み画面まで移動（事前準備）
  3. 朝5:00:00.000まで 1ms 単位でビジーウェイト
  4. 5:00:00ちょうどに日付選択 → 検索クリック（サイト更新直後の最速アクセス）
  5. D面 16:00〜18:00（赤丸）セルをクリック → 確定① → 確定②

■ 使い方
  python reserve.py              # 時報待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用: 時報待ちをスキップ）
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

# ─────────────────────────────────────────────────────────────────
# 設定値（本番は以下を書き換えること）
# ─────────────────────────────────────────────────────────────────
LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"

# 予約対象日（練習: 令和08年06月19日）
# 本番で7月を取る場合は "令和08年07月XX日" に変更
TARGET_DATE_WAREKI = "令和08年06月19日"

# 検索時に試すvalue候補（実際の値はanalyze_site.pyの出力で確認）
TARGET_DATE_VALUES = [
    "20260619", "2026-06-19", "2026/06/19",
    "260619", "0619",
]
# 検索時に試すtext候補
TARGET_DATE_TEXTS = [
    "令和08年06月19日", "令和8年6月19日",
    "令和０８年０６月１９日", "2026年06月19日",
]

# 年・月・日が分割SELECTの場合の候補
TARGET_YEAR_VALUES  = ["8", "08", "2026", "r8", "r08", "令和8", "令和08"]
TARGET_MONTH_VALUES = ["6", "06", "６", "６月", "06月"]
TARGET_DAY_VALUES   = ["19", "１９", "19日"]

# 予約対象コート＆時間
TARGET_FACILITY  = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報設定（朝5:00:00.000 に検索クリック）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000   # ページ遷移
ELEM_TIMEOUT = 10_000   # 要素待ち

# スクリーンショット保存ディレクトリ
SS_DIR = "screenshots"

# ─────────────────────────────────────────────────────────────────


def parse_args() -> dict:
    args = sys.argv[1:]
    return {
        "headless":      "--headful" not in args,
        "wait_for_open": "--now"     not in args,
    }


# ─── タイミング制御 ───────────────────────────────────────────────

async def wait_until_open():
    """
    朝 5:00:00.000 ちょうどまでミリ秒単位で待機する。

    実行フロー:
      - 5分以上前: 30秒ごとにチェック（ログ出力あり）
      - 10秒〜5分前: 1秒ごとにポーリング
      - 0.5秒〜10秒前: 50ms ごとにポーリング
      - 最後の 500ms: 1ms ビジーウェイト（フライング防止）
    """
    now = datetime.datetime.now()
    target = now.replace(
        hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
    )
    if now >= target:
        print(f"[時報] 既に {OPEN_HOUR:02d}:00:00 を過ぎています。このまま続行します。")
        return

    diff_sec = (target - now).total_seconds()
    print(f"[時報待ち] {OPEN_HOUR:02d}:00:00.000 まで {diff_sec:.1f} 秒 待機します ...")

    while True:
        now = datetime.datetime.now()
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            break
        elif diff_sec > 300:          # 5分以上前
            print(f"  残り {diff_sec:.0f} 秒 ({diff_sec/60:.1f} 分) ...")
            await asyncio.sleep(30)
        elif diff_sec > 10:           # 10秒〜5分前
            await asyncio.sleep(1)
        elif diff_sec > 0.5:          # 0.5秒〜10秒前
            await asyncio.sleep(0.05)
        else:                         # 最後の 500ms: ビジーウェイト
            while datetime.datetime.now() < target:
                await asyncio.sleep(0.001)
            break

    print(f"[時報] 開始時刻到達: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")


# ─── ユーティリティ ──────────────────────────────────────────────

async def save_ss(page, name: str):
    """スクリーンショットを SS_DIR に保存（常に全ページ）"""
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def find_and_click(page, selectors: list, label: str, timeout: int = 5_000) -> bool:
    """
    selectors を上から順に試し、最初に見つかった要素をクリック。
    どれも見つからなければ False を返す。
    """
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
    print(f"  [FAIL] {label}: 該当なし")
    return False


async def find_and_fill(page, selectors: list, value: str, label: str, timeout: int = 5_000) -> bool:
    """selectors を順番に試して入力"""
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
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: 該当なし")
    return False


# ─── 各ステップ ──────────────────────────────────────────────────

async def step_login(page):
    """Step 1: ログイン"""
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号（よく使われるname属性を優先順に試す）
    ok = await find_and_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid',
        'input[type="text"]',
    ], USER_ID, "利用者番号")
    if not ok:
        raise RuntimeError("利用者番号フィールドが見つかりません。analyze_site.py で確認してください。")

    # パスワード
    ok = await find_and_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")
    if not ok:
        raise RuntimeError("パスワードフィールドが見つかりません。")

    # ログインボタン
    ok = await find_and_click(page, [
        'input[value="ログイン"]',
        'input[value*="ログイン"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("ログイン")',
    ], "ログインボタン")
    if not ok:
        raise RuntimeError("ログインボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


async def step_favorite(page):
    """Step 2: お気に入りをクリック → 絞り込み画面へ"""
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await find_and_click(page, [
        'a:text("お気に入り")',
        'button:text("お気に入り")',
        'input[value="お気に入り"]',
        'input[value*="お気に入り"]',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト走査フォールバック
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            txt = (await elem.inner_text() or "").strip()
            val = (await elem.get_attribute("value") or "")
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（走査）: text={txt!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.pyを実行してメニュー画面のHTMLを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")
    print("  >>> 絞り込み画面に到達。時報待ちに入ります。")


async def step_select_date_and_search(page):
    """
    Step 3: 日付選択 → 検索クリック

    ★ この関数は wait_until_open() の直後に呼ぶこと。
       サイトが5:00に更新されて新しい日付が追加される前提。
       必要に応じてページをリロードしてから選択する。
    """
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    # ── 日付選択（まず全体 SELECT から一致するオプションを探す）────
    date_selected = await _try_select_combined_date(page)

    if not date_selected:
        print("  [試行] 年・月・日が分割 SELECT の可能性あり...")
        date_selected = await _try_select_split_date(page)

    if not date_selected:
        # 5:00 直後でページが更新される場合: リロードして再試行
        print("  [試行] ページをリロードして再試行...")
        await page.reload(wait_until="networkidle", timeout=NAV_TIMEOUT)
        await save_ss(page, "03b_reload")
        date_selected = await _try_select_combined_date(page)
        if not date_selected:
            date_selected = await _try_select_split_date(page)

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。\n"
            f"analyze_site.py を実行して SELECT の options を確認してください。"
        )

    # ── 検索ボタンをクリック（5:00:00 直後の最速実行）───────────
    ok = await find_and_click(page, [
        'input[value="検索"]',
        'input[value*="検索"]',
        'button:text("検索")',
        'button[type="submit"]',
        'input[type="submit"]',
        'a:text("検索")',
    ], "検索ボタン")
    if not ok:
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


async def _try_select_combined_date(page) -> bool:
    """日付が1つの SELECT に入っている場合の選択"""
    for sel_elem in await page.query_selector_all("select"):
        for opt in await sel_elem.query_selector_all("option"):
            v   = (await opt.get_attribute("value") or "").strip()
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_TEXTS)
                    or v in TARGET_DATE_VALUES):
                name = await sel_elem.get_attribute("name") or ""
                if v:
                    await sel_elem.select_option(value=v)
                else:
                    await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択（一体型）: name={name!r} value={v!r} text={txt!r}")
                return True
    return False


async def _try_select_split_date(page) -> bool:
    """年・月・日が別々の SELECT に分かれている場合の選択"""
    selects = await page.query_selector_all("select")
    year_done = month_done = day_done = False

    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = (await opt.get_attribute("value") or "").strip()
            txt = (await opt.inner_text()).strip()

            if not year_done and any(p == txt or p == v for p in TARGET_YEAR_VALUES):
                await sel_elem.select_option(value=v or txt)
                print(f"  [OK] 年選択: text={txt!r} value={v!r}")
                year_done = True
                break

            if not month_done and any(p == txt or p == v for p in TARGET_MONTH_VALUES):
                await sel_elem.select_option(value=v or txt)
                print(f"  [OK] 月選択: text={txt!r} value={v!r}")
                month_done = True
                break

            if not day_done and any(p == txt or p == v for p in TARGET_DAY_VALUES):
                await sel_elem.select_option(value=v or txt)
                print(f"  [OK] 日選択: text={txt!r} value={v!r}")
                day_done = True
                break

    return month_done  # 月が選択できていれば成功とみなす


async def step_select_slot(page):
    """
    Step 4: D面 × 16:00〜18:00 のセル（赤丸）をクリック。

    アプローチ①: テーブル走査（行テキストで D面 を特定 → 列で 16:00 を特定）
    アプローチ②: ヘッダー行から列インデックスを特定してから行を探す
    アプローチ③: onclick / href の文字列で D面 + 16 を含む要素を探す
    """
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    tables = await page.query_selector_all("table")
    clicked = False

    # ── アプローチ①: 行テキストに D面 を含む行の 16:00 セルを探す ──
    for table in tables:
        rows = await table.query_selector_all("tr")
        for row in rows:
            cells = await row.query_selector_all("td, th")
            texts = [(await c.inner_text()).strip() for c in cells]

            if not any(TARGET_FACILITY in t for t in texts):
                continue

            # D面行発見
            print(f"  [INFO] D面行: {texts[:8]}")

            for i, cell in enumerate(cells):
                txt = texts[i]
                if TARGET_TIME_START in txt:
                    print(f"  [FOUND] ①D面×16:00 text={txt!r}")
                    await cell.click()
                    clicked = True
                    break

                # セル内リンク（<a>タグ）を試す
                link = await cell.query_selector("a")
                if link and TARGET_TIME_START in txt:
                    print(f"  [FOUND] ①D面×16:00(link) text={txt!r}")
                    await link.click()
                    clicked = True
                    break

            if clicked:
                break
        if clicked:
            break

    # ── アプローチ②: ヘッダーで 16:00〜18:00 の列インデックスを特定 ──
    if not clicked:
        print("  [試行] ②ヘッダーから列インデックス特定...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            time_col_idx = -1

            for row in rows[:4]:  # ヘッダーは先頭4行以内
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
                texts = [(await c.inner_text()).strip() for c in cells]
                if any(TARGET_FACILITY in t for t in texts):
                    if time_col_idx < len(cells):
                        target_cell = cells[time_col_idx]
                        tc_txt = texts[time_col_idx]
                        print(f"  [FOUND] ②D面×col{time_col_idx} text={tc_txt!r}")
                        # セル内のリンクを優先
                        link = await target_cell.query_selector("a")
                        if link:
                            await link.click()
                        else:
                            await target_cell.click()
                        clicked = True
                    break
            if clicked:
                break

    # ── アプローチ③: onclick/href に D面+16 の情報が含まれる要素 ──
    if not clicked:
        print("  [試行] ③onclick/href で D面×16:00 を探す...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            onclick = (await elem.get_attribute("onclick") or "")
            href    = (await elem.get_attribute("href")    or "")
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if (TARGET_FACILITY in combined or "D" in combined) and "16" in combined:
                print(f"  [FOUND] ③: onclick={onclick[:60]!r} txt={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。\n"
            f"screenshots/04_search_results.png を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


async def step_confirm1(page):
    """Step 5: 確定①（料金確認画面へ進む）"""
    print("\n[Step 5] 確定①クリック...")
    ok = await find_and_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'button:text("確定")',
        'button:text("確認")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")
    if not ok:
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


async def step_confirm2(page):
    """
    Step 6: 確定②（最終確定）

    Tampermonkey で window.confirm が無効化されている前提。
    万一ダイアログが出た場合は context の add_init_script が自動承認する。
    """
    print("\n[Step 6] 確定②クリック...")

    ok = await find_and_click(page, [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="最終確定"]',
        'input[value*="確定"]',
        'button:text("予約確定")',
        'button:text("確定")',
        'a:text("確定")',
        'a:text("予約確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")
    if not ok:
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final")
    print(f"  現在URL: {page.url}")

    body = await page.inner_text("body")
    if any(w in body for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。screenshots/07_final.png を確認してください。")
    print(f"  本文（先頭300字）:\n  {body[:300]}")


# ─── メイン ──────────────────────────────────────────────────────

async def main():
    opts = parse_args()

    print("=" * 64)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"  対象日: {TARGET_DATE_WAREKI}")
    print(f"  施設:   {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"  モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00:00)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print(f"  開始:   {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 64)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
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

        # window.confirm / window.alert を完全に無効化
        # （Tampermonkey のバックアップとして）
        await context.add_init_script("""
            window.confirm = function() { return true; };
            window.alert   = function() {};
            window.onbeforeunload = null;
        """)

        page = await context.new_page()

        try:
            # ─── Phase 1: 事前準備（5:00 AM 前に完了させる）──────────
            await step_login(page)
            await step_favorite(page)

            # ─── Phase 2: 時報待ち ─────────────────────────────────
            # お気に入り絞り込み画面で待機。
            # サイトは 5:00:00 に更新されて新しい日付を公開する。
            if opts["wait_for_open"]:
                await wait_until_open()

            # ─── Phase 3: 高速実行（5:00:00.000 以降） ─────────────
            # 日付選択→検索→セル選択→確定①→確定②
            print(f"\n[Phase 3] 高速実行開始: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)

            print("\n✅ すべてのステップが完了しました。")

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラーが発生しました: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
