"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する

使い方:
  python analyze_site.py
"""

import asyncio
import os
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"
OUTPUT_DIR = "analysis_output"


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[保存] {step_name}.png / {step_name}.html")


async def dump_form_elements(page, label: str):
    """ページ内のすべてのフォーム要素・リンクを出力"""
    print(f"\n{'='*60}")
    print(f"  {label} のフォーム要素")
    print(f"{'='*60}")

    # フォームのaction
    forms = await page.query_selector_all("form")
    for fi, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        print(f"  FORM[{fi}] action={action!r} method={method!r}")

    # input要素
    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r}")

    # select要素（オプション全件表示）
    selects = await page.query_selector_all("select")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        print(f"\n  SELECT name={name!r} id={id_!r} class={cls!r}")
        options = await sel.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected")
            mark = " ← 選択中" if sel_attr is not None else ""
            print(f"    OPTION value={v!r} text={txt!r}{mark}")

    # ボタン・サブミット
    buttons = await page.query_selector_all("button, input[type=submit], input[type=button]")
    for btn in buttons:
        t    = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        val  = await btn.get_attribute("value") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  BUTTON type={t!r} name={name!r} id={id_!r} value={val!r} text={txt!r}")

    # リンク
    print(f"\n  --- リンク一覧 ---")
    links = await page.query_selector_all("a")
    for link in links:
        href    = await link.get_attribute("href") or ""
        onclick = await link.get_attribute("onclick") or ""
        cls     = await link.get_attribute("class") or ""
        try:
            txt = (await link.inner_text()).strip()
        except Exception:
            txt = ""
        if txt or href:
            print(f"  A href={href!r} onclick={onclick!r} class={cls!r} text={txt!r}")


async def dump_table_structure(page, label: str):
    """テーブル構造を詳細出力（予約グリッド解析用）"""
    print(f"\n{'='*60}")
    print(f"  {label} のテーブル構造")
    print(f"{'='*60}")

    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        tbl_id  = await tbl.get_attribute("id") or ""
        tbl_cls = await tbl.get_attribute("class") or ""
        rows    = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] id={tbl_id!r} class={tbl_cls!r}  行数={len(rows)}")

        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_data = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip().replace("\n", " ")
                id_     = await cell.get_attribute("id") or ""
                cls     = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                href_in = ""
                inner_a = await cell.query_selector("a")
                if inner_a:
                    href_in = await inner_a.get_attribute("href") or ""
                cell_info = f"[{txt[:20]}](id={id_} cls={cls} onclick={onclick[:30]} href={href_in[:30]})"
                row_data.append(cell_info)
            print(f"    ROW[{ri}]: {' | '.join(row_data)}")


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
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

        # ──────────────────────────────────────────────
        # Step 1: ログインページ
        # ──────────────────────────────────────────────
        print("\n[Step 1] ログインページに移動...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_form_elements(page, "ログインページ")

        # ──────────────────────────────────────────────
        # Step 2: ログイン実行
        # ──────────────────────────────────────────────
        print("\n[Step 2] ログイン実行...")

        # 利用者番号（複数候補）
        userid_selectors = [
            'input[name="userid"]',
            'input[name="user_id"]',
            'input[name="memberNo"]',
            'input[name="userno"]',
            'input[name="loginId"]',
            'input[name="login_id"]',
            'input[name="id"]',
            '#userid', '#user_id', '#memberNo',
            'input[type="text"]',
        ]
        for sel in userid_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.fill(USER_ID)
                    print(f"  [OK] 利用者番号入力: {sel}")
                    break
            except Exception:
                pass

        # パスワード
        passwd_selectors = [
            'input[type="password"]',
            'input[name="passwd"]',
            'input[name="password"]',
            'input[name="pass"]',
        ]
        for sel in passwd_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.fill(PASSWORD)
                    print(f"  [OK] パスワード入力: {sel}")
                    break
            except Exception:
                pass

        # サブミット
        for sel in ['input[type="submit"]', 'button[type="submit"]', 'input[value*="ログイン"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.click()
                    print(f"  [OK] ログインボタン: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "02_after_login")
        await dump_form_elements(page, "ログイン直後ページ")
        print(f"  現在URL: {page.url}")

        # ──────────────────────────────────────────────
        # Step 3: お気に入りクリック
        # ──────────────────────────────────────────────
        print("\n[Step 3] お気に入りクリック...")

        fav_clicked = False
        fav_selectors = [
            'a:has-text("お気に入り")',
            'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
            '[id*="favorite"]', '[id*="okiniri"]',
            '[class*="favorite"]',
        ]
        for sel in fav_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    txt = (await elem.inner_text()).strip()
                    print(f"  [OK] お気に入り: {sel} text={txt!r}")
                    await elem.click()
                    fav_clicked = True
                    break
            except Exception:
                pass

        if not fav_clicked:
            # テキスト走査フォールバック
            all_elems = await page.query_selector_all("a, button, input, td")
            for elem in all_elems:
                try:
                    txt = (await elem.inner_text()).strip()
                    val = await elem.get_attribute("value") or ""
                    if "お気に入り" in txt or "お気に入り" in val:
                        tag = await elem.evaluate("e => e.tagName")
                        id_ = await elem.get_attribute("id") or ""
                        cls = await elem.get_attribute("class") or ""
                        print(f"  [FOUND] お気に入り: tag={tag} id={id_!r} class={cls!r} text={txt!r}")
                        await elem.click()
                        fav_clicked = True
                        break
                except Exception:
                    pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "03_after_favorite")
        await dump_form_elements(page, "お気に入り後（絞り込み画面）")
        print(f"  現在URL: {page.url}")

        # ──────────────────────────────────────────────
        # Step 4: 日付プルダウン全件解析
        # ──────────────────────────────────────────────
        print("\n[Step 4] 日付プルダウン全件解析...")
        selects = await page.query_selector_all("select")
        for sel in selects:
            name    = await sel.get_attribute("name") or ""
            id_     = await sel.get_attribute("id") or ""
            options = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r} ({len(options)}件)")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    OPTION value={v!r}  text={txt!r}")

        # ──────────────────────────────────────────────
        # Step 5: 令和08年06月19日を選択して検索
        # ──────────────────────────────────────────────
        print("\n[Step 5] 令和08年06月19日を選択...")

        TARGET_TEXTS  = ["令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日", "2026/06/19", "2026年06月19日"]
        TARGET_VALUES = ["20260619", "2026-06-19", "260619"]

        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in TARGET_TEXTS) or v in TARGET_VALUES:
                    sel_name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 日付選択: SELECT name={sel_name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 対象日が見つかりません。HTMLを確認してください")

        # 検索ボタン
        for sel in ['input[value*="検索"]', 'button:has-text("検索")', 'input[type="submit"]']:
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
        await dump_table_structure(page, "検索結果ページ")
        print(f"  現在URL: {page.url}")

        # ──────────────────────────────────────────────
        # Step 6: 検索結果テーブルの詳細解析（D面・16:00〜18:00）
        # ──────────────────────────────────────────────
        print("\n[Step 6] D面 16:00〜18:00 セルを探す...")
        cells = await page.query_selector_all("td, th, a")
        for i, cell in enumerate(cells):
            try:
                txt     = (await cell.inner_text()).strip().replace("\n", " ")
                id_     = await cell.get_attribute("id") or ""
                cls     = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                href    = await cell.get_attribute("href") or ""
                if "D面" in txt or "16:00" in txt or "18:00" in txt or "D" in id_:
                    print(f"  CELL[{i}] tag={await cell.evaluate('e=>e.tagName')} "
                          f"id={id_!r} class={cls!r} "
                          f"onclick={onclick[:60]!r} href={href[:60]!r} text={txt[:60]!r}")
            except Exception:
                pass

        await browser.close()
        print(f"\n\n解析完了。'{OUTPUT_DIR}/' フォルダのHTML/スクリーンショットを確認してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
