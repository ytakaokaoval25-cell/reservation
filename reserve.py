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

■ 動作フロー（本番モード）
  [起動] → ブラウザ起動 → ログイン → お気に入りページ → [5:00待機]
        → ページリロード → 日付選択＆検索 → D面セルクリック → 確定① → 確定②

  ※ ブラウザ起動・ログインを5時前に完了させ、お気に入り画面で待機。
    5時ちょうどにリロード＋日付選択で即座に検索できる。
"""

import asyncio
import datetime
import glob
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────
LOGIN_URL   = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID     = "12015873"
PASSWORD    = "0508"

# 予約対象日（令和08年06月19日 = 2026-06-19 で練習。本番は変更）
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_VALUE  = "20260619"
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


def find_chromium_executable() -> str | None:
    """インストール済みのChromium実行ファイルを自動検出する"""
    candidates = [
        "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
        os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"),
        os.path.expanduser(
            "~/Library/Caches/ms-playwright/chromium-*/chrome-mac"
            "/Chromium.app/Contents/MacOS/Chromium"
        ),
    ]
    for pattern in candidates:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    return None


def parse_args():
    args = sys.argv[1:]
    return {
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


async def wait_until_open():
    """
    朝5:00:00.000 ぴったりまでミリ秒単位で待機。
    ブラウザ起動・ログインを先に済ませてからここで待機することで、
    5時ちょうどに即座に検索を実行できる。
    """
    now = datetime.datetime.now()
    target = now.replace(
        hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
    )
    if now >= target:
        print(f"[時報] すでに開始時刻を過ぎています。即時実行します。({now.strftime('%H:%M:%S.%f')})")
        return

    print(f"[時報待ち] {target.strftime('%H:%M:%S')} まで待機します（お気に入り画面で待機中）...")
    while True:
        now = datetime.datetime.now()
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
            break
        elif diff_sec > 300:
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            await asyncio.sleep(1)
        elif diff_sec > 0.1:
            await asyncio.sleep(0.05)
        else:
            # 100ms以内: 1msごとの精密ループ
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    """スクリーンショット保存（デバッグ用）"""
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception as e:
        print(f"  [SS失敗] {name}: {e}")


async def suppress_confirms(page):
    """window.confirm/alert を自動承認に上書き（Tampermonkey 代替）"""
    try:
        await page.evaluate(
            "() => { window.confirm = () => true; window.alert = () => undefined; }"
        )
    except Exception:
        pass


async def try_click(page, selectors: list[str], label: str, timeout: int = 5000) -> bool:
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


async def try_fill(page, selectors: list[str], value: str, label: str, timeout: int = 5000) -> bool:
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


async def click_cell_or_inner_link(cell) -> None:
    """
    テーブルセルをクリック。
    セル内に <a> タグがある場合はリンクを優先クリックする。
    """
    link = await cell.query_selector("a")
    if link:
        await link.click()
    else:
        await cell.click()


# ──────────────────────────────────────────────
# 各ステップ
# ──────────────────────────────────────────────

async def step_login(page):
    """Step1: ログイン"""
    print("\n[Step 1] ログインページへ移動...")
    response = await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)

    if response and response.status == 403:
        body = await page.inner_text("body")
        if "allowlist" in body or "not in allowlist" in body:
            raise RuntimeError(
                "このサーバーはサイトのIPホワイトリストに含まれていません。\n"
                "ローカルPC（接続許可済みのネットワーク）から実行してください。"
            )

    await suppress_confirms(page)
    await save_ss(page, "01_login")

    # 利用者番号
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
    await suppress_confirms(page)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


async def step_favorite(page):
    """Step2: お気に入りクリック → 絞り込み画面"""
    print("\n[Step 2] お気に入りをクリック...")
    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        'a:text-matches("お気に入り")',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        elems = await page.query_selector_all(
            "a, button, input[type=button], input[type=submit]"
        )
        for elem in elems:
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（フォールバック）: text={txt!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。analyze_site.pyで解析してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await suppress_confirms(page)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


async def step_select_date_and_search(page):
    """
    Step3: 日付プルダウンで令和08年06月19日を選択して検索。
    5:00到達直後に呼ばれる。リロードで新データを取得してから即座に選択・検索する。
    """
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    # 5:00ちょうどに最新状態を取得するためリロード
    print("  [リロード] ページを最新化...")
    await page.reload(wait_until="networkidle", timeout=NAV_TIMEOUT)
    await suppress_confirms(page)

    date_selected = False
    selects = await page.query_selector_all("select")

    # アプローチ①: 統合SELECTでテキスト/value一致
    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = (await opt.get_attribute("value") or "").strip()
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                try:
                    if v:
                        await sel_elem.select_option(value=v)
                    else:
                        await sel_elem.select_option(label=txt)
                    print(f"  [OK] 日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                    date_selected = True
                except Exception as e:
                    print(f"  [WARN] select_option失敗: {e}")
                break
        if date_selected:
            break

    # アプローチ②: 年・月・日が分割SELECTの場合
    if not date_selected:
        print("  [試行] 年月日分割SELECT...")
        year_patterns  = ["令和08", "令和8", "08", "2026", "R08", "R8"]
        month_patterns = ["06", "6", "６月", "06月"]
        day_patterns   = ["19", "１９", "19日"]

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = (await opt.get_attribute("value") or "").strip()
                if any(p == txt or p == v for p in year_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年選択: {txt!r}")
                    break

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = (await opt.get_attribute("value") or "").strip()
                if any(p == txt or p == v for p in month_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月選択: {txt!r}")
                    date_selected = True
                    break

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                v   = (await opt.get_attribute("value") or "").strip()
                if any(p == txt or p == v for p in day_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日選択: {txt!r}")
                    break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.pyを実行してセレクターを確認してください。"
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
    await suppress_confirms(page)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


async def step_select_slot(page):
    """Step4: D面 16:00〜18:00 の赤丸セルをクリック"""
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    clicked = False
    tables = await page.query_selector_all("table")

    # ── アプローチ①: ヘッダー列インデックス × D面行 ────────────
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # 最初の3行からヘッダーで列インデックスを特定
        for row in rows[:3]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_idx = ci
                    print(f"  [INFO] 列ヘッダー発見: col={ci} text={txt!r}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行を特定してそのインデックスのセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_texts = [(await c.inner_text()).strip() for c in cells]
            if not any(TARGET_FACILITY in t for t in row_texts):
                continue

            if time_col_idx < len(cells):
                target_cell = cells[time_col_idx]
                tc_txt = (await target_cell.inner_text()).strip()
                tc_cls = await target_cell.get_attribute("class") or ""
                print(f"  [FOUND] D面×{TARGET_TIME_START}: text={tc_txt!r} class={tc_cls!r}")
                await click_cell_or_inner_link(target_cell)
                clicked = True
            break
        if clicked:
            break

    # ── アプローチ②: D面行を全テーブル走査し時刻含みセルを探す ──
    if not clicked:
        print("  [試行] D面行を全テーブル走査...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                row_texts = [(await c.inner_text()).strip() for c in cells]
                if not any(TARGET_FACILITY in t for t in row_texts):
                    continue

                print(f"  [INFO] D面行テキスト: {row_texts}")
                for i, cell in enumerate(cells):
                    txt = row_texts[i]
                    cls = await cell.get_attribute("class") or ""
                    if TARGET_TIME_START in txt or any(
                        kw in cls.lower()
                        for kw in ["red", "maru", "available", "circle", "yoyaku"]
                    ):
                        print(f"  [FOUND] アプローチ②: col={i} text={txt!r} class={cls!r}")
                        await click_cell_or_inner_link(cell)
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick/href にD面+16が含まれる要素 ────────
    if not clicked:
        print("  [試行] onclick/href からD面16:00を探す...")
        all_elems = await page.query_selector_all("[onclick], a[href]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if ("D面" in combined or "d面" in combined.lower()) and "16" in combined:
                print(f"  [FOUND] アプローチ③: onclick={onclick!r} href={href!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。"
            "screenshotsフォルダのスクリーンショットを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await suppress_confirms(page)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


async def step_confirm1(page):
    """Step5: 確定①（料金確認画面へ）"""
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
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await suppress_confirms(page)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


async def step_confirm2(page):
    """
    Step6: 確定②（最終確定）
    window.confirm は context.add_init_script と suppress_confirms() で無効化済み。
    """
    print("\n[Step 6] 確定②クリック...")

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
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    body_text = await page.inner_text("body")
    if any(w in body_text for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。スクリーンショットを確認してください。")
    print(f"  最終本文（先頭200字）: {body_text[:200]}")


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────

async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

    chromium_path = find_chromium_executable()
    launch_kwargs: dict = {
        "headless": opts["headless"],
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ],
    }
    if chromium_path:
        print(f"[INFO] Chromium: {chromium_path}")
        launch_kwargs["executable_path"] = chromium_path

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )

        # window.confirm/alert を全ページで自動承認（Tampermonkey 代替）
        await context.add_init_script(
            "window.confirm = () => true; window.alert = () => undefined;"
        )

        page = await context.new_page()

        # ダイアログが来ても自動承認（Playwright レベルのフォールバック）
        async def _auto_accept_dialog(dialog):
            try:
                await dialog.accept()
            except Exception:
                pass

        page.on("dialog", _auto_accept_dialog)

        try:
            # ── 5時前に完了させるステップ ────────────────────────
            await step_login(page)
            await step_favorite(page)
            # ────────────────────────────────────────────────────

            # 5:00ちょうどまで待機（ブラウザはお気に入り画面で待機中）
            if opts["wait_for_open"]:
                await wait_until_open()

            # ── 5:00ちょうどに実行するステップ ──────────────────
            await step_select_date_and_search(page)  # リロード→日付選択→検索
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)
            # ────────────────────────────────────────────────────

            print("\n✅ すべてのステップが完了しました。")

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー: {e}")
            raise

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
