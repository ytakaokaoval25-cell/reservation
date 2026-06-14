"""
まんまるよやく2 サイト構造解析スクリプト

reserve.py が動かない場合はまずこちらを実行してください。
各ステップの HTML・スクリーンショットを analysis_output/ に保存し、
正確なセレクターを特定します。

使い方:
  python analyze_site.py
  python analyze_site.py --headful   # ブラウザ表示あり（推奨）
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

HEADLESS = "--headful" not in sys.argv[1:]


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ss_path   = f"{OUTPUT_DIR}/{step_name}.png"
    html_path = f"{OUTPUT_DIR}/{step_name}.html"
    await page.screenshot(path=ss_path, full_page=True)
    html = await page.content()
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [保存] {step_name}.png / {step_name}.html")


async def dump_page(page, label: str):
    """フォーム要素・リンクをコンソールに全出力"""
    print(f"\n{'='*50}")
    print(f" {label}")
    print(f" URL: {page.url}")
    print(f"{'='*50}")

    # ── フォーム要素 ──────────────────────────────────
    print("\n--- INPUT 要素 ---")
    for inp in await page.query_selector_all("input"):
        t    = await inp.get_attribute("type")  or "text"
        name = await inp.get_attribute("name")  or ""
        id_  = await inp.get_attribute("id")    or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        ph   = await inp.get_attribute("placeholder") or ""
        print(f"  <input type={t!r} name={name!r} id={id_!r} class={cls!r} "
              f"value={val!r} placeholder={ph!r}>")

    print("\n--- SELECT 要素 ---")
    for sel in await page.query_selector_all("select"):
        name = await sel.get_attribute("name")  or ""
        id_  = await sel.get_attribute("id")    or ""
        cls  = await sel.get_attribute("class") or ""
        opts = await sel.query_selector_all("option")
        print(f"  <select name={name!r} id={id_!r} class={cls!r}> ({len(opts)}件)")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected") or ""
            print(f"      <option value={v!r}{' selected' if sel_attr else ''}> {txt!r}")

    print("\n--- BUTTON / SUBMIT 要素 ---")
    for btn in await page.query_selector_all("button, input[type=submit], input[type=button], input[type=image]"):
        t    = await btn.get_attribute("type")   or ""
        name = await btn.get_attribute("name")   or ""
        id_  = await btn.get_attribute("id")     or ""
        val  = await btn.get_attribute("value")  or ""
        cls  = await btn.get_attribute("class")  or ""
        src  = await btn.get_attribute("src")    or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = ""
        print(f"  <{await btn.evaluate('e => e.tagName').lower() if False else 'btn'} "
              f"type={t!r} name={name!r} id={id_!r} value={val!r} "
              f"class={cls!r} src={src!r}> text={txt!r}")

    print("\n--- FORM 要素 ---")
    for form in await page.query_selector_all("form"):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        id_    = await form.get_attribute("id")     or ""
        print(f"  <form action={action!r} method={method!r} id={id_!r}>")

    print("\n--- LINK 要素 (テキストあり) ---")
    for link in await page.query_selector_all("a"):
        href = await link.get_attribute("href")    or ""
        cls  = await link.get_attribute("class")   or ""
        id_  = await link.get_attribute("id")      or ""
        onclick = await link.get_attribute("onclick") or ""
        try:
            txt = (await link.inner_text()).strip()
        except Exception:
            txt = ""
        if txt:
            print(f"  <a href={href!r} id={id_!r} class={cls!r} onclick={onclick[:60]!r}> {txt!r}")


async def dump_table(page, label: str):
    """テーブル構造を詳細出力（検索結果解析用）"""
    print(f"\n{'='*50}")
    print(f" テーブル解析: {label}")
    print(f"{'='*50}")

    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        tbl_id  = await tbl.get_attribute("id")    or ""
        tbl_cls = await tbl.get_attribute("class") or ""
        print(f"\n[TABLE {ti}] id={tbl_id!r} class={tbl_cls!r}  行数={len(rows)}")

        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            parts = []
            for cell in cells:
                txt  = (await cell.inner_text()).strip().replace("\n", " ")
                cls  = await cell.get_attribute("class")   or ""
                id_  = await cell.get_attribute("id")      or ""
                span = await cell.get_attribute("colspan") or ""
                # セル内のリンク
                links = await cell.query_selector_all("a")
                link_info = ""
                for lnk in links:
                    lhref    = await lnk.get_attribute("href")    or ""
                    lonclick = await lnk.get_attribute("onclick") or ""
                    ltxt     = (await lnk.inner_text()).strip()
                    lclass   = await lnk.get_attribute("class")   or ""
                    link_info += f"[a class={lclass!r} href={lhref[:40]!r} onclick={lonclick[:40]!r} text={ltxt!r}]"
                cell_desc = f"{txt!r}"
                if cls:   cell_desc += f"(cls={cls})"
                if id_:   cell_desc += f"(id={id_})"
                if span:  cell_desc += f"(colspan={span})"
                if link_info: cell_desc += f" {link_info}"
                parts.append(cell_desc)
            print(f"  ROW[{ri}]: " + " | ".join(parts))


async def try_login(page):
    """ログインを実行し、True/False を返す"""
    print("\n[Step 1] ログインページ...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
    await save_step(page, "01_login_page")
    await dump_page(page, "ログインページ")

    # フォームのaction確認
    form = await page.query_selector("form")
    if form:
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        print(f"\n  FORM action={action!r} method={method!r}")

    print("\n[Step 2] ログイン実行...")
    filled_id = False
    for sel in [
        'input[name="userid"]', 'input[name="user_id"]',
        'input[name="memberNo"]', 'input[name="userno"]',
        'input[name="loginId"]', 'input[name="login_id"]',
        '#userid', 'input[type="text"]:first-of-type',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            await elem.fill(USER_ID)
            print(f"  [OK] 利用者番号 → {sel}")
            filled_id = True
            break
        except Exception:
            pass
    if not filled_id:
        print("  [NG] 利用者番号フィールドが見つかりません")

    filled_pw = False
    for sel in [
        'input[type="password"]',
        'input[name="passwd"]', 'input[name="password"]', 'input[name="pass"]',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            await elem.fill(PASSWORD)
            print(f"  [OK] パスワード → {sel}")
            filled_pw = True
            break
        except Exception:
            pass
    if not filled_pw:
        print("  [NG] パスワードフィールドが見つかりません")

    for sel in [
        'input[value="ログイン"]', 'button:text("ログイン")',
        'input[type="submit"]', 'button[type="submit"]',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            await elem.click()
            print(f"  [OK] ログインボタン → {sel}")
            break
        except Exception:
            pass

    await page.wait_for_load_state("networkidle", timeout=20000)
    await save_step(page, "02_after_login")
    await dump_page(page, "ログイン後")
    return True


async def try_favorite(page):
    print("\n[Step 3] お気に入りクリック...")
    for sel in [
        'a:text("お気に入り")', 'input[value="お気に入り"]',
        'a[href*="okiniiri"]', '[onclick*="okiniiri"]',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=3000, state="visible")
            txt = (await elem.inner_text()).strip()
            print(f"  [OK] お気に入り → {sel}  text={txt!r}")
            await elem.click()
            break
        except Exception:
            pass

    # フォールバック: テキストで探す
    else:
        for elem in await page.query_selector_all("a, button, input"):
            try:
                txt = (await elem.inner_text()).strip()
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    print(f"  [OK] お気に入り（フォールバック）: {txt!r}")
                    await elem.click()
                    break
            except Exception:
                pass

    await page.wait_for_load_state("networkidle", timeout=15000)
    await save_step(page, "03_after_favorite")
    await dump_page(page, "お気に入り後（絞り込み画面）")


async def try_date_and_search(page):
    print("\n[Step 4] 日付プルダウン詳細解析 + 令和08年06月19日を選択して検索...")

    # 全SELECTの全OPTIONを出力
    for sel in await page.query_selector_all("select"):
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id")   or ""
        opts = await sel.query_selector_all("option")
        print(f"\n  SELECT name={name!r} id={id_!r}:")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            print(f"    value={v!r}  text={txt!r}")

    # 日付選択を試みる
    target_texts  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19", "06月19日"]
    target_values = ["20260619", "2026-06-19", "260619"]

    selected = False
    for sel_elem in await page.query_selector_all("select"):
        for opt in await sel_elem.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if any(t in txt for t in target_texts) or v in target_values:
                name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                print(f"\n  [OK] 日付選択: name={name!r} value={v!r} text={txt!r}")
                selected = True
                break
        if selected:
            break

    if not selected:
        print("  [NG] 対象日付がプルダウンに見つかりませんでした。HTML を確認してください。")

    # 検索ボタン
    for sel in [
        'input[value="検索"]', 'button:text("検索")',
        'input[type="submit"]', 'button[type="submit"]',
    ]:
        try:
            elem = await page.wait_for_selector(sel, timeout=3000, state="visible")
            print(f"  [OK] 検索ボタン → {sel}")
            await elem.click()
            break
        except Exception:
            pass

    await page.wait_for_load_state("networkidle", timeout=15000)
    await save_step(page, "04_search_results")
    await dump_table(page, "検索結果")
    print(f"\n  現在URL: {page.url}")

    # D面・16:00 を含むセルを個別出力
    print("\n--- D面 / 16:00 / 18:00 / 赤丸（○）関連セル ---")
    for cell in await page.query_selector_all("td, th, a"):
        try:
            txt = (await cell.inner_text()).strip()
        except Exception:
            continue
        cls     = await cell.get_attribute("class")   or ""
        id_     = await cell.get_attribute("id")      or ""
        onclick = await cell.get_attribute("onclick") or ""
        href    = await cell.get_attribute("href")    or ""
        if any(k in txt for k in ["D面", "16:00", "18:00", "○", "◯"]):
            tag = await cell.evaluate("el => el.tagName")
            print(f"  <{tag}> id={id_!r} class={cls!r} onclick={onclick[:60]!r} "
                  f"href={href[:60]!r}  text={txt!r}")


async def main():
    print("=" * 60)
    print("まんまるよやく2 サイト構造解析スクリプト")
    print(f"出力先: {OUTPUT_DIR}/")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()

        try:
            await try_login(page)
            await try_favorite(page)
            await try_date_and_search(page)
        except Exception as e:
            await save_step(page, "ERROR")
            print(f"\n❌ エラー: {e}")
        finally:
            await browser.close()

    print(f"\n解析完了。{OUTPUT_DIR}/ を確認してください。")


if __name__ == "__main__":
    asyncio.run(main())
