"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する

■ 実行方法
  python analyze_site.py
  python analyze_site.py --headful   # ブラウザ表示あり

■ 出力先
  analysis_output/
    01_login_page.html/.png
    02_after_login.html/.png
    03_after_favorite.html/.png
    04_search_results.html/.png
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"


def headful() -> bool:
    return "--headful" in sys.argv


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / {step_name}.html")


def sep(label: str):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")


async def dump_all(page, label: str):
    sep(label)
    print(f"URL   : {page.url}")
    try:
        title = await page.title()
        print(f"Title : {title}")
    except Exception:
        pass

    # ── FORMタグ ────────────────────────────────────────────────
    print("\n--- FORM ---")
    for f in await page.query_selector_all("form"):
        action = await f.get_attribute("action") or ""
        method = await f.get_attribute("method") or ""
        id_    = await f.get_attribute("id") or ""
        name   = await f.get_attribute("name") or ""
        print(f"  FORM id={id_!r} name={name!r} action={action!r} method={method!r}")

    # ── INPUT ───────────────────────────────────────────────────
    print("\n--- INPUT ---")
    for inp in await page.query_selector_all("input"):
        t   = await inp.get_attribute("type") or "text"
        n   = await inp.get_attribute("name") or ""
        i   = await inp.get_attribute("id") or ""
        cls = await inp.get_attribute("class") or ""
        val = await inp.get_attribute("value") or ""
        ph  = await inp.get_attribute("placeholder") or ""
        print(f"  INPUT type={t!r} name={n!r} id={i!r} class={cls!r} value={val!r} placeholder={ph!r}")

    # ── SELECT / OPTION ─────────────────────────────────────────
    print("\n--- SELECT ---")
    for sel in await page.query_selector_all("select"):
        n   = await sel.get_attribute("name") or ""
        i   = await sel.get_attribute("id") or ""
        cls = await sel.get_attribute("class") or ""
        opts = await sel.query_selector_all("option")
        print(f"  SELECT name={n!r} id={i!r} class={cls!r}  ({len(opts)} options)")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected") or ""
            print(f"    OPTION value={v!r}  text={txt!r}  selected={sel_attr!r}")

    # ── BUTTON / SUBMIT ─────────────────────────────────────────
    print("\n--- BUTTON/SUBMIT ---")
    for btn in await page.query_selector_all("button, input[type=submit], input[type=button], input[type=image]"):
        t   = await btn.get_attribute("type") or ""
        n   = await btn.get_attribute("name") or ""
        i   = await btn.get_attribute("id") or ""
        val = await btn.get_attribute("value") or ""
        cls = await btn.get_attribute("class") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = ""
        print(f"  BTN type={t!r} name={n!r} id={i!r} value={val!r} class={cls!r} text={txt!r}")

    # ── リンク ─────────────────────────────────────────────────
    print("\n--- LINK ---")
    for a in await page.query_selector_all("a"):
        href = await a.get_attribute("href") or ""
        cls  = await a.get_attribute("class") or ""
        onc  = await a.get_attribute("onclick") or ""
        try:
            txt = (await a.inner_text()).strip()
        except Exception:
            txt = ""
        if txt or href:
            print(f"  A href={href!r} class={cls!r} onclick={onc!r} text={txt!r}")

    # ── onclick 持つ要素 ────────────────────────────────────────
    print("\n--- ONCLICK ---")
    for elem in await page.query_selector_all("[onclick]"):
        tag = await elem.evaluate("e => e.tagName")
        onc = await elem.get_attribute("onclick") or ""
        cls = await elem.get_attribute("class") or ""
        try:
            txt = (await elem.inner_text()).strip()[:40]
        except Exception:
            txt = ""
        print(f"  {tag} onclick={onc!r} class={cls!r} text={txt!r}")


async def dump_table_structure(page, label: str):
    sep(f"テーブル構造解析: {label}")
    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        id_  = await tbl.get_attribute("id") or ""
        cls  = await tbl.get_attribute("class") or ""
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] id={id_!r} class={cls!r}  rows={len(rows)}")

        for ri, row in enumerate(rows[:10]):  # 最大10行
            cells = await row.query_selector_all("td, th")
            row_data = []
            for ci, cell in enumerate(cells):
                txt     = (await cell.inner_text()).strip()
                cls_c   = await cell.get_attribute("class") or ""
                onc     = await cell.get_attribute("onclick") or ""
                rowspan = await cell.get_attribute("rowspan") or "1"
                colspan = await cell.get_attribute("colspan") or "1"
                inner_a = await cell.query_selector("a")
                href    = (await inner_a.get_attribute("href") or "") if inner_a else ""
                row_data.append(
                    f"[{ci}]{txt!r}(cls={cls_c},onc={onc[:30]},href={href[:30]})"
                )
            print(f"    ROW[{ri}]: {' | '.join(row_data[:8])}")

        if len(rows) > 10:
            print(f"    ... (残り{len(rows)-10}行省略)")

    # D面セル特定
    print("\n--- D面・16:00 に関連するセル ---")
    for cell in await page.query_selector_all("td, th"):
        txt = (await cell.inner_text()).strip()
        if "D面" in txt or "16:00" in txt or "18:00" in txt:
            cls  = await cell.get_attribute("class") or ""
            onc  = await cell.get_attribute("onclick") or ""
            innr = await cell.inner_html()
            print(f"  CELL text={txt!r} class={cls!r} onclick={onc!r}")
            print(f"       innerHTML={innr[:120]!r}")


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headful(),
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

        # ── STEP 1: ログインページ ─────────────────────────────────
        print("\n[Step 1] ログインページ取得...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_all(page, "ログインページ")

        # ── STEP 2: ログイン実行 ───────────────────────────────────
        print("\n[Step 2] ログイン実行...")
        filled = False
        for sel in [
            'input[name="loginno"]', 'input[name="riyousyano"]',
            'input[name="userid"]', 'input[name="userno"]',
            'input[name="memberNo"]', 'input[name="loginId"]',
            '#userid', '#loginno', 'input[type="text"]:first-of-type',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
                if elem:
                    await elem.fill(USER_ID)
                    print(f"  [OK] 利用者番号入力: {sel}")
                    filled = True
                    break
            except Exception:
                pass
        if not filled:
            print("  [WARNING] 利用者番号フィールドが見つかりません")

        for sel in ['input[type="password"]', 'input[name="passwd"]',
                    'input[name="password"]', '#passwd']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
                if elem:
                    await elem.fill(PASSWORD)
                    print(f"  [OK] パスワード入力: {sel}")
                    break
            except Exception:
                pass

        for sel in ['input[value="ログイン"]', 'button:has-text("ログイン")',
                    'input[type="submit"]', 'button[type="submit"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
                if elem:
                    await elem.click()
                    print(f"  [OK] ログインボタン: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=30000)
        await save_step(page, "02_after_login")
        await dump_all(page, "ログイン後メニュー")

        # ── STEP 3: お気に入りクリック ─────────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        for sel in [
            'a:has-text("お気に入り")', 'input[value="お気に入り"]',
            'button:has-text("お気に入り")', 'input[value*="お気に入り"]',
            'a:has-text("お気に入りから選択")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000, state="visible")
                if elem:
                    await elem.click()
                    print(f"  [OK] お気に入り: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=30000)
        await save_step(page, "03_after_favorite")
        await dump_all(page, "お気に入り後（絞り込み画面）")

        # ── STEP 4: 日付プルダウン詳細解析 ──────────────────────────
        print("\n[Step 4] 日付プルダウン詳細解析...")
        selects = await page.query_selector_all("select")
        print(f"  SELECTタグ数: {len(selects)}")
        for sel in selects:
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id") or ""
            opts = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r}  ({len(opts)} options)")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    OPTION value={v!r}  text={txt!r}")

        # ── STEP 5: 日付選択・検索 ───────────────────────────────────
        print("\n[Step 5] 令和08年06月19日を選択して検索...")
        target_texts  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19", "2026年06月19日"]
        target_values = ["20260619", "2026-06-19", "2026/06/19"]
        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in target_texts) or v in target_values:
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 日付選択: value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません。01〜03のHTMLを確認してください。")

        for sel in ['input[value="検索"]', 'button:has-text("検索")',
                    'input[type="submit"]', 'button[type="submit"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
                if elem:
                    await elem.click()
                    print(f"  [OK] 検索ボタン: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=30000)
        await save_step(page, "04_search_results")
        await dump_table_structure(page, "検索結果（予約表）")

        await browser.close()
        print(f"\n\n解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print("→ HTMLファイルで正確なセレクターを確認し、reserve.py に反映してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
