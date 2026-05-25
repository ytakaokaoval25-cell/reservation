"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・セレクター情報・スクリーンショットを保存する。

reserve.py が動かない場合、先にこのスクリプトを実行して
analysis_output/ フォルダの .html と .png を確認してください。

使い方:
  python analyze_site.py
"""

import asyncio
import os
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUT_DIR    = "analysis_output"


async def save_step(page, name: str):
    os.makedirs(OUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUT_DIR}/{name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUT_DIR}/{name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[保存] {name}.png / {name}.html → {OUT_DIR}/")


async def dump_forms(page, label: str):
    print(f"\n{'='*50}")
    print(f" {label} のフォーム要素")
    print(f"{'='*50}")

    # フォーム属性
    forms = await page.query_selector_all("form")
    for i, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        print(f"  FORM[{i}] action={action!r} method={method!r}")

    # INPUT
    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t    = await inp.get_attribute("type")  or "text"
        name = await inp.get_attribute("name")  or ""
        id_  = await inp.get_attribute("id")    or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT  type={t!r:10} name={name!r:25} id={id_!r:20} class={cls!r:20} value={val!r}")

    # SELECT + OPTIONS（全件）
    selects = await page.query_selector_all("select")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id")   or ""
        cls  = await sel.get_attribute("class") or ""
        options = await sel.query_selector_all("option")
        print(f"\n  SELECT name={name!r} id={id_!r} class={cls!r}  ({len(options)}件)")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected")
            mark = "◀selected" if sel_attr is not None else ""
            print(f"    OPTION value={v!r:20} text={txt!r:30} {mark}")

    # BUTTON / SUBMIT
    buttons = await page.query_selector_all("button, input[type=submit], input[type=button]")
    for btn in buttons:
        t    = await btn.get_attribute("type")  or ""
        name = await btn.get_attribute("name")  or ""
        id_  = await btn.get_attribute("id")    or ""
        val  = await btn.get_attribute("value") or ""
        txt  = (await btn.inner_text()).strip()
        print(f"  BUTTON type={t!r} name={name!r:20} id={id_!r:20} value={val!r:20} text={txt!r}")

    # LINKS（メニュー用）
    links = await page.query_selector_all("a")
    print(f"\n  --- リンク ({len(links)}件) ---")
    for link in links:
        href = await link.get_attribute("href") or ""
        onclick = await link.get_attribute("onclick") or ""
        txt = (await link.inner_text()).strip()
        if txt:
            print(f"  A  href={href!r:40} onclick={onclick!r:30} text={txt!r}")


async def dump_tables(page, label: str):
    print(f"\n{'='*50}")
    print(f" {label} のテーブル構造")
    print(f"{'='*50}")
    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")
    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        tbl_id  = await tbl.get_attribute("id")    or ""
        tbl_cls = await tbl.get_attribute("class") or ""
        print(f"\n  TABLE[{ti}] id={tbl_id!r} class={tbl_cls!r} 行数={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td,th")
            row_parts = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip()
                cls     = await cell.get_attribute("class")   or ""
                onclick = await cell.get_attribute("onclick") or ""
                links_in_cell = await cell.query_selector_all("a,input[type=radio],input[type=submit]")
                link_info = ""
                for lnk in links_in_cell:
                    href  = await lnk.get_attribute("href")    or ""
                    lval  = await lnk.get_attribute("value")   or ""
                    ltxt  = (await lnk.inner_text()).strip()
                    link_info += f"[{href or lval or ltxt}]"
                row_parts.append(f"{txt}(cls={cls!r}{(',onclick=' + onclick) if onclick else ''}{link_info})")
            print(f"    ROW[{ri:2d}]: {' | '.join(row_parts[:10])}")

    # D面・16:00 を含むセルを強調表示
    print(f"\n  --- 「D面」「16:00」を含むセル ---")
    cells_all = await page.query_selector_all("td,th")
    for i, cell in enumerate(cells_all):
        txt     = (await cell.inner_text()).strip()
        id_     = await cell.get_attribute("id")      or ""
        cls     = await cell.get_attribute("class")   or ""
        onclick = await cell.get_attribute("onclick") or ""
        if "D面" in txt or "16:00" in txt or "18:00" in txt:
            print(f"  CELL[{i:3d}] id={id_!r} class={cls!r} onclick={onclick!r} text={txt!r}")


async def try_login(page):
    """ログイン実行（複数セレクター候補を試す）"""
    # 利用者番号
    for sel in [
        'input[name="riyousya_bango"]',
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[type="text"]:first-of-type',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if elem:
                await elem.fill(USER_ID)
                print(f"  [OK] 利用者番号: {sel}")
                break
        except Exception:
            pass

    # パスワード
    for sel in [
        'input[name="passwd"]',
        'input[type="password"]',
        'input[name="password"]',
        'input[name="pass"]',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if elem:
                await elem.fill(PASSWORD)
                print(f"  [OK] パスワード: {sel}")
                break
        except Exception:
            pass

    # サブミット
    for sel in [
        'input[value="ログイン"]',
        'input[type="submit"]',
        'button[type="submit"]',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if elem:
                await elem.click()
                print(f"  [OK] サブミット: {sel}")
                break
        except Exception:
            pass

    await page.wait_for_load_state("networkidle", timeout=15000)


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # ブラウザを表示して確認しやすくする
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
        page = await context.new_page()

        # ── Step 1: ログインページ ─────────────────────────
        print("\n[Step 1] ログインページへ移動...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_forms(page, "ログインページ")

        # ── Step 2: ログイン実行 ──────────────────────────
        print("\n[Step 2] ログイン実行...")
        await try_login(page)
        await save_step(page, "02_after_login")
        await dump_forms(page, "ログイン後（メインメニュー）")
        print(f"  現在URL: {page.url}")

        # ── Step 3: お気に入りクリック ────────────────────
        print("\n[Step 3] お気に入りクリック...")
        for sel in [
            'a:has-text("お気に入り")',
            'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                if elem:
                    print(f"  [OK] {sel}")
                    await elem.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        await dump_forms(page, "お気に入り後（絞り込み画面）")
        print(f"  現在URL: {page.url}")

        # ── Step 4: 日付プルダウン全件出力 ───────────────
        print("\n[Step 4] 日付プルダウン全件解析...")
        selects = await page.query_selector_all("select")
        for sel in selects:
            name    = await sel.get_attribute("name") or ""
            id_     = await sel.get_attribute("id")   or ""
            options = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r}  ({len(options)}件)")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r:25}  text={txt!r}")

        # ── Step 5: 日付選択 + 検索 ───────────────────────
        print("\n[Step 5] 令和08年06月19日を選択して検索...")
        date_target_texts  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19"]
        date_target_values = ["20260619", "2026-06-19", "260619"]
        date_selected = False

        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in date_target_texts) or v in date_target_values:
                    name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 日付選択: name={name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません。スクリーンショット 03_after_favorite.png を確認してください")

        for sel in [
            'input[value*="検索"]',
            'input[type="submit"]',
            'button[type="submit"]',
            'button:has-text("検索")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    print(f"  [OK] 検索ボタン: {sel}")
                    await elem.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        await dump_tables(page, "検索結果（時間割テーブル）")
        print(f"  現在URL: {page.url}")

        await browser.close()
        print(f"\n{'='*60}")
        print(f"解析完了！{OUT_DIR}/ フォルダのファイルを確認してください。")
        print("reserve.py のセレクターが合わない場合は、")
        print("04_search_results.html を開いて D面の行構造を確認してください。")
        print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(analyze())
