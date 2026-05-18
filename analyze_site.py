"""
まんまるよやく2 サイト構造解析スクリプト
==================================================
■ 使い方（ローカルPCで実行してください）
  python analyze_site.py

■ 出力
  analysis_output/ フォルダに各ステップのスクリーンショット(.png)と
  HTML(.html)を保存します。HTMLをブラウザで開いて実際のID/name/classを確認し、
  reserve.py の各セレクターを正確なものに書き換えてください。

■ 準備
  pip install playwright
  playwright install chromium
"""

import asyncio
import os
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUT_DIR    = "analysis_output"


# ──────────────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────────────
async def save_step(page, name: str):
    os.makedirs(OUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUT_DIR}/{name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUT_DIR}/{name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {name}.png / {name}.html")


async def dump_all(page, label: str):
    """ページ内の全フォーム要素・リンクを出力する"""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  URL: {page.url}")

    # ── form ──
    forms = await page.query_selector_all("form")
    for fi, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        print(f"\n  [FORM {fi}] action={action!r} method={method!r}")

    # ── input ──
    print("\n  --- INPUT要素 ---")
    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        placeholder = await inp.get_attribute("placeholder") or ""
        print(f"  INPUT type={t!r:10} name={name!r:20} id={id_!r:20} "
              f"class={cls!r:25} value={val!r:15} placeholder={placeholder!r}")

    # ── select ──
    print("\n  --- SELECT要素 ---")
    selects = await page.query_selector_all("select")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        print(f"\n  SELECT name={name!r} id={id_!r} class={cls!r}")
        options = await sel.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_mark = await opt.get_attribute("selected")
            mark = " ← selected" if sel_mark is not None else ""
            print(f"    OPTION value={v!r:15} text={txt!r}{mark}")

    # ── button / submit ──
    print("\n  --- BUTTON要素 ---")
    buttons = await page.query_selector_all(
        "button, input[type=submit], input[type=button], input[type=image]"
    )
    for btn in buttons:
        t    = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        val  = await btn.get_attribute("value") or ""
        cls  = await btn.get_attribute("class") or ""
        onclick = await btn.get_attribute("onclick") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  BUTTON type={t!r:8} name={name!r:20} id={id_!r:20} "
              f"value={val!r:15} class={cls!r:20} onclick={onclick[:40]!r} text={txt!r}")

    # ── a リンク ──
    print("\n  --- リンク(a要素) ---")
    links = await page.query_selector_all("a")
    for link in links:
        href    = await link.get_attribute("href") or ""
        id_     = await link.get_attribute("id") or ""
        cls     = await link.get_attribute("class") or ""
        onclick = await link.get_attribute("onclick") or ""
        try:
            txt = (await link.inner_text()).strip()
        except Exception:
            txt = ""
        if txt or href:
            print(f"  A href={href!r:40} id={id_!r:15} class={cls!r:20} "
                  f"onclick={onclick[:30]!r} text={txt!r}")

    # ── テーブル概要 ──
    print("\n  --- TABLE構造 ---")
    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")
    for ti, tbl in enumerate(tables):
        id_  = await tbl.get_attribute("id") or ""
        cls  = await tbl.get_attribute("class") or ""
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] id={id_!r} class={cls!r} 行数={len(rows)}")
        for ri, row in enumerate(rows[:10]):
            cells = await row.query_selector_all("td, th")
            row_data = []
            for cell in cells:
                txt = (await cell.inner_text()).strip()
                cls_c = await cell.get_attribute("class") or ""
                onclick_c = await cell.get_attribute("onclick") or ""
                row_data.append(f"{txt!r}(cls={cls_c!r},onclick={onclick_c[:30]!r})")
            print(f"    ROW[{ri}]: {' | '.join(row_data[:8])}")
        if len(rows) > 10:
            print(f"    ... 以下 {len(rows)-10} 行省略 ...")

    print(f"\n{'='*60}\n")


# ──────────────────────────────────────────────────────────────
# 日付・スロット検索ダンプ
# ──────────────────────────────────────────────────────────────
async def dump_date_slots(page, label="検索結果"):
    """D面・16:00を含むセルを詳細出力"""
    print(f"\n  --- {label}: 関連セル詳細 ---")
    cells = await page.query_selector_all("td, th")
    for i, cell in enumerate(cells):
        txt = (await cell.inner_text()).strip()
        if "D面" in txt or "16:00" in txt or "18:00" in txt or "16" in txt:
            id_     = await cell.get_attribute("id") or ""
            cls     = await cell.get_attribute("class") or ""
            onclick = await cell.get_attribute("onclick") or ""
            href_a  = ""
            a = await cell.query_selector("a")
            if a:
                href_a = await a.get_attribute("href") or ""
            print(f"  CELL[{i:3}] id={id_!r:15} class={cls!r:25} "
                  f"onclick={onclick[:50]!r} href_a={href_a!r} text={txt!r}")


# ──────────────────────────────────────────────────────────────
# メイン解析フロー
# ──────────────────────────────────────────────────────────────
async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
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
        await context.add_init_script("window.confirm = function() { return true; };")
        page = await context.new_page()

        # ── Step 1: ログインページ ──────────────────────────────────
        print("\n[Step 1] ログインページ解析...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_all(page, "ログインページ")

        # ── Step 2: ログイン実行 ────────────────────────────────────
        print("\n[Step 2] ログイン実行...")
        # 利用者番号（候補セレクターを全試行）
        userid_selectors = [
            'input[name="userid"]', 'input[name="user_id"]',
            'input[name="memberNo"]', 'input[name="userno"]',
            'input[name="loginId"]', 'input[name="login_id"]',
            'input[name="id"]', 'input[name="uid"]',
            'input[name="usernm"]', 'input[name="username"]',
            '#userid', '#user_id',
            'input[type="text"]:first-of-type',
        ]
        for sel in userid_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.fill(USER_ID)
                    print(f"  [OK] 利用者番号入力: {sel}")
                    break
            except Exception:
                pass

        passwd_selectors = [
            'input[type="password"]', 'input[name="passwd"]',
            'input[name="password"]', 'input[name="pass"]', '#passwd',
        ]
        for sel in passwd_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.fill(PASSWORD)
                    print(f"  [OK] パスワード入力: {sel}")
                    break
            except Exception:
                pass

        submit_selectors = [
            'input[value="ログイン"]', 'button:text("ログイン")',
            'input[type="submit"]', 'button[type="submit"]',
        ]
        for sel in submit_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.click()
                    print(f"  [OK] サブミット: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "02_after_login")
        await dump_all(page, "ログイン後ページ")

        # ── Step 3: お気に入りクリック ──────────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        fav_selectors = [
            'a:text("お気に入り")', 'input[value*="お気に入り"]',
            'button:text("お気に入り")', '*[onclick*="okiniri"]',
            '*[onclick*="okini"]', '*[onclick*="favorite"]',
            '[id*="favorite"]', '[class*="favorite"]',
            'a[href*="favorite"]', 'a[href*="okiniri"]',
        ]
        clicked = False
        for sel in fav_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.click()
                    print(f"  [OK] お気に入り: {sel}")
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            elems = await page.query_selector_all("a, button, input, span, td, li")
            for elem in elems:
                try:
                    txt = (await elem.inner_text()).strip()
                except Exception:
                    txt = ""
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    await elem.click()
                    print(f"  [OK] お気に入り（全走査）: {txt!r}")
                    clicked = True
                    break

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "03_after_favorite")
        await dump_all(page, "お気に入り後（絞り込み画面）")

        # ── Step 4: 日付を令和08年06月19日に選択して検索 ──────────
        print("\n[Step 4] 日付選択・検索...")
        date_target_values = ["20260619", "2026-06-19", "2026/06/19", "260619"]
        date_target_texts  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19"]

        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                v   = (await opt.get_attribute("value") or "").strip()
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in date_target_texts) or v in date_target_values:
                    await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                    sel_name = await sel_elem.get_attribute("name") or ""
                    print(f"  [OK] 日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりませんでした。スクリーンショットを確認してください。")

        for sel in ['input[value*="検索"]', 'button:text("検索")',
                    'input[type="submit"]', 'button[type="submit"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.click()
                    print(f"  [OK] 検索ボタン: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "04_search_results")
        await dump_all(page, "検索結果ページ")
        await dump_date_slots(page, "D面・16:00関連セル")

        await browser.close()

    print(f"\n{'='*60}")
    print(f"  解析完了！")
    print(f"  出力先: {os.path.abspath(OUT_DIR)}/")
    print(f"  次のステップ:")
    print(f"  1. analysis_output/*.html をブラウザで開いて構造を確認")
    print(f"  2. 各ステップのセレクターをreserve.pyに反映")
    print(f"  3. python reserve.py --now --headful でテスト実行")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(analyze())
