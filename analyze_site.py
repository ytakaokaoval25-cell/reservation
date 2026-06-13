"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する

使い方:
  python analyze_site.py            # ヘッドレス（サーバー実行）
  python analyze_site.py --headful  # ブラウザ表示あり（ローカルデバッグ）
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

HEADFUL = "--headful" in sys.argv


# ─── ユーティリティ ──────────────────────────────────────────────────────────

async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / .html  (URL: {page.url})")


async def dump_all_elements(page, label: str):
    print(f"\n{'='*60}")
    print(f"【{label}】 URL: {page.url}")
    print(f"{'='*60}")

    # ── FORM ──
    forms = await page.query_selector_all("form")
    for fi, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        id_    = await form.get_attribute("id") or ""
        print(f"\n  FORM[{fi}] id={id_!r} action={action!r} method={method!r}")

    # ── INPUT ──
    print("\n  --- INPUT要素 ---")
    for inp in await page.query_selector_all("input"):
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"    INPUT type={t!r:12} name={name!r:25} id={id_!r:20} "
              f"class={cls!r:20} value={val!r}")

    # ── SELECT (全option表示) ──
    print("\n  --- SELECT要素 ---")
    for sel in await page.query_selector_all("select"):
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        opts = await sel.query_selector_all("option")
        print(f"\n    SELECT name={name!r} id={id_!r} class={cls!r}  ({len(opts)}件)")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected")
            marker = " ← selected" if sel_attr is not None else ""
            print(f"      OPTION value={v!r:20} text={txt!r}{marker}")

    # ── BUTTON / SUBMIT ──
    print("\n  --- ボタン要素 ---")
    for btn in await page.query_selector_all(
            "button, input[type=submit], input[type=button], input[type=image]"):
        t    = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        val  = await btn.get_attribute("value") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        cls = await btn.get_attribute("class") or ""
        print(f"    BTN type={t!r:8} name={name!r:20} id={id_!r:20} "
              f"value={val!r:20} text={txt!r:20} class={cls!r}")

    # ── リンク ──
    print("\n  --- リンク ---")
    for a in await page.query_selector_all("a"):
        href = await a.get_attribute("href") or ""
        txt  = (await a.inner_text()).strip()
        if txt:
            print(f"    A text={txt!r:30} href={href!r}")


async def dump_table_structure(page, label: str):
    print(f"\n  --- テーブル構造 ({label}) ---")
    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] 行数={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip()
                cls     = await cell.get_attribute("class") or ""
                id_     = await cell.get_attribute("id") or ""
                onclick = (await cell.get_attribute("onclick") or "")[:40]
                row_info.append(f"{txt!r}(cls={cls!r},id={id_!r},onclick={onclick!r})")
            print(f"    ROW[{ri}]: {' | '.join(row_info)}")


# ─── メイン解析フロー ─────────────────────────────────────────────────────────

async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not HEADFUL,
            args=["--disable-blink-features=AutomationControlled"],
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

        # ── Step 1: ログインページ ────────────────────────────────────────
        print("\n[Step 1] ログインページ")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
        await save_step(page, "01_login_page")
        await dump_all_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ──────────────────────────────────────────
        print("\n[Step 2] ログイン実行")
        userid_filled = False
        for sel in ['input[name="userid"]', 'input[name="user_id"]',
                    'input[name="memberNo"]', 'input[name="userno"]',
                    'input[name="loginId"]', 'input[name="id"]',
                    'input[type="text"]:first-of-type']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                await elem.fill(USER_ID)
                print(f"  利用者番号 → {sel}")
                userid_filled = True
                break
            except Exception:
                pass
        if not userid_filled:
            print("  [WARNING] 利用者番号フィールドが見つかりません")

        passwd_filled = False
        for sel in ['input[type="password"]', 'input[name="passwd"]',
                    'input[name="password"]', 'input[name="pass"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                await elem.fill(PASSWORD)
                print(f"  パスワード → {sel}")
                passwd_filled = True
                break
            except Exception:
                pass
        if not passwd_filled:
            print("  [WARNING] パスワードフィールドが見つかりません")

        for sel in ['input[value="ログイン"]', 'button:has-text("ログイン")',
                    'input[type="submit"]', 'button[type="submit"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                await elem.click()
                print(f"  ログインボタン → {sel}")
                break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15_000)
        await save_step(page, "02_after_login")
        await dump_all_elements(page, "ログイン後")

        # ── Step 3: お気に入りクリック ───────────────────────────────────
        print("\n[Step 3] お気に入りクリック")
        fav_clicked = False
        for sel in ['a:has-text("お気に入り")', 'input[value="お気に入り"]',
                    'button:has-text("お気に入り")']:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                txt = (await elem.inner_text()).strip()
                print(f"  お気に入り → {sel}  text={txt!r}")
                await elem.click()
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
                    print(f"  お気に入り（全探索）: text={txt!r}")
                    await elem.click()
                    fav_clicked = True
                    break
        if not fav_clicked:
            print("  [WARNING] お気に入りが見つかりません")

        await page.wait_for_load_state("networkidle", timeout=15_000)
        await save_step(page, "03_after_favorite")
        await dump_all_elements(page, "お気に入り後（絞り込み画面）")

        # ── Step 4: 日付プルダウン全option表示 ──────────────────────────
        print("\n[Step 4] 日付プルダウン詳細解析")
        for sel in await page.query_selector_all("select"):
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id") or ""
            opts = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r} ({len(opts)}件)")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r:20}  text={txt!r}")

        # ── Step 5: 日付選択・検索実行 ───────────────────────────────────
        print("\n[Step 5] 日付選択・検索")
        date_found = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if "20260619" in v or "令和08年06月19日" in txt or "令和8年6月19日" in txt:
                    sel_name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                    date_found = True
                    break
            if date_found:
                break
        if not date_found:
            print("  [WARNING] 対象日付が見つかりません")

        for sel in ['input[value="検索"]', 'button:has-text("検索")',
                    'input[type="submit"]', 'button[type="submit"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                await elem.click()
                print(f"  検索ボタン → {sel}")
                break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15_000)
        await save_step(page, "04_search_results")

        # ── Step 6: 検索結果テーブル完全解析 ─────────────────────────────
        print("\n[Step 6] 検索結果テーブル解析")
        await dump_table_structure(page, "検索結果")
        await dump_all_elements(page, "検索結果ページ")

        await browser.close()
        print(f"\n\n解析完了。'{OUTPUT_DIR}/' フォルダを確認してください。")
        print("特に 04_search_results.html でD面の行と16:00列を探してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
