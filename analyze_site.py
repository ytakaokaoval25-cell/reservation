"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・フォーム要素・スクリーンショットを保存して
正確なセレクターを確認する。

  python analyze_site.py
  python analyze_site.py --headful   # ブラウザ表示あり

出力先: analysis_output/
  01_login_page.html/png
  02_after_login.html/png
  03_after_favorite.html/png
  04_search_results.html/png
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

# 予約対象日 (解析用: どれにも当てはまれば日付選択を試みる)
TARGET_DATE_TEXTS  = [
    "令和08年06月19日", "令和8年6月19日",
    "2026年06月19日", "2026/06/19",
]
TARGET_DATE_VALUES = ["20260619", "2026-06-19", "260619"]

# Chromium実行バイナリ（環境によって変更）
CHROMIUM_EXECUTABLE = None


async def save_step(page, name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {name}.png / .html")


def hr(label: str):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)


async def dump_all_elements(page, label: str):
    hr(f"{label} のフォーム・リンク要素")

    # FORM
    forms = await page.query_selector_all("form")
    for fi, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        print(f"FORM[{fi}] action={action!r} method={method!r}")

    # INPUT
    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t    = await inp.get_attribute("type")   or "text"
        name = await inp.get_attribute("name")   or ""
        id_  = await inp.get_attribute("id")     or ""
        cls  = await inp.get_attribute("class")  or ""
        val  = await inp.get_attribute("value")  or ""
        print(f"  INPUT  type={t:<10} name={name:<20} id={id_:<15} class={cls:<20} value={val!r}")

    # SELECT + OPTIONS（全件）
    selects = await page.query_selector_all("select")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id")   or ""
        cls  = await sel.get_attribute("class") or ""
        print(f"\n  SELECT name={name!r} id={id_!r} class={cls!r}")
        options = await sel.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            print(f"    OPTION value={v!r:<20} text={txt!r}")

    # BUTTON / SUBMIT
    buttons = await page.query_selector_all(
        "button, input[type=submit], input[type=button], input[type=image]"
    )
    for btn in buttons:
        t    = await btn.get_attribute("type")   or ""
        name = await btn.get_attribute("name")   or ""
        id_  = await btn.get_attribute("id")     or ""
        val  = await btn.get_attribute("value")  or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  BUTTON type={t} name={name!r} id={id_!r} value={val!r} text={txt!r}")

    # ANCHOR
    print("\n  --- リンク ---")
    links = await page.query_selector_all("a")
    for link in links:
        href    = await link.get_attribute("href")    or ""
        onclick = await link.get_attribute("onclick") or ""
        cls     = await link.get_attribute("class")   or ""
        txt     = (await link.inner_text()).strip()
        if txt or onclick:
            print(f"  A  href={href!r}  onclick={onclick!r}  class={cls!r}  text={txt!r}")


async def dump_table_structure(page, label: str):
    hr(f"{label} のテーブル構造")

    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")

    for ti, table in enumerate(tables):
        rows = await table.query_selector_all("tr")
        cls  = await table.get_attribute("class") or ""
        id_  = await table.get_attribute("id")    or ""
        print(f"\nTABLE[{ti}] id={id_!r} class={cls!r} 行数={len(rows)}")

        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_data = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip()
                cls_c   = await cell.get_attribute("class")   or ""
                onclick = await cell.get_attribute("onclick") or ""
                id_c    = await cell.get_attribute("id")      or ""
                img_src = ""
                img = await cell.query_selector("img")
                if img:
                    img_src = await img.get_attribute("src") or ""
                link_href = ""
                a = await cell.query_selector("a")
                if a:
                    link_href = await a.get_attribute("href") or ""

                cell_info = f"{txt!r}"
                if cls_c:    cell_info += f" [cls={cls_c}]"
                if onclick:  cell_info += f" [onclick={onclick[:50]}]"
                if id_c:     cell_info += f" [id={id_c}]"
                if img_src:  cell_info += f" [img={img_src.split('/')[-1]}]"
                if link_href: cell_info += f" [href={link_href[-40:]}]"
                row_data.append(cell_info)

            row_str = " | ".join(row_data[:8])
            if len(row_data) > 8:
                row_str += f" ... (+{len(row_data)-8}列)"
            print(f"  ROW[{ri:02d}]: {row_str}")


async def analyze():
    headful = "--headful" in sys.argv

    launch_opts = dict(
        headless=not headful,
        args=["--no-sandbox", "--disable-setuid-sandbox"],
    )
    if CHROMIUM_EXECUTABLE:
        launch_opts["executable_path"] = CHROMIUM_EXECUTABLE

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_opts)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()

        # ── Step 1: ログインページ ──────────────────────────────
        hr("Step 1: ログインページ")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_all_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ───────────────────────────────
        hr("Step 2: ログイン実行")

        # 利用者番号
        for sel in [
            'input[name="userid"]', 'input[name="user_id"]', 'input[name="userId"]',
            'input[name="memberNo"]', 'input[name="userno"]', 'input[name="loginId"]',
            'input[id="userid"]', 'input[type="text"]:first-of-type',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.fill(USER_ID)
                    print(f"  [OK] 利用者番号: {sel}")
                    break
            except Exception:
                pass

        # パスワード
        for sel in [
            'input[name="passwd"]', 'input[name="password"]',
            'input[name="pass"]', 'input[type="password"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.fill(PASSWORD)
                    print(f"  [OK] パスワード: {sel}")
                    break
            except Exception:
                pass

        # サブミット
        for sel in [
            'input[value="ログイン"]', 'input[type="submit"]',
            'button[type="submit"]', 'button:has-text("ログイン")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.click()
                    print(f"  [OK] サブミット: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "02_after_login")
        await dump_all_elements(page, "ログイン後ページ")
        print(f"\n  現在URL: {page.url}")

        # ── Step 3: お気に入りクリック ─────────────────────────
        hr("Step 3: お気に入りクリック")
        for sel in [
            'a:has-text("お気に入り")', 'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                if elem:
                    txt = (await elem.inner_text()).strip()
                    print(f"  [OK] お気に入り: {sel}  text={txt!r}")
                    await elem.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "03_after_favorite")
        await dump_all_elements(page, "お気に入り後（絞り込み画面）")
        print(f"\n  現在URL: {page.url}")

        # ── Step 4: 日付プルダウン詳細解析 ───────────────────
        hr("Step 4: 日付プルダウン詳細解析（全SELECT・全OPTION）")
        selects = await page.query_selector_all("select")
        print(f"SELECTの数: {len(selects)}")
        for sel in selects:
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id")   or ""
            options = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r}  ({len(options)}件)")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r:<25} text={txt!r}")

        # ── Step 5: 日付選択・検索実行 ───────────────────────
        hr("Step 5: 日付選択 → 検索")
        date_selected = False
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                v   = (await opt.get_attribute("value") or "").strip()
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in TARGET_DATE_TEXTS) or v in TARGET_DATE_VALUES:
                    nm = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v) if v else None
                    print(f"  [OK] 日付選択: name={nm!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません。上記のSELECT/OPTIONの出力を確認してください。")

        for sel in [
            'input[value="検索"]', 'input[value="空き照会"]', 'input[value="照会"]',
            'input[type="submit"]', 'button:has-text("検索")', 'button[type="submit"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    print(f"  [OK] 検索ボタン: {sel}")
                    await elem.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "04_search_results")
        print(f"\n  現在URL: {page.url}")

        # ── Step 6: 検索結果テーブル解析 ─────────────────────
        await dump_table_structure(page, "検索結果（予約一覧テーブル）")

        # D面 / 16:00 を含むセルを特定
        hr("Step 6: D面 / 16:00 に関連するセル・リンク")
        cells = await page.query_selector_all("td, th")
        for i, cell in enumerate(cells):
            txt = (await cell.inner_text()).strip()
            if "D面" in txt or "16:00" in txt or "16時" in txt or "18:00" in txt:
                id_     = await cell.get_attribute("id")      or ""
                cls     = await cell.get_attribute("class")   or ""
                onclick = await cell.get_attribute("onclick") or ""
                print(f"  CELL[{i:03d}] id={id_!r} class={cls!r} onclick={onclick!r} text={txt!r}")
                a = await cell.query_selector("a")
                if a:
                    href = await a.get_attribute("href") or ""
                    atxt = (await a.inner_text()).strip()
                    print(f"    └ A href={href!r} text={atxt!r}")

        await browser.close()
        hr(f"解析完了 → {OUTPUT_DIR}/ フォルダを確認してください")
        print(f"  ファイル: 01〜04の .html / .png")


if __name__ == "__main__":
    asyncio.run(analyze())
