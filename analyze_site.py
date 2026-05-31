"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する。

■ 使い方
  pip install playwright
  playwright install chromium
  python analyze_site.py

■ 出力フォルダ: analysis_output/
  01_login_page.html/png    ← ログインページ（フォーム要素を確認）
  02_after_login.html/png   ← ログイン後メニュー（お気に入りリンクを確認）
  03_after_favorite.html/png← 絞り込み画面（SELECTのname/value/textを確認）
  04_search_results.html/png← 検索結果（テーブル構造・セルのclass/onclickを確認）
"""

import asyncio
import os
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

# 解析対象日（reserve.pyと同じ値を使う）
TARGET_DATE_TEXTS  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19"]
TARGET_DATE_VALUES = ["20260619", "2026-06-19", "260619"]


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / {step_name}.html")


async def dump_form_elements(page, label: str):
    print(f"\n{'='*60}")
    print(f"=== {label} ===")
    print(f"URL: {page.url}")
    print("=" * 60)

    # FORMのaction/method
    form = await page.query_selector("form")
    if form:
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        print(f"\n[FORM] action={action!r}  method={method!r}")

    # INPUT
    print("\n[INPUT要素]")
    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  type={t:<12} name={name:<20} id={id_:<20} class={cls:<20} value={val!r}")

    # SELECT + OPTION（全件）
    print("\n[SELECT要素]")
    selects = await page.query_selector_all("select")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        print(f"\n  SELECT name={name!r}  id={id_!r}  class={cls!r}")
        options = await sel.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_flag = " ← ★ターゲット" if (
                any(t in txt for t in TARGET_DATE_TEXTS) or v in TARGET_DATE_VALUES
            ) else ""
            print(f"    value={v!r:<20} text={txt!r}{sel_flag}")

    # BUTTON / submit
    print("\n[BUTTON要素]")
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
        print(f"  type={t:<8} name={name:<20} id={id_:<20} value={val!r}  text={txt!r}")

    # リンク
    print("\n[Aリンク]")
    links = await page.query_selector_all("a")
    for link in links:
        href = await link.get_attribute("href") or ""
        cls  = await link.get_attribute("class") or ""
        try:
            txt = (await link.inner_text()).strip()
        except Exception:
            txt = ""
        if txt:
            print(f"  href={href!r:<50}  class={cls:<20}  text={txt!r}")


async def dump_table_structure(page):
    print(f"\n{'='*60}")
    print("=== テーブル構造（検索結果）===")

    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        print(f"\n[TABLE {ti}] 行数={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_data = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip().replace("\n", " ")[:20]
                cls     = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                href_a  = ""
                inner_a = await cell.query_selector("a")
                if inner_a:
                    href_a = await inner_a.get_attribute("href") or ""
                info = f"{txt}"
                if cls:
                    info += f"(cls={cls})"
                if onclick:
                    info += f"(onclick=...)"
                if href_a:
                    info += f"(href=...)"
                row_data.append(info)
            print(f"  行[{ri:2}]: {' | '.join(row_data[:10])}")

    # D面・16:00 を含むセルの詳細
    print(f"\n[D面・16:00 関連セル詳細]")
    cells = await page.query_selector_all("td, th")
    for i, cell in enumerate(cells):
        txt     = (await cell.inner_text()).strip()
        id_     = await cell.get_attribute("id") or ""
        cls     = await cell.get_attribute("class") or ""
        onclick = await cell.get_attribute("onclick") or ""
        if "D面" in txt or "16:00" in txt or "18:00" in txt:
            print(f"  CELL[{i}] text={txt!r}  id={id_!r}  class={cls!r}  onclick={onclick!r}")

    # clickable要素（onclick or aタグ）の一覧
    print(f"\n[クリック可能要素（onclick or a）]")
    clickables = await page.query_selector_all("[onclick], td > a, th > a")
    for elem in clickables[:30]:
        tag     = await elem.evaluate("e => e.tagName")
        txt     = (await elem.inner_text()).strip()[:30]
        cls     = await elem.get_attribute("class") or ""
        onclick = await elem.get_attribute("onclick") or ""
        href    = await elem.get_attribute("href") or ""
        print(f"  {tag:<4} text={txt!r:<25} class={cls:<15} onclick={onclick[:50]!r}  href={href[:50]!r}")


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
        )
        page = await context.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        # ── Step 1: ログインページ ─────────────────────────────
        print("\n[Step 1] ログインページ解析...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_form_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ──────────────────────────────
        print("\n[Step 2] ログイン実行...")
        userid_candidates = [
            'input[name="userid"]', 'input[name="uid"]',   'input[name="userno"]',
            'input[name="user_id"]','input[name="memberNo"]','input[name="loginId"]',
            '#userid', '#uid', '#userno',
            'input[type="text"]:first-of-type',
        ]
        for sel in userid_candidates:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.fill(USER_ID)
                    print(f"  [OK] 利用者番号: {sel}")
                    break
            except Exception:
                pass

        for sel in ['input[type="password"]', 'input[name="passwd"]',
                    'input[name="password"]', 'input[name="pass"]', 'input[name="pw"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.fill(PASSWORD)
                    print(f"  [OK] パスワード: {sel}")
                    break
            except Exception:
                pass

        for sel in ['input[value="ログイン"]', 'input[type="submit"]',
                    'button[type="submit"]', 'button:text("ログイン")']:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.click()
                    print(f"  [OK] ログインボタン: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_form_elements(page, "ログイン後ページ")

        # ── Step 3: お気に入りクリック ────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        fav_done = False
        for sel in ['a:text("お気に入り")', 'input[value="お気に入り"]',
                    'button:text("お気に入り")', '[href*="favorite"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.click()
                    print(f"  [OK] お気に入り: {sel}")
                    fav_done = True
                    break
            except Exception:
                pass
        if not fav_done:
            # テキスト全探索
            for elem in await page.query_selector_all("a, button, input"):
                try:
                    txt = (await elem.inner_text()).strip()
                except Exception:
                    txt = ""
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    await elem.click()
                    print(f"  [OK] お気に入り（フォールバック）: {txt!r}")
                    fav_done = True
                    break

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        await dump_form_elements(page, "絞り込み画面（お気に入り後）")

        # ── Step 4: 日付選択して検索 ──────────────────────────
        print("\n[Step 4] 日付選択・検索...")
        date_found = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if (any(t in txt for t in TARGET_DATE_TEXTS) or v in TARGET_DATE_VALUES):
                    await sel_elem.select_option(value=v if v else None, label=txt if not v else None)
                    name = await sel_elem.get_attribute("name") or ""
                    print(f"  [OK] 日付: name={name!r} value={v!r} text={txt!r}")
                    date_found = True
                    break
            if date_found:
                break

        if not date_found:
            print("  [INFO] 日付が見つかりません（SELECTを再確認してください）")

        for sel in ['input[value="検索"]', 'input[type="submit"]',
                    'button[type="submit"]', 'button:text("検索")']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.click()
                    print(f"  [OK] 検索: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        await dump_table_structure(page)

        await browser.close()
        print(f"\n\n{'='*60}")
        print(f"解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print("reserve.py のセレクターを実際の値に合わせて修正してください。")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(analyze())
