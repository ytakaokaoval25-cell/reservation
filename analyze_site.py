"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する

実行:
  python analyze_site.py
  python analyze_site.py --headful   # ブラウザ表示あり

出力フォルダ: analysis_output/
  *.png  -- スクリーンショット
  *.html -- ページHTML
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / {step_name}.html  (URL: {page.url})")


async def dump_all_elements(page, label: str):
    """ページ内の全フォーム要素・リンクを詳細出力"""
    print(f"\n{'='*60}")
    print(f"[{label}]")

    # フォーム
    forms = await page.query_selector_all("form")
    print(f"\n--- FORM ({len(forms)}件) ---")
    for i, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        print(f"  FORM[{i}] action={action!r} method={method!r}")

    # INPUT
    inputs = await page.query_selector_all("input")
    print(f"\n--- INPUT ({len(inputs)}件) ---")
    for inp in inputs:
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r}")

    # SELECT / OPTION
    selects = await page.query_selector_all("select")
    print(f"\n--- SELECT ({len(selects)}件) ---")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        options = await sel.query_selector_all("option")
        print(f"  SELECT name={name!r} id={id_!r} class={cls!r}  ({len(options)}件のoption)")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            selected = await opt.get_attribute("selected")
            mark = " ← selected" if selected is not None else ""
            print(f"    OPTION value={v!r} text={txt!r}{mark}")

    # BUTTON / SUBMIT
    buttons = await page.query_selector_all("button, input[type=submit], input[type=button]")
    print(f"\n--- BUTTON ({len(buttons)}件) ---")
    for btn in buttons:
        tag  = await btn.evaluate("el => el.tagName.toLowerCase()")
        t    = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        cls  = await btn.get_attribute("class") or ""
        val  = await btn.get_attribute("value") or ""
        if tag == "button":
            txt = (await btn.inner_text()).strip()
        else:
            txt = val
        print(f"  {tag.upper()} type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r} text={txt!r}")

    # LINK (a タグ)
    links = await page.query_selector_all("a")
    print(f"\n--- A ({len(links)}件) ---")
    for link in links:
        href   = await link.get_attribute("href") or ""
        id_    = await link.get_attribute("id") or ""
        cls    = await link.get_attribute("class") or ""
        onclick = await link.get_attribute("onclick") or ""
        txt    = (await link.inner_text()).strip()
        if txt or onclick:
            print(f"  A href={href!r} id={id_!r} class={cls!r} onclick={onclick!r} text={txt!r}")


async def dump_table_structure(page, label: str):
    """予約テーブルの構造を詳細に出力"""
    print(f"\n{'='*60}")
    print(f"[{label} - テーブル構造]")

    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")

    for ti, table in enumerate(tables):
        id_  = await table.get_attribute("id") or ""
        cls  = await table.get_attribute("class") or ""
        rows = await table.query_selector_all("tr")
        print(f"\nTABLE[{ti}] id={id_!r} class={cls!r}  ({len(rows)}行)")

        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            print(f"  ROW[{ri}] ({len(cells)}列):")
            for ci, cell in enumerate(cells):
                tag     = await cell.evaluate("el => el.tagName.toLowerCase()")
                id_     = await cell.get_attribute("id") or ""
                cls     = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                colspan = await cell.get_attribute("colspan") or "1"
                rowspan = await cell.get_attribute("rowspan") or "1"
                txt     = (await cell.inner_text()).strip().replace("\n", " ")

                # セル内のリンクも確認
                links_in_cell = await cell.query_selector_all("a")
                link_info = ""
                for lnk in links_in_cell:
                    lhref = await lnk.get_attribute("href") or ""
                    lonclick = await lnk.get_attribute("onclick") or ""
                    ltxt  = (await lnk.inner_text()).strip()
                    limg  = await lnk.query_selector("img")
                    limg_src = ""
                    if limg:
                        limg_src = await limg.get_attribute("src") or ""
                    link_info += f" [LINK href={lhref!r} onclick={lonclick!r} text={ltxt!r} img={limg_src!r}]"

                print(
                    f"    CELL[{ci}] {tag.upper()} "
                    f"id={id_!r} class={cls!r} "
                    f"onclick={onclick[:60]!r} "
                    f"colspan={colspan} rowspan={rowspan} "
                    f"text={txt[:40]!r}"
                    f"{link_info}"
                )


async def try_fill(page, selectors, value, label):
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if elem:
                await elem.fill(value)
                print(f"  [OK] {label}: {sel}")
                return True
        except Exception:
            pass
    print(f"  [FAIL] {label}: 見つかりません")
    return False


async def try_click(page, selectors, label):
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if elem:
                await elem.click()
                print(f"  [OK] {label}: {sel}")
                return True
        except Exception:
            pass
    # テキストフォールバック
    for selector_type in ["a", "button", "input"]:
        elems = await page.query_selector_all(selector_type)
        for elem in elems:
            try:
                if selector_type in ["a", "button"]:
                    txt = (await elem.inner_text()).strip()
                else:
                    txt = (await elem.get_attribute("value") or "").strip()
                if label.split("：")[-1].strip() in txt or label.split(":")[-1].strip() in txt:
                    await elem.click()
                    print(f"  [OK] {label}（テキストフォールバック）: text={txt!r}")
                    return True
            except Exception:
                pass
    print(f"  [FAIL] {label}: 見つかりません")
    return False


async def analyze():
    headless = "--headful" not in sys.argv
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
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

        # ── Step 1: ログインページ ────────────────────────────────
        print("\n[Step 1] ログインページ解析...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_all_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ──────────────────────────────────
        print("\n[Step 2] ログイン実行...")
        await try_fill(page, [
            'input[name="userid"]', 'input[name="user_id"]',
            'input[name="memberNo"]', 'input[name="userno"]',
            'input[name="loginId"]', 'input[name="login_id"]',
            'input[name="id"]', '#userid', 'input[type="text"]',
        ], USER_ID, "利用者番号")

        await try_fill(page, [
            'input[type="password"]', 'input[name="passwd"]',
            'input[name="password"]', 'input[name="pass"]',
        ], PASSWORD, "パスワード")

        await try_click(page, [
            'input[value="ログイン"]', 'button:has-text("ログイン")',
            'input[type="submit"]', 'button[type="submit"]',
        ], "ログインボタン")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_all_elements(page, "ログイン後ページ")

        # ── Step 3: お気に入りクリック ────────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        await try_click(page, [
            'a:has-text("お気に入り")', 'input[value="お気に入り"]',
            'button:has-text("お気に入り")',
        ], "お気に入り")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        await dump_all_elements(page, "お気に入り後（絞り込み画面）")

        # ── Step 4: 日付SELECTを全件出力 ─────────────────────────
        print("\n[Step 4] 日付プルダウン全件出力...")
        selects = await page.query_selector_all("select")
        print(f"SELECT要素数: {len(selects)}")
        for si, sel in enumerate(selects):
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id") or ""
            options = await sel.query_selector_all("option")
            print(f"\nSELECT[{si}] name={name!r} id={id_!r}  ({len(options)}件)")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"  OPTION value={v!r} text={txt!r}")

        # ── Step 5: 日付選択・検索 ────────────────────────────────
        print("\n[Step 5] 令和08年06月19日を選択して検索...")
        TARGET_TEXTS  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19"]
        TARGET_VALUES = ["20260619", "2026-06-19"]
        date_selected = False

        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in TARGET_TEXTS) or v in TARGET_VALUES:
                    await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                    print(f"  [OK] 日付選択: value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません（スクリーンショット参照）")

        await try_click(page, [
            'input[value="検索"]', 'input[value*="検索"]',
            'button:has-text("検索")', 'input[type="submit"]',
            'button[type="submit"]',
        ], "検索ボタン")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")

        # ── Step 6: 検索結果テーブル詳細解析 ─────────────────────
        print("\n[Step 6] 検索結果テーブル詳細解析...")
        await dump_table_structure(page, "検索結果")

        # D面 / 16:00 に関連するセルをハイライト表示
        print("\n--- D面 or 16:00 を含むセル ---")
        cells = await page.query_selector_all("td, th")
        for i, cell in enumerate(cells):
            txt = (await cell.inner_text()).strip()
            if "D面" in txt or "16:00" in txt or "16" in txt:
                id_     = await cell.get_attribute("id") or ""
                cls     = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                links   = await cell.query_selector_all("a")
                link_hrefs = [await l.get_attribute("href") or "" for l in links]
                print(
                    f"  CELL[{i}] id={id_!r} class={cls!r} "
                    f"onclick={onclick!r} text={txt!r} links={link_hrefs}"
                )

        await browser.close()
        print(f"\n\n{'='*60}")
        print(f"解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(analyze())
