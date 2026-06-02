"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショット・フォーム要素を丸ごと保存する。

■ 使い方（ユーザーのローカル機で実行）
  pip install playwright
  playwright install chromium
  python analyze_site.py

■ 出力
  analysis_output/ 以下にHTMLとスクリーンショットを保存
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
    print(f"[SAVED] {step_name}.png / {step_name}.html")


async def dump_all_elements(page, label: str):
    """ページ内の全フォーム要素・リンクを詳細出力"""
    print(f"\n{'='*60}")
    print(f"=== {label} ===")
    print(f"URL: {page.url}")
    print(f"{'='*60}")

    # --- input 要素 ---
    inputs = await page.query_selector_all("input")
    print(f"\n[INPUT要素 ({len(inputs)}件)]")
    for inp in inputs:
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  type={t!r:10} name={name!r:20} id={id_!r:20} class={cls!r:20} value={val!r}")

    # --- select 要素（プルダウン全option含む） ---
    selects = await page.query_selector_all("select")
    print(f"\n[SELECT要素 ({len(selects)}件)]")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        opts = await sel.query_selector_all("option")
        print(f"  SELECT name={name!r} id={id_!r} class={cls!r} ({len(opts)}件)")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected") or ""
            print(f"    OPTION value={v!r:20} text={txt!r:30} selected={sel_attr!r}")

    # --- textarea ---
    textareas = await page.query_selector_all("textarea")
    print(f"\n[TEXTAREA要素 ({len(textareas)}件)]")
    for ta in textareas:
        name = await ta.get_attribute("name") or ""
        id_  = await ta.get_attribute("id") or ""
        print(f"  name={name!r} id={id_!r}")

    # --- button / submit / input[type=submit] ---
    buttons = await page.query_selector_all(
        "button, input[type='submit'], input[type='button'], input[type='image']"
    )
    print(f"\n[BUTTON要素 ({len(buttons)}件)]")
    for btn in buttons:
        t    = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        cls  = await btn.get_attribute("class") or ""
        val  = await btn.get_attribute("value") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  type={t!r:10} name={name!r:20} id={id_!r:20} value={val!r:20} text={txt!r}")

    # --- form のaction・method ---
    forms = await page.query_selector_all("form")
    print(f"\n[FORM ({len(forms)}件)]")
    for form in forms:
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        id_    = await form.get_attribute("id") or ""
        name   = await form.get_attribute("name") or ""
        print(f"  action={action!r} method={method!r} id={id_!r} name={name!r}")

    # --- リンク一覧 ---
    links = await page.query_selector_all("a")
    print(f"\n[リンク ({len(links)}件)]")
    for link in links:
        href    = await link.get_attribute("href") or ""
        id_     = await link.get_attribute("id") or ""
        cls     = await link.get_attribute("class") or ""
        onclick = await link.get_attribute("onclick") or ""
        try:
            txt = (await link.inner_text()).strip()
        except Exception:
            txt = ""
        if txt or href:
            print(f"  href={href!r:40} id={id_!r:15} class={cls!r:20} onclick={onclick!r:30} text={txt!r}")

    # --- onclick属性を持つ全要素 ---
    onclicks = await page.query_selector_all("[onclick]")
    print(f"\n[onclick要素 ({len(onclicks)}件)]")
    for elem in onclicks:
        tag     = await elem.evaluate("el => el.tagName.toLowerCase()")
        onclick = await elem.get_attribute("onclick") or ""
        id_     = await elem.get_attribute("id") or ""
        cls     = await elem.get_attribute("class") or ""
        try:
            txt = (await elem.inner_text()).strip()[:50]
        except Exception:
            txt = ""
        print(f"  <{tag}> id={id_!r:15} class={cls!r:20} onclick={onclick!r:50} text={txt!r}")

    # --- テーブル構造（最初の3テーブル×5行） ---
    tables = await page.query_selector_all("table")
    print(f"\n[TABLE ({len(tables)}件)]")
    for ti, tbl in enumerate(tables[:5]):
        id_  = await tbl.get_attribute("id") or ""
        cls  = await tbl.get_attribute("class") or ""
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] id={id_!r} class={cls!r} 行数={len(rows)}")
        for ri, row in enumerate(rows[:8]):
            cells = await row.query_selector_all("td, th")
            row_data = []
            for cell in cells:
                try:
                    txt     = (await cell.inner_text()).strip()[:20]
                    cls_c   = await cell.get_attribute("class") or ""
                    id_c    = await cell.get_attribute("id") or ""
                    onclick = await cell.get_attribute("onclick") or ""
                    row_data.append(f"{txt}[cls={cls_c} id={id_c} onclick={onclick[:20]}]")
                except Exception:
                    row_data.append("?")
            print(f"    ROW[{ri}]: {' | '.join(row_data[:6])}")


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
    print(f"  [FAIL] {label}: 入力フィールド未検出")
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
    print(f"  [FAIL] {label}: 要素未検出")
    return False


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

        # ── Step 1: ログインページ ─────────────────────────────────
        print("\n[Step 1] ログインページへ移動...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        # JS描画を待つ
        await page.wait_for_timeout(3000)
        await save_step(page, "01_login_page")
        await dump_all_elements(page, "ログインページ")

        # ── Step 2: ログイン ──────────────────────────────────────
        print("\n[Step 2] ログイン実行...")
        userid_ok = await try_fill(page, [
            'input[name="userid"]',
            'input[name="user_id"]',
            'input[name="memberNo"]',
            'input[name="userno"]',
            'input[name="loginId"]',
            'input[name="login_id"]',
            'input[name="id"]',
            '#userid', '#user_id', '#memberNo', '#loginId',
            'input[type="text"]:first-of-type',
        ], USER_ID, "利用者番号")

        passwd_ok = await try_fill(page, [
            'input[type="password"]',
            'input[name="passwd"]',
            'input[name="password"]',
            'input[name="pass"]',
            'input[name="pw"]',
            '#passwd', '#password',
        ], PASSWORD, "パスワード")

        submit_ok = await try_click(page, [
            'input[value="ログイン"]',
            'input[value="LOGIN"]',
            'input[value*="ログイン"]',
            'button:text("ログイン")',
            'button[type="submit"]',
            'input[type="submit"]',
            'a:text("ログイン")',
        ], "ログインボタン")

        await page.wait_for_load_state("networkidle", timeout=20000)
        await page.wait_for_timeout(2000)
        await save_step(page, "02_after_login")
        await dump_all_elements(page, "ログイン後ページ")

        # ── Step 3: お気に入り ────────────────────────────────────
        print("\n[Step 3] お気に入りリンクを探す...")
        # まずすべてのリンクからテキスト一致を探す
        fav_found = False
        all_links = await page.query_selector_all("a, input[type='submit'], input[type='button'], button")
        for elem in all_links:
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                href    = await elem.get_attribute("href") or ""
                onclick = await elem.get_attribute("onclick") or ""
                id_     = await elem.get_attribute("id") or ""
                cls     = await elem.get_attribute("class") or ""
                print(f"  [FOUND] お気に入り: href={href!r} onclick={onclick!r} id={id_!r} class={cls!r} text={txt!r}")
                await elem.click()
                fav_found = True
                break

        if not fav_found:
            print("  [WARNING] お気に入りが見つかりません")

        await page.wait_for_load_state("networkidle", timeout=20000)
        await page.wait_for_timeout(2000)
        await save_step(page, "03_after_favorite")
        await dump_all_elements(page, "お気に入り後（絞り込み画面）")

        # ── Step 4: 日付プルダウン全件出力 ───────────────────────
        print("\n[Step 4] 全SELECTのoption一覧（完全版）...")
        selects = await page.query_selector_all("select")
        for i, sel in enumerate(selects):
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id") or ""
            opts = await sel.query_selector_all("option")
            print(f"\n  SELECT[{i}] name={name!r} id={id_!r} ({len(opts)}件)")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r:25} text={txt!r}")

        # ── Step 5: 日付選択して検索 ──────────────────────────────
        print("\n[Step 5] 日付選択・検索...")
        date_target_texts  = [
            "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
            "2026年06月19日", "2026/06/19", "06/19",
        ]
        date_target_values = ["20260619", "2026-06-19", "260619"]

        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            opts = await sel_elem.query_selector_all("option")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in date_target_texts) or v in date_target_values:
                    sel_name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                    print(f"  [OK] 日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません")

        search_ok = await try_click(page, [
            'input[value="検索"]',
            'input[value*="検索"]',
            'button:text("検索")',
            'input[type="submit"]',
            'button[type="submit"]',
            'a:text("検索")',
        ], "検索ボタン")

        await page.wait_for_load_state("networkidle", timeout=20000)
        await page.wait_for_timeout(2000)
        await save_step(page, "04_search_results")
        await dump_all_elements(page, "検索結果ページ")

        # ── Step 6: D面×16:00〜18:00 セルの特定 ─────────────────
        print("\n[Step 6] D面 16:00〜18:00 のセル詳細...")
        tables = await page.query_selector_all("table")
        for ti, tbl in enumerate(tables):
            rows = await tbl.query_selector_all("tr")
            for ri, row in enumerate(rows):
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    try:
                        txt = (await cell.inner_text()).strip()
                    except Exception:
                        txt = ""
                    if "D面" in txt or ("16" in txt and "18" in txt) or "16:00" in txt:
                        id_     = await cell.get_attribute("id") or ""
                        cls     = await cell.get_attribute("class") or ""
                        onclick = await cell.get_attribute("onclick") or ""
                        style   = await cell.get_attribute("style") or ""
                        bgcolor = await cell.get_attribute("bgcolor") or ""
                        print(
                            f"  TABLE[{ti}]ROW[{ri}]CELL[{ci}] "
                            f"id={id_!r} class={cls!r} onclick={onclick!r} "
                            f"bgcolor={bgcolor!r} text={txt!r}"
                        )

        await browser.close()
        print(f"\n\n✅ 解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print("  各HTMLを開いて D面/16:00 などで検索してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
