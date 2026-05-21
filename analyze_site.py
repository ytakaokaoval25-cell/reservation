"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存し、正確なセレクターを特定する

■ 使い方
  python analyze_site.py
  python analyze_site.py --headful   # ブラウザ表示あり

■ 出力
  analysis_output/ 以下に各ステップのHTMLとスクリーンショットを保存
  コンソールに全フォーム要素・リンク・テーブル構造を出力

■ 準備
  pip install playwright
  playwright install chromium
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"
OUT_DIR   = "analysis_output"


async def save_step(page, step_name: str):
    os.makedirs(OUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [保存] {OUT_DIR}/{step_name}.png / .html")


async def dump_forms(page, label: str):
    """ページ内のすべてのフォーム要素を出力"""
    print(f"\n{'='*60}")
    print(f"  {label} のフォーム要素")
    print(f"{'='*60}")

    # FORMタグ
    for i, form in enumerate(await page.query_selector_all("form")):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        print(f"  FORM[{i}] action={action!r} method={method!r}")

    # INPUT
    for inp in await page.query_selector_all("input"):
        t    = await inp.get_attribute("type")  or "text"
        name = await inp.get_attribute("name")  or ""
        id_  = await inp.get_attribute("id")    or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT  type={t!r:12} name={name!r:20} id={id_!r:20} "
              f"class={cls!r:20} value={val!r}")

    # SELECT
    for sel in await page.query_selector_all("select"):
        name = await sel.get_attribute("name")  or ""
        id_  = await sel.get_attribute("id")    or ""
        cls  = await sel.get_attribute("class") or ""
        opts = await sel.query_selector_all("option")
        print(f"\n  SELECT name={name!r} id={id_!r} class={cls!r} ({len(opts)}件)")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected")
            marker = " ★選択中" if sel_attr is not None else ""
            print(f"    OPTION value={v!r:20} text={txt!r}{marker}")

    # BUTTON / SUBMIT
    print()
    for btn in await page.query_selector_all(
            "button, input[type=submit], input[type=button]"):
        t    = await btn.get_attribute("type")  or ""
        name = await btn.get_attribute("name")  or ""
        id_  = await btn.get_attribute("id")    or ""
        val  = await btn.get_attribute("value") or ""
        txt  = (await btn.inner_text()).strip()
        print(f"  BUTTON type={t!r:10} name={name!r:20} id={id_!r:20} "
              f"value={val!r:20} text={txt!r}")

    # LINK
    print(f"\n  --- リンク一覧 ---")
    for a in await page.query_selector_all("a"):
        href    = await a.get_attribute("href")    or ""
        onclick = await a.get_attribute("onclick") or ""
        txt     = (await a.inner_text()).strip()
        if txt or onclick:
            print(f"  A href={href!r:40} onclick={onclick!r:30} text={txt!r}")


async def dump_table(page, label: str):
    """テーブル構造を全出力"""
    print(f"\n{'='*60}")
    print(f"  {label} のテーブル構造")
    print(f"{'='*60}")

    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        id_  = await tbl.get_attribute("id")    or ""
        cls  = await tbl.get_attribute("class") or ""
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] id={id_!r} class={cls!r} 行数={len(rows)}")

        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for ci, cell in enumerate(cells):
                txt     = (await cell.inner_text()).strip().replace("\n", " ")[:30]
                id_c    = await cell.get_attribute("id")      or ""
                cls_c   = await cell.get_attribute("class")   or ""
                onclick = await cell.get_attribute("onclick") or ""
                inner_a = await cell.query_selector("a")
                href    = (await inner_a.get_attribute("href") or "") if inner_a else ""

                info = f"[{ci}]{txt!r}"
                if id_c:    info += f"(id={id_c!r})"
                if cls_c:   info += f"(cls={cls_c!r})"
                if onclick: info += f"(onclick={onclick[:40]!r})"
                if href:    info += f"(href={href[:40]!r})"
                row_info.append(info)

            print(f"    ROW[{ri}]: {' | '.join(row_info[:10])}")


async def try_login(page):
    print("\n[Step 1] ログインページ解析...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
    await save_step(page, "01_login_page")
    await dump_forms(page, "ログインページ")

    # ログイン実行
    print("\n[Step 2] ログイン実行...")
    userid_selectors = [
        'input[name="userid"]', 'input[name="userno"]',
        'input[name="user_id"]', 'input[name="memberNo"]',
        'input[name="loginId"]', 'input[name="id"]',
        '#userid', 'input[type="text"]',
    ]
    for sel in userid_selectors:
        try:
            e = await page.wait_for_selector(sel, timeout=1500)
            if e:
                await e.fill(USER_ID)
                print(f"  [OK] 利用者番号: {sel}")
                break
        except Exception:
            pass

    for sel in ['input[type="password"]', 'input[name="passwd"]',
                'input[name="password"]', 'input[name="pass"]']:
        try:
            e = await page.wait_for_selector(sel, timeout=1500)
            if e:
                await e.fill(PASSWORD)
                print(f"  [OK] パスワード: {sel}")
                break
        except Exception:
            pass

    for sel in ['input[value="ログイン"]', 'button:text("ログイン")',
                'input[type="submit"]', 'button[type="submit"]']:
        try:
            e = await page.wait_for_selector(sel, timeout=1500)
            if e:
                await e.click()
                print(f"  [OK] ログインボタン: {sel}")
                break
        except Exception:
            pass

    await page.wait_for_load_state("networkidle", timeout=20000)
    await save_step(page, "02_after_login")
    await dump_forms(page, "ログイン後メニュー")
    print(f"  URL: {page.url}")


async def try_favorite(page):
    print("\n[Step 3] お気に入りクリック...")
    for sel in ['a:text("お気に入り")', 'input[value="お気に入り"]',
                'button:text("お気に入り")', '[onclick*="okiniri"]']:
        try:
            e = await page.wait_for_selector(sel, timeout=2000)
            if e:
                await e.click()
                print(f"  [OK] お気に入り: {sel}")
                break
        except Exception:
            pass
    else:
        # テキスト全走査
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            txt = (await elem.inner_text()).strip()
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（テキスト走査）: {txt!r}")
                break

    await page.wait_for_load_state("networkidle", timeout=20000)
    await save_step(page, "03_filter_page")
    await dump_forms(page, "絞り込みページ（日付SELECT詳細）")
    print(f"  URL: {page.url}")


async def analyze():
    headful = "--headful" in sys.argv
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headful)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()

        try:
            await try_login(page)
            await try_favorite(page)

            # ── 検索を実行して結果テーブルを解析 ─────────────────
            print("\n[Step 4] 検索実行（最初の日付で検索）...")
            for sel in ['input[type="submit"]', 'button[type="submit"]',
                        'input[value*="検索"]', 'a:text("検索")']:
                try:
                    e = await page.wait_for_selector(sel, timeout=2000)
                    if e:
                        await e.click()
                        print(f"  [OK] 検索: {sel}")
                        break
                except Exception:
                    pass

            await page.wait_for_load_state("networkidle", timeout=20000)
            await save_step(page, "04_search_results")
            await dump_table(page, "検索結果")
            print(f"  URL: {page.url}")

            # ── D面・16:00 を含むセルを特定 ────────────────────
            print("\n=== D面 / 16:00 を含む要素 ===")
            for cell in await page.query_selector_all("td, th, a, input"):
                txt = (await cell.inner_text()).strip()
                id_ = await cell.get_attribute("id")      or ""
                cls = await cell.get_attribute("class")   or ""
                onclick = await cell.get_attribute("onclick") or ""
                if "D面" in txt or "16:00" in txt or "18:00" in txt:
                    print(f"  TAG={cell} id={id_!r} cls={cls!r} "
                          f"onclick={onclick!r} text={txt!r}")

        finally:
            await browser.close()

    print(f"\n\n解析完了。{OUT_DIR}/ フォルダの HTML/PNGファイルを確認してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
