"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する
"""

import asyncio
import os
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID = "12015873"
PASSWORD = "0508"
OUTPUT_DIR = "analysis_output"
CHROMIUM_PATH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / {step_name}.html")


async def dump_form_elements(page, label: str):
    """ページ内のすべてのフォーム要素を出力"""
    print(f"\n=== {label} のフォーム要素 ===")

    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_ = await inp.get_attribute("id") or ""
        cls = await inp.get_attribute("class") or ""
        val = await inp.get_attribute("value") or ""
        print(f"  INPUT type={t} name={name!r} id={id_!r} class={cls!r} value={val!r}")

    selects = await page.query_selector_all("select")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_ = await sel.get_attribute("id") or ""
        cls = await sel.get_attribute("class") or ""
        print(f"  SELECT name={name!r} id={id_!r} class={cls!r}")
        options = await sel.query_selector_all("option")
        for opt in options[:30]:
            v = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            print(f"    OPTION value={v!r} text={txt!r}")

    buttons = await page.query_selector_all("button, input[type=submit], input[type=button]")
    for btn in buttons:
        t = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_ = await btn.get_attribute("id") or ""
        val = await btn.get_attribute("value") or ""
        cls = await btn.get_attribute("class") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  BUTTON type={t} name={name!r} id={id_!r} value={val!r} class={cls!r} text={txt!r}")

    links = await page.query_selector_all("a")
    print(f"\n  --- リンク一覧 ---")
    for link in links:
        href = await link.get_attribute("href") or ""
        cls = await link.get_attribute("class") or ""
        onclick = await link.get_attribute("onclick") or ""
        txt = (await link.inner_text()).strip()
        if txt:
            print(f"  A href={href!r} class={cls!r} onclick={onclick!r} text={txt!r}")

    forms = await page.query_selector_all("form")
    print(f"\n  --- フォーム一覧 ---")
    for form in forms:
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        id_ = await form.get_attribute("id") or ""
        name = await form.get_attribute("name") or ""
        print(f"  FORM id={id_!r} name={name!r} action={action!r} method={method!r}")


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROMIUM_PATH,
            args=["--ignore-certificate-errors", "--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = await browser.new_context(
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()

        # ── Step 1: ログインページ ──────────────────────────────
        print("\n[Step 1] ログインページに移動...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_form_elements(page, "ログインページ")
        print(f"  現在URL: {page.url}")

        # ── Step 2: ログイン実行 ───────────────────────────────
        print("\n[Step 2] ログイン実行...")
        userid_selectors = [
            'input[name="userid"]',
            'input[name="user_id"]',
            'input[name="memberNo"]',
            'input[name="userno"]',
            'input[name="loginId"]',
            'input[name="login_id"]',
            'input[name="id"]',
            'input[id="userid"]',
            'input[type="text"]:first-of-type',
        ]
        userid_filled = False
        for sel in userid_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.fill(USER_ID)
                    print(f"  [OK] 利用者番号入力: {sel}")
                    userid_filled = True
                    break
            except Exception:
                pass
        if not userid_filled:
            print("  [WARNING] 利用者番号フィールドが見つかりません")

        passwd_selectors = [
            'input[name="passwd"]',
            'input[name="password"]',
            'input[name="pass"]',
            'input[type="password"]',
        ]
        passwd_filled = False
        for sel in passwd_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.fill(PASSWORD)
                    print(f"  [OK] パスワード入力: {sel}")
                    passwd_filled = True
                    break
            except Exception:
                pass
        if not passwd_filled:
            print("  [WARNING] パスワードフィールドが見つかりません")

        submit_selectors = [
            'input[type="submit"]',
            'button[type="submit"]',
            'input[value*="ログイン"]',
            'button:has-text("ログイン")',
        ]
        for sel in submit_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    print(f"  [OK] サブミットクリック: {sel}")
                    await elem.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_form_elements(page, "ログイン後ページ")
        print(f"  現在URL: {page.url}")

        # ── Step 3: お気に入りクリック ─────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        fav_selectors = [
            'a:has-text("お気に入り")',
            'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
            'td:has-text("お気に入り")',
        ]
        fav_clicked = False
        for sel in fav_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                if elem:
                    txt = (await elem.inner_text()).strip()
                    id_ = await elem.get_attribute("id") or ""
                    cls = await elem.get_attribute("class") or ""
                    href = await elem.get_attribute("href") or ""
                    print(f"  [OK] お気に入り要素発見: sel={sel!r} id={id_!r} class={cls!r} href={href!r} text={txt!r}")
                    await elem.click()
                    fav_clicked = True
                    break
            except Exception:
                pass
        if not fav_clicked:
            print("  [WARNING] お気に入りボタンが見つかりません")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        await dump_form_elements(page, "お気に入り後（絞り込み画面）")
        print(f"  現在URL: {page.url}")

        # ── Step 4: 日付プルダウン全options出力 ──────────────────
        print("\n[Step 4] 全selectオプション詳細出力...")
        date_selects = await page.query_selector_all("select")
        for sel in date_selects:
            name = await sel.get_attribute("name") or ""
            id_ = await sel.get_attribute("id") or ""
            options = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r} - {len(options)}件")
            for opt in options:
                v = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r}  text={txt!r}")

        # ── Step 5: 日付選択・検索 ────────────────────────────
        print("\n[Step 5] 令和08年06月19日を選択して検索...")
        date_target_texts = ["令和08年06月19日", "令和8年6月19日", "08年06月19日", "06月19日", "2026/06/19", "20260619"]

        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                v = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in date_target_texts) or v in date_target_texts:
                    name = await sel_elem.get_attribute("name") or ""
                    id_ = await sel_elem.get_attribute("id") or ""
                    await sel_elem.select_option(value=v)
                    print(f"  [OK] 日付選択: select name={name!r} id={id_!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません。スクリーンショットを確認してください")

        search_selectors = [
            'input[value*="検索"]',
            'button:has-text("検索")',
            'input[type="submit"]',
            'button[type="submit"]',
            'a:has-text("検索")',
        ]
        for sel in search_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    val = await elem.get_attribute("value") or ""
                    id_ = await elem.get_attribute("id") or ""
                    print(f"  [OK] 検索ボタン: {sel} id={id_!r} value={val!r}")
                    await elem.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        print(f"  現在URL: {page.url}")

        # ── Step 6: 検索結果テーブル解析 ─────────────────────
        print("\n[Step 6] 検索結果テーブル解析...")
        cells = await page.query_selector_all("td, th")
        for i, cell in enumerate(cells):
            txt = (await cell.inner_text()).strip()
            if any(kw in txt for kw in ["D面", "16:00", "18:00", "赤丸", "○", "●", "×", "空き"]):
                id_ = await cell.get_attribute("id") or ""
                cls = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                rowspan = await cell.get_attribute("rowspan") or ""
                colspan = await cell.get_attribute("colspan") or ""
                print(f"  CELL[{i}] id={id_!r} class={cls!r} onclick={onclick!r} rowspan={rowspan!r} txt={txt!r}")

        tables = await page.query_selector_all("table")
        print(f"\n  テーブル数: {len(tables)}")
        for ti, tbl in enumerate(tables[:5]):
            rows = await tbl.query_selector_all("tr")
            print(f"\n  TABLE[{ti}] 行数={len(rows)}")
            for ri, row in enumerate(rows[:10]):
                cells_in_row = await row.query_selector_all("td, th")
                row_data = []
                for cell in cells_in_row:
                    txt = (await cell.inner_text()).strip()
                    cls = await cell.get_attribute("class") or ""
                    id_ = await cell.get_attribute("id") or ""
                    onclick = await cell.get_attribute("onclick") or ""
                    row_data.append(f"[{txt}|cls={cls}|id={id_}|onclick={onclick[:30]}]")
                print(f"    ROW[{ri}]: {'  '.join(row_data[:8])}")

        await browser.close()
        print(f"\n\n解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
