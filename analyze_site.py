"""
まんまるよやく2 サイト構造解析スクリプト
===========================================
■ 使い方（ローカルPCで実行）
  python analyze_site.py

■ 出力
  analysis_output/ フォルダに各ステップのHTMLとスクリーンショットを保存
  コンソールに全フォーム要素・リンク・テーブル構造を出力

■ 前提
  pip install playwright
  playwright install chromium
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
    print(f"[SAVED] {step_name}.png / .html  ({len(html):,} bytes)")


async def dump_all(page, label: str):
    """ページ内の全フォーム要素・リンク・テーブルを出力"""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  URL   : {page.url}")
    print(f"  Title : {await page.title()}")
    print(f"{'='*60}")

    # ── form ──────────────────────────────────────────────────
    forms = await page.query_selector_all("form")
    for fi, form in enumerate(forms):
        action  = await form.get_attribute("action")  or ""
        method  = await form.get_attribute("method")  or ""
        enctype = await form.get_attribute("enctype") or ""
        name    = await form.get_attribute("name")    or ""
        id_     = await form.get_attribute("id")      or ""
        print(f"\nFORM[{fi}] name={name!r} id={id_!r} action={action!r} method={method!r} enctype={enctype!r}")

    # ── input ─────────────────────────────────────────────────
    print("\n--- INPUT ---")
    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t       = await inp.get_attribute("type")     or "text"
        name    = await inp.get_attribute("name")     or ""
        id_     = await inp.get_attribute("id")       or ""
        val     = await inp.get_attribute("value")    or ""
        cls     = await inp.get_attribute("class")    or ""
        placeholder = await inp.get_attribute("placeholder") or ""
        print(f"  <input type={t!r} name={name!r} id={id_!r} value={val!r} class={cls!r} placeholder={placeholder!r}>")

    # ── select ────────────────────────────────────────────────
    print("\n--- SELECT (プルダウン) ---")
    selects = await page.query_selector_all("select")
    for sel in selects:
        name    = await sel.get_attribute("name")  or ""
        id_     = await sel.get_attribute("id")    or ""
        cls     = await sel.get_attribute("class") or ""
        print(f"  <select name={name!r} id={id_!r} class={cls!r}>")
        options = await sel.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            sel_attr = await opt.get_attribute("selected")
            txt = (await opt.inner_text()).strip()
            mark = " ← selected" if sel_attr is not None else ""
            print(f"      <option value={v!r}>{txt!r}{mark}</option>")

    # ── button / submit ───────────────────────────────────────
    print("\n--- BUTTON / SUBMIT ---")
    buttons = await page.query_selector_all("button, input[type=submit], input[type=button], input[type=image]")
    for btn in buttons:
        t       = await btn.get_attribute("type")    or ""
        name    = await btn.get_attribute("name")    or ""
        id_     = await btn.get_attribute("id")      or ""
        val     = await btn.get_attribute("value")   or ""
        cls     = await btn.get_attribute("class")   or ""
        onclick = await btn.get_attribute("onclick") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  type={t!r} name={name!r} id={id_!r} value={val!r} class={cls!r} text={txt!r} onclick={onclick!r}")

    # ── anchor ────────────────────────────────────────────────
    print("\n--- LINK (a) ---")
    links = await page.query_selector_all("a")
    for link in links:
        href    = await link.get_attribute("href")    or ""
        onclick = await link.get_attribute("onclick") or ""
        id_     = await link.get_attribute("id")      or ""
        cls     = await link.get_attribute("class")   or ""
        try:
            txt = (await link.inner_text()).strip()
        except Exception:
            txt = ""
        print(f"  text={txt!r} href={href!r} onclick={onclick!r} id={id_!r} class={cls!r}")

    # ── table 構造 ────────────────────────────────────────────
    print("\n--- TABLE 構造 ---")
    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")
    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        tbl_id  = await tbl.get_attribute("id")    or ""
        tbl_cls = await tbl.get_attribute("class") or ""
        print(f"\n  TABLE[{ti}] id={tbl_id!r} class={tbl_cls!r} rows={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            parts = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip().replace("\n", " ")
                cls     = await cell.get_attribute("class")   or ""
                id_     = await cell.get_attribute("id")      or ""
                onclick = await cell.get_attribute("onclick") or ""
                tag     = await cell.evaluate("el => el.tagName.toLowerCase()")
                info = f"<{tag}"
                if cls:     info += f" class={cls!r}"
                if id_:     info += f" id={id_!r}"
                if onclick: info += f" onclick={onclick!r}"
                info += f">{txt[:30]!r}"
                parts.append(info)
            print(f"    ROW[{ri}]: " + " | ".join(parts))


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
    print(f"  [FAIL] {label} 入力フィールドが見つかりません")
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
    # フォールバック: テキストで検索
    for elem in await page.query_selector_all("a, button, input[type=submit], input[type=button]"):
        try:
            txt = (await elem.inner_text()).strip()
            val = await elem.get_attribute("value") or ""
            if label.split("(")[0].strip() in txt or label.split("(")[0].strip() in val:
                await elem.click()
                print(f"  [OK] {label} (テキストマッチ): {txt!r}")
                return True
        except Exception:
            pass
    print(f"  [FAIL] {label}")
    return False


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,   # ★ SSL証明書エラーを無視
        )
        page = await ctx.new_page()

        # ── Step 1: ログインページ ────────────────────────────
        print("\n[Step 1] ログインページへ移動...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_all(page, "ログインページ")

        # ── Step 2: ログイン実行 ──────────────────────────────
        print("\n[Step 2] ログイン実行...")
        await try_fill(page, [
            'input[name="userid"]', 'input[name="user_id"]', 'input[name="memberNo"]',
            'input[name="userno"]', 'input[name="loginId"]', 'input[name="login_id"]',
            '#userid', 'input[type="text"]',
        ], USER_ID, "利用者番号")

        await try_fill(page, [
            'input[type="password"]', 'input[name="passwd"]',
            'input[name="password"]', 'input[name="pass"]',
        ], PASSWORD, "パスワード")

        await try_click(page, [
            'input[value="ログイン"]', 'input[type="submit"]',
            'button[type="submit"]', 'button:has-text("ログイン")',
        ], "ログインボタン")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_all(page, "ログイン後")

        # ── Step 3: お気に入りクリック ────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        await try_click(page, [
            'a:has-text("お気に入り")', 'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
        ], "お気に入り")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        await dump_all(page, "お気に入り後（絞り込み画面）")

        # ── Step 4: 日付SELECTの全オプション詳細表示 ─────────
        print("\n[Step 4] 全SELECT要素の詳細（日付選択用）...")
        selects = await page.query_selector_all("select")
        for si, sel in enumerate(selects):
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id")   or ""
            opts = await sel.query_selector_all("option")
            print(f"\n  SELECT[{si}] name={name!r} id={id_!r} オプション数={len(opts)}")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r}  text={txt!r}")

        # ── Step 5: 日付選択・検索（令和08年06月19日）─────────
        print("\n[Step 5] 日付を令和08年06月19日に設定して検索...")
        date_texts  = ["令和08年06月19日", "令和8年6月19日", "2026年06月19日", "2026/06/19"]
        date_values = ["20260619", "2026-06-19", "260619"]

        date_set = False
        for sel in await page.query_selector_all("select"):
            for opt in await sel.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in date_texts) or v in date_values:
                    name = await sel.get_attribute("name") or ""
                    await sel.select_option(value=v)
                    print(f"  [OK] 日付選択 name={name!r} value={v!r} text={txt!r}")
                    date_set = True
                    break
            if date_set:
                break

        if not date_set:
            print("  [WARN] 日付オプションが見つかりません（分割プルダウンかもしれません）")

        await try_click(page, [
            'input[value="検索"]', 'input[value*="検索"]', 'button:has-text("検索")',
            'input[type="submit"]', 'button[type="submit"]',
        ], "検索ボタン")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        await dump_all(page, "検索結果ページ")

        # ── Step 6: D面 16:00〜18:00 セル詳細解析 ────────────
        print("\n[Step 6] D面 / 16:00 を含む全セル情報...")
        cells = await page.query_selector_all("td, th")
        for i, cell in enumerate(cells):
            try:
                txt     = (await cell.inner_text()).strip().replace("\n", " ")
                cls     = await cell.get_attribute("class")   or ""
                id_     = await cell.get_attribute("id")      or ""
                onclick = await cell.get_attribute("onclick") or ""
                # 行全体のテキストも取得
                row = await cell.evaluate_handle("el => el.parentElement")
                row_txt = (await row.evaluate("el => el.innerText")).strip().replace("\n", " ")[:80]
            except Exception:
                continue
            if "D面" in txt or "D面" in row_txt or "16:00" in txt or "16:00" in row_txt:
                print(f"\n  CELL[{i}]")
                print(f"    text   = {txt!r}")
                print(f"    class  = {cls!r}")
                print(f"    id     = {id_!r}")
                print(f"    onclick= {onclick!r}")
                # セル内のリンク
                child_links = await cell.query_selector_all("a, input[type=button], input[type=submit]")
                for ci, cl in enumerate(child_links):
                    ch_href    = await cl.get_attribute("href")    or ""
                    ch_onclick = await cl.get_attribute("onclick") or ""
                    ch_val     = await cl.get_attribute("value")   or ""
                    try:
                        ch_txt = (await cl.inner_text()).strip()
                    except Exception:
                        ch_txt = ch_val
                    print(f"    CHILD[{ci}] text={ch_txt!r} href={ch_href!r} onclick={ch_onclick!r}")

        await browser.close()
        print(f"\n\n{'='*60}")
        print(f"解析完了。{OUTPUT_DIR}/ を確認してください。")
        print("="*60)


if __name__ == "__main__":
    asyncio.run(analyze())
