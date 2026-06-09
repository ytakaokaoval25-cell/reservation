"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する

使い方:
  python analyze_site.py
"""

import asyncio
import os
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
    print(f"  [SAVED] {step_name}.png / {step_name}.html")


async def dump_all_forms(page, label: str):
    """ページ内フォーム要素をすべてコンソール出力"""
    print(f"\n{'='*60}")
    print(f"【{label}】フォーム・リンク解析")
    print(f"{'='*60}")

    # フォームのaction
    for form in await page.query_selector_all("form"):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or "get"
        name   = await form.get_attribute("name") or ""
        print(f"  FORM  name={name!r}  action={action!r}  method={method!r}")

    # hidden含む全input
    print()
    for inp in await page.query_selector_all("input"):
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT  type={t!r:12}  name={name!r:25}  id={id_!r:20}  class={cls!r:20}  value={val!r}")

    # select + option
    print()
    for sel in await page.query_selector_all("select"):
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        print(f"  SELECT  name={name!r}  id={id_!r}  class={cls!r}")
        for opt in await sel.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected")
            mark = " ← SELECTED" if sel_attr is not None else ""
            print(f"    OPTION  value={v!r:20}  text={txt!r}{mark}")

    # ボタン系
    print()
    for btn in await page.query_selector_all(
        "button, input[type='submit'], input[type='button'], input[type='image']"
    ):
        t    = await btn.get_attribute("type") or "button"
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        val  = await btn.get_attribute("value") or ""
        txt  = (await btn.inner_text()).strip()
        print(f"  BUTTON  type={t!r}  name={name!r}  id={id_!r}  value={val!r}  text={txt!r}")

    # リンク（テキスト付き）
    print()
    for a in await page.query_selector_all("a"):
        href    = await a.get_attribute("href") or ""
        onclick = await a.get_attribute("onclick") or ""
        txt     = (await a.inner_text()).strip()
        if txt or onclick:
            print(f"  A  href={href!r:40}  onclick={onclick!r:30}  text={txt!r}")


async def dump_table_detail(page, label: str):
    """テーブル構造の詳細出力（予約カレンダー解析用）"""
    print(f"\n{'='*60}")
    print(f"【{label}】テーブル構造")
    print(f"{'='*60}")

    tables = await page.query_selector_all("table")
    print(f"テーブル総数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        print(f"\nTABLE[{ti}]  行数={len(rows)}")
        tbl_id  = await tbl.get_attribute("id") or ""
        tbl_cls = await tbl.get_attribute("class") or ""
        if tbl_id or tbl_cls:
            print(f"  id={tbl_id!r}  class={tbl_cls!r}")

        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for ci, cell in enumerate(cells):
                txt     = (await cell.inner_text()).strip()
                cls     = await cell.get_attribute("class") or ""
                id_     = await cell.get_attribute("id") or ""
                onclick = await cell.get_attribute("onclick") or ""
                # 子要素のaタグ確認
                a_tags = await cell.query_selector_all("a")
                a_hrefs = []
                for a in a_tags:
                    h = await a.get_attribute("href") or ""
                    oc = await a.get_attribute("onclick") or ""
                    a_hrefs.append(f"href={h!r} onclick={oc!r}")

                cell_str = f"[{ci}]{txt!r}"
                if cls:
                    cell_str += f"(cls={cls!r})"
                if id_:
                    cell_str += f"(id={id_!r})"
                if onclick:
                    cell_str += f"(onclick={onclick!r})"
                if a_hrefs:
                    cell_str += f"(a:{','.join(a_hrefs)})"
                row_info.append(cell_str)
            print(f"  ROW[{ri}]: {' | '.join(row_info)}")


async def try_login(page):
    """ログイン試行"""
    print("\n[Step 1] ログインページに移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
    await save_step(page, "01_login_page")
    await dump_all_forms(page, "ログインページ")

    # 利用者番号
    for sel in [
        'input[name="userid"]', 'input[name="user_id"]', 'input[name="memberNo"]',
        'input[name="userno"]', 'input[name="loginId"]', 'input[name="login_id"]',
        'input[name="id"]', '#userid',
        'input[type="text"]:nth-of-type(1)',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=1500, state="visible")
            if elem:
                await elem.fill(USER_ID)
                print(f"  [OK] 利用者番号: {sel}")
                break
        except PWTimeout:
            pass

    # パスワード
    for sel in [
        'input[type="password"]', 'input[name="passwd"]',
        'input[name="password"]', 'input[name="pass"]',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=1500, state="visible")
            if elem:
                await elem.fill(PASSWORD)
                print(f"  [OK] パスワード: {sel}")
                break
        except PWTimeout:
            pass

    # サブミット
    for sel in [
        'input[value="ログイン"]', 'button:text("ログイン")',
        'input[type="submit"]', 'button[type="submit"]',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=1500)
            if elem:
                await elem.click()
                print(f"  [OK] ログインボタン: {sel}")
                break
        except PWTimeout:
            pass

    await page.wait_for_load_state("networkidle", timeout=20000)
    await save_step(page, "02_after_login")
    await dump_all_forms(page, "ログイン後ページ")
    print(f"  現在URL: {page.url}")


async def try_favorite(page):
    """お気に入りクリック"""
    print("\n[Step 2] お気に入りクリック...")
    clicked = False
    for sel in [
        'a:text("お気に入り")', 'input[value="お気に入り"]',
        'button:text("お気に入り")', '[onclick*="okini"]',
        '[onclick*="favor"]', '[class*="favor"]',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if elem:
                print(f"  [OK] お気に入り: {sel}")
                await elem.click()
                clicked = True
                break
        except PWTimeout:
            pass

    if not clicked:
        # フォールバック: テキストスキャン
        for elem in await page.query_selector_all("a, button, input[type=submit], input[type=button]"):
            txt = (await elem.inner_text()).strip()
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                print(f"  [OK] お気に入り(fallback): text={txt!r}")
                await elem.click()
                clicked = True
                break
    if not clicked:
        print("  [WARNING] お気に入りが見つかりません")

    await page.wait_for_load_state("networkidle", timeout=20000)
    await save_step(page, "03_favorite_filter")
    await dump_all_forms(page, "お気に入り後（絞り込み画面）")
    print(f"  現在URL: {page.url}")


async def try_date_and_search(page):
    """日付選択・検索"""
    print("\n[Step 3] 日付プルダウン詳細解析 + 令和08年06月19日 選択...")

    selects = await page.query_selector_all("select")
    date_selected = False
    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if ("令和08年06月19日" in txt or "令和8年6月19日" in txt
                    or v in ("20260619", "2026-06-19", "2026/06/19")):
                name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択: name={name!r}  value={v!r}  text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    if not date_selected:
        print("  [WARNING] 令和08年06月19日が見つかりません。全オプションを確認してください↑")

    # 検索ボタン
    for sel in [
        'input[value="検索"]', 'button:text("検索")', 'input[value*="検索"]',
        'input[type="submit"]', 'button[type="submit"]', 'a:text("検索")',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000)
            if elem:
                print(f"  [OK] 検索ボタン: {sel}")
                await elem.click()
                break
        except PWTimeout:
            pass

    await page.wait_for_load_state("networkidle", timeout=20000)
    await save_step(page, "04_search_results")
    await dump_table_detail(page, "検索結果（予約カレンダー）")
    print(f"  現在URL: {page.url}")

    # D面 16:00 関連のセルを追加抽出
    print("\n【D面 / 16:00 関連セル詳細】")
    for cell in await page.query_selector_all("td, th, a"):
        txt = (await cell.inner_text()).strip()
        cls = await cell.get_attribute("class") or ""
        id_ = await cell.get_attribute("id") or ""
        onclick = await cell.get_attribute("onclick") or ""
        href    = await cell.get_attribute("href") or ""
        if any(k in txt for k in ("D面", "16:00", "18:00", "○", "◯", "〇", "●")):
            print(f"  TAG={cell.__class__.__name__}  text={txt!r}  cls={cls!r}  "
                  f"id={id_!r}  onclick={onclick!r}  href={href!r}")


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()

        await try_login(page)
        await try_favorite(page)
        await try_date_and_search(page)

        await browser.close()
        print(f"\n\n✅ 解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print("   コンソール出力のSELECT/OPTION/TABLEの情報でreserve.pyを修正してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
