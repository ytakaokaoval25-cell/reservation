"""
まんまるよやく2 サイト構造解析スクリプト
====================================================
各ステップのHTML・スクリーンショットを保存して
正確なセレクターを確認する。

■ 使い方（ローカルPCで実行すること ※日本国内IP必須）
  pip install playwright
  playwright install chromium
  python analyze_site.py

■ 出力先
  analysis_output/01_login.html        ← ログインページHTML
  analysis_output/01_login.png         ← スクリーンショット
  analysis_output/02_after_login.html  ← ログイン後
  analysis_output/03_favorite.html     ← お気に入り後（絞り込み画面）
  analysis_output/04_search.html       ← 検索結果
  (コンソールに全セレクター情報を出力)
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"
OUTPUT_DIR = "analysis_output"

# ローカルのChromium実行パス（インストール後に playwright install で自動解決）
# 明示したい場合はここに指定（例: r"C:\Users\xxx\AppData\Local\ms-playwright\chromium-xxxx\chrome-win\chrome.exe"）
CHROMIUM_PATH: str | None = None


# ─────────────────────────────────────────────────────────
async def save_step(page, name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ss_path = f"{OUTPUT_DIR}/{name}.png"
    html_path = f"{OUTPUT_DIR}/{name}.html"
    await page.screenshot(path=ss_path, full_page=True)
    html = await page.content()
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [SAVED] {ss_path}  /  {html_path}")


async def dump_page_structure(page, label: str):
    """ページ内の全フォーム要素・リンク・テーブルを出力"""
    sep = "─" * 60
    print(f"\n{sep}")
    print(f"  {label}")
    print(f"  URL: {page.url}")
    print(sep)

    # ── INPUT ──────────────────────────────────────────
    inputs = await page.query_selector_all("input")
    if inputs:
        print(f"\n  【INPUT要素】({len(inputs)}件)")
        for inp in inputs:
            t    = await inp.get_attribute("type")  or "text"
            name = await inp.get_attribute("name")  or ""
            id_  = await inp.get_attribute("id")    or ""
            cls  = await inp.get_attribute("class") or ""
            val  = await inp.get_attribute("value") or ""
            print(f"    type={t:<12} name={name!r:<20} id={id_!r:<20} class={cls!r:<20} value={val!r}")

    # ── SELECT ─────────────────────────────────────────
    selects = await page.query_selector_all("select")
    if selects:
        print(f"\n  【SELECT要素】({len(selects)}件)")
        for sel in selects:
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id")   or ""
            cls  = await sel.get_attribute("class") or ""
            opts = await sel.query_selector_all("option")
            print(f"    SELECT name={name!r} id={id_!r} class={cls!r}  → {len(opts)}オプション")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                sel_flag = await opt.get_attribute("selected")
                flag = " ★selected" if sel_flag is not None else ""
                print(f"      OPTION value={v!r:<20} text={txt!r}{flag}")

    # ── BUTTON / SUBMIT ────────────────────────────────
    buttons = await page.query_selector_all(
        "button, input[type=submit], input[type=button], input[type=image]"
    )
    if buttons:
        print(f"\n  【ボタン要素】({len(buttons)}件)")
        for btn in buttons:
            t    = await btn.get_attribute("type")  or ""
            name = await btn.get_attribute("name")  or ""
            id_  = await btn.get_attribute("id")    or ""
            val  = await btn.get_attribute("value") or ""
            try:
                txt = (await btn.inner_text()).strip()
            except Exception:
                txt = val
            print(f"    type={t:<12} name={name!r:<20} id={id_!r:<20} value={val!r:<20} text={txt!r}")

    # ── FORM ───────────────────────────────────────────
    forms = await page.query_selector_all("form")
    if forms:
        print(f"\n  【FORM要素】({len(forms)}件)")
        for form in forms:
            action = await form.get_attribute("action") or ""
            method = await form.get_attribute("method") or ""
            id_    = await form.get_attribute("id")     or ""
            name   = await form.get_attribute("name")   or ""
            print(f"    FORM name={name!r} id={id_!r} action={action!r} method={method!r}")

    # ── ANCHOR ─────────────────────────────────────────
    links = await page.query_selector_all("a")
    visible_links = []
    for link in links:
        txt  = (await link.inner_text()).strip()
        href = await link.get_attribute("href")    or ""
        cls  = await link.get_attribute("class")   or ""
        id_  = await link.get_attribute("id")      or ""
        if txt:
            visible_links.append((txt, href, cls, id_))
    if visible_links:
        print(f"\n  【リンク（テキストあり）】({len(visible_links)}件)")
        for txt, href, cls, id_ in visible_links:
            print(f"    text={txt!r:<30} href={href!r:<40} class={cls!r} id={id_!r}")

    # ── TABLE ──────────────────────────────────────────
    tables = await page.query_selector_all("table")
    if tables:
        print(f"\n  【テーブル】({len(tables)}件)")
        for ti, tbl in enumerate(tables):
            rows = await tbl.query_selector_all("tr")
            print(f"    TABLE[{ti}]  行数={len(rows)}")
            for ri, row in enumerate(rows[:10]):
                cells = await row.query_selector_all("td, th")
                row_info = []
                for cell in cells:
                    txt     = (await cell.inner_text()).strip().replace("\n", " ")[:30]
                    cls     = await cell.get_attribute("class")   or ""
                    onclick = await cell.get_attribute("onclick") or ""
                    href_a  = ""
                    anc     = await cell.query_selector("a")
                    if anc:
                        href_a = await anc.get_attribute("href") or ""
                    row_info.append(f"{txt!r}(cls={cls!r},onclick={onclick!r},href={href_a!r})")
                print(f"      ROW[{ri}]: {' | '.join(row_info[:6])}")
            if len(rows) > 10:
                print(f"      ... 残り {len(rows)-10} 行省略")

    # ── onclick属性を持つ全要素 ─────────────────────────
    onclicks = await page.query_selector_all("[onclick]")
    if onclicks:
        print(f"\n  【onclick属性を持つ要素】({len(onclicks)}件)")
        for elem in onclicks[:30]:
            tag     = await elem.evaluate("el => el.tagName")
            onclick = await elem.get_attribute("onclick") or ""
            txt     = (await elem.inner_text()).strip()[:30]
            cls     = await elem.get_attribute("class") or ""
            print(f"    <{tag}> onclick={onclick!r:<60} class={cls!r} text={txt!r}")


# ─────────────────────────────────────────────────────────
async def analyze():
    async with async_playwright() as p:
        launch_opts = {
            "headless": False,   # ← 実際の画面を見ながら解析する（必要なら True に変更）
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
            "slow_mo": 500,      # 人間らしい操作速度（ms）
        }
        if CHROMIUM_PATH:
            launch_opts["executable_path"] = CHROMIUM_PATH

        browser = await p.chromium.launch(**launch_opts)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,
        )
        page = await ctx.new_page()

        # ══════════════════════════════════════════════
        # Step 1: ログインページ
        # ══════════════════════════════════════════════
        print("\n" + "═" * 60)
        print("[Step 1] ログインページに移動...")
        print("═" * 60)
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
        await save_step(page, "01_login")
        await dump_page_structure(page, "ログインページ")

        # ══════════════════════════════════════════════
        # Step 2: ログイン実行
        # ══════════════════════════════════════════════
        print("\n" + "═" * 60)
        print("[Step 2] ログイン実行...")
        print("═" * 60)

        # 最初のtextまたはtel/number系inputに利用者番号を入力
        all_inputs = await page.query_selector_all("input")
        filled_id = False
        for inp in all_inputs:
            t = await inp.get_attribute("type") or "text"
            if t.lower() in ("text", "tel", "number", "email"):
                name = await inp.get_attribute("name") or ""
                id_  = await inp.get_attribute("id")   or ""
                await inp.fill(USER_ID)
                print(f"  → 利用者番号入力: type={t!r} name={name!r} id={id_!r}")
                filled_id = True
                break

        if not filled_id:
            print("  [WARNING] 利用者番号フィールドが見つかりません")

        pw = await page.query_selector("input[type=password]")
        if pw:
            name = await pw.get_attribute("name") or ""
            await pw.fill(PASSWORD)
            print(f"  → パスワード入力: name={name!r}")
        else:
            print("  [WARNING] パスワードフィールドが見つかりません")

        sub = await page.query_selector("input[type=submit], button[type=submit]")
        if sub:
            val = await sub.get_attribute("value") or ""
            print(f"  → サブミット: value={val!r}")
            await sub.click()
        else:
            print("  [WARNING] サブミットボタンが見つかりません")

        await page.wait_for_load_state("networkidle", timeout=20_000)
        await save_step(page, "02_after_login")
        await dump_page_structure(page, "ログイン後ページ")

        # ══════════════════════════════════════════════
        # Step 3: お気に入りクリック
        # ══════════════════════════════════════════════
        print("\n" + "═" * 60)
        print("[Step 3] お気に入りをクリック...")
        print("═" * 60)

        clicked = False
        for sel in [
            'a:text("お気に入り")',
            'input[value="お気に入り"]',
            'button:text("お気に入り")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=3_000)
                if elem:
                    txt = (await elem.inner_text()).strip() if await elem.inner_text() else ""
                    href = await elem.get_attribute("href") or ""
                    print(f"  → お気に入り要素: selector={sel!r} text={txt!r} href={href!r}")
                    await elem.click()
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            # テキストで全要素を検索
            all_elems = await page.query_selector_all("a, button, input[type=submit], input[type=button]")
            for elem in all_elems:
                try:
                    txt = (await elem.inner_text()).strip()
                except Exception:
                    txt = await elem.get_attribute("value") or ""
                if "お気に入り" in txt:
                    href  = await elem.get_attribute("href")  or ""
                    cls   = await elem.get_attribute("class") or ""
                    print(f"  → お気に入り（フォールバック）: text={txt!r} href={href!r} class={cls!r}")
                    await elem.click()
                    clicked = True
                    break

        if not clicked:
            print("  [WARNING] お気に入りリンクが見つかりません！")

        await page.wait_for_load_state("networkidle", timeout=20_000)
        await save_step(page, "03_favorite")
        await dump_page_structure(page, "お気に入り後（絞り込み画面）")

        # ══════════════════════════════════════════════
        # Step 4: 日付プルダウン詳細確認
        # ══════════════════════════════════════════════
        print("\n" + "═" * 60)
        print("[Step 4] 日付プルダウン全optionを出力...")
        print("═" * 60)
        selects = await page.query_selector_all("select")
        for si, sel in enumerate(selects):
            name  = await sel.get_attribute("name")  or ""
            id_   = await sel.get_attribute("id")    or ""
            opts  = await sel.query_selector_all("option")
            print(f"\n  SELECT[{si}] name={name!r} id={id_!r}")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    OPTION value={v!r:<25} text={txt!r}")

        # ══════════════════════════════════════════════
        # Step 5: 令和08年06月19日を選択して検索
        # ══════════════════════════════════════════════
        print("\n" + "═" * 60)
        print("[Step 5] 令和08年06月19日を選択して検索...")
        print("═" * 60)

        date_texts  = ["令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日"]
        date_values = ["20260619", "2026-06-19", "2026/06/19", "260619"]
        date_selected = False

        for sel in await page.query_selector_all("select"):
            for opt in await sel.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in date_texts) or v in date_values:
                    sel_name = await sel.get_attribute("name") or ""
                    await sel.select_option(value=v) if v else await sel.select_option(label=txt)
                    print(f"  → 日付選択: SELECT name={sel_name!r}  value={v!r}  text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません。analysis_output/03_favorite.html を確認してください")

        # 検索ボタン
        for sel in [
            'input[value="検索"]',
            'input[value*="検索"]',
            'button:text("検索")',
            'input[type="submit"]',
            'button[type="submit"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2_000)
                if elem:
                    val = await elem.get_attribute("value") or ""
                    print(f"  → 検索ボタン: selector={sel!r} value={val!r}")
                    await elem.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20_000)
        await save_step(page, "04_search_results")
        await dump_page_structure(page, "検索結果ページ")

        # ══════════════════════════════════════════════
        # Step 6: D面 16:00〜18:00 セルの詳細解析
        # ══════════════════════════════════════════════
        print("\n" + "═" * 60)
        print("[Step 6] D面・16:00関連セルの詳細解析...")
        print("═" * 60)
        cells = await page.query_selector_all("td, th")
        print(f"  全セル数: {len(cells)}")
        for i, cell in enumerate(cells):
            txt     = (await cell.inner_text()).strip()
            cls     = await cell.get_attribute("class")   or ""
            onclick = await cell.get_attribute("onclick") or ""
            id_     = await cell.get_attribute("id")      or ""
            # D面または16:00を含むもの
            if "D面" in txt or "D面" in cls or "16:00" in txt or "16:00" in onclick:
                anc = await cell.query_selector("a")
                href = ""
                if anc:
                    href = await anc.get_attribute("href") or ""
                print(
                    f"  CELL[{i:03d}] text={txt!r:<30} id={id_!r:<15} "
                    f"class={cls!r:<20} onclick={onclick!r:<40} href={href!r}"
                )

        print("\n\n" + "═" * 60)
        print("  解析完了！")
        print(f"  出力フォルダ: {os.path.abspath(OUTPUT_DIR)}/")
        print("  → 各HTMLファイルをブラウザで開いてセレクターを確認してください")
        print("═" * 60)

        input("\n  [Enter]を押すとブラウザを閉じます...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(analyze())
