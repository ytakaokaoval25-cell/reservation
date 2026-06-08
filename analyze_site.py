"""
まんまるよやく2 サイト構造解析スクリプト

reserve.py で要素が見つからない場合に実行して
正確なセレクターを特定します。

■ 使い方
  python analyze_site.py
  python analyze_site.py --headful  # ブラウザを表示して確認

■ 出力
  analysis_output/01_login_page.html + .png
  analysis_output/02_after_login.html + .png
  analysis_output/03_after_favorite.html + .png
  analysis_output/04_search_results.html + .png
  コンソールに各ページのフォーム要素・SELECT・テーブル構造を出力
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

# テスト検索日
DATE_ALT_TEXTS  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19",
                   "令和08年06月19日（木）", "令和08年06月19日(木)"]
DATE_ALT_VALUES = ["20260619", "2026-06-19", "260619"]


def parse_args():
    return {"headless": "--headful" not in sys.argv[1:]}


async def save_step(page, name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {name}.png / {name}.html")


async def dump_forms(page, label: str):
    print(f"\n{'='*50}")
    print(f"  {label} のフォーム要素")
    print("=" * 50)

    print("\n--- FORM ---")
    for form in await page.query_selector_all("form"):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        name   = await form.get_attribute("name") or ""
        print(f"  <form name={name!r} action={action!r} method={method!r}>")

    print("\n--- INPUT ---")
    for inp in await page.query_selector_all("input"):
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  <input type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r}>")

    print("\n--- SELECT ---")
    for sel in await page.query_selector_all("select"):
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        print(f"  <select name={name!r} id={id_!r} class={cls!r}>")
        for opt in await sel.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected")
            mark = " [selected]" if sel_attr is not None else ""
            print(f"    <option value={v!r}>{txt}</option>{mark}")

    print("\n--- BUTTON/SUBMIT ---")
    for btn in await page.query_selector_all("button, input[type=submit], input[type=button]"):
        t    = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        val  = await btn.get_attribute("value") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  <{t} name={name!r} id={id_!r} value={val!r}>{txt!r}")

    print("\n--- LINKS ---")
    for a in await page.query_selector_all("a"):
        href = await a.get_attribute("href") or ""
        txt  = (await a.inner_text()).strip()
        if txt:
            print(f"  <a href={href!r}>{txt!r}</a>")


async def dump_table_structure(page, label: str):
    print(f"\n{'='*50}")
    print(f"  {label} のテーブル構造")
    print("=" * 50)

    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        print(f"\nTABLE[{ti}]  行数={len(rows)}")
        for ri, row in enumerate(rows[:10]):
            cells = await row.query_selector_all("td, th")
            parts = []
            for cell in cells:
                txt    = (await cell.inner_text()).strip().replace("\n", " ")[:30]
                cls    = await cell.get_attribute("class") or ""
                id_    = await cell.get_attribute("id") or ""
                onclick = await cell.get_attribute("onclick") or ""
                info = txt
                if cls:
                    info += f"[cls={cls}]"
                if id_:
                    info += f"[id={id_}]"
                if onclick:
                    info += f"[onclick={onclick[:40]}]"
                parts.append(info)
            print(f"  ROW[{ri}]: " + " | ".join(parts[:8]))

    # D面 / 16:00 を含むセルを重点表示
    print("\n--- D面 or 16:00 に関連するセル ---")
    for i, cell in enumerate(await page.query_selector_all("td, th")):
        txt     = (await cell.inner_text()).strip()
        onclick = await cell.get_attribute("onclick") or ""
        cls     = await cell.get_attribute("class") or ""
        id_     = await cell.get_attribute("id") or ""
        if "D面" in txt or "16:00" in txt or "18:00" in txt:
            print(f"  CELL[{i}] id={id_!r} class={cls!r} "
                  f"onclick={onclick[:60]!r} text={txt!r}")


async def try_fill_login(page):
    """ログインフォームに入力（複数候補を試す）"""
    for sel in ['input[name="userId"]', 'input[name="userid"]', 'input[name="user_id"]',
                'input[name="memberNo"]', 'input[name="loginId"]',
                '#userId', '#userid', 'input[type="text"]:first-of-type']:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000)
            if elem:
                await elem.fill(USER_ID)
                print(f"  [OK] 利用者番号入力: {sel}")
                break
        except PWTimeout:
            pass

    for sel in ['input[type="password"]', 'input[name="passwd"]',
                'input[name="password"]', 'input[name="pass"]']:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000)
            if elem:
                await elem.fill(PASSWORD)
                print(f"  [OK] パスワード入力: {sel}")
                break
        except PWTimeout:
            pass

    for sel in ['input[value="ログイン"]', 'button:text("ログイン")',
                'input[type="submit"]', 'button[type="submit"]']:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000)
            if elem:
                await elem.click()
                print(f"  [OK] ログインクリック: {sel}")
                break
        except PWTimeout:
            pass


async def analyze():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 サイト解析")
    print(f"出力先: {OUTPUT_DIR}/")
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

        # ── Step 1: ログインページ ──────────────────────────────────
        print("\n[Step 1] ログインページ解析...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_forms(page, "ログインページ")

        # ── Step 2: ログイン実行 ────────────────────────────────────
        print("\n[Step 2] ログイン実行...")
        await try_fill_login(page)
        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_forms(page, "ログイン後")
        print(f"  現在URL: {page.url}")

        # ── Step 3: お気に入りクリック ──────────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        clicked = False
        for sel in ['a:has-text("お気に入り")', 'input[value*="お気に入り"]',
                    'button:has-text("お気に入り")']:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                if elem:
                    print(f"  [OK] {sel}")
                    await elem.click()
                    clicked = True
                    break
            except PWTimeout:
                pass
        if not clicked:
            # テキストスキャン
            for elem in await page.query_selector_all("a, button, input"):
                try:
                    txt = (await elem.inner_text()).strip()
                except Exception:
                    txt = ""
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    print(f"  [OK] フォールバック: {txt!r}")
                    await elem.click()
                    clicked = True
                    break
        if not clicked:
            print("  [WARNING] お気に入りリンクが見つかりません")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        await dump_forms(page, "お気に入り後（絞り込み画面）")
        print(f"  現在URL: {page.url}")

        # ── Step 4: 日付選択・検索 ──────────────────────────────────
        print("\n[Step 4] 日付選択...")
        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in DATE_ALT_TEXTS) or v in DATE_ALT_VALUES:
                    name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                    print(f"  [OK] 日付選択: name={name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません。03_after_favorite.html を確認してください。")

        for sel in ['input[value*="検索"]', 'button:has-text("検索")',
                    'input[type="submit"]', 'button[type="submit"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    print(f"  [OK] 検索ボタン: {sel}")
                    await elem.click()
                    break
            except PWTimeout:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        await dump_table_structure(page, "検索結果")
        print(f"  現在URL: {page.url}")

        await browser.close()

    print(f"\n解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
    print("HTMLファイルをブラウザで開いて構造を確認し、")
    print("reserve.py のセレクターを必要に応じて修正してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
