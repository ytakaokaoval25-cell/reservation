"""
まんまるよやく2 サイト構造解析スクリプト
ログイン〜確定②までの各ステップの HTML / スクリーンショットを保存し、
正確なセレクターを確認する。

■ 使い方
  python analyze_site.py
  python analyze_site.py --headful   # ブラウザ表示あり

■ 出力
  analysis_output/ に各ステップの .png と .html を保存
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"


# ─── ユーティリティ ─────────────────────────────────────
async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / .html")


async def dump_forms(page, label: str):
    print(f"\n=== {label} のフォーム要素 ===")

    # フォーム
    for form in await page.query_selector_all("form"):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        print(f"  FORM action={action!r} method={method!r}")

    # input
    for inp in await page.query_selector_all("input"):
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r}")

    # select + options（全件）
    for sel in await page.query_selector_all("select"):
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        print(f"  SELECT name={name!r} id={id_!r} class={cls!r}")
        for opt in await sel.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            print(f"    OPTION value={v!r} text={txt!r}")

    # button / submit
    for btn in await page.query_selector_all("button, input[type=submit], input[type=button]"):
        t    = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        val  = await btn.get_attribute("value") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  BUTTON type={t!r} name={name!r} id={id_!r} value={val!r} text={txt!r}")

    # リンク
    print("  --- リンク ---")
    for a in await page.query_selector_all("a"):
        href = await a.get_attribute("href") or ""
        try:
            txt = (await a.inner_text()).strip()
        except Exception:
            txt = ""
        onclick = await a.get_attribute("onclick") or ""
        if txt or onclick:
            print(f"  A href={href!r} onclick={onclick[:60]!r} text={txt!r}")


async def dump_table(page, label: str):
    print(f"\n=== {label} のテーブル構造 ===")
    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")
    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        print(f"\nTABLE[{ti}] 行数={len(rows)}")
        for ri, row in enumerate(rows[:10]):
            cells = await row.query_selector_all("td, th")
            cols  = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip()
                cls     = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                cols.append(f"{txt[:12]}(cls={cls[:15]},on={onclick[:20]})")
            print(f"  ROW[{ri}]: {' | '.join(cols[:8])}")

    # onclick / href を持つ全要素
    print("\n  --- onclick / href 要素 ---")
    for elem in await page.query_selector_all("[onclick], a[href]"):
        tag     = await page.evaluate("el => el.tagName", elem)
        onclick = await elem.get_attribute("onclick") or ""
        href    = await elem.get_attribute("href") or ""
        cls     = await elem.get_attribute("class") or ""
        try:
            txt = (await elem.inner_text()).strip()[:30]
        except Exception:
            txt = ""
        if onclick or href:
            print(f"  {tag} cls={cls!r} href={href!r} onclick={onclick[:60]!r} text={txt!r}")


# ─── メイン解析フロー ────────────────────────────────────
async def analyze():
    headless = "--headful" not in sys.argv

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,
        )
        # window.confirm を常に true に（確定②で止まらないよう）
        await context.add_init_script("window.confirm = () => true;")
        page = await context.new_page()

        # ── Step 1: ログインページ ──────────────────────────────
        print("\n[Step 1] ログインページ解析")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_forms(page, "ログインページ")

        # ── Step 2: ログイン実行 ───────────────────────────────
        print("\n[Step 2] ログイン実行")
        uid_filled = False
        for sel in [
            'input[name="userId"]', 'input[name="userid"]', 'input[name="user_id"]',
            'input[name="memberNo"]', 'input[name="userno"]', 'input[name="loginId"]',
            'input[name="id"]', '#userId', '#userid', 'input[type="text"]:first-of-type',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=2000)
                if e:
                    await e.fill(USER_ID)
                    print(f"  [OK] 利用者番号: {sel}")
                    uid_filled = True
                    break
            except Exception:
                pass
        if not uid_filled:
            print("  [WARN] 利用者番号フィールド未検出")

        for sel in [
            'input[name="passwd"]', 'input[name="password"]',
            'input[name="pass"]', 'input[type="password"]',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=2000)
                if e:
                    await e.fill(PASSWORD)
                    print(f"  [OK] パスワード: {sel}")
                    break
            except Exception:
                pass

        for sel in [
            'input[value="ログイン"]', 'input[value="LOGIN"]',
            'button:text("ログイン")', 'input[type="submit"]',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=2000)
                if e:
                    await e.click()
                    print(f"  [OK] ログインボタン: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_forms(page, "ログイン後（メニュー）")
        print(f"  URL: {page.url}")

        # ── Step 3: お気に入りクリック ─────────────────────────
        print("\n[Step 3] お気に入りクリック")
        clicked = False
        for sel in [
            'a:text("お気に入り")', 'input[value="お気に入り"]',
            'button:text("お気に入り")', 'a[href*="favorite"]',
            'a[href*="okiniri"]', 'a[href*="okiniiri"]',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=2000)
                if e:
                    txt = (await e.inner_text()).strip()
                    print(f"  [OK] お気に入り: {sel} text={txt!r}")
                    await e.click()
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            print("  [WARN] お気に入り要素が見つかりませんでした")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_favorite_filter")
        await dump_forms(page, "絞り込み画面")
        print(f"  URL: {page.url}")

        # ── Step 4: 日付プルダウン詳細解析 ────────────────────
        print("\n[Step 4] 日付プルダウン詳細")
        for sel in await page.query_selector_all("select"):
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id") or ""
            opts = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r} ({len(opts)}件)")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r}  text={txt!r}")

        # ── Step 5: 日付選択・検索 ────────────────────────────
        print("\n[Step 5] 日付選択・検索")
        target_texts  = ["令和08年06月19日", "令和8年6月19日", "2026年06月19日", "2026/06/19"]
        target_values = ["20260619", "2026-06-19", "260619"]
        for sel in await page.query_selector_all("select"):
            for opt in await sel.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in target_texts) or v in target_values:
                    sname = await sel.get_attribute("name") or ""
                    await sel.select_option(value=v) if v else await sel.select_option(label=txt)
                    print(f"  [OK] 日付選択: name={sname!r} value={v!r} text={txt!r}")
                    break

        for sel in [
            'input[value="検索"]', 'input[value*="検索"]',
            'button:text("検索")', 'input[type="submit"]',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=2000)
                if e:
                    print(f"  [OK] 検索ボタン: {sel}")
                    await e.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        await dump_table(page, "検索結果テーブル")
        print(f"  URL: {page.url}")

        # D面 16:00 に関連するセルを特定表示
        print("\n  --- D面 / 16:00 関連セル ---")
        for cell in await page.query_selector_all("td, th"):
            txt     = (await cell.inner_text()).strip()
            cls     = await cell.get_attribute("class") or ""
            onclick = await cell.get_attribute("onclick") or ""
            if "D面" in txt or "16:00" in txt or "16" in txt:
                print(f"  CELL text={txt!r} class={cls!r} onclick={onclick[:80]!r}")

        await browser.close()
        print(f"\n解析完了。{OUTPUT_DIR}/ を確認してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
