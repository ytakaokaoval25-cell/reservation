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
# 設定値  ← ここを変更して本番に対応させる
# ──────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日（練習: 令和08年06月19日 / 本番: 令和08年07月XX日 に変更）
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日",
    "令和０８年０６月１９日", "令和08年 06月19日",
    "2026年06月19日", "2026/06/19", "2026-06-19",
]

# 分割プルダウン対応: 年・月・日それぞれに一致するパターン
YEAR_PATTERNS  = ["令和08", "令和8", "08", "2026", "R08", "R8", "R.08"]
MONTH_PATTERNS = ["06", "6", "６月", "06月", "6月"]
DAY_PATTERNS   = ["19", "１９", "19日"]

# 予約対象コート・時間帯
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 予約可能を示す記号（赤丸など）
AVAILABLE_MARKS = ["○", "◯", "〇", "●", "◎", "空", "可", "空き", "×以外"]

# 時報待ち設定
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト
NAV_TIMEOUT  = 30_000  # ページ遷移
ELEM_TIMEOUT = 10_000  # 要素待機
FAST_TIMEOUT = 3_000   # 高速クリック試行

# スクリーンショット保存先
SS_DIR = "screenshots"
# ──────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


# ──────────────────────────────────────────────
# 時報待ちロジック（ミリ秒精度）
# ──────────────────────────────────────────────
async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位で待機するループ"""
    print(f"[時報待ち] 朝{OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d}.000 まで待機中...")

    while True:
        now    = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            # 時刻到達
            print(f"[時報] 開始時刻到達: {now.strftime('%H:%M:%S.%f')}")
            return

        if diff_sec > 300:
            # 5分以上前 → 30秒おきに残り時間を表示
            m = int(diff_sec // 60)
            s = int(diff_sec % 60)
            print(f"[時報待ち] あと {m}分{s}秒...")
            await asyncio.sleep(min(30, diff_sec - 5))
        elif diff_sec > 10:
            # 10秒〜5分前 → 1秒おき
            await asyncio.sleep(1)
        elif diff_sec > 0.5:
            # 0.5〜10秒前 → 50msおき（CPU負荷低め）
            await asyncio.sleep(0.05)
        elif diff_sec > 0.01:
            # 10〜500ms前 → 1msおき（精密待機）
            await asyncio.sleep(0.001)
        else:
            # 10ms以内 → スピンウェイト（ほぼ0遅延）
            pass


# ──────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────
async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception:
        pass


async def try_click(page, selectors: list, label: str, timeout: int = FAST_TIMEOUT) -> bool:
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
    print(f"  [FAIL] {label}: セレクター不一致")
    return False


async def try_fill(page, selectors: list, value: str, label: str, timeout: int = FAST_TIMEOUT) -> bool:
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
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: セレクター不一致")
    return False


# ──────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号
    ok = await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid', '#user_id',
        'input[type="text"]',
    ], USER_ID, "利用者番号", timeout=ELEM_TIMEOUT)
    if not ok:
        raise RuntimeError("利用者番号フィールドが見つかりません。analyze_site.pyで確認してください。")

    # パスワード
    ok = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        '#passwd', '#password',
    ], PASSWORD, "パスワード", timeout=ELEM_TIMEOUT)
    if not ok:
        raise RuntimeError("パスワードフィールドが見つかりません。analyze_site.pyで確認してください。")

    # ログインボタン
    ok = await try_click(page, [
        'input[value="ログイン"]',
        'button:text("ログイン")',
        'a:text("ログイン")',
        'input[value*="ログイン"]',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "ログインボタン", timeout=ELEM_TIMEOUT)
    if not ok:
        raise RuntimeError("ログインボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if any(w in body for w in ["エラー", "パスワード", "ログインできません", "正しくない", "間違い"]):
        print(f"  [WARNING] ログイン失敗の可能性: {body[:200]}")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 2: お気に入りクリック
# ──────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        'a[href*="okini"]',
        'a[href*="favor"]',
        '[onclick*="okini"]',
        '[onclick*="favor"]',
        '[class*="okini"]',
        '[class*="favor"]',
    ], "お気に入り", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全スキャン
        for elem in await page.query_selector_all("a, button, input[type=submit], input[type=button]"):
            txt = (await elem.inner_text()).strip()
            val  = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り(full-scan): text={txt!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError(
            "お気に入りが見つかりません。"
            "02_after_login.html でリンクのhref/onclickを確認して修正してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 3: 日付選択 + 検索（5:00:00 到達後に即実行）
# ──────────────────────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}  検索実行...")

    selects = await page.query_selector_all("select")
    date_selected = False

    # ── アプローチ①: 単一プルダウンにフル日付テキストが含まれる ──
    for sel_elem in selects:
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
                print(f"  [OK] 日付(単一): name={sel_name!r}  value={v!r}  text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── アプローチ②: 年・月・日が別SELECTに分割されている ──
    if not date_selected:
        print("  [試行] 分割プルダウン（年・月・日）を探しています...")
        year_done = month_done = day_done = False
        for sel_elem in selects:
            opts = await sel_elem.query_selector_all("option")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if not year_done and any(p in txt or p == v for p in YEAR_PATTERNS):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年: {txt!r}")
                    year_done = True
                    break
                if not month_done and any(p == txt or p == v or p in txt
                                          for p in MONTH_PATTERNS):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月: {txt!r}")
                    month_done = True
                    break
                if not day_done and any(p == txt or p == v or p in txt
                                        for p in DAY_PATTERNS):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日: {txt!r}")
                    day_done = True
                    break
        if month_done or day_done:
            date_selected = True

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。\n"
            "analyze_site.pyを実行してSELECT/OPTIONのvalue・textを確認し\n"
            "TARGET_DATE_ALT_VALUES / TARGET_DATE_ALT_TEXTS を修正してください。"
        )

    # 検索ボタン
    ok = await try_click(page, [
        'input[value="検索"]',
        'button:text("検索")',
        'input[value*="検索"]',
        'a:text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "検索ボタン", timeout=ELEM_TIMEOUT)
    if not ok:
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 4: D面 16:00〜18:00 の赤丸セルをクリック
# ──────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}（赤丸）セルをクリック...")

    clicked = False
    tables  = await page.query_selector_all("table")

    # ── アプローチ①: ヘッダーから時間列インデックスを特定 → D面行と交差クリック ──
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_indices = []

        # ヘッダー行（最初の数行）で "16:00" と "18:00" を含む列を探す
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_indices.append(ci)
                elif TARGET_TIME_START in txt:
                    # "16:00〜18:00" が2セル分割の場合
                    time_col_indices.append(ci)
            if time_col_indices:
                break

        if not time_col_indices:
            continue

        # D面の行を探してターゲット列セルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            cell_texts = [(await c.inner_text()).strip() for c in cells]

            # D面を含む行か確認
            has_d = any(TARGET_FACILITY in t for t in cell_texts)
            if not has_d:
                continue

            print(f"  [INFO] D面行発見: {cell_texts[:8]}")
            for col_idx in time_col_indices:
                if col_idx >= len(cells):
                    continue
                target_cell = cells[col_idx]
                tc_txt = cell_texts[col_idx]
                tc_cls = await target_cell.get_attribute("class") or ""
                tc_onclick = await target_cell.get_attribute("onclick") or ""

                print(f"  [CANDIDATE] col={col_idx} text={tc_txt!r} class={tc_cls!r}")

                # セル内の <a> タグを優先クリック
                a_tags = await target_cell.query_selector_all("a")
                if a_tags:
                    await a_tags[0].click()
                    print(f"  [OK] <a>タグクリック in D面×16:00セル")
                    clicked = True
                    break

                # onclick付きセルを直接クリック
                if tc_onclick or any(m in tc_txt for m in AVAILABLE_MARKS):
                    await target_cell.click()
                    print(f"  [OK] セル直接クリック: text={tc_txt!r}")
                    clicked = True
                    break

                # ×や空でない場合も試みる
                if tc_txt and "×" not in tc_txt:
                    await target_cell.click()
                    print(f"  [OK] セルクリック(非×): text={tc_txt!r}")
                    clicked = True
                    break

            if clicked:
                break
        if clicked:
            break

    # ── アプローチ②: D面行内のテキストから直接時間を探す ──
    if not clicked:
        print("  [試行] D面行テキストスキャン...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                cell_texts = [(await c.inner_text()).strip() for c in cells]
                if not any(TARGET_FACILITY in t for t in cell_texts):
                    continue
                for ci, (cell, txt) in enumerate(zip(cells, cell_texts)):
                    if TARGET_TIME_START in txt or ("16" in txt and any(m in txt for m in AVAILABLE_MARKS)):
                        a_tags = await cell.query_selector_all("a")
                        if a_tags:
                            await a_tags[0].click()
                        else:
                            await cell.click()
                        print(f"  [OK] テキストスキャン: col={ci} text={txt!r}")
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick/href にキーワードが含まれる要素を探す ──
    if not clicked:
        print("  [試行] onclick/href スキャン...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            # D面 + 16 の組み合わせで判断
            if ("D面" in combined or "d_" in combined.lower()) and (
                "16" in combined or "1600" in combined
            ):
                print(f"  [OK] onclick/href: onclick={onclick!r}  href={href!r}  text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。\n"
            "04_search_results.html / analyze_site.pyの出力でテーブル構造を確認し\n"
            "step_select_slot()のクリック条件を修正してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ進む）
# ──────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①（料金確認へ）クリック...")

    # ダイアログ自動承認（Tampermonkeyで無効化済み想定だが念のため）
    page.on("dialog", lambda dlg: asyncio.ensure_future(dlg.accept()))

    ok = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="予約する"]',
        'input[value="次へ"]',
        'button:text("確定")',
        'button:text("確認")',
        'button:text("次へ")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'a:text("確定")',
        'a:text("確認")',
        'a:text("次へ")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①", timeout=ELEM_TIMEOUT)

    if not ok:
        raise RuntimeError(
            "確定①ボタンが見つかりません。"
            "05_slot_selected.html でボタンのvalue/textを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# ──────────────────────────────────────────────
async def step_confirm2(page):
    print("\n[Step 6] 確定②（最終確定）クリック...")

    # window.confirm を強制的に true に（Tampermonkey未適用環境でのフォールバック）
    await page.evaluate("window.confirm = () => true")
    await page.evaluate("window.alert   = () => undefined")

    # ダイアログ自動承認（二重保険）
    page.on("dialog", lambda dlg: asyncio.ensure_future(dlg.accept()))

    ok = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="確認"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'input[value*="確定"]',
        'a:text("確定")',
        'a:text("予約確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②", timeout=ELEM_TIMEOUT)

    if not ok:
        raise RuntimeError(
            "確定②ボタンが見つかりません。"
            "06_confirm1.html でボタンのvalue/textを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了確認
    body = await page.inner_text("body")
    if any(w in body for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました"]):
        print("\n✅ 予約完了を確認！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。07_final_result.pngを確認してください。")
    print(f"  本文先頭: {body[:300]}")


# ──────────────────────────────────────────────
# メインフロー
# ──────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}")
    print(f"施設: {TARGET_FACILITY}  {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else f'時報待ち ({OPEN_HOUR:02d}:00)'}"
          f" / {'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

    # ── ブラウザを先に起動しておく（5:00直前にすぐ動けるように）──
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()

        try:
            # ── ログインは時報待ち前に済ませる ──────────────────
            await step_login(page)
            await step_favorite(page)
            # ここで絞り込み画面（日付プルダウン）が表示されている状態

            # ── 時報待ち ──────────────────────────────────────
            if opts["wait_for_open"]:
                await wait_until_open()

            # ── 5:00:00 到達 → 一気に検索・選択・確定 ──────────
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)

            print("\n✅ すべてのステップが完了しました。")

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー発生: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
