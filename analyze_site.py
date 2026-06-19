"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショット・フォーム要素を保存して
正確なセレクターを確認する

使い方:
  python analyze_site.py

出力先: analysis_output/
  01_login_page.html/png    … ログインページ
  02_after_login.html/png   … ログイン後メニュー
  03_after_favorite.html/png … お気に入り後（絞り込み画面）
  04_search_results.html/png … 検索結果（予約表）

コンソールに INPUT / SELECT / BUTTON / A タグの属性が出力されるので
reserve.py のセレクターと照合してください。
"""

import asyncio
import os
import glob
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

# 日付検索用
DATE_TARGET_VALUES = ["20260619", "2026-06-19", "260619", "0619"]
DATE_TARGET_TEXTS  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19", "2026年06月19日"]


def find_chromium():
    """利用可能なChromiumの実行ファイルパスを返す（なければNone）"""
    candidates = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    candidates += glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"))
    return candidates[0] if candidates else None


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {OUTPUT_DIR}/{step_name}.png / .html")


async def dump_form_elements(page, label: str):
    print(f"\n{'='*60}")
    print(f" {label}  ({page.url})")
    print(f"{'='*60}")

    # FORM
    for form in await page.query_selector_all("form"):
        a = await form.get_attribute("action") or ""
        m = await form.get_attribute("method") or ""
        print(f"FORM  action={a!r}  method={m!r}")

    # INPUT
    for inp in await page.query_selector_all("input"):
        t  = await inp.get_attribute("type")  or "text"
        n  = await inp.get_attribute("name")  or ""
        i  = await inp.get_attribute("id")    or ""
        v  = await inp.get_attribute("value") or ""
        cl = await inp.get_attribute("class") or ""
        print(f"  INPUT  type={t!r}  name={n!r}  id={i!r}  value={v!r}  class={cl!r}")

    # SELECT + OPTIONS
    for sel in await page.query_selector_all("select"):
        n  = await sel.get_attribute("name")  or ""
        i  = await sel.get_attribute("id")    or ""
        cl = await sel.get_attribute("class") or ""
        opts = await sel.query_selector_all("option")
        print(f"  SELECT  name={n!r}  id={i!r}  class={cl!r}  ({len(opts)}件)")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            print(f"      OPTION  value={v!r}  text={txt!r}")

    # BUTTON / SUBMIT
    for btn in await page.query_selector_all(
        "button, input[type=submit], input[type=button], input[type=image]"
    ):
        t  = await btn.get_attribute("type")  or ""
        n  = await btn.get_attribute("name")  or ""
        v  = await btn.get_attribute("value") or ""
        i  = await btn.get_attribute("id")    or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = ""
        print(f"  BUTTON  type={t!r}  name={n!r}  id={i!r}  value={v!r}  text={txt!r}")

    # A リンク
    print(f"  --- リンク ---")
    for a in await page.query_selector_all("a"):
        href = await a.get_attribute("href")    or ""
        oc   = await a.get_attribute("onclick") or ""
        try:
            txt = (await a.inner_text()).strip()
        except Exception:
            txt = ""
        if txt or href:
            print(f"  A  href={href!r}  onclick={oc[:60]!r}  text={txt!r}")


async def analyze_table(page):
    """検索結果テーブルの構造を解析する"""
    print("\n=== テーブル構造解析 ===")
    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        print(f"\n[TABLE {ti}]  行数={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for ci, cell in enumerate(cells):
                txt  = (await cell.inner_text()).strip()
                cls  = await cell.get_attribute("class")   or ""
                oc   = await cell.get_attribute("onclick") or ""
                href = ""
                a    = await cell.query_selector("a")
                if a:
                    href = await a.get_attribute("href") or ""
                row_info.append(f"[{ci}]{txt}(cls={cls},oc={oc[:30]},href={href[:30]})")
            print(f"  ROW[{ri}]: " + " | ".join(row_info[:10]))

    # D面 / 16:00 / 18:00 を含むセルを強調表示
    print("\n=== D面/16:00/18:00 を含むセル ===")
    for cell in await page.query_selector_all("td, th"):
        txt = (await cell.inner_text()).strip()
        if "D面" in txt or "16:00" in txt or "18:00" in txt:
            cls = await cell.get_attribute("class")   or ""
            oc  = await cell.get_attribute("onclick") or ""
            a   = await cell.query_selector("a")
            href = ""
            if a:
                href = await a.get_attribute("href") or ""
            print(f"  CELL  text={txt!r}  class={cls!r}  onclick={oc!r}  a_href={href!r}")


async def analyze():
    chromium_path = find_chromium()
    launch_kwargs = {}
    if chromium_path:
        print(f"[INFO] Chromium: {chromium_path}")
        launch_kwargs["executable_path"] = chromium_path

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            **launch_kwargs,
        )
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
            "window.confirm = () => true; window.alert = () => {}; window.prompt = () => null;"
        )
        page = await context.new_page()

        # ────────────────────────────────────────────────
        # Step 1: ログインページ
        # ────────────────────────────────────────────────
        print("\n[Step 1] ログインページに移動...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
        await save_step(page, "01_login_page")
        await dump_form_elements(page, "ログインページ")

        # ────────────────────────────────────────────────
        # Step 2: ログイン実行
        # ────────────────────────────────────────────────
        print("\n[Step 2] ログイン実行...")
        filled_userid = False
        for sel in [
            'input[name="userid"]', 'input[name="user_id"]',
            'input[name="memberNo"]', 'input[name="userno"]',
            'input[name="loginId"]', 'input[name="login_id"]',
            '#userid', 'input[type="text"]:first-of-type',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=2_000)
                if e:
                    await e.fill(USER_ID)
                    print(f"  [OK] 利用者番号: {sel}")
                    filled_userid = True
                    break
            except Exception:
                pass
        if not filled_userid:
            print("  [WARNING] 利用者番号フィールドが見つかりません")

        filled_pass = False
        for sel in [
            'input[type="password"]', 'input[name="passwd"]',
            'input[name="password"]', 'input[name="pass"]',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=2_000)
                if e:
                    await e.fill(PASSWORD)
                    print(f"  [OK] パスワード: {sel}")
                    filled_pass = True
                    break
            except Exception:
                pass
        if not filled_pass:
            print("  [WARNING] パスワードフィールドが見つかりません")

        for sel in [
            'input[type="submit"]', 'button[type="submit"]',
            'input[value="ログイン"]', 'button:has-text("ログイン")',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=2_000)
                if e:
                    await e.click()
                    print(f"  [OK] ログインボタン: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15_000)
        await save_step(page, "02_after_login")
        await dump_form_elements(page, "ログイン後メニュー")

        # ────────────────────────────────────────────────
        # Step 3: お気に入りクリック
        # ────────────────────────────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        fav_clicked = False
        for sel in [
            'a:has-text("お気に入り")', 'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=3_000)
                if e:
                    print(f"  [OK] お気に入り: {sel}")
                    await e.click()
                    fav_clicked = True
                    break
            except Exception:
                pass

        if not fav_clicked:
            for elem in await page.query_selector_all("a, button, input"):
                try:
                    txt = (await elem.inner_text()).strip()
                except Exception:
                    txt = ""
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    print(f"  [OK] お気に入り（全探索）: text={txt!r}")
                    await elem.click()
                    fav_clicked = True
                    break

        await page.wait_for_load_state("networkidle", timeout=15_000)
        await save_step(page, "03_after_favorite")
        await dump_form_elements(page, "お気に入り後（絞り込み画面）")

        # ────────────────────────────────────────────────
        # Step 4: 日付プルダウン詳細解析
        # ────────────────────────────────────────────────
        print("\n[Step 4] 日付プルダウン詳細解析...")
        for sel in await page.query_selector_all("select"):
            n    = await sel.get_attribute("name") or ""
            i    = await sel.get_attribute("id")   or ""
            opts = await sel.query_selector_all("option")
            print(f"\n  SELECT name={n!r} id={i!r}  ({len(opts)}件)")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r}  text={txt!r}")

        # ────────────────────────────────────────────────
        # Step 5: 日付選択 → 検索
        # ────────────────────────────────────────────────
        print("\n[Step 5] 令和08年06月19日を選択して検索...")
        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in DATE_TARGET_TEXTS) or v in DATE_TARGET_VALUES:
                    n = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v)
                    print(f"  [OK] 日付選択: name={n!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break
        if not date_selected:
            print("  [WARNING] 日付が見つかりません。HTMLファイルでプルダウンを確認してください")

        for sel in [
            'input[type="submit"]', 'button[type="submit"]',
            'input[value*="検索"]', 'button:has-text("検索")',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=2_000)
                if e:
                    print(f"  [OK] 検索ボタン: {sel}")
                    await e.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15_000)
        await save_step(page, "04_search_results")

        # ────────────────────────────────────────────────
        # Step 6: 検索結果テーブル解析
        # ────────────────────────────────────────────────
        await analyze_table(page)

        await browser.close()
        print(f"\n\n{'='*60}")
        print(f"解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(analyze())
