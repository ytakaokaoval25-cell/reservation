"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する

■ 使い方
  python analyze_site.py

実行後、analysis_output/ フォルダを開いて .html / .png を確認してください。
"""

import asyncio
import os
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"


def _chromium_path() -> str | None:
    """環境に合ったChromiumの実行ファイルパスを返す。見つからなければ None。"""
    candidates = [
        # このリモート実行環境にプリインストールされているパス
        "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
        "/opt/pw-browsers/chromium/chrome-linux/chrome",
        # Playwright デフォルト（ローカル開発時）
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None  # デフォルト（playwright install chromium が済んでいる場合）


async def save_step(page, name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {OUTPUT_DIR}/{name}.{{html,png}}")


async def dump_elements(page, label: str):
    print(f"\n{'='*50}")
    print(f"=== {label} ===")
    print(f"{'='*50}")

    # INPUT
    for inp in await page.query_selector_all("input"):
        t    = await inp.get_attribute("type")  or "text"
        name = await inp.get_attribute("name")  or ""
        id_  = await inp.get_attribute("id")    or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT  type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r}")

    # SELECT
    for sel in await page.query_selector_all("select"):
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id")   or ""
        cls  = await sel.get_attribute("class") or ""
        opts = await sel.query_selector_all("option")
        print(f"  SELECT name={name!r} id={id_!r} class={cls!r}  [{len(opts)} options]")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            print(f"    OPTION value={v!r}  text={txt!r}")

    # BUTTON / SUBMIT
    for btn in await page.query_selector_all("button, input[type=submit], input[type=button]"):
        t    = await btn.get_attribute("type")  or ""
        name = await btn.get_attribute("name")  or ""
        id_  = await btn.get_attribute("id")    or ""
        val  = await btn.get_attribute("value") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  BUTTON type={t!r} name={name!r} id={id_!r} value={val!r} text={txt!r}")

    # FORM
    for form in await page.query_selector_all("form"):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        print(f"  FORM   action={action!r} method={method!r}")

    # LINKS
    print("\n  --- リンク一覧 ---")
    for a in await page.query_selector_all("a"):
        href    = await a.get_attribute("href")    or ""
        onclick = await a.get_attribute("onclick")  or ""
        txt = (await a.inner_text()).strip()
        if txt:
            print(f"  A  href={href!r}  onclick={onclick!r}  text={txt!r}")


async def dump_table(page, label: str):
    print(f"\n{'='*50}")
    print(f"=== {label} テーブル構造 ===")
    print(f"{'='*50}")
    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")
    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] 行数={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_data = []
            for ci, cell in enumerate(cells):
                txt     = (await cell.inner_text()).strip().replace("\n", " ")
                cls     = await cell.get_attribute("class")   or ""
                id_     = await cell.get_attribute("id")      or ""
                onclick = await cell.get_attribute("onclick") or ""
                a_el    = await cell.query_selector("a")
                href    = (await a_el.get_attribute("href") or "") if a_el else ""
                if txt:
                    row_data.append(
                        f"[{ci}]{txt!r}(cls={cls!r} id={id_!r} onclick={onclick!r} href={href!r})"
                    )
            if row_data:
                print(f"    ROW[{ri}]: {chr(10) + '      | '.join(row_data)}")


async def analyze():
    launch_kwargs = {
        "headless": True,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    cp = _chromium_path()
    if cp:
        launch_kwargs["executable_path"] = cp
        print(f"[INFO] Chromium: {cp}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await ctx.new_page()

        # ── Step 1: ログインページ ──────────────────────────────
        print("\n[Step 1] ログインページ...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ───────────────────────────────
        print("\n[Step 2] ログイン実行...")
        for sel in ['input[name="userno"]', 'input[name="userid"]',
                    '#userno', '#userid', 'input[type="text"]']:
            try:
                el = await page.wait_for_selector(sel, timeout=2000, state="visible")
                if el:
                    await el.fill(USER_ID)
                    print(f"  利用者番号入力: {sel}")
                    break
            except Exception:
                pass

        for sel in ['input[name="passwd"]', 'input[name="password"]',
                    '#passwd', 'input[type="password"]']:
            try:
                el = await page.wait_for_selector(sel, timeout=2000, state="visible")
                if el:
                    await el.fill(PASSWORD)
                    print(f"  パスワード入力: {sel}")
                    break
            except Exception:
                pass

        for sel in ['input[type="submit"]', 'button[type="submit"]',
                    'input[value="ログイン"]']:
            try:
                el = await page.wait_for_selector(sel, timeout=2000, state="visible")
                if el:
                    await el.click()
                    print(f"  ログインクリック: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_elements(page, "ログイン後メニュー")
        print(f"  URL: {page.url}")

        # ── Step 3: お気に入りクリック ─────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        fav_clicked = False
        for el in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            try:
                txt = (await el.inner_text()).strip()
            except Exception:
                txt = ""
            val = await el.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                print(f"  [OK] お気に入り: text={txt!r} val={val!r}")
                await el.click()
                fav_clicked = True
                break
        if not fav_clicked:
            print("  [WARNING] お気に入りが見つかりません")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        await dump_elements(page, "お気に入り後（絞り込み画面）")
        print(f"  URL: {page.url}")

        # ── Step 4: 日付選択・検索 ────────────────────────────
        print("\n[Step 4] 日付選択...")
        target_texts  = ["令和08年06月19日", "令和8年6月19日", "2026年06月19日", "2026/06/19"]
        target_values = ["20260619", "2026-06-19", "260619"]

        date_selected = False
        for sel_el in await page.query_selector_all("select"):
            for opt in await sel_el.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in target_texts) or v in target_values:
                    sel_name = await sel_el.get_attribute("name") or ""
                    if v:
                        await sel_el.select_option(value=v)
                    else:
                        await sel_el.select_option(label=txt)
                    print(f"  [OK] 日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付プルダウンに該当日が見つかりません（上のSELECT出力を確認）")

        for sel in ['input[value="検索"]', 'button:has-text("検索")',
                    'input[type="submit"]', 'button[type="submit"]']:
            try:
                el = await page.wait_for_selector(sel, timeout=2000, state="visible")
                if el:
                    await el.click()
                    print(f"  [OK] 検索ボタン: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        await dump_table(page, "検索結果")
        print(f"  URL: {page.url}")

        await browser.close()

    print(f"\n\n{'='*50}")
    print(f"解析完了！{OUTPUT_DIR}/ フォルダを確認してください。")
    print(f"{'='*50}")
    print("""
次のステップ:
1. analysis_output/04_search_results.html をブラウザで開く
2. コンソールの TABLE ダンプで D面 × 16:00〜18:00 セルのセレクターを確認
3. reserve.py の step_select_slot() を必要に応じて修正
4. python reserve.py --now --headful でテスト実行
""")


if __name__ == "__main__":
    asyncio.run(analyze())
