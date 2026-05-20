"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）
本番（7月分）は TARGET_DATE_* と OPEN_DATE を書き換えてください。

■ 使い方
  python reserve.py              # 朝5:00ちょうど待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備
  pip install playwright
  playwright install chromium      # または既存Chromiumを使用（後述）
"""

import asyncio
import datetime
import os
import sys
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────────────────────
# ▼ 設定値（本番時はここを変更）
# ──────────────────────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日（練習：令和08年06月19日）
# 本番7月分に変えるときは以下を更新
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日",
    "令和8年6月19日",
    "令和０８年０６月１９日",
    "2026年06月19日",
    "2026/06/19",
]
TARGET_DATE_ALT_VALUES = [
    "20260619",
    "2026-06-19",
    "2026/06/19",
    "260619",
    "0619",
]

# 予約対象コート・時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# ──────────────────────────────────────────────────────────────
# ▼ 時報待ち設定（本番 5月19日 05:00:00 に開始）
# ──────────────────────────────────────────────────────────────
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0
# 当日限定（例: 2026-05-19）にしたい場合は以下を設定（None=日付チェックなし）
OPEN_DATE   = None  # datetime.date(2026, 5, 19)

# ──────────────────────────────────────────────────────────────
# ▼ タイムアウト（ミリ秒）
# ──────────────────────────────────────────────────────────────
NAV_TIMEOUT  = 30_000   # ページ遷移
ELEM_TIMEOUT = 10_000   # 要素待ち
CLICK_TIMEOUT = 5_000   # クリック前の要素待ち

# ──────────────────────────────────────────────────────────────
# ▼ スクリーンショット保存先
# ──────────────────────────────────────────────────────────────
SS_DIR = "screenshots"

# ──────────────────────────────────────────────────────────────
# ▼ Chromium実行ファイル候補（playwright install 不要で動く）
# ──────────────────────────────────────────────────────────────
CHROMIUM_CANDIDATES = [
    None,  # デフォルト（playwright install chromium 済みの場合）
    "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
]

# ──────────────────────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


def get_executable_path():
    """利用可能なChromiumの実行ファイルパスを返す（見つからなければNone）"""
    for path in CHROMIUM_CANDIDATES:
        if path is None:
            return None
        if os.path.isfile(path):
            print(f"[Browser] executable_path = {path}")
            return path
    return None


# ──────────────────────────────────────────────────────────────
# 時報待ちロジック（ミリ秒精度）
# ──────────────────────────────────────────────────────────────
async def wait_until_open():
    """設定した時刻（デフォルト 05:00:00.000）までミリ秒単位で待機"""
    print(f"[時報待ち] {OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d}.000 まで待機します...")

    while True:
        now = datetime.datetime.now()

        # 日付制限が設定されている場合はその日になるまで待つ
        if OPEN_DATE is not None and now.date() < OPEN_DATE:
            remaining_days = (OPEN_DATE - now.date()).days
            print(f"[時報待ち] 開始日まであと {remaining_days} 日。60秒ごとに確認...")
            await asyncio.sleep(60)
            continue

        target = now.replace(
            hour=OPEN_HOUR,
            minute=OPEN_MINUTE,
            second=OPEN_SECOND,
            microsecond=0,
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            # 時刻到達
            print(f"[時報] 開始時刻到達: {now.strftime('%H:%M:%S.%f')}")
            break
        elif diff_sec > 300:
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分) ...")
            await asyncio.sleep(30)
        elif diff_sec > 30:
            await asyncio.sleep(1)
        elif diff_sec > 1:
            await asyncio.sleep(0.05)  # 50ms
        else:
            await asyncio.sleep(0.001)  # 1ms（最終1秒はスピンウェイト）


# ──────────────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────────────
async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_fill(page, selectors: list, value: str, label: str,
                   timeout: int = CLICK_TIMEOUT) -> bool:
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
    print(f"  [FAIL] {label}: 該当フィールドなし → analyze_site.py で確認してください")
    return False


async def try_click(page, selectors: list, label: str,
                    timeout: int = CLICK_TIMEOUT) -> bool:
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
    print(f"  [FAIL] {label}: 該当要素なし → analyze_site.py で確認してください")
    return False


# ──────────────────────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────────────────────
async def step_login(page):
    print("\n" + "="*55)
    print("[Step 1] ログイン")
    print("="*55)
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await page.wait_for_load_state("networkidle", timeout=10_000)
    await save_ss(page, "01_login")

    # 利用者番号
    ok = await try_fill(page, [
        'input[name="userno"]',
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userno',
        '#userid',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")
    if not ok:
        raise RuntimeError("利用者番号フィールドが見つかりません。analyze_site.pyを実行してください。")

    # パスワード
    ok = await try_fill(page, [
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[type="password"]',
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

    # ログイン失敗チェック（エラーメッセージ検出）
    body = await page.inner_text("body")
    ng_words = ["パスワードが違います", "ログインできません", "エラー", "error", "incorrect"]
    for w in ng_words:
        if w in body:
            raise RuntimeError(f"ログイン失敗の可能性があります: '{w}' を検出。スクリーンショットを確認してください。")


# ──────────────────────────────────────────────────────────────
# Step 2: お気に入りクリック
# ──────────────────────────────────────────────────────────────
async def step_favorite(page):
    print("\n" + "="*55)
    print("[Step 2] お気に入りクリック")
    print("="*55)

    clicked = await try_click(page, [
        'a:has-text("お気に入り")',
        'input[value="お気に入り"]',
        'button:has-text("お気に入り")',
        'input[value*="お気に入り"]',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
        'a[href*="okiniri"]',
        'a[href*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # 全要素スキャン（フォールバック）
        for tag in ["a", "button", "input[type=button]", "input[type=submit]"]:
            elems = await page.query_selector_all(tag)
            for elem in elems:
                try:
                    txt = (await elem.inner_text()).strip()
                except Exception:
                    txt = ""
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    await elem.click()
                    print(f"  [OK] お気に入り（全スキャン）: tag={tag} text={txt!r}")
                    clicked = True
                    break
            if clicked:
                break

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。analyze_site.pyを実行してHTMLを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────────────
# Step 3: 日付選択 → 検索
# ──────────────────────────────────────────────────────────────
async def step_select_date_and_search(page):
    print("\n" + "="*55)
    print(f"[Step 3] 日付選択: {TARGET_DATE_WAREKI}")
    print("="*55)

    date_selected = False
    selects = await page.query_selector_all("select")

    # ── パターンA: 日付が1つのSELECTにまとまっている ──────────
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
                print(f"  [OK] 日付選択（1SELECT型）: name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── パターンB: 年・月・日が別々のSELECT ───────────────────
    if not date_selected:
        print("  [試行] 年月日が分割SELECTの可能性...")
        YEAR_PATS  = ["令和08", "令和8", "R08", "R8", "2026", "08"]
        MONTH_PATS = ["06", "6", "６", "６月", "06月", "6月"]
        DAY_PATS   = ["19", "１９", "19日"]

        for sel_elem in selects:
            opts = await sel_elem.query_selector_all("option")
            for opt in opts:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(txt == p or v == p for p in YEAR_PATS):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年選択: {txt!r}")
                    break

        for sel_elem in selects:
            opts = await sel_elem.query_selector_all("option")
            for opt in opts:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(txt == p or v == p for p in MONTH_PATS):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月選択: {txt!r}")
                    date_selected = True
                    break

        for sel_elem in selects:
            opts = await sel_elem.query_selector_all("option")
            for opt in opts:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if any(txt == p or v == p for p in DAY_PATS):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日選択: {txt!r}")
                    break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.py を実行して SELECT の option を確認してください。"
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


# ──────────────────────────────────────────────────────────────
# Step 4: D面 16:00〜18:00 セル選択
# ──────────────────────────────────────────────────────────────
async def step_select_slot(page):
    print("\n" + "="*55)
    print(f"[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択")
    print("="*55)

    clicked = False

    tables = await page.query_selector_all("table")

    # ── アプローチ①: ヘッダー行から列インデックスを特定してD面行をクリック ──
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # 最初の数行でヘッダーを探す
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_idx = ci
                    print(f"  [INFO] 「{TARGET_TIME_START}〜{TARGET_TIME_END}」列 = 列インデックス {ci}")
                    break
                # 「16:00」だけの列ヘッダーにも対応
                if txt == TARGET_TIME_START or txt.startswith(TARGET_TIME_START):
                    time_col_idx = ci
                    print(f"  [INFO] 「{TARGET_TIME_START}」列 = 列インデックス {ci}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue  # このテーブルには時間列がない

        # D面行を探してその列のセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_has_d = False
            for cell in cells:
                txt = (await cell.inner_text()).strip()
                if TARGET_FACILITY in txt:
                    row_has_d = True
                    break
            if row_has_d and time_col_idx < len(cells):
                target_cell = cells[time_col_idx]
                tc_txt = (await target_cell.inner_text()).strip()
                tc_cls = await target_cell.get_attribute("class") or ""
                tc_onclick = await target_cell.get_attribute("onclick") or ""
                print(f"  [FOUND①] D面×{TARGET_TIME_START}: text={tc_txt!r} class={tc_cls!r}")
                # セル内のリンクがあればリンクをクリック
                inner_a = await target_cell.query_selector("a")
                if inner_a:
                    await inner_a.click()
                    print(f"  [OK①] セル内のリンクをクリック")
                else:
                    await target_cell.click()
                    print(f"  [OK①] セルを直接クリック")
                clicked = True
                break
        if clicked:
            break

    # ── アプローチ②: D面行を見つけ、時間テキストを含むセルをクリック ──
    if not clicked:
        print("  [試行②] D面行から時間テキストで特定...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                cell_texts = [(await c.inner_text()).strip() for c in cells]
                if TARGET_FACILITY not in cell_texts:
                    continue
                print(f"  [INFO] D面行: {cell_texts}")
                for ci, cell in enumerate(cells):
                    txt = cell_texts[ci]
                    if TARGET_TIME_START in txt:
                        tc_cls = await cell.get_attribute("class") or ""
                        print(f"  [FOUND②] D面×{TARGET_TIME_START}: index={ci} text={txt!r} class={tc_cls!r}")
                        inner_a = await cell.query_selector("a")
                        if inner_a:
                            await inner_a.click()
                        else:
                            await cell.click()
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick / href にD面+時間が埋め込まれているリンク ──
    if not clicked:
        print("  [試行③] onclick/href からD面16:00を探す...")
        all_elems = await page.query_selector_all("[onclick], a[href], td")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href")    or ""
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            combined = onclick + href + txt
            # D面 AND 16 の両方を含む
            if (TARGET_FACILITY in combined or "d面" in combined.lower()) and "16" in combined:
                print(f"  [FOUND③] onclick={onclick!r:.60} href={href!r:.60} text={txt!r:.30}")
                await elem.click()
                clicked = True
                break

    # ── アプローチ④: 赤丸（○ / ● / 空き）で絞り込み ────────────
    if not clicked:
        print("  [試行④] 空き表示セルから D面 行を探す...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            d_row_idx = -1
            time_col_idx = -1

            # D面行インデックスを取得
            for ri, row in enumerate(rows):
                cells = await row.query_selector_all("td, th")
                for cell in cells:
                    if TARGET_FACILITY in (await cell.inner_text()).strip():
                        d_row_idx = ri
                        break
                if d_row_idx >= 0:
                    break

            # 時間列インデックスを取得（ヘッダー行）
            for row in rows[:5]:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_TIME_START in txt:
                        time_col_idx = ci
                        break
                if time_col_idx >= 0:
                    break

            if d_row_idx >= 0 and time_col_idx >= 0:
                target_row = rows[d_row_idx]
                cells = await target_row.query_selector_all("td, th")
                if time_col_idx < len(cells):
                    cell = cells[time_col_idx]
                    inner_a = await cell.query_selector("a")
                    if inner_a:
                        await inner_a.click()
                    else:
                        await cell.click()
                    tc_txt = (await cell.inner_text()).strip()
                    print(f"  [FOUND④] D面×{TARGET_TIME_START}: text={tc_txt!r}")
                    clicked = True
                    break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。"
            "analysis_output/04_search_results.html でテーブル構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ──────────────────────────────────────────────────────────────
async def step_confirm1(page):
    print("\n" + "="*55)
    print("[Step 5] 確定① クリック")
    print("="*55)

    ok = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'input[value*="次へ"]',
        'button:has-text("確定")',
        'button:has-text("確認")',
        'button:has-text("次へ")',
        'a:has-text("確定")',
        'a:has-text("確認")',
        'a:has-text("次へ")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン", timeout=ELEM_TIMEOUT)

    if not ok:
        await save_ss(page, "ERROR_confirm1_not_found")
        raise RuntimeError("確定①ボタンが見つかりません。スクリーンショットを確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# ──────────────────────────────────────────────────────────────
async def step_confirm2(page):
    print("\n" + "="*55)
    print("[Step 6] 確定② クリック（最終確定）")
    print("="*55)

    # Tampermonkey で window.confirm が無効化されている前提だが
    # 万一ダイアログが出た場合も自動 accept するフォールバック
    def handle_dialog(dialog):
        asyncio.ensure_future(dialog.accept())
        print(f"  [Dialog] '{dialog.message}' → 自動承認")

    page.on("dialog", handle_dialog)

    ok = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="最終確定"]',
        'input[value*="確定"]',
        'button:has-text("予約確定")',
        'button:has-text("確定")',
        'button:has-text("最終確定")',
        'a:has-text("予約確定")',
        'a:has-text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン", timeout=ELEM_TIMEOUT)

    if not ok:
        await save_ss(page, "ERROR_confirm2_not_found")
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了メッセージ確認
    body = await page.inner_text("body")
    success_words = ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました", "受け付けました"]
    found = [w for w in success_words if w in body]
    if found:
        print(f"\n✅ 予約完了確認 → キーワード: {found}")
    else:
        print("\n⚠️  完了メッセージが見つかりません。07_final_result.png を確認してください。")
    print(f"  ページ本文（先頭300字）:\n{body[:300]}")


# ──────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────
async def main():
    opts = parse_args()

    print("=" * 55)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"  対象日  : {TARGET_DATE_WAREKI}")
    print(f"  施設    : {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"  モード  : {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00:00)'}")
    print(f"  表示    : {'ブラウザあり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 55)

    # 時報待ち
    if opts["wait_for_open"]:
        await wait_until_open()

    exe = get_executable_path()
    launch_kwargs = {
        "headless": opts["headless"],
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if exe:
        launch_kwargs["executable_path"] = exe

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,
        )
        page = await context.new_page()

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
