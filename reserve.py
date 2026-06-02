"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00

■ 練習モード   → 令和08年06月19日 を予約（現在）
■ 本番モード   → TARGET_DATE_WAREKI を令和08年07月19日に書き換えて実行

■ 使い方
  python reserve.py              # 朝5:00:00ちょうどまで待ってから実行（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザを画面表示（デバッグ用）
  python reserve.py --now --headful

■ 事前準備
  pip install playwright
  playwright install chromium
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────────────────
#  設定値（ここだけ変更すればOK）
# ──────────────────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# ★ 本番は "令和08年07月19日" / "20260719" に変更する ★
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_VALUE  = "20260619"

# マッチング候補（サイトの表記揺れに対応）
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
    "0619", "6/19", "06-19",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日",
    "令和０８年０６月１９日", "令和8年6月19日",
    "2026年06月19日", "2026/06/19", "2026-06-19",
    "06/19", "6/19", "R08.06.19",
]

TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報待ち設定
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト(ms)
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

SS_DIR = "screenshots"
# ──────────────────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


# ──────────────── 時報待ち ────────────────────────────────
async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位で待機
    ・残り5分超: 30秒ごとに確認
    ・残り10秒〜5分: 1秒ごと
    ・残り100ms〜10秒: 50msごと
    ・残り100ms以内: 1msごと（フライング防止）
    """
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
            break
        elif diff > 300:
            print(f"[時報待ち] あと {diff:.0f}秒 ({diff/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff > 10:
            await asyncio.sleep(1)
        elif diff > 0.1:
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.001)


# ──────────────── ユーティリティ ─────────────────────────
async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception as e:
        print(f"  [SS FAIL] {path}: {e}")


async def try_click(page, selectors: list, label: str, timeout: int = ELEM_TIMEOUT) -> bool:
    """複数セレクターを順番に試してクリック。成功したらTrue。"""
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
    # フォールバック: inner_textで探す
    for text in [label]:
        try:
            elems = await page.query_selector_all("a, button, input[type='submit'], input[type='button']")
            for elem in elems:
                try:
                    txt = (await elem.inner_text()).strip()
                except Exception:
                    txt = ""
                val = await elem.get_attribute("value") or ""
                if label in txt or label in val:
                    await elem.click()
                    print(f"  [OK] {label} (text fallback): {txt!r}")
                    return True
        except Exception:
            pass
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


async def try_fill(page, selectors: list, value: str, label: str, timeout: int = ELEM_TIMEOUT) -> bool:
    """複数セレクターを順番に試して入力。"""
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
    print(f"  [FAIL] {label}: 入力フィールドなし")
    return False


# ──────────────── Step 1: ログイン ───────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await page.wait_for_timeout(2000)
    await save_ss(page, "01_login")

    await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid', '#user_id', '#memberNo', '#loginId',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")

    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[name="pw"]',
        '#passwd', '#password',
    ], PASSWORD, "パスワード")

    await try_click(page, [
        'input[value="ログイン"]',
        'input[value="LOGIN"]',
        'input[value*="ログイン"]',
        'button:text("ログイン")',
        'button[type="submit"]',
        'input[type="submit"]',
        'a:text("ログイン")',
    ], "ログイン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await page.wait_for_timeout(1000)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


# ──────────────── Step 2: お気に入り ─────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    # テキスト・value・href・onclick から "お気に入り" を総当たりで探す
    clicked = False
    candidates = await page.query_selector_all(
        "a, button, input[type='submit'], input[type='button']"
    )
    for elem in candidates:
        try:
            txt = (await elem.inner_text()).strip()
        except Exception:
            txt = ""
        val     = await elem.get_attribute("value") or ""
        href    = await elem.get_attribute("href") or ""
        onclick = await elem.get_attribute("onclick") or ""
        combined = txt + val + href + onclick
        if "お気に入り" in combined or "okiniri" in combined.lower() or "favorite" in combined.lower():
            await elem.click()
            print(f"  [OK] お気に入り: text={txt!r} val={val!r}")
            clicked = True
            break

    if not clicked:
        # CSS/XPath フォールバック
        clicked = await try_click(page, [
            'a:text("お気に入り")',
            'input[value="お気に入り"]',
            'button:text("お気に入り")',
            '[class*="favorite"]',
            '[id*="favorite"]',
            '[class*="okiniri"]',
            '[id*="okiniri"]',
        ], "お気に入り", timeout=5000)

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行してHTML構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await page.wait_for_timeout(1000)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ──────────────── Step 3: 日付選択 → 検索 ───────────────
async def step_select_date_and_search(page):
    """
    朝5:00:00に到達した直後に呼び出される。
    日付プルダウンを最速で選択して検索する。
    """
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False

    # ── パターンA: 一体型プルダウン（例: "令和08年06月19日"） ──────
    for sel_elem in await page.query_selector_all("select"):
        opts = await sel_elem.query_selector_all("option")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                try:
                    if v:
                        await sel_elem.select_option(value=v)
                    else:
                        await sel_elem.select_option(label=txt)
                    print(f"  [OK] 日付選択(一体型): name={sel_name!r} value={v!r} text={txt!r}")
                    date_selected = True
                except Exception as e:
                    print(f"  [WARN] select_option失敗: {e}")
            if date_selected:
                break
        if date_selected:
            break

    # ── パターンB: 年・月・日が別々のプルダウン ──────────────────
    if not date_selected:
        print("  [試行B] 年/月/日が分割SELECTの可能性...")
        # 年セレクト
        year_patterns  = ["令和08", "令和8", "08", "2026", "R08", "R8", "8"]
        month_patterns = ["06", "6", "６月", "06月", "6月"]
        day_patterns   = ["19", "１９", "19日"]

        selects = await page.query_selector_all("select")
        year_done = month_done = day_done = False

        for sel_elem in selects:
            opts = await sel_elem.query_selector_all("option")
            for opt in opts:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if not year_done and any(p == txt or p == v for p in year_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年選択: {txt!r}")
                    year_done = True
                    break

        for sel_elem in selects:
            opts = await sel_elem.query_selector_all("option")
            for opt in opts:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if not month_done and any(p == txt or p == v for p in month_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月選択: {txt!r}")
                    month_done = True
                    break

        for sel_elem in selects:
            opts = await sel_elem.query_selector_all("option")
            for opt in opts:
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if not day_done and any(p == txt or p == v for p in day_patterns):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日選択: {txt!r}")
                    day_done = True
                    break

        if month_done:  # 最低限 月が選択できれば続行
            date_selected = True

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。\n"
            "analyze_site.py を実行してセレクターを確認してください。"
        )

    # 検索ボタン
    await try_click(page, [
        'input[value="検索"]',
        'input[value*="検索"]',
        'button:text("検索")',
        'a:text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "検索")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await page.wait_for_timeout(500)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


# ──────────────── Step 4: D面 16:00〜18:00 クリック ─────
async def step_select_slot(page):
    """
    D面 × 16:00〜18:00 のセルを特定してクリックする。
    テーブル構造の違いに対応するため3段階のアプローチ。
    """
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} を選択...")
    clicked = False

    tables = await page.query_selector_all("table")

    # ── アプローチA: ヘッダーで列インデックスを特定 → D面行をクリック ──
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行（上位3行）で "16:00〜18:00" または "16:00" の列番号を特定
        for row in rows[:4]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt or (TARGET_TIME_START in txt and TARGET_TIME_END in txt):
                    time_col_idx = ci
                    print(f"  [INFO] {TARGET_TIME_START} 列インデックス={ci} (text={txt!r})")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue  # このテーブルには時間ヘッダーがない

        # D面の行を探してそのインデックス列をクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_FACILITY in txt:
                    if time_col_idx < len(cells):
                        target_cell = cells[time_col_idx]
                        tc_txt = (await target_cell.inner_text()).strip()
                        tc_cls = await target_cell.get_attribute("class") or ""
                        print(
                            f"  [FOUND A] D面×列{time_col_idx}: "
                            f"text={tc_txt!r} class={tc_cls!r}"
                        )
                        await target_cell.click()
                        clicked = True
                    break
            if clicked:
                break
        if clicked:
            break

    # ── アプローチB: D面行のtextと同じ行にある16:00セルを直接クリック ──
    if not clicked:
        print("  [試行B] D面行内の16:00セルを直接探す...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells       = await row.query_selector_all("td, th")
                cell_texts  = [(await c.inner_text()).strip() for c in cells]
                if TARGET_FACILITY in " ".join(cell_texts):
                    for i, (cell, ctxt) in enumerate(zip(cells, cell_texts)):
                        if TARGET_TIME_START in ctxt or "16" in ctxt:
                            cls = await cell.get_attribute("class") or ""
                            print(f"  [FOUND B] text={ctxt!r} class={cls!r}")
                            await cell.click()
                            clicked = True
                            break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチC: onclick/href の文字列で探す ───────────────────
    if not clicked:
        print("  [試行C] onclick/href にD面・16の情報を持つ要素を探す...")
        all_elems = await page.query_selector_all("[onclick], a[href], td[onclick], td[href]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            combined = (onclick + href + txt).lower()
            if ("d面" in combined or "ｄ面" in combined) and "16" in combined:
                print(f"  [FOUND C] onclick={onclick!r} href={href!r}")
                await elem.click()
                clicked = True
                break

    # ── アプローチD: 全tdのtextから "16:00" かつ赤丸（○・●・◎）を含む ──
    if not clicked:
        print("  [試行D] 全tdのtext/classで赤丸＋16:00を探す...")
        all_tds = await page.query_selector_all("td, a")
        for elem in all_tds:
            try:
                txt = (await elem.inner_text()).strip()
                cls = await elem.get_attribute("class") or ""
            except Exception:
                continue
            # 赤丸を示す典型的なクラス: "akamaru" "red" "○" など
            is_red_dot = any(
                k in cls.lower() for k in ["aka", "red", "maru", "koyomi_red", "○"]
            ) or "○" in txt or "●" in txt
            if "16" in txt and is_red_dot:
                print(f"  [FOUND D] text={txt!r} class={cls!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。\n"
            "analyze_site.py で検索結果ページのHTML(04_search_results.html)を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await page.wait_for_timeout(500)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ──────────────── Step 5: 確定① ─────────────────────────
async def step_confirm1(page):
    """料金確認画面への進捗（確定①）"""
    print("\n[Step 5] 確定①クリック...")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="次へ"]',
        'input[value="次へ進む"]',
        'input[value="確認"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'input[value*="次へ"]',
        'button:text("確定")',
        'button:text("確認")',
        'button:text("次へ")',
        'a:text("確定")',
        'a:text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①")

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。screenshots/05_slot_selected.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await page.wait_for_timeout(500)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


# ──────────────── Step 6: 確定② ─────────────────────────
async def step_confirm2(page):
    """最終確定（確定②）
    Tampermonkey で window.confirm を無効化済みのため
    dialog イベントは発火しない前提。
    万一 confirm が来た場合は自動承認するフォールバックも実装。
    """
    print("\n[Step 6] 確定②クリック...")

    # ダイアログが来た場合のフォールバック（自動承認）
    async def handle_dialog(dialog):
        print(f"  [DIALOG] {dialog.type}: {dialog.message!r} → 承認")
        await dialog.accept()

    page.on("dialog", handle_dialog)

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value*="確定"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②")

    if not clicked:
        raise RuntimeError("確定②ボタンが見つかりません。screenshots/06_confirm1.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await page.wait_for_timeout(1000)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了判定
    try:
        body = await page.inner_text("body")
        if any(w in body for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました"]):
            print("\n✅ 予約完了を確認しました！")
        else:
            print("\n⚠️  完了メッセージ未検出。07_final_result.png を確認してください。")
        print(f"  本文（先頭300字）:\n{body[:300]}")
    except Exception:
        pass


# ──────────────── メイン ─────────────────────────────────
async def main():
    opts = parse_args()

    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"  対象日  : {TARGET_DATE_WAREKI}")
    print(f"  施設/時間: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    mode = "即時実行" if not opts["wait_for_open"] else "時報待ち(5:00)"
    hd   = "ヘッドレス" if opts["headless"] else "ブラウザ表示あり"
    print(f"  モード  : {mode} / {hd}")
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
            ignore_https_errors=True,
        )
        page = await context.new_page()

        try:
            # ── ログインは5:00前に済ませる ──────────────────────
            await step_login(page)
            await step_favorite(page)

            # ── 時報待ち ─────────────────────────────────────
            if opts["wait_for_open"]:
                await wait_until_open()

            # ── 5:00:00 到達後、最速で日付選択→検索→予約 ──────
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
