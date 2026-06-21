"""
まんまるよやく2 サイト構造解析スクリプト
各ステップの HTML・スクリーンショットを保存し、正確なセレクターを特定する。
reserve.py を実行する前にこのスクリプトを走らせてセレクターを確認すること。

使い方:
  python analyze_site.py
  → analysis_output/ に HTML と PNG が保存される
"""

import asyncio
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

# 確認したい日付
DATE_TEXTS  = ["令和08年06月19日", "令和8年6月19日", "2026年06月19日", "2026/06/19"]
DATE_VALUES = ["20260619", "2026-06-19", "260619"]


async def save_step(page, name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [SAVED] {name}.png / {name}.html → {OUTPUT_DIR}/")


async def dump_inputs(page, label: str):
    """INPUT / SELECT / BUTTON / A を全件ダンプ"""
    print(f"\n{'='*10} {label} {'='*10}")

    # INPUT
    for el in await page.query_selector_all("input"):
        t   = await el.get_attribute("type")  or "text"
        n   = await el.get_attribute("name")  or ""
        i   = await el.get_attribute("id")    or ""
        c   = await el.get_attribute("class") or ""
        v   = await el.get_attribute("value") or ""
        print(f"  INPUT  type={t:<10} name={n!r:<20} id={i!r:<20} class={c!r:<20} value={v!r}")

    # SELECT + OPTION（全件）
    for el in await page.query_selector_all("select"):
        n   = await el.get_attribute("name")  or ""
        i   = await el.get_attribute("id")    or ""
        c   = await el.get_attribute("class") or ""
        opts = await el.query_selector_all("option")
        print(f"  SELECT name={n!r:<20} id={i!r:<20} class={c!r} [{len(opts)} options]")
        for opt in opts:
            v   = (await opt.get_attribute("value") or "").strip()
            txt = (await opt.inner_text()).strip()
            print(f"    OPTION  value={v!r:<20} text={txt!r}")

    # BUTTON / submit
    for el in await page.query_selector_all("button, input[type=submit], input[type=button]"):
        t   = await el.get_attribute("type")  or ""
        n   = await el.get_attribute("name")  or ""
        i   = await el.get_attribute("id")    or ""
        v   = await el.get_attribute("value") or ""
        try:
            txt = (await el.inner_text()).strip()
        except Exception:
            txt = v
        print(f"  BUTTON type={t:<8} name={n!r:<15} id={i!r:<15} value={v!r:<15} text={txt!r}")

    # A リンク
    print("  --- リンク ---")
    for el in await page.query_selector_all("a"):
        href = await el.get_attribute("href") or ""
        try:
            txt = (await el.inner_text()).strip()
        except Exception:
            txt = ""
        if txt:
            print(f"  A  href={href!r:<50} text={txt!r}")


async def dump_table_structure(page):
    """テーブルの行・列構造と各セルの属性を全件ダンプ"""
    tables = await page.query_selector_all("table")
    print(f"\n  テーブル数: {len(tables)}")
    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        tbl_cls = await tbl.get_attribute("class") or ""
        tbl_id  = await tbl.get_attribute("id")    or ""
        print(f"\n  TABLE[{ti}] id={tbl_id!r} class={tbl_cls!r}  行数={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_data = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip()
                cls     = await cell.get_attribute("class")   or ""
                onclick = await cell.get_attribute("onclick") or ""
                cid     = await cell.get_attribute("id")      or ""
                summary = f"{txt!r}(id={cid!r},cls={cls!r},onclick={onclick[:40]!r})"
                row_data.append(summary)
            print(f"    ROW[{ri:02d}]: {' | '.join(row_data[:10])}")


async def try_click_first(page, selectors: list, label: str, timeout=3000) -> bool:
    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                await el.click()
                print(f"  [OK] {label}: {sel}")
                return True
        except (PWTimeout, Exception):
            pass
    return False


async def try_fill_first(page, selectors: list, value: str, label: str, timeout=3000) -> bool:
    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                await el.fill(value)
                print(f"  [OK] {label}: {sel}")
                return True
        except (PWTimeout, Exception):
            pass
    return False


async def analyze():
    print("=" * 60)
    print("  まんまるよやく2 サイト構造解析")
    print(f"  出力先: {OUTPUT_DIR}/")
    print("=" * 60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await ctx.new_page()

        # ────────── Step 1: ログインページ ──────────────────────────
        print("\n[Step 1] ログインページ解析...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
        await save_step(page, "01_login")
        await dump_inputs(page, "ログインページ")

        form = await page.query_selector("form")
        if form:
            action = await form.get_attribute("action") or ""
            method = await form.get_attribute("method") or ""
            print(f"  FORM action={action!r} method={method!r}")

        # ────────── Step 2: ログイン実行 ────────────────────────────
        print("\n[Step 2] ログイン実行...")
        await try_fill_first(page, [
            'input[name="userid"]', 'input[name="user_id"]', 'input[name="userno"]',
            'input[name="memberNo"]', 'input[name="loginId"]', 'input[name="login_id"]',
            '#userid', 'input[type="text"]:first-of-type',
        ], USER_ID, "利用者番号")

        await try_fill_first(page, [
            'input[type="password"]', 'input[name="passwd"]',
            'input[name="password"]', 'input[name="pass"]',
        ], PASSWORD, "パスワード")

        await try_click_first(page, [
            'input[value="ログイン"]', 'input[type="submit"]',
            'button:text("ログイン")', 'button[type="submit"]',
        ], "ログインボタン")

        await page.wait_for_load_state("networkidle", timeout=20_000)
        await save_step(page, "02_after_login")
        await dump_inputs(page, "ログイン後ページ")
        print(f"  URL: {page.url}")

        # ────────── Step 3: お気に入りクリック ──────────────────────
        print("\n[Step 3] お気に入りクリック...")
        clicked = await try_click_first(page, [
            'a:text("お気に入り")', 'input[value="お気に入り"]',
            'button:text("お気に入り")',
        ], "お気に入り")

        if not clicked:
            for el in await page.query_selector_all("a, input[type=submit], button"):
                txt = (await el.inner_text() or "").strip()
                val = (await el.get_attribute("value") or "").strip()
                if "お気に入り" in txt or "お気に入り" in val:
                    await el.click()
                    print(f"  [OK] お気に入り（スキャン）: text={txt!r}")
                    clicked = True
                    break

        if not clicked:
            print("  [WARN] お気に入りが見つかりません。02_after_login.html を確認してください。")

        await page.wait_for_load_state("networkidle", timeout=20_000)
        await save_step(page, "03_after_favorite")
        await dump_inputs(page, "お気に入り後（絞り込み画面）")
        print(f"  URL: {page.url}")

        # ────────── Step 4: 日付プルダウン詳細解析 ──────────────────
        print("\n[Step 4] 日付 SELECT 全件ダンプ...")
        selects = await page.query_selector_all("select")
        for sel in selects:
            name = await sel.get_attribute("name") or ""
            i_   = await sel.get_attribute("id")   or ""
            opts = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={i_!r} [{len(opts)} options]")
            for opt in opts:
                v   = (await opt.get_attribute("value") or "").strip()
                txt = (await opt.inner_text()).strip()
                mark = " ← 目標" if (any(t in txt for t in DATE_TEXTS) or v in DATE_VALUES) else ""
                print(f"    value={v!r:<20} text={txt!r}{mark}")

        # ────────── Step 5: 日付選択 → 検索 ────────────────────────
        print("\n[Step 5] 日付選択 → 検索...")
        date_selected = False
        for sel_el in await page.query_selector_all("select"):
            opts = await sel_el.query_selector_all("option")
            for opt in opts:
                v   = (await opt.get_attribute("value") or "").strip()
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in DATE_TEXTS) or v in DATE_VALUES:
                    name = await sel_el.get_attribute("name") or ""
                    if v:
                        await sel_el.select_option(value=v)
                    else:
                        await sel_el.select_option(label=txt)
                    print(f"  [OK] 日付選択: name={name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARN] 日付が見つかりませんでした。03_after_favorite.html を確認してください。")

        await try_click_first(page, [
            'input[value="検索"]', 'input[value*="検索"]',
            'button:text("検索")', 'input[type="submit"]',
            'button[type="submit"]', 'a:text("検索")',
        ], "検索ボタン")

        await page.wait_for_load_state("networkidle", timeout=20_000)
        await save_step(page, "04_search_results")
        print(f"  URL: {page.url}")

        # ────────── Step 6: 検索結果テーブル詳細解析 ────────────────
        print("\n[Step 6] 検索結果テーブル解析...")
        await dump_table_structure(page)

        # D面・16:00 に関連するセルをハイライトダンプ
        print("\n  --- D面 / 16:00 関連セル ---")
        for cell in await page.query_selector_all("td, th"):
            txt     = (await cell.inner_text()).strip()
            onclick = (await cell.get_attribute("onclick") or "")
            cls     = (await cell.get_attribute("class")   or "")
            cid     = (await cell.get_attribute("id")      or "")
            if "D面" in txt or "16:00" in txt or "18:00" in txt:
                print(f"  CELL id={cid!r} class={cls!r} onclick={onclick[:60]!r} text={txt!r}")

        # onclick / href を持つ要素の中で D面・16 に関連するもの
        print("\n  --- D面/16 に関連するリンク・クリック要素 ---")
        for el in await page.query_selector_all("[onclick], a[href]"):
            onclick = (await el.get_attribute("onclick") or "")
            href    = (await el.get_attribute("href") or "")
            txt     = (await el.inner_text() or "").strip()
            if ("D面" in onclick + href + txt) or ("16" in onclick + href and "面" in onclick + href + txt):
                print(f"  EL  onclick={onclick[:80]!r}  href={href!r}  text={txt!r}")

        await browser.close()

    print(f"\n\n{'='*60}")
    print(f"  解析完了。{OUTPUT_DIR}/ を確認してください。")
    print(f"  各ステップの .html を開けば正確なセレクターがわかります。")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(analyze())
