"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショット・フォーム要素を保存して正確なセレクターを確認する

■ 使い方
  python analyze_site.py
  # → analysis_output/ フォルダに PNG + HTML が保存される
  # → コンソールに全フォーム要素・リンク・テーブル構造が出力される
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
    print(f"[SAVED] {step_name}.png / .html")


async def dump_inputs(page, label: str):
    """ページ内の全フォーム要素を出力"""
    print(f"\n{'='*60}")
    print(f"  {label} のフォーム要素")
    print(f"{'='*60}")

    forms = await page.query_selector_all("form")
    for fi, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        print(f"  FORM[{fi}] action={action!r} method={method!r}")

    # input
    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT  type={t!r:<12} name={name!r:<25} id={id_!r:<20} class={cls!r} value={val!r}")

    # select + options
    selects = await page.query_selector_all("select")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        opts = await sel.query_selector_all("option")
        print(f"\n  SELECT name={name!r} id={id_!r} class={cls!r}  ({len(opts)} options)")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected")
            marker = " ← selected" if sel_attr is not None else ""
            print(f"    OPTION value={v!r:<20} text={txt!r}{marker}")

    # textarea
    textareas = await page.query_selector_all("textarea")
    for ta in textareas:
        name = await ta.get_attribute("name") or ""
        id_  = await ta.get_attribute("id") or ""
        print(f"  TEXTAREA name={name!r} id={id_!r}")

    # buttons
    buttons = await page.query_selector_all(
        "button, input[type=submit], input[type=button], input[type=image]"
    )
    for btn in buttons:
        t   = await btn.get_attribute("type") or ""
        nm  = await btn.get_attribute("name") or ""
        id_ = await btn.get_attribute("id") or ""
        val = await btn.get_attribute("value") or ""
        txt = (await btn.inner_text()).strip() if await btn.inner_text() else val
        print(f"  BUTTON type={t!r} name={nm!r} id={id_!r} value={val!r} text={txt!r}")

    # リンク
    print("\n  --- リンク一覧 ---")
    links = await page.query_selector_all("a")
    for link in links:
        href    = await link.get_attribute("href") or ""
        onclick = await link.get_attribute("onclick") or ""
        txt     = (await link.inner_text()).strip()
        if txt or href:
            print(f"  A  href={href!r}  onclick={onclick!r}  text={txt!r}")


async def dump_tables(page, label: str, max_rows: int = 10):
    """テーブル構造を出力"""
    print(f"\n{'='*60}")
    print(f"  {label} のテーブル構造")
    print(f"{'='*60}")

    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        cls  = await tbl.get_attribute("class") or ""
        id_  = await tbl.get_attribute("id") or ""
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] id={id_!r} class={cls!r}  行数={len(rows)}")

        for ri, row in enumerate(rows[:max_rows]):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip()
                cls_c   = await cell.get_attribute("class") or ""
                id_c    = await cell.get_attribute("id") or ""
                onclick = await cell.get_attribute("onclick") or ""
                tag     = await cell.evaluate("el => el.tagName")
                # リンクがあれば href も表示
                a = await cell.query_selector("a")
                href_c = ""
                if a:
                    href_c = await a.get_attribute("href") or ""
                info = f"[{tag}] {txt!r}"
                if cls_c:
                    info += f" cls={cls_c!r}"
                if id_c:
                    info += f" id={id_c!r}"
                if onclick:
                    info += f" onclick={onclick!r}"
                if href_c:
                    info += f" href={href_c!r}"
                row_info.append(info)
            print(f"    ROW[{ri}]: {' | '.join(row_info[:8])}")

        if len(rows) > max_rows:
            print(f"    ... 残り {len(rows) - max_rows} 行省略")


async def try_login(page):
    """ログインを試みる（解析用）"""
    print("\n[Step 2] ログイン実行...")
    userid_selectors = [
        'input[name="userid"]', 'input[name="user_id"]',
        'input[name="memberNo"]', 'input[name="userno"]',
        'input[name="loginId"]', 'input[name="login_id"]',
        'input[id="userid"]', 'input[type="text"]:first-of-type',
    ]
    for sel in userid_selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000)
            if elem:
                await elem.fill(USER_ID)
                print(f"  [OK] 利用者番号入力: {sel}")
                break
        except Exception:
            pass

    passwd_selectors = [
        'input[name="passwd"]', 'input[name="password"]',
        'input[name="pass"]', 'input[type="password"]',
    ]
    for sel in passwd_selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000)
            if elem:
                await elem.fill(PASSWORD)
                print(f"  [OK] パスワード入力: {sel}")
                break
        except Exception:
            pass

    submit_selectors = [
        'input[type="submit"]', 'button[type="submit"]',
        'input[value="ログイン"]', 'button:has-text("ログイン")',
    ]
    for sel in submit_selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000)
            if elem:
                await elem.click()
                print(f"  [OK] サブミット: {sel}")
                break
        except Exception:
            pass

    await page.wait_for_load_state("networkidle", timeout=20000)
    print(f"  ログイン後URL: {page.url}")


async def try_favorite(page):
    """お気に入りを試みる（解析用）"""
    print("\n[Step 3] お気に入りクリック...")
    for sel in [
        'a:has-text("お気に入り")', 'input[value*="お気に入り"]',
        'button:has-text("お気に入り")',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=3000)
            if elem:
                txt = (await elem.inner_text()).strip() if await elem.inner_text() else ""
                print(f"  [OK] お気に入り要素: {sel} text={txt!r}")
                await elem.click()
                break
        except Exception:
            pass

    await page.wait_for_load_state("networkidle", timeout=15000)
    print(f"  お気に入り後URL: {page.url}")


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # 動作確認しやすいようヘッドフルで実行
            args=["--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        await context.add_init_script("window.confirm = () => true; window.alert = () => {};")
        page = await context.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        # ── Step 1: ログインページ ──────────────────────────────────
        print("\n[Step 1] ログインページへ移動...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_inputs(page, "ログインページ")

        # ── Step 2: ログイン ────────────────────────────────────────
        await try_login(page)
        await save_step(page, "02_after_login")
        await dump_inputs(page, "ログイン後ページ")
        await dump_tables(page, "ログイン後ページ")

        # ── Step 3: お気に入り ──────────────────────────────────────
        await try_favorite(page)
        await save_step(page, "03_after_favorite")
        await dump_inputs(page, "お気に入り後（絞り込み画面）")
        await dump_tables(page, "お気に入り後（絞り込み画面）")

        # ── Step 4: 日付SELECTの全オプションを詳細出力 ─────────────
        print("\n[Step 4] 日付プルダウン詳細解析...")
        selects = await page.query_selector_all("select")
        for sel in selects:
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id") or ""
            opts = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r}  ({len(opts)} options)")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r:<25} text={txt!r}")

        # ── Step 5: 日付選択 + 検索 ────────────────────────────────
        print("\n[Step 5] 令和08年06月19日を選択して検索...")
        date_targets_v = ["20260619", "2026-06-19", "260619"]
        date_targets_t = ["令和08年06月19日", "令和8年6月19日", "2026/06/19"]
        date_selected  = False

        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in date_targets_t) or v in date_targets_v:
                    nm = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v)
                    print(f"  [OK] 日付選択 name={nm!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません。上記の SELECT/OPTION 一覧を確認してください。")

        for sel in ['input[type="submit"]', 'button[type="submit"]',
                    'input[value*="検索"]', 'button:has-text("検索")', 'a:has-text("検索")']:
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
        print(f"  検索後URL: {page.url}")

        # ── Step 6: 検索結果テーブル詳細解析 ───────────────────────
        print("\n[Step 6] 検索結果テーブル詳細解析...")
        await dump_tables(page, "検索結果", max_rows=20)

        # D面・16:00・18:00 を含むセルを特に詳細出力
        print("\n  --- D面 / 16:00 / 18:00 を含むセル ---")
        cells = await page.query_selector_all("td, th")
        for i, cell in enumerate(cells):
            txt = (await cell.inner_text()).strip()
            if any(kw in txt for kw in ["D面", "16:00", "18:00"]):
                id_     = await cell.get_attribute("id") or ""
                cls     = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                a       = await cell.query_selector("a")
                href    = (await a.get_attribute("href") or "") if a else ""
                print(f"  CELL[{i}] text={txt!r} id={id_!r} class={cls!r} "
                      f"onclick={onclick!r} href={href!r}")

        await browser.close()
        print(f"\n\n✅ 解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print("  reserve.py のセレクターをここで確認した値に合わせてください。")


if __name__ == "__main__":
    asyncio.run(analyze())
