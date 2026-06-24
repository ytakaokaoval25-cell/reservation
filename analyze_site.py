"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する

■ 使い方（ローカル環境で実行）
  pip install playwright
  playwright install chromium
  python analyze_site.py
"""

import asyncio
import os
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID = "12015873"
PASSWORD = "0508"
OUTPUT_DIR = "analysis_output"


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / {step_name}.html")


async def dump_all_elements(page, label: str):
    print(f"\n{'='*60}")
    print(f"=== {label} の全要素 ===")
    print(f"{'='*60}")
    print(f"  URL: {page.url}")
    print(f"  Title: {await page.title()}")

    # FORMタグ
    forms = await page.query_selector_all("form")
    for fi, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        id_ = await form.get_attribute("id") or ""
        print(f"\n  FORM[{fi}] action={action!r} method={method!r} id={id_!r}")

    # INPUTタグ
    inputs = await page.query_selector_all("input")
    print(f"\n  --- INPUT要素 ({len(inputs)}件) ---")
    for inp in inputs:
        t = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_ = await inp.get_attribute("id") or ""
        cls = await inp.get_attribute("class") or ""
        val = await inp.get_attribute("value") or ""
        onclick = await inp.get_attribute("onclick") or ""
        print(f"  INPUT type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r} onclick={onclick!r}")

    # SELECTタグ（全オプション）
    selects = await page.query_selector_all("select")
    print(f"\n  --- SELECT要素 ({len(selects)}件) ---")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_ = await sel.get_attribute("id") or ""
        cls = await sel.get_attribute("class") or ""
        options = await sel.query_selector_all("option")
        print(f"  SELECT name={name!r} id={id_!r} class={cls!r} ({len(options)}件)")
        for opt in options:
            v = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected") or ""
            print(f"    OPTION value={v!r} text={txt!r} selected={sel_attr!r}")

    # BUTTONタグ
    buttons = await page.query_selector_all("button")
    print(f"\n  --- BUTTON要素 ({len(buttons)}件) ---")
    for btn in buttons:
        t = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_ = await btn.get_attribute("id") or ""
        val = await btn.get_attribute("value") or ""
        cls = await btn.get_attribute("class") or ""
        onclick = await btn.get_attribute("onclick") or ""
        txt = (await btn.inner_text()).strip()
        print(f"  BUTTON type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r} text={txt!r} onclick={onclick!r}")

    # Aタグ（全リンク）
    links = await page.query_selector_all("a")
    print(f"\n  --- A要素 ({len(links)}件) ---")
    for link in links:
        href = await link.get_attribute("href") or ""
        onclick = await link.get_attribute("onclick") or ""
        cls = await link.get_attribute("class") or ""
        id_ = await link.get_attribute("id") or ""
        txt = (await link.inner_text()).strip()
        print(f"  A href={href!r} onclick={onclick!r} class={cls!r} id={id_!r} text={txt!r}")


async def analyze_table(page, label: str):
    print(f"\n{'='*60}")
    print(f"=== {label} のテーブル構造 ===")
    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")
    for ti, tbl in enumerate(tables):
        tbl_id = await tbl.get_attribute("id") or ""
        tbl_cls = await tbl.get_attribute("class") or ""
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] id={tbl_id!r} class={tbl_cls!r} 行数={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                cls = await cell.get_attribute("class") or ""
                id_ = await cell.get_attribute("id") or ""
                onclick = await cell.get_attribute("onclick") or ""
                bgcolor = await cell.get_attribute("bgcolor") or ""
                # 子要素のAタグを確認
                a_child = await cell.query_selector("a")
                a_href = (await a_child.get_attribute("href") or "") if a_child else ""
                a_onclick = (await a_child.get_attribute("onclick") or "") if a_child else ""
                a_txt = (await a_child.inner_text()).strip() if a_child else ""
                if txt or cls or onclick or a_href:
                    print(f"    CELL[{ri},{ci}] text={txt!r} class={cls!r} id={id_!r} "
                          f"onclick={onclick!r} bgcolor={bgcolor!r} "
                          f"a_href={a_href!r} a_onclick={a_onclick!r} a_txt={a_txt!r}")


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP",
        )
        page = await context.new_page()

        # ── Step 1: ログインページ ──────────────────────────────
        print("\n[Step 1] ログインページに移動...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_all_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ───────────────────────────────
        print("\n[Step 2] ログイン実行...")
        userid_filled = False
        for sel in [
            'input[name="userid"]', 'input[name="user_id"]', 'input[name="memberNo"]',
            'input[name="userno"]', 'input[name="loginId"]', 'input[name="login_id"]',
            'input[name="id"]', '#userid', 'input[type="text"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.fill(USER_ID)
                    print(f"  [OK] 利用者番号入力: {sel}")
                    userid_filled = True
                    break
            except Exception:
                pass
        if not userid_filled:
            print("  [WARNING] 利用者番号フィールドが見つかりません")

        for sel in ['input[type="password"]', 'input[name="passwd"]', 'input[name="password"]', 'input[name="pass"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.fill(PASSWORD)
                    print(f"  [OK] パスワード入力: {sel}")
                    break
            except Exception:
                pass

        for sel in ['input[value="ログイン"]', 'input[type="submit"]', 'button[type="submit"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.click()
                    print(f"  [OK] サブミット: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_all_elements(page, "ログイン後ページ")

        body = await page.inner_text("body")
        print(f"\n  本文先頭500字:\n{body[:500]}")

        # ── Step 3: お気に入りクリック ─────────────────────────
        print("\n[Step 3] お気に入りを探してクリック...")
        all_clickable = await page.query_selector_all("a, button, input[type=button], input[type=submit]")
        print(f"  クリック可能要素: {len(all_clickable)}件")

        clicked = False
        for elem in all_clickable:
            txt = ""
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                pass
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                tag = await elem.evaluate("e => e.tagName")
                href = await elem.get_attribute("href") or ""
                onclick = await elem.get_attribute("onclick") or ""
                print(f"  [FOUND] お気に入り要素: tag={tag} text={txt!r} value={val!r} href={href!r} onclick={onclick!r}")
                await elem.click()
                clicked = True
                break

        if not clicked:
            print("  [WARNING] お気に入りが見つかりません")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        await dump_all_elements(page, "お気に入り後（絞り込み画面）")

        body = await page.inner_text("body")
        print(f"\n  本文先頭500字:\n{body[:500]}")

        # ── Step 4: 日付プルダウン詳細解析 ────────────────────
        print("\n[Step 4] 日付プルダウン詳細解析（全オプション）...")
        date_selects = await page.query_selector_all("select")
        for sel in date_selects:
            name = await sel.get_attribute("name") or ""
            id_ = await sel.get_attribute("id") or ""
            options = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r} - {len(options)}件")
            for opt in options:
                v = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r}  text={txt!r}")

        # ── Step 5: 日付選択・検索 ────────────────────────────
        print("\n[Step 5] 令和08年06月19日を選択して検索...")
        TARGET_TEXTS = ["令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日", "2026年06月19日"]
        TARGET_VALUES = ["20260619", "2026-06-19", "2026/06/19", "260619"]

        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                v = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in TARGET_TEXTS) or v in TARGET_VALUES:
                    sel_name = await sel_elem.get_attribute("name") or ""
                    if v:
                        await sel_elem.select_option(value=v)
                    else:
                        await sel_elem.select_option(label=txt)
                    print(f"  [OK] 日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません")

        # 検索ボタン
        for sel in ['input[value="検索"]', 'input[value*="検索"]', 'button:text("検索")', 'input[type="submit"]']:
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
        print(f"  URL: {page.url}")

        # ── Step 6: 検索結果テーブル詳細解析 ─────────────────
        print("\n[Step 6] 検索結果テーブル詳細解析...")
        await analyze_table(page, "検索結果")

        # D面 16:00 に関連するセルを強調表示
        print("\n  --- D面 / 16:00 に関連するセル ---")
        all_cells = await page.query_selector_all("td, th")
        for i, cell in enumerate(all_cells):
            txt = (await cell.inner_text()).strip()
            cls = await cell.get_attribute("class") or ""
            id_ = await cell.get_attribute("id") or ""
            onclick = await cell.get_attribute("onclick") or ""
            if "D面" in txt or "16:00" in txt or "16" in txt and "18" in txt:
                print(f"  CELL[{i}] text={txt!r} class={cls!r} id={id_!r} onclick={onclick!r}")
                a = await cell.query_selector("a")
                if a:
                    a_href = await a.get_attribute("href") or ""
                    a_onclick = await a.get_attribute("onclick") or ""
                    a_txt = (await a.inner_text()).strip()
                    print(f"    -> A href={a_href!r} onclick={a_onclick!r} text={a_txt!r}")

        await browser.close()
        print(f"\n\n解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print("次のファイルを確認してください:")
        for f in sorted(os.listdir(OUTPUT_DIR)):
            print(f"  {OUTPUT_DIR}/{f}")


if __name__ == "__main__":
    asyncio.run(analyze())
