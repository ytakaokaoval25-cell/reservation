"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する。

実行方法:
  python analyze_site.py
  python analyze_site.py --headful   # ブラウザを表示して確認

出力先: analysis_output/
  01_login_page.html/png       ログインページ
  02_after_login.html/png      ログイン後メニュー
  03_after_favorite.html/png   お気に入り絞り込み画面
  04_search_results.html/png   検索結果（予約表）
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

HEADLESS = "--headful" not in sys.argv


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / {step_name}.html")


async def dump_forms(page, label: str):
    """ページ内のすべてのフォーム・インタラクティブ要素を出力"""
    print(f"\n{'='*60}")
    print(f"  {label} のフォーム要素")
    print(f"{'='*60}")

    # ── FORM ──
    for form in await page.query_selector_all("form"):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        id_    = await form.get_attribute("id") or ""
        print(f"\n  FORM id={id_!r} action={action!r} method={method!r}")

    # ── INPUT ──
    for inp in await page.query_selector_all("input"):
        t    = await inp.get_attribute("type")  or "text"
        name = await inp.get_attribute("name")  or ""
        id_  = await inp.get_attribute("id")    or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        ph   = await inp.get_attribute("placeholder") or ""
        print(f"  INPUT  type={t:<10} name={name!r:<20} id={id_!r:<20} class={cls!r:<20} value={val!r}  placeholder={ph!r}")

    # ── SELECT ──
    for sel in await page.query_selector_all("select"):
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id")   or ""
        cls  = await sel.get_attribute("class") or ""
        opts = await sel.query_selector_all("option")
        print(f"\n  SELECT name={name!r} id={id_!r} class={cls!r}  ({len(opts)}件)")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_flag = "★" if await opt.get_attribute("selected") else " "
            print(f"    {sel_flag} value={v!r:<20} text={txt!r}")

    # ── BUTTON / SUBMIT ──
    for btn in await page.query_selector_all("button, input[type=submit], input[type=button]"):
        t    = await btn.get_attribute("type")  or ""
        name = await btn.get_attribute("name")  or ""
        id_  = await btn.get_attribute("id")    or ""
        val  = await btn.get_attribute("value") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  BUTTON type={t:<8} name={name!r:<20} id={id_!r:<20} value={val!r:<20} text={txt!r}")

    # ── LINK ──
    print(f"\n  --- リンク一覧 ---")
    for a in await page.query_selector_all("a"):
        href    = await a.get_attribute("href")    or ""
        onclick = await a.get_attribute("onclick")  or ""
        try:
            txt = (await a.inner_text()).strip()
        except Exception:
            txt = ""
        if txt or href:
            print(f"  A  href={href!r:<50} onclick={onclick[:40]!r:<42} text={txt!r}")


async def dump_table_structure(page, label: str):
    """テーブル構造（予約表）を詳細出力"""
    print(f"\n{'='*60}")
    print(f"  {label} のテーブル構造")
    print(f"{'='*60}")

    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        tbl_id  = await tbl.get_attribute("id")    or ""
        tbl_cls = await tbl.get_attribute("class") or ""
        rows    = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] id={tbl_id!r} class={tbl_cls!r}  行数={len(rows)}")

        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip()
                cls     = await cell.get_attribute("class")   or ""
                onclick = await cell.get_attribute("onclick") or ""
                # セル内のリンク・画像を確認
                link  = await cell.query_selector("a")
                img   = await cell.query_selector("img")
                link_href    = (await link.get_attribute("href")    if link else "") or ""
                link_onclick = (await link.get_attribute("onclick") if link else "") or ""
                img_src      = (await img.get_attribute("src")  if img else "") or ""
                img_alt      = (await img.get_attribute("alt")  if img else "") or ""

                cell_desc = f"[{txt[:12]}]"
                if cls:
                    cell_desc += f"(cls={cls[:20]})"
                if onclick:
                    cell_desc += f"(onclick={onclick[:30]})"
                if link_href or link_onclick:
                    cell_desc += f"(a_href={link_href[:30]}|a_onclick={link_onclick[:30]})"
                if img_src:
                    cell_desc += f"(img={img_src[-20:]}|alt={img_alt})"
                row_info.append(cell_desc)

            print(f"    ROW[{ri:02d}]: {'  '.join(row_info[:10])}")

    # ── D面 / 16:00 を含む要素を特別ハイライト ──
    print(f"\n  --- D面 / 16:00 を含むセル ---")
    for cell in await page.query_selector_all("td, th"):
        txt     = (await cell.inner_text()).strip()
        cls     = await cell.get_attribute("class")   or ""
        onclick = await cell.get_attribute("onclick") or ""
        if "D面" in txt or "16:00" in txt or "16" in txt:
            link  = await cell.query_selector("a")
            img   = await cell.query_selector("img")
            link_href    = (await link.get_attribute("href")    if link else "") or ""
            link_onclick = (await link.get_attribute("onclick") if link else "") or ""
            img_src      = (await img.get_attribute("src")  if img else "") or ""
            img_alt      = (await img.get_attribute("alt")  if img else "") or ""
            print(f"  CELL text={txt!r:<30} class={cls!r:<20} onclick={onclick[:40]!r}")
            if link_href or link_onclick:
                print(f"       a_href={link_href!r:<40} a_onclick={link_onclick[:40]!r}")
            if img_src:
                print(f"       img_src={img_src!r}  alt={img_alt!r}")


async def try_fill_first(page, selectors, value, label):
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000)
            if elem:
                await elem.fill(value)
                print(f"  [OK] {label}: {sel}")
                return True
        except Exception:
            pass
    print(f"  [NG] {label}: 見つからず")
    return False


async def try_click_first(page, selectors, label):
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000)
            if elem:
                await elem.click()
                print(f"  [OK] {label}: {sel}")
                return True
        except Exception:
            pass
    print(f"  [NG] {label}: 見つからず")
    return False


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        await context.add_init_script("""
            window.confirm = () => true;
            window.alert   = () => {};
        """)
        page = await context.new_page()

        # ─────────────────────────────────────────────
        # Step 1: ログインページ解析
        # ─────────────────────────────────────────────
        print("\n[Step 1] ログインページに移動...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_forms(page, "ログインページ")

        # ─────────────────────────────────────────────
        # Step 2: ログイン実行
        # ─────────────────────────────────────────────
        print("\n[Step 2] ログイン実行...")
        await try_fill_first(page, [
            'input[name="userid"]', 'input[name="user_id"]',
            'input[name="memberNo"]', 'input[name="userno"]',
            'input[name="loginId"]', '#userid',
            'input[type="text"]:first-of-type',
        ], USER_ID, "利用者番号")

        await try_fill_first(page, [
            'input[type="password"]', 'input[name="passwd"]',
            'input[name="password"]', 'input[name="pass"]',
        ], PASSWORD, "パスワード")

        await try_click_first(page, [
            'input[value="ログイン"]', 'button:text("ログイン")',
            'input[type="submit"]', 'button[type="submit"]',
        ], "ログインボタン")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_forms(page, "ログイン後ページ")
        print(f"  現在URL: {page.url}")

        # ─────────────────────────────────────────────
        # Step 3: お気に入りクリック
        # ─────────────────────────────────────────────
        print("\n[Step 3] お気に入りをクリック...")
        clicked = False
        for sel in ['a:text("お気に入り")', 'input[value="お気に入り"]',
                    'button:text("お気に入り")']:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                if elem:
                    href    = await elem.get_attribute("href")    or ""
                    onclick = await elem.get_attribute("onclick") or ""
                    val     = await elem.get_attribute("value")   or ""
                    try:
                        txt = (await elem.inner_text()).strip()
                    except Exception:
                        txt = val
                    print(f"  [FOUND] お気に入り要素: {sel}")
                    print(f"    href={href!r}  onclick={onclick!r}  text={txt!r}")
                    await elem.click()
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            # フォールバック: テキスト全探索
            for elem in await page.query_selector_all("a, button, input"):
                try:
                    txt = (await elem.inner_text()).strip()
                except Exception:
                    txt = ""
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    print(f"  [FOUND-fallback] お気に入り: text={txt!r} value={val!r}")
                    await elem.click()
                    clicked = True
                    break

        if not clicked:
            print("  [NG] お気に入りリンクが見つかりませんでした。02_after_login.png を確認してください。")
        else:
            await page.wait_for_load_state("networkidle", timeout=15000)

        await save_step(page, "03_after_favorite")
        await dump_forms(page, "お気に入り後（絞り込み画面）")
        print(f"  現在URL: {page.url}")

        # ─────────────────────────────────────────────
        # Step 4: 日付プルダウン詳細解析（全optionを出力）
        # ─────────────────────────────────────────────
        print("\n[Step 4] 日付プルダウン詳細解析...")
        date_target_values = ["20260619", "2026-06-19", "2026/06/19", "260619"]
        date_target_texts  = ["令和08年06月19日", "令和8年6月19日", "2026年06月19日"]

        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            name = await sel_elem.get_attribute("name") or ""
            id_  = await sel_elem.get_attribute("id")   or ""
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in date_target_texts) or v in date_target_values:
                    print(f"  [日付一致] SELECT name={name!r} id={id_!r} → option value={v!r} text={txt!r}")
                    await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [INFO] 日付が1つのSELECTにない。年月日分割SELECTを確認中...")
            year_p  = ["令和08年", "令和8年", "令和08", "08", "2026"]
            month_p = ["06月", "06", "6月", "6"]
            day_p   = ["19日", "19"]
            for sel_elem in await page.query_selector_all("select"):
                name = await sel_elem.get_attribute("name") or ""
                for opt in await sel_elem.query_selector_all("option"):
                    txt = (await opt.inner_text()).strip()
                    v   = await opt.get_attribute("value") or ""
                    for p in year_p + month_p + day_p:
                        if p == txt or p == v:
                            print(f"  [分割候補] SELECT name={name!r} option value={v!r} text={txt!r}")

        # ─────────────────────────────────────────────
        # Step 5: 検索→結果表解析
        # ─────────────────────────────────────────────
        print("\n[Step 5] 検索実行...")
        await try_click_first(page, [
            'input[value="検索"]', 'button:text("検索")',
            'input[type="submit"]', 'button[type="submit"]',
        ], "検索ボタン")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        print(f"  現在URL: {page.url}")

        await dump_table_structure(page, "検索結果")

        await browser.close()
        print(f"\n解析完了。{OUTPUT_DIR}/ フォルダの .html/.png を確認し、")
        print("reserve.py の定数（セレクター）を必要に応じて修正してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
