"""
まんまるよやく2 サイト構造解析スクリプト
ログインから検索結果まで各ステップのHTML・スクリーンショットを保存して
正確なセレクターを確認する。

■ 使い方
  python analyze_site.py

■ 出力先
  analysis_output/01_login_page.html / .png
  analysis_output/02_after_login.html / .png
  ...

※ 日本国内ネットワークからのみ動作します。
"""

import asyncio
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

# Chromiumパス（クラウド環境用。ローカルでは不要な場合は None に変更）
_CHROMIUM_CANDIDATES = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
]

def _find_chromium():
    for path in _CHROMIUM_CANDIDATES:
        if os.path.exists(path):
            return path
    return None

CHROMIUM_PATH = _find_chromium()


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / .html")


async def dump_all_elements(page, label: str):
    print(f"\n{'='*60}")
    print(f"=== {label} ===")
    print(f"{'='*60}")
    print(f"URL: {page.url}")
    print(f"Title: {await page.title()}")

    # FORM
    for form in await page.query_selector_all("form"):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        name   = await form.get_attribute("name") or ""
        print(f"\n<form> action={action!r} method={method!r} name={name!r}")

    # INPUT
    print("\n--- INPUT要素 ---")
    for inp in await page.query_selector_all("input"):
        t   = await inp.get_attribute("type") or "text"
        nm  = await inp.get_attribute("name") or ""
        id_ = await inp.get_attribute("id") or ""
        cls = await inp.get_attribute("class") or ""
        val = await inp.get_attribute("value") or ""
        print(f"  <input type={t!r} name={nm!r} id={id_!r} class={cls!r} value={val!r}>")

    # SELECT（全オプション表示）
    print("\n--- SELECT要素 ---")
    for sel in await page.query_selector_all("select"):
        nm  = await sel.get_attribute("name") or ""
        id_ = await sel.get_attribute("id") or ""
        cls = await sel.get_attribute("class") or ""
        opts = await sel.query_selector_all("option")
        print(f"\n  <select name={nm!r} id={id_!r} class={cls!r}>  ({len(opts)}件)")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected")
            mark = " ★selected" if sel_attr is not None else ""
            print(f"    <option value={v!r}>{txt}{mark}</option>")

    # BUTTON / SUBMIT
    print("\n--- BUTTON/SUBMIT要素 ---")
    for btn in await page.query_selector_all("button, input[type=submit], input[type=button]"):
        tag = await btn.evaluate("el => el.tagName")
        t   = await btn.get_attribute("type") or ""
        nm  = await btn.get_attribute("name") or ""
        id_ = await btn.get_attribute("id") or ""
        val = await btn.get_attribute("value") or ""
        cls = await btn.get_attribute("class") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  <{tag.lower()} type={t!r} name={nm!r} id={id_!r} value={val!r} class={cls!r}> {txt!r}")

    # LINK
    print("\n--- リンク一覧 ---")
    for a in await page.query_selector_all("a"):
        href    = await a.get_attribute("href") or ""
        onclick = await a.get_attribute("onclick") or ""
        try:
            txt = (await a.inner_text()).strip()
        except Exception:
            txt = ""
        if txt or href:
            print(f"  <a href={href!r} onclick={onclick[:60]!r}> {txt!r}")

    # TABLE構造（D面・時間を含む行を重点表示）
    print("\n--- TABLE構造（D面/16:00 検索）---")
    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")
    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        tbl_id  = await tbl.get_attribute("id") or ""
        tbl_cls = await tbl.get_attribute("class") or ""
        print(f"\n  TABLE[{ti}] id={tbl_id!r} class={tbl_cls!r}  行数={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_data = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip()
                cls     = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                id_     = await cell.get_attribute("id") or ""
                entry = f"{txt}"
                if cls:
                    entry += f"[cls:{cls}]"
                if onclick:
                    entry += f"[onclick:{onclick[:40]}]"
                if id_:
                    entry += f"[id:{id_}]"
                row_data.append(entry)
            row_str = " | ".join(row_data[:10])
            # D面・16:00 を含む行は常に表示
            if "D面" in row_str or "16:00" in row_str or "18:00" in row_str:
                print(f"  ★ ROW[{ri}]: {row_str}")
            elif ri < 5:  # 最初の5行は無条件表示
                print(f"    ROW[{ri}]: {row_str}")


async def do_login(page):
    """ログイン実行。セレクターが見つからない場合は詳細をダンプして終了"""
    print("\n[Step 1] ログインページ...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except PWTimeout:
        pass
    await save_step(page, "01_login_page")
    await dump_all_elements(page, "ログインページ")

    # 利用者番号を入力
    userid_selectors = [
        'input[name="userid"]', 'input[name="user_id"]', 'input[name="memberNo"]',
        'input[name="userno"]', 'input[name="loginId"]', 'input[name="login_id"]',
        'input[name="id"]', '#userid', '#user_id', '#memberNo',
        'input[type="text"]',
    ]
    for sel in userid_selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if el:
                await el.fill(USER_ID)
                print(f"\n[OK] 利用者番号: {sel}")
                break
        except PWTimeout:
            pass

    # パスワード入力
    for sel in ['input[type="password"]', 'input[name="passwd"]',
                'input[name="password"]', 'input[name="pass"]', '#passwd']:
        try:
            el = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if el:
                await el.fill(PASSWORD)
                print(f"[OK] パスワード: {sel}")
                break
        except PWTimeout:
            pass

    # サブミット
    for sel in ['input[value="ログイン"]', 'button:text("ログイン")',
                'input[type="submit"]', 'button[type="submit"]']:
        try:
            el = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if el:
                await el.click()
                print(f"[OK] ログインボタン: {sel}")
                break
        except PWTimeout:
            pass

    await page.wait_for_load_state("networkidle", timeout=20_000)
    await save_step(page, "02_after_login")
    await dump_all_elements(page, "ログイン後")


async def do_favorite(page):
    print("\n[Step 2] お気に入りクリック...")
    for sel in [
        'a:text("お気に入り")', 'input[value="お気に入り"]', 'input[value*="お気に入り"]',
        'button:text("お気に入り")', 'td:text("お気に入り")',
    ]:
        try:
            el = await page.wait_for_selector(sel, timeout=3000, state="visible")
            if el:
                await el.click()
                print(f"[OK] お気に入り: {sel}")
                break
        except PWTimeout:
            pass
    else:
        # テキスト全走査
        for el in await page.query_selector_all("a, button, input, td"):
            try:
                txt = (await el.inner_text()).strip()
                val = await el.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    await el.click()
                    print(f"[OK] お気に入り（走査）: text={txt!r}")
                    break
            except Exception:
                pass

    await page.wait_for_load_state("networkidle", timeout=20_000)
    await save_step(page, "03_favorite_filter")
    await dump_all_elements(page, "お気に入り後（絞り込み画面）")


async def do_date_select(page):
    print("\n[Step 3] 日付プルダウン解析（選択はしない）...")
    # すべてのSELECTを完全ダンプ（dump_all_elementsで実施済み）
    # 6月19日に相当するvalueを探して表示するだけ
    target_texts = ["令和08年06月19日", "令和8年6月19日", "2026年06月19日", "2026/06/19"]
    target_vals  = ["20260619", "2026-06-19", "2026/06/19", "260619"]

    print("\n  [検索] 令和08年06月19日 相当のoption を探します...")
    for sel_el in await page.query_selector_all("select"):
        sel_name = await sel_el.get_attribute("name") or ""
        for opt in await sel_el.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if any(t in txt for t in target_texts) or v in target_vals:
                print(f"  ★ 発見: select[name={sel_name!r}] value={v!r} text={txt!r}")


async def analyze():
    launch_opts = {
        "headless": True,
        "args": ["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    }
    if CHROMIUM_PATH:
        launch_opts["executable_path"] = CHROMIUM_PATH

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_opts)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,
        )
        await context.add_init_script(
            "window.confirm = () => true; window.alert = () => {};"
        )
        page = await context.new_page()

        await do_login(page)
        await do_favorite(page)
        await do_date_select(page)

        # 日付選択して検索
        print("\n[Step 4] 日付を選択して検索実行...")
        date_selected = False
        target_texts = ["令和08年06月19日", "令和8年6月19日", "2026年06月19日"]
        target_vals  = ["20260619", "2026-06-19", "2026/06/19", "260619"]

        for sel_el in await page.query_selector_all("select"):
            for opt in await sel_el.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in target_texts) or v in target_vals:
                    await sel_el.select_option(value=v or txt)
                    print(f"  [OK] 日付選択: value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません")

        # 検索ボタン
        for sel in ['input[value="検索"]', 'input[value*="検索"]', 'input[value*="照会"]',
                    'button:text("検索")', 'input[type="submit"]', 'button[type="submit"]']:
            try:
                el = await page.wait_for_selector(sel, timeout=2000, state="visible")
                if el:
                    await el.click()
                    print(f"  [OK] 検索ボタン: {sel}")
                    break
            except PWTimeout:
                pass

        await page.wait_for_load_state("networkidle", timeout=20_000)
        await save_step(page, "04_search_results")
        await dump_all_elements(page, "検索結果（D面・時間スロット確認）")

        await browser.close()
        print(f"\n\n解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print("reserve.py のセレクターを analysis_output/*.html を参照して調整してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
