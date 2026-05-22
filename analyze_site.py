"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する

■ 使い方
  python analyze_site.py

実行後 analysis_output/ フォルダに HTML と PNG が生成されます。
reserve.py のセレクターを調整する前に必ずこのスクリプトを実行してください。
"""

import asyncio
import os
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

# 解析対象の日付（練習: 2026-06-19）
TARGET_YYYYMMDD = "20260619"


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / .html → {OUTPUT_DIR}/")


async def dump_form_elements(page, label: str):
    """ページ内のすべてのフォーム要素を標準出力に表示"""
    print(f"\n{'='*50}")
    print(f"  {label} のフォーム要素")
    print(f"{'='*50}")

    # FORM タグ
    for form in await page.query_selector_all("form"):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        print(f"  FORM action={action!r} method={method!r}")

    # INPUT
    for inp in await page.query_selector_all("input"):
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r}")

    # SELECT + OPTION（全件出力）
    for sel in await page.query_selector_all("select"):
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        opts = await sel.query_selector_all("option")
        print(f"  SELECT name={name!r} id={id_!r} class={cls!r} [{len(opts)}件]")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            print(f"    OPTION value={v!r}  text={txt!r}")

    # BUTTON / SUBMIT
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

    # リンク一覧
    print(f"\n  --- リンク一覧 ---")
    for link in await page.query_selector_all("a"):
        href = await link.get_attribute("href") or ""
        try:
            txt = (await link.inner_text()).strip()
        except Exception:
            txt = ""
        onclick = await link.get_attribute("onclick") or ""
        if txt or onclick:
            print(f"  A href={href!r} onclick={onclick!r} text={txt!r}")


async def dump_table_structure(page, label: str):
    """テーブル構造を表示（先頭10行×10列）"""
    print(f"\n{'='*50}")
    print(f"  {label} のテーブル構造")
    print(f"{'='*50}")

    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] 行数={len(rows)}")
        for ri, row in enumerate(rows[:10]):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for cell in cells[:10]:
                try:
                    txt = (await cell.inner_text()).strip()
                except Exception:
                    txt = ""
                cls     = await cell.get_attribute("class") or ""
                id_     = await cell.get_attribute("id") or ""
                onclick = await cell.get_attribute("onclick") or ""
                row_info.append(
                    f"{txt!r}"
                    + (f"[cls={cls}]" if cls else "")
                    + (f"[id={id_}]" if id_ else "")
                    + (f"[onclick=...]" if onclick else "")
                )
            print(f"    ROW[{ri}]: {' | '.join(row_info)}")

    # D面 / 16:00 を含むセルをハイライト
    print(f"\n  --- D面・16:00 関連セル ---")
    for cell in await page.query_selector_all("td, th"):
        try:
            txt = (await cell.inner_text()).strip()
        except Exception:
            txt = ""
        if "D面" in txt or "16:00" in txt or "18:00" in txt:
            cls     = await cell.get_attribute("class") or ""
            id_     = await cell.get_attribute("id") or ""
            onclick = await cell.get_attribute("onclick") or ""
            print(f"  CELL id={id_!r} class={cls!r} onclick={onclick!r} text={txt!r}")


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
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
        await context.add_init_script("window.confirm = () => true;")
        page = await context.new_page()

        # ── Step 1: ログインページ ─────────────────────────────────
        print("\n[Step 1] ログインページ解析...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_form_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ───────────────────────────────────
        print("\n[Step 2] ログイン実行...")
        userid_filled = False
        for sel in [
            'input[name="userid"]', 'input[name="user_id"]',
            'input[name="memberNo"]', 'input[name="userno"]',
            'input[name="loginId"]', 'input[name="login_id"]',
            'input[id="userid"]', 'input[type="text"]:first-of-type',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.fill(USER_ID)
                    print(f"  [OK] 利用者番号 → {sel}")
                    userid_filled = True
                    break
            except Exception:
                pass
        if not userid_filled:
            print("  [WARNING] 利用者番号フィールドが見つかりません → HTMLを確認してください")

        passwd_filled = False
        for sel in [
            'input[name="passwd"]', 'input[name="password"]',
            'input[name="pass"]', 'input[type="password"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.fill(PASSWORD)
                    print(f"  [OK] パスワード → {sel}")
                    passwd_filled = True
                    break
            except Exception:
                pass
        if not passwd_filled:
            print("  [WARNING] パスワードフィールドが見つかりません")

        for sel in [
            'input[type="submit"]', 'button[type="submit"]',
            'input[value="ログイン"]', 'button:has-text("ログイン")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    print(f"  [OK] ログインボタン → {sel}")
                    await elem.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_form_elements(page, "ログイン後ページ")
        print(f"  現在URL: {page.url}")

        # ── Step 3: お気に入りクリック ────────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        fav_clicked = False
        for sel in [
            'a:has-text("お気に入り")',
            'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                if elem:
                    try:
                        txt = (await elem.inner_text()).strip()
                    except Exception:
                        txt = ""
                    print(f"  [OK] お気に入り → {sel} text={txt!r}")
                    await elem.click()
                    fav_clicked = True
                    break
            except Exception:
                pass

        if not fav_clicked:
            print("  [WARNING] お気に入りが見つかりません → ログイン後HTMLを確認してください")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        await dump_form_elements(page, "お気に入り後（絞り込み画面）")
        print(f"  現在URL: {page.url}")

        # ── Step 4: 日付SELECT全件出力 ────────────────────────────
        print("\n[Step 4] 日付プルダウン詳細解析...")
        for sel in await page.query_selector_all("select"):
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id") or ""
            opts = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r} - {len(opts)}件")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r}  text={txt!r}")

        # ── Step 5: 日付選択・検索 ────────────────────────────────
        print(f"\n[Step 5] 日付 {TARGET_YYYYMMDD} を選択して検索...")
        y, m, d = TARGET_YYYYMMDD[:4], TARGET_YYYYMMDD[4:6], TARGET_YYYYMMDD[6:8]
        reiwa   = int(y) - 2018
        target_texts  = [
            f"令和{reiwa:02d}年{m}月{d}日", f"令和{reiwa}年{m}月{d}日",
            f"{y}年{m}月{d}日", f"{y}/{m}/{d}",
        ]
        target_values = [TARGET_YYYYMMDD, f"{y}-{m}-{d}", f"{y[2:]}{m}{d}"]

        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in target_texts) or v in target_values:
                    sname = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  [OK] 日付選択: name={sname!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません → Step4の出力でvalue値を確認してください")

        for sel in [
            'input[type="submit"]', 'button[type="submit"]',
            'input[value*="検索"]', 'button:has-text("検索")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    print(f"  [OK] 検索ボタン → {sel}")
                    await elem.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        print(f"  現在URL: {page.url}")

        # ── Step 6: テーブル構造解析 ──────────────────────────────
        await dump_table_structure(page, "検索結果（予約表）")

        await browser.close()
        print(f"\n\n{'='*60}")
        print(f"解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print(f"HTMLファイルをブラウザで開くか、テキストエディタで確認して")
        print(f"reserve.py のセレクターを調整してください。")
        print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(analyze())
