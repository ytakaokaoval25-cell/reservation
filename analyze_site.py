"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する

実行方法（ローカルPCで実行してください）:
  pip install playwright==1.56.0
  playwright install chromium
  python analyze_site.py
"""

import asyncio
import os
from playwright.async_api import async_playwright

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
    print(f"[SAVED] {step_name}.png / {step_name}.html")


async def dump_form_elements(page, label: str):
    print(f"\n{'='*60}")
    print(f"=== {label} のフォーム要素 ===")
    print(f"URL: {page.url}")
    print(f"{'='*60}")

    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r}")

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
            print(f"    OPTION value={v!r} text={txt!r}")

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

    print(f"\n  --- リンク一覧 ---")
    links = await page.query_selector_all("a")
    for link in links:
        href = await link.get_attribute("href") or ""
        onclick = await link.get_attribute("onclick") or ""
        txt  = (await link.inner_text()).strip()
        if txt:
            print(f"  A href={href!r} onclick={onclick!r} text={txt!r}")


async def dump_table(page, label: str):
    print(f"\n--- {label} テーブル構造 ---")
    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")
    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        cls  = await tbl.get_attribute("class") or ""
        print(f"\n  TABLE[{ti}] class={cls!r} 行数={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            parts = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip()
                cls_c   = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                id_c    = await cell.get_attribute("id") or ""
                parts.append(f"[{txt}|cls={cls_c}|id={id_c}|onclick={onclick[:30]}]")
            print(f"    ROW[{ri}]: {' '.join(parts)}")


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,
        )
        page = await context.new_page()

        # ── Step 1: ログインページ ──────────────────────────────
        print("\n[Step 1] ログインページに移動...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "01_login_page")
        await dump_form_elements(page, "ログインページ")

        form = await page.query_selector("form")
        if form:
            action = await form.get_attribute("action") or ""
            method = await form.get_attribute("method") or ""
            print(f"\n  FORM action={action!r} method={method!r}")

        # ── Step 2: ログイン実行 ───────────────────────────────
        print("\n[Step 2] ログイン実行...")
        userid_filled = False
        for sel in [
            'input[name="userid"]', 'input[name="user_id"]',
            'input[name="userno"]', 'input[name="memberNo"]',
            'input[name="loginId"]', 'input[name="login_id"]',
            '#userid', '#user_id', '#userno',
            'input[type="text"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.fill(USER_ID)
                    print(f"  [OK] 利用者番号: {sel}")
                    userid_filled = True
                    break
            except Exception:
                pass
        if not userid_filled:
            print("  [WARNING] 利用者番号フィールドが見つかりません")

        passwd_filled = False
        for sel in ['input[type="password"]', 'input[name="passwd"]',
                    'input[name="password"]', 'input[name="pass"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.fill(PASSWORD)
                    print(f"  [OK] パスワード: {sel}")
                    passwd_filled = True
                    break
            except Exception:
                pass
        if not passwd_filled:
            print("  [WARNING] パスワードフィールドが見つかりません")

        for sel in [
            'input[value="ログイン"]', 'button:has-text("ログイン")',
            'input[type="submit"]', 'button[type="submit"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.click()
                    print(f"  [OK] ログインボタン: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_form_elements(page, "ログイン後ページ")
        print(f"  現在URL: {page.url}")

        # ── Step 3: お気に入りクリック ─────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        fav_clicked = False
        for sel in [
            'a:has-text("お気に入り")',
            'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                if elem:
                    txt = (await elem.inner_text()).strip()
                    print(f"  [OK] お気に入り: {sel} text={txt!r}")
                    await elem.click()
                    fav_clicked = True
                    break
            except Exception:
                pass

        if not fav_clicked:
            # テキスト全走査
            all_elems = await page.query_selector_all("a, button, input")
            for elem in all_elems:
                try:
                    txt = (await elem.inner_text()).strip()
                except Exception:
                    txt = ""
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    href    = await elem.get_attribute("href") or ""
                    onclick = await elem.get_attribute("onclick") or ""
                    print(f"  [FOUND] お気に入り: txt={txt!r} val={val!r} href={href!r} onclick={onclick!r}")
                    await elem.click()
                    fav_clicked = True
                    break

        if not fav_clicked:
            print("  [WARNING] お気に入りリンクが見つかりません")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        await dump_form_elements(page, "お気に入り後（絞り込み画面）")
        print(f"  現在URL: {page.url}")

        # ── Step 4: 日付SELECTを全件ダンプ ───────────────────
        print("\n[Step 4] 日付プルダウン詳細解析...")
        date_selects = await page.query_selector_all("select")
        print(f"  SELECT数: {len(date_selects)}")
        for sel in date_selects:
            name    = await sel.get_attribute("name") or ""
            id_     = await sel.get_attribute("id") or ""
            cls     = await sel.get_attribute("class") or ""
            options = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r} class={cls!r} - {len(options)}件")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r}  text={txt!r}")

        # ── Step 5: 日付選択・検索 ────────────────────────────
        print("\n[Step 5] 令和08年06月19日を選択して検索...")
        date_target_values = ["20260619", "2026-06-19", "260619"]
        date_target_texts  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19"]

        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in date_target_texts) or v in date_target_values:
                    name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v)
                    print(f"  [OK] 日付選択: name={name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません")

        for sel in [
            'input[value*="検索"]', 'button:has-text("検索")',
            'input[type="submit"]', 'button[type="submit"]',
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
        print(f"  現在URL: {page.url}")

        # ── Step 6: 検索結果テーブル解析 ─────────────────────
        print("\n[Step 6] 検索結果テーブル解析...")
        await dump_table(page, "検索結果")

        # D面・16:00 を含むセルをピンポイントで出力
        cells = await page.query_selector_all("td, th")
        print(f"\n  D面/16:00 関連セル:")
        for i, cell in enumerate(cells):
            txt     = (await cell.inner_text()).strip()
            id_     = await cell.get_attribute("id") or ""
            cls     = await cell.get_attribute("class") or ""
            onclick = await cell.get_attribute("onclick") or ""
            if "D面" in txt or "16:00" in txt or "18:00" in txt or "1600" in onclick:
                print(f"  CELL[{i}] id={id_!r} cls={cls!r} onclick={onclick!r} text={txt!r}")

        await browser.close()
        print(f"\n\n✅ 解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
