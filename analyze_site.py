"""
まんまるよやく2 サイト構造解析スクリプト

reserve.py が動かない場合にまずこれを実行し、
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する。

使い方:
  python analyze_site.py
  python analyze_site.py --headful   # ブラウザ表示あり

出力先: ./analysis_output/
  01_login_page.html/png     → ログインフォームのinput name/id
  02_after_login.html/png    → ログイン後メニュー（お気に入りリンクを確認）
  03_after_favorite.html/png → 絞り込み画面（日付SELECT を確認）
  04_search_results.html/png → 検索結果グリッド（D面×16:00 のセルを確認）
"""

import asyncio
import sys
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
    print(f"  [SAVED] {OUTPUT_DIR}/{step_name}.png  /  {step_name}.html")


def print_separator(label: str):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print("=" * 60)


async def dump_inputs(page, label: str):
    print_separator(label + " - フォーム要素一覧")

    # INPUT
    for inp in await page.query_selector_all("input"):
        t    = (await inp.get_attribute("type") or "text").lower()
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT  type={t!r:10} name={name!r:20} id={id_!r:20} class={cls!r:20} value={val!r}")

    # SELECT（全オプションを出力）
    for sel in await page.query_selector_all("select"):
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        print(f"\n  SELECT name={name!r} id={id_!r} class={cls!r}")
        for opt in await sel.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            selected = await opt.get_attribute("selected") or ""
            print(f"    OPTION  value={v!r:20}  text={txt!r}  {'[selected]' if selected else ''}")

    # BUTTON / SUBMIT
    for btn in await page.query_selector_all("button, input[type=submit], input[type=button]"):
        t    = (await btn.get_attribute("type") or "").lower()
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        val  = await btn.get_attribute("value") or ""
        txt  = (await btn.inner_text()).strip() if await btn.inner_text() else ""
        print(f"  BUTTON type={t!r:10} name={name!r:20} id={id_!r:20} value={val!r:20} text={txt!r}")

    # LINK（メニューナビ）
    print("\n  --- リンク ---")
    for link in await page.query_selector_all("a"):
        href    = await link.get_attribute("href") or ""
        onclick = await link.get_attribute("onclick") or ""
        txt     = (await link.inner_text()).strip()
        if txt:
            print(f"  A  href={href!r:40}  onclick={onclick!r:40}  text={txt!r}")


async def dump_table_structure(page, label: str):
    print_separator(label + " - テーブル構造")
    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] 行数={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_data = []
            for ci, cell in enumerate(cells):
                txt     = (await cell.inner_text()).strip().replace("\n", " ")[:30]
                cls     = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                bgcolor = await cell.get_attribute("bgcolor") or ""
                row_data.append(
                    f"[{ci}]{txt!r}"
                    + (f"(cls={cls})" if cls else "")
                    + (f"(onclick=...)" if onclick else "")
                    + (f"(bg={bgcolor})" if bgcolor else "")
                )
            print(f"    ROW[{ri:2}]: " + "  |  ".join(row_data[:8]))
            if len(cells) > 8:
                print(f"           ... ({len(cells)}列)")


async def try_fill(page, selectors, value, label):
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if elem:
                await elem.fill(value)
                print(f"  [OK] {label}: {sel}")
                return sel
        except Exception:
            pass
    print(f"  [FAIL] {label}: 全セレクター失敗")
    return None


async def try_click(page, selectors, label):
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if elem:
                await elem.click()
                print(f"  [OK] {label}: {sel}")
                return sel
        except Exception:
            pass
    print(f"  [FAIL] {label}: 全セレクター失敗")
    return None


async def analyze():
    headless = "--headful" not in sys.argv
    print(f"まんまるよやく2 サイト解析開始 (headless={headless})")
    print(f"出力先: {os.path.abspath(OUTPUT_DIR)}/\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()

        # ── Step 1: ログインページ ──────────────────────────────────
        print("\n[Step 1] ログインページ")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_inputs(page, "ログインページ")

        form = await page.query_selector("form")
        if form:
            action = await form.get_attribute("action") or ""
            method = await form.get_attribute("method") or ""
            print(f"\n  FORM action={action!r} method={method!r}")

        # ── Step 2: ログイン実行 ────────────────────────────────────
        print("\n[Step 2] ログイン実行")
        await try_fill(page, [
            'input[name="userid"]', 'input[name="user_id"]', 'input[name="memberNo"]',
            'input[name="userno"]', 'input[name="loginId"]', 'input[name="login_id"]',
            'input[name="id"]', '#userid', 'input[type="text"]:first-of-type',
        ], USER_ID, "利用者番号")

        await try_fill(page, [
            'input[type="password"]', 'input[name="passwd"]',
            'input[name="password"]', 'input[name="pass"]', '#passwd',
        ], PASSWORD, "パスワード")

        await try_click(page, [
            'input[value="ログイン"]', 'input[type="submit"]',
            'button[type="submit"]', 'input[name="submit"]',
        ], "ログインボタン")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_inputs(page, "ログイン後ページ")
        print(f"  URL: {page.url}")

        # ── Step 3: お気に入りクリック ─────────────────────────────
        print("\n[Step 3] お気に入りクリック")
        fav_sel = await try_click(page, [
            'a:has-text("お気に入り")',
            'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
        ], "お気に入り")

        if not fav_sel:
            # フォールバック: 全リンクを検索
            for elem in await page.query_selector_all("a, input[type=button], button"):
                txt = (await elem.inner_text()).strip()
                val = (await elem.get_attribute("value") or "").strip()
                if "お気に入り" in txt or "お気に入り" in val:
                    href    = await elem.get_attribute("href") or ""
                    onclick = await elem.get_attribute("onclick") or ""
                    print(f"  [FOUND] お気に入り: text={txt!r} val={val!r} href={href!r} onclick={onclick!r}")
                    await elem.click()
                    break

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        await dump_inputs(page, "お気に入り後（絞り込み画面）")
        print(f"  URL: {page.url}")

        # ── Step 4: 日付プルダウン詳細解析（選択して検索） ──────────
        print("\n[Step 4] 日付プルダウン・検索")
        date_targets_txt = ["令和08年06月19日", "令和8年6月19日", "2026/06/19", "2026年06月19日"]
        date_targets_val = ["20260619", "2026-06-19", "260619"]
        date_selected = False

        for sel_elem in await page.query_selector_all("select"):
            name = await sel_elem.get_attribute("name") or ""
            id_  = await sel_elem.get_attribute("id") or ""
            options = await sel_elem.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r} ({len(options)}件)")
            for opt in options:
                v   = (await opt.get_attribute("value") or "").strip()
                txt = (await opt.inner_text()).strip()
                matched = (
                    any(t in txt for t in date_targets_txt)
                    or v in date_targets_val
                )
                mark = " ← ★TARGET★" if matched else ""
                print(f"    OPTION  value={v!r:25}  text={txt!r}{mark}")
                if matched and not date_selected:
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 日付選択完了: {txt!r}")
                    date_selected = True

        if not date_selected:
            print("  [WARNING] 対象日が見つかりません。03_after_favorite.html を確認してください。")

        await try_click(page, [
            'input[value="検索"]', 'input[value="絞込み検索"]', 'input[value="空き照会"]',
            'button:text("検索")', 'input[type="submit"]', 'button[type="submit"]',
        ], "検索ボタン")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        print(f"  URL: {page.url}")

        # ── Step 5: 検索結果テーブル詳細解析 ──────────────────────
        await dump_table_structure(page, "検索結果グリッド")

        # D面 × 16:00 に関係するセルをピックアップ
        print_separator("D面・16:00 関連セル一覧")
        for i, cell in enumerate(await page.query_selector_all("td, th")):
            txt     = (await cell.inner_text()).strip()
            if not ("D面" in txt or "16:00" in txt or "16" in txt[:5]):
                continue
            id_     = await cell.get_attribute("id") or ""
            cls     = await cell.get_attribute("class") or ""
            onclick = await cell.get_attribute("onclick") or ""
            bgcolor = await cell.get_attribute("bgcolor") or ""
            href    = ""
            a = await cell.query_selector("a")
            if a:
                href = await a.get_attribute("href") or ""
            print(f"  CELL[{i:3}] id={id_!r:15} class={cls!r:20} bgcolor={bgcolor!r:10} "
                  f"onclick={onclick!r:50} href={href!r:30} text={txt!r}")

        await browser.close()

        print("\n" + "=" * 60)
        print(f"解析完了。次のファイルを確認してください:")
        print(f"  {os.path.abspath(OUTPUT_DIR)}/01_login_page.html    ← ログインフォームのname/id")
        print(f"  {os.path.abspath(OUTPUT_DIR)}/02_after_login.html   ← お気に入りリンク")
        print(f"  {os.path.abspath(OUTPUT_DIR)}/03_after_favorite.html ← 日付SELECTのvalue値")
        print(f"  {os.path.abspath(OUTPUT_DIR)}/04_search_results.html ← D面×16:00セルのclass/onclick")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(analyze())
