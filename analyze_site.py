"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する

使い方:
  python analyze_site.py

実行後に analysis_output/ フォルダを確認してください。
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"
OUTPUT_DIR = "analysis_output"

# 既存Chromiumのパス候補（playwright install 不要で動く）
CHROMIUM_CANDIDATES = [
    None,  # デフォルト（playwright install chromium 済みの場合）
    "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
]


def get_executable_path():
    for path in CHROMIUM_CANDIDATES:
        if path is None:
            return None
        if os.path.isfile(path):
            return path
    return None


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ss_path = f"{OUTPUT_DIR}/{step_name}.png"
    html_path = f"{OUTPUT_DIR}/{step_name}.html"
    await page.screenshot(path=ss_path, full_page=True)
    html = await page.content()
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [SAVED] {ss_path}  /  {html_path}")


async def dump_form_elements(page, label: str):
    """ページ内のすべてのフォーム要素・リンクを標準出力に列挙"""
    print(f"\n{'='*60}")
    print(f"  {label} のフォーム要素")
    print(f"{'='*60}")

    # フォームのaction/method
    forms = await page.query_selector_all("form")
    for i, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        enc    = await form.get_attribute("enctype") or ""
        print(f"  FORM[{i}] action={action!r} method={method!r} enctype={enc!r}")

    # INPUT
    print()
    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t   = await inp.get_attribute("type")   or "text"
        name= await inp.get_attribute("name")   or ""
        id_ = await inp.get_attribute("id")     or ""
        cls = await inp.get_attribute("class")  or ""
        val = await inp.get_attribute("value")  or ""
        print(f"  INPUT  type={t:<10} name={name!r:<20} id={id_!r:<20} class={cls!r:<25} value={val!r}")

    # SELECT + OPTION
    print()
    selects = await page.query_selector_all("select")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id")   or ""
        cls  = await sel.get_attribute("class")or ""
        options = await sel.query_selector_all("option")
        print(f"  SELECT name={name!r} id={id_!r} class={cls!r} ({len(options)} options)")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected")
            mark = " [selected]" if sel_attr is not None else ""
            print(f"    OPTION  value={v!r:<20} text={txt!r}{mark}")

    # BUTTON / SUBMIT
    print()
    buttons = await page.query_selector_all(
        "button, input[type=submit], input[type=button], input[type=image]"
    )
    for btn in buttons:
        t   = await btn.get_attribute("type")  or ""
        name= await btn.get_attribute("name")  or ""
        id_ = await btn.get_attribute("id")    or ""
        val = await btn.get_attribute("value") or ""
        cls = await btn.get_attribute("class") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  BUTTON type={t:<8} name={name!r:<20} id={id_!r:<20} class={cls!r:<25} value={val!r} text={txt!r}")

    # TEXTAREA
    textareas = await page.query_selector_all("textarea")
    for ta in textareas:
        name = await ta.get_attribute("name") or ""
        id_  = await ta.get_attribute("id")   or ""
        print(f"  TEXTAREA name={name!r} id={id_!r}")

    # A リンク
    print()
    print("  --- リンク一覧 ---")
    links = await page.query_selector_all("a")
    for link in links:
        href = await link.get_attribute("href")    or ""
        onclick = await link.get_attribute("onclick") or ""
        cls  = await link.get_attribute("class")   or ""
        try:
            txt = (await link.inner_text()).strip()
        except Exception:
            txt = ""
        if txt or href:
            print(f"  A  href={href!r:<50} onclick={onclick!r:<30} class={cls!r:<20} text={txt!r}")


async def dump_table_structure(page, label: str):
    """テーブル構造をすべて出力（検索結果解析用）"""
    print(f"\n{'='*60}")
    print(f"  {label} のテーブル構造")
    print(f"{'='*60}")
    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        tbl_id  = await tbl.get_attribute("id")    or ""
        tbl_cls = await tbl.get_attribute("class") or ""
        rows    = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] id={tbl_id!r} class={tbl_cls!r}  rows={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            parts = []
            for ci, cell in enumerate(cells):
                txt     = (await cell.inner_text()).strip().replace("\n", " ")[:30]
                cls     = await cell.get_attribute("class")   or ""
                id_     = await cell.get_attribute("id")      or ""
                onclick = await cell.get_attribute("onclick") or ""
                href_a  = ""
                inner_a = await cell.query_selector("a")
                if inner_a:
                    href_a = await inner_a.get_attribute("href") or ""
                parts.append(
                    f"[{ci}]{txt!r}(cls={cls!r},id={id_!r},onclick={onclick!r},href={href_a!r})"
                )
            print(f"    ROW[{ri}]: " + " | ".join(parts))


async def analyze():
    exe = get_executable_path()
    print(f"[Browser] executable_path = {exe!r}")

    async with async_playwright() as p:
        launch_kwargs = {
            "headless": True,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if exe:
            launch_kwargs["executable_path"] = exe

        browser = await p.chromium.launch(**launch_kwargs)
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

        # ── Step 1: ログインページ ────────────────────────────────
        print("\n" + "="*60)
        print("[Step 1] ログインページに移動...")
        print("="*60)
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_load_state("networkidle", timeout=10_000)
        print(f"  URL   : {page.url}")
        print(f"  Title : {await page.title()}")
        await save_step(page, "01_login_page")
        await dump_form_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ──────────────────────────────────
        print("\n" + "="*60)
        print("[Step 2] ログイン実行...")
        print("="*60)

        # 利用者番号（name候補を順番に試す）
        userid_filled = False
        for sel in [
            'input[name="userno"]',
            'input[name="userid"]',
            'input[name="user_id"]',
            'input[name="memberNo"]',
            'input[name="loginId"]',
            'input[name="login_id"]',
            'input[name="id"]',
            '#userno', '#userid',
            'input[type="text"]:first-of-type',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.fill(USER_ID)
                    print(f"  [OK] 利用者番号 → {sel}")
                    userid_filled = True
                    break
            except Exception:
                pass
        if not userid_filled:
            print("  [WARNING] 利用者番号フィールドが見つかりません")

        # パスワード
        passwd_filled = False
        for sel in [
            'input[name="passwd"]',
            'input[name="password"]',
            'input[name="pass"]',
            'input[type="password"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.fill(PASSWORD)
                    print(f"  [OK] パスワード → {sel}")
                    passwd_filled = True
                    break
            except Exception:
                pass
        if not passwd_filled:
            print("  [WARNING] パスワードフィールドが見つかりません")

        # サブミット
        for sel in [
            'input[type="submit"]',
            'button[type="submit"]',
            'input[value="ログイン"]',
            'button:has-text("ログイン")',
            'input[name="submit"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.click()
                    print(f"  [OK] ログインボタン → {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15_000)
        print(f"  URL   : {page.url}")
        print(f"  Title : {await page.title()}")
        await save_step(page, "02_after_login")
        await dump_form_elements(page, "ログイン後メニュー")

        # ── Step 3: お気に入りクリック ───────────────────────────
        print("\n" + "="*60)
        print("[Step 3] お気に入りクリック...")
        print("="*60)

        clicked = False
        # まずテキストで探す
        for sel in [
            'a:has-text("お気に入り")',
            'input[value="お気に入り"]',
            'button:has-text("お気に入り")',
            'input[value*="お気に入り"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    txt = (await elem.inner_text()).strip() if await elem.inner_text() else ""
                    print(f"  [OK] お気に入り → {sel} text={txt!r}")
                    await elem.click()
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            # フォールバック: すべての要素からテキスト検索
            for tag in ["a", "button", "input[type=button]", "input[type=submit]"]:
                elems = await page.query_selector_all(tag)
                for elem in elems:
                    try:
                        txt = (await elem.inner_text()).strip()
                    except Exception:
                        txt = ""
                    val = await elem.get_attribute("value") or ""
                    if "お気に入り" in txt or "お気に入り" in val:
                        print(f"  [OK] お気に入り（フォールバック）: tag={tag} text={txt!r} value={val!r}")
                        await elem.click()
                        clicked = True
                        break
                if clicked:
                    break

        if not clicked:
            print("  [WARNING] お気に入りリンクが見つかりません")

        await page.wait_for_load_state("networkidle", timeout=15_000)
        print(f"  URL   : {page.url}")
        print(f"  Title : {await page.title()}")
        await save_step(page, "03_after_favorite")
        await dump_form_elements(page, "お気に入り後（絞り込み画面）")

        # ── Step 4: 日付プルダウン全オプション表示 ───────────────
        print("\n" + "="*60)
        print("[Step 4] 日付プルダウン詳細解析（全オプション表示）")
        print("="*60)
        selects = await page.query_selector_all("select")
        print(f"  SELECT要素数: {len(selects)}")
        for i, sel_elem in enumerate(selects):
            name = await sel_elem.get_attribute("name") or ""
            id_  = await sel_elem.get_attribute("id")   or ""
            cls  = await sel_elem.get_attribute("class")or ""
            options = await sel_elem.query_selector_all("option")
            print(f"\n  SELECT[{i}] name={name!r} id={id_!r} class={cls!r} ({len(options)}件)")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    OPTION value={v!r:<25} text={txt!r}")

        # ── Step 5: 日付選択・検索 ────────────────────────────────
        print("\n" + "="*60)
        print("[Step 5] 令和08年06月19日を選択して検索...")
        print("="*60)

        DATE_TEXTS  = ["令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日", "2026年06月19日"]
        DATE_VALUES = ["20260619", "2026-06-19", "2026/06/19", "260619"]

        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in DATE_TEXTS) or v in DATE_VALUES:
                    sel_name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                    print(f"  [OK] 日付選択: SELECT name={sel_name!r} → value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 対象日付が見つかりません（HTMLを確認してください）")

        # 検索ボタン
        for sel in [
            'input[value="検索"]',
            'input[value*="検索"]',
            'button:has-text("検索")',
            'input[type="submit"]',
            'button[type="submit"]',
            'a:has-text("検索")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    print(f"  [OK] 検索ボタン → {sel}")
                    await elem.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15_000)
        print(f"  URL   : {page.url}")
        await save_step(page, "04_search_results")

        # ── Step 6: 検索結果テーブル全解析 ───────────────────────
        await dump_table_structure(page, "検索結果（予約表）")

        # D面 / 16:00 / 18:00 を含むセルを強調表示
        print("\n  --- D面 / 16:00 / 18:00 を含むセル ---")
        all_cells = await page.query_selector_all("td, th")
        for ci, cell in enumerate(all_cells):
            txt     = (await cell.inner_text()).strip()
            cls     = await cell.get_attribute("class")   or ""
            id_     = await cell.get_attribute("id")      or ""
            onclick = await cell.get_attribute("onclick") or ""
            if any(k in txt for k in ["D面", "16:00", "18:00", "16時", "18時"]):
                print(
                    f"    CELL[{ci}] text={txt!r:<30} class={cls!r:<20} "
                    f"id={id_!r:<15} onclick={onclick!r}"
                )
                inner_link = await cell.query_selector("a")
                if inner_link:
                    href = await inner_link.get_attribute("href") or ""
                    print(f"      └─ A href={href!r}")

        await browser.close()
        print(f"\n\n✅ 解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print("   特に 04_search_results.html で予約テーブルの構造を確認し")
        print("   reserve.py の TARGET_* 定数やセレクターを必要に応じて修正してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
