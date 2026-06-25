"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する

■ 使い方
  python analyze_site.py              # ヘッドレス
  python analyze_site.py --headful    # ブラウザ表示あり（推奨）
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

# 練習日（confirm操作は行わないが絞り込みまで進む）
DATE_TARGET_VALUES = ["20260619", "2026-06-19", "2026/06/19", "260619"]
DATE_TARGET_TEXTS  = ["令和08年06月19日", "令和8年6月19日", "2026年06月19日"]


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / .html")


def divider(label: str):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)


async def dump_inputs(page):
    """INPUT / SELECT / BUTTON / A をすべて出力"""
    # --- input ---
    inputs = await page.query_selector_all("input")
    if inputs:
        print("\n[INPUT要素]")
        for inp in inputs:
            t    = await inp.get_attribute("type") or "text"
            name = await inp.get_attribute("name") or ""
            id_  = await inp.get_attribute("id")   or ""
            cls  = await inp.get_attribute("class") or ""
            val  = await inp.get_attribute("value") or ""
            print(f"  <input type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r}>")

    # --- select ---
    selects = await page.query_selector_all("select")
    if selects:
        print("\n[SELECT要素]")
        for sel in selects:
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id")   or ""
            cls  = await sel.get_attribute("class") or ""
            print(f"  <select name={name!r} id={id_!r} class={cls!r}>")
            options = await sel.query_selector_all("option")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                sel_attr = await opt.get_attribute("selected")
                mark = " ★" if sel_attr is not None else ""
                print(f"    <option value={v!r}>{txt}{mark}</option>")

    # --- button/submit ---
    buttons = await page.query_selector_all("button, input[type=submit], input[type=button]")
    if buttons:
        print("\n[BUTTON/SUBMIT要素]")
        for btn in buttons:
            t    = await btn.get_attribute("type") or ""
            name = await btn.get_attribute("name") or ""
            id_  = await btn.get_attribute("id")   or ""
            val  = await btn.get_attribute("value") or ""
            try:
                txt = (await btn.inner_text()).strip()
            except Exception:
                txt = val
            print(f"  <button/input type={t!r} name={name!r} id={id_!r} value={val!r} text={txt!r}>")

    # --- a links ---
    links = await page.query_selector_all("a")
    if links:
        print("\n[Aリンク要素]")
        for link in links:
            href    = await link.get_attribute("href")    or ""
            onclick = await link.get_attribute("onclick") or ""
            try:
                txt = (await link.inner_text()).strip()
            except Exception:
                txt = ""
            if txt:
                print(f"  <a href={href!r} onclick={onclick[:60]!r}>{txt}</a>")


async def dump_table_structure(page, label: str):
    """テーブル構造（特にD面×16:00セル付近）を詳細出力"""
    print(f"\n[テーブル構造: {label}]")
    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        tbl_id  = await tbl.get_attribute("id")    or ""
        tbl_cls = await tbl.get_attribute("class") or ""
        rows    = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] id={tbl_id!r} class={tbl_cls!r}  行数={len(rows)}")

        for ri, row in enumerate(rows[:20]):  # 最大20行
            cells = await row.query_selector_all("td, th")
            row_info = []
            for ci, cell in enumerate(cells):
                txt     = (await cell.inner_text()).strip()
                cls     = await cell.get_attribute("class")   or ""
                onclick = await cell.get_attribute("onclick") or ""
                id_     = await cell.get_attribute("id")      or ""
                # セル内リンク
                links_in_cell = await cell.query_selector_all("a")
                link_info = ""
                for lnk in links_in_cell:
                    lhref = await lnk.get_attribute("href") or ""
                    ltxt  = (await lnk.inner_text()).strip()
                    link_info += f"[A href={lhref!r} text={ltxt!r}]"
                # セル内画像
                imgs_in_cell = await cell.query_selector_all("img")
                img_info = ""
                for img in imgs_in_cell:
                    alt = await img.get_attribute("alt") or ""
                    src = await img.get_attribute("src") or ""
                    img_info += f"[IMG alt={alt!r} src={src!r}]"

                info = f"[{ci}]{txt!r}"
                if cls:
                    info += f"(cls={cls!r})"
                if onclick:
                    info += f"(onclick={onclick[:40]!r})"
                if link_info:
                    info += link_info
                if img_info:
                    info += img_info
                row_info.append(info)

            print(f"    ROW[{ri}]: {' | '.join(row_info)}")

    # D面 / 16:00 を含むセルだけ抜き出す
    print("\n[D面・16:00 関連セル]")
    all_cells = await page.query_selector_all("td, th")
    for i, cell in enumerate(all_cells):
        txt     = (await cell.inner_text()).strip()
        cls     = await cell.get_attribute("class")   or ""
        onclick = await cell.get_attribute("onclick") or ""
        id_     = await cell.get_attribute("id")      or ""
        if "D面" in txt or "16:00" in txt or "18:00" in txt:
            print(f"  CELL[{i}] id={id_!r} class={cls!r} onclick={onclick[:80]!r} text={txt!r}")
            links_in_cell = await cell.query_selector_all("a")
            for lnk in links_in_cell:
                lhref = await lnk.get_attribute("href") or ""
                print(f"    -> A href={lhref!r}")


async def try_selector(page, selectors: list, label: str, timeout: int = 3000):
    """複数セレクターを試してヒットしたものを出力"""
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout)
            if elem:
                txt = ""
                try:
                    txt = (await elem.inner_text()).strip()
                except Exception:
                    pass
                val = await elem.get_attribute("value") or ""
                print(f"  [HIT] {label}: {sel!r} text={txt!r} value={val!r}")
                return elem
        except PWTimeout:
            pass
    print(f"  [MISS] {label}: セレクターすべて不一致")
    return None


async def analyze():
    headful = "--headful" in sys.argv
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headful,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP",
        )
        page = await context.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))

        # ─────────────────────────────────────
        divider("Step 1: ログインページ")
        # ─────────────────────────────────────
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
        print(f"URL: {page.url}")
        print(f"Title: {await page.title()}")

        form = await page.query_selector("form")
        if form:
            action = await form.get_attribute("action") or ""
            method = await form.get_attribute("method") or ""
            print(f"FORM action={action!r} method={method!r}")

        await dump_inputs(page)
        await save_step(page, "01_login_page")

        # ─────────────────────────────────────
        divider("Step 2: ログイン実行")
        # ─────────────────────────────────────
        userid_field = await try_selector(page, [
            'input[name="userid"]', 'input[name="user_id"]',
            'input[name="memberNo"]', 'input[name="userno"]',
            'input[name="loginId"]', 'input[name="login_id"]',
            'input[name="id"]', '#userid',
            'input[type="text"]:first-of-type',
        ], "利用者番号フィールド")
        if userid_field:
            await userid_field.fill(USER_ID)

        passwd_field = await try_selector(page, [
            'input[type="password"]', 'input[name="passwd"]',
            'input[name="password"]', 'input[name="pass"]',
        ], "パスワードフィールド")
        if passwd_field:
            await passwd_field.fill(PASSWORD)

        submit = await try_selector(page, [
            'input[value="ログイン"]', 'input[value*="ログイン"]',
            'button:has-text("ログイン")', 'input[type="submit"]',
            'button[type="submit"]',
        ], "ログインボタン")
        if submit:
            await submit.click()

        await page.wait_for_load_state("networkidle", timeout=15_000)
        print(f"ログイン後URL: {page.url}")
        await dump_inputs(page)
        await save_step(page, "02_after_login")

        # ─────────────────────────────────────
        divider("Step 3: お気に入りクリック")
        # ─────────────────────────────────────
        fav = await try_selector(page, [
            'a:has-text("お気に入り")',
            'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
        ], "お気に入り要素")
        if not fav:
            # 全aタグをテキストで探す
            for link in await page.query_selector_all("a, button, input"):
                try:
                    txt = (await link.inner_text()).strip()
                    val = await link.get_attribute("value") or ""
                    if "お気に入り" in txt or "お気に入り" in val:
                        print(f"  [FOUND FALLBACK] お気に入り: text={txt!r} val={val!r}")
                        await link.click()
                        fav = link
                        break
                except Exception:
                    pass

        if fav:
            await page.wait_for_load_state("networkidle", timeout=15_000)

        print(f"お気に入り後URL: {page.url}")
        await dump_inputs(page)
        await save_step(page, "03_after_favorite")

        # ─────────────────────────────────────
        divider("Step 4: 日付プルダウン全オプション表示")
        # ─────────────────────────────────────
        selects = await page.query_selector_all("select")
        print(f"SELECT要素数: {len(selects)}")
        date_sel_elem = None
        for sel in selects:
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id")   or ""
            opts = await sel.query_selector_all("option")
            print(f"\nSELECT name={name!r} id={id_!r}  option数={len(opts)}")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"  value={v!r}  text={txt!r}")
                if not date_sel_elem and (
                    any(t in txt for t in DATE_TARGET_TEXTS)
                    or v in DATE_TARGET_VALUES
                ):
                    date_sel_elem = (sel, v, txt)

        # ─────────────────────────────────────
        divider("Step 5: 日付選択 + 検索実行")
        # ─────────────────────────────────────
        if date_sel_elem:
            sel_el, v, txt = date_sel_elem
            await sel_el.select_option(value=v)
            print(f"[OK] 日付選択: value={v!r} text={txt!r}")
        else:
            print("[WARNING] 対象日のoption未発見。検索ボタンのみ押します。")

        search_btn = await try_selector(page, [
            'input[value="検索"]', 'input[value*="検索"]',
            'button:has-text("検索")', 'input[type="submit"]',
            'button[type="submit"]',
        ], "検索ボタン")
        if search_btn:
            await search_btn.click()
            await page.wait_for_load_state("networkidle", timeout=20_000)

        print(f"検索後URL: {page.url}")
        await save_step(page, "04_search_results")

        # ─────────────────────────────────────
        divider("Step 6: 検索結果テーブル解析（D面・時間帯）")
        # ─────────────────────────────────────
        await dump_table_structure(page, "検索結果")
        await dump_inputs(page)

        await browser.close()
        print(f"\n\n{'='*60}")
        print(f"解析完了！ {OUTPUT_DIR}/ フォルダを確認してください。")
        print(f"{'='*60}")
        print("""
次のステップ:
1. analysis_output/04_search_results.html を開いてD面×16:00セルを確認
2. 「D面・16:00 関連セル」出力の onclick= や href= の値を reserve.py に反映
3. python reserve.py --now --headful でテスト実行
""")


if __name__ == "__main__":
    asyncio.run(analyze())
