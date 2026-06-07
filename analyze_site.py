#!/usr/bin/env python3
"""
まんまるよやく2 サイト構造解析スクリプト

各ステップのHTML・スクリーンショットを保存し、
正確なセレクターを特定するために使用します。

■ 使い方
  python analyze_site.py

■ 出力
  analysis_output/
    01_login_page.html/png       -- ログインページ
    02_after_login.html/png      -- ログイン後メニュー
    03_after_favorite.html/png   -- お気に入り絞り込み画面
    04_search_results.html/png   -- 検索結果（予約表）

■ このスクリプトで確認すること
  1. ログインフォームの input[name=?] 属性
  2. お気に入りリンクの href / onclick / text
  3. 日付SELECTの name と各OPTIONのvalue
  4. 検索結果テーブルのD面行・16:00列の class / onclick / href
"""

import asyncio
import os
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

# 解析対象の日付
TARGET_DATE_TEXTS  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19"]
TARGET_DATE_VALUES = ["20260619", "2026-06-19", "260619"]


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [SAVED] {step_name}.png / .html")


def sep(title=""):
    print(f"\n{'━'*64}")
    if title:
        print(f"  {title}")
    print(f"{'━'*64}")


async def dump_inputs(page):
    sep("INPUT 要素")
    for el in await page.query_selector_all("input"):
        t   = await el.get_attribute("type")  or "text"
        n   = await el.get_attribute("name")  or "-"
        i   = await el.get_attribute("id")    or "-"
        v   = await el.get_attribute("value") or ""
        cls = await el.get_attribute("class") or ""
        ph  = await el.get_attribute("placeholder") or ""
        print(f"  <input type={t!r:12} name={n!r:20} id={i!r:20} value={v!r:20} class={cls!r} ph={ph!r}>")


async def dump_selects(page):
    sep("SELECT 要素（日付プルダウン候補）")
    for sel in await page.query_selector_all("select"):
        n   = await sel.get_attribute("name") or "-"
        i   = await sel.get_attribute("id")   or "-"
        cls = await sel.get_attribute("class") or ""
        opts = await sel.query_selector_all("option")
        print(f"\n  <select name={n!r} id={i!r} class={cls!r}>  ({len(opts)} options)")
        for opt in opts[:30]:
            v  = await opt.get_attribute("value") or ""
            tx = (await opt.inner_text()).strip()
            sl = await opt.get_attribute("selected")
            mark = " ← selected" if sl is not None else ""
            print(f"    value={v!r:20}  text={tx!r}{mark}")
        if len(opts) > 30:
            print(f"    ...他 {len(opts)-30} 件")
        print("  </select>")


async def dump_buttons(page):
    sep("BUTTON / SUBMIT 要素")
    sels = "button, input[type='submit'], input[type='button'], input[type='image']"
    for el in await page.query_selector_all(sels):
        tag = await el.evaluate("e => e.tagName")
        t   = await el.get_attribute("type")  or "-"
        n   = await el.get_attribute("name")  or "-"
        i   = await el.get_attribute("id")    or "-"
        v   = await el.get_attribute("value") or ""
        cls = await el.get_attribute("class") or ""
        txt = ""
        if tag == "BUTTON":
            txt = (await el.inner_text()).strip()
        print(f"  <{tag.lower()} type={t!r} name={n!r} id={i!r} value={v!r} class={cls!r}>{txt}</{tag.lower()}>")


async def dump_links(page):
    sep("LINK 要素（aタグ）")
    for el in await page.query_selector_all("a"):
        href = await el.get_attribute("href")    or ""
        oc   = await el.get_attribute("onclick") or ""
        cls  = await el.get_attribute("class")   or ""
        txt  = (await el.inner_text()).strip()[:50]
        if txt or href:
            print(f"  href={href!r:40}  onclick={oc!r:30}  class={cls!r:15}  text={txt!r}")


async def dump_tables(page):
    sep("TABLE 要素")
    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")
    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        print(f"\n  ── TABLE[{ti}] {len(rows)} 行 ──")
        for ri, row in enumerate(rows[:12]):
            cells = await row.query_selector_all("td, th")
            parts = []
            for cell in cells:
                txt = (await cell.inner_text()).strip()[:12].replace("\n", "")
                cls = await cell.get_attribute("class")   or ""
                oc  = await cell.get_attribute("onclick") or ""
                href_el = await cell.query_selector("a")
                href = ""
                if href_el:
                    href = await href_el.get_attribute("href") or ""
                parts.append(f"[{txt}|{cls}|oc:{oc[:15]}|a:{href[:20]}]")
            print(f"    Row[{ri:2}]: " + " ".join(parts))
        if len(rows) > 12:
            print(f"    ...他 {len(rows)-12} 行")


async def dump_form(page):
    sep("FORM 要素")
    for form in await page.query_selector_all("form"):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        name   = await form.get_attribute("name")   or ""
        print(f"  <form name={name!r} action={action!r} method={method!r}>")


# ──────────────────────────────────────────────────────────────
async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # 実際のブラウザ表示で解析（botブロック回避）
            args=["--start-maximized"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            viewport=None,
        )
        # ダイアログ自動承認
        page = await context.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        # ── Step 1: ログインページ ────────────────────────────────
        print("\n[Step 1] ログインページ解析...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        print(f"  URL: {page.url}")

        await dump_form(page)
        await dump_inputs(page)
        await dump_buttons(page)
        await dump_links(page)

        # ── Step 2: ログイン実行 ──────────────────────────────────
        print("\n[Step 2] ログイン実行...")

        userid_selectors = [
            'input[name="userid"]', 'input[name="user_id"]',
            'input[name="memberNo"]', 'input[name="userno"]',
            'input[name="loginId"]', 'input[name="login_id"]',
            'input[name="id"]', '#userid', '#user_id',
            'input[type="text"]:first-of-type',
        ]
        for sel in userid_selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=2000)
                if el:
                    await el.fill(USER_ID)
                    print(f"  [OK] 利用者番号: {sel!r}")
                    break
            except Exception:
                pass

        for sel in ['input[type="password"]', 'input[name="passwd"]',
                    'input[name="password"]', 'input[name="pass"]']:
            try:
                el = await page.wait_for_selector(sel, timeout=2000)
                if el:
                    await el.fill(PASSWORD)
                    print(f"  [OK] パスワード: {sel!r}")
                    break
            except Exception:
                pass

        for sel in ['input[type="submit"]', 'button[type="submit"]',
                    'input[value="ログイン"]', 'button:has-text("ログイン")']:
            try:
                el = await page.wait_for_selector(sel, timeout=2000)
                if el:
                    await el.click()
                    print(f"  [OK] ログインボタン: {sel!r}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "02_after_login")
        print(f"  ログイン後 URL: {page.url}")
        await dump_links(page)
        await dump_buttons(page)

        # ── Step 3: お気に入りクリック ───────────────────────────
        print("\n[Step 3] お気に入りクリック...")

        fav_clicked = False
        for sel in ['a:has-text("お気に入り")', 'input[value*="お気に入り"]',
                    'button:has-text("お気に入り")']:
            try:
                el = await page.wait_for_selector(sel, timeout=3000)
                if el:
                    txt = (await el.inner_text()).strip()
                    print(f"  [OK] お気に入り: {sel!r}  text={txt!r}")
                    await el.click()
                    fav_clicked = True
                    break
            except Exception:
                pass

        if not fav_clicked:
            # フォールバック: テキスト検索
            elems = await page.query_selector_all("a, button, input")
            for el in elems:
                txt = (await el.inner_text()).strip() if await el.inner_text() else ""
                val = await el.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    print(f"  [OK] お気に入り（フォールバック）: text={txt!r} value={val!r}")
                    await el.click()
                    fav_clicked = True
                    break

        if not fav_clicked:
            print("  [WARNING] お気に入りリンクが見つかりません")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        print(f"  お気に入り後 URL: {page.url}")

        await dump_form(page)
        await dump_selects(page)
        await dump_buttons(page)

        # ── Step 4: 日付選択・検索 ────────────────────────────────
        print("\n[Step 4] 日付選択・検索...")

        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            opts = await sel_elem.query_selector_all("option")
            for opt in opts:
                v  = await opt.get_attribute("value") or ""
                tx = (await opt.inner_text()).strip()
                if (any(t in tx for t in TARGET_DATE_TEXTS) or
                        v in TARGET_DATE_VALUES):
                    name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v)
                    print(f"  [OK] 日付選択: name={name!r} value={v!r} text={tx!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 対象日付が見つかりません。SELECTの内容を上記で確認してください")

        for sel in ['input[type="submit"]', 'button[type="submit"]',
                    'input[value*="検索"]', 'button:has-text("検索")']:
            try:
                el = await page.wait_for_selector(sel, timeout=2000)
                if el:
                    print(f"  [OK] 検索ボタン: {sel!r}")
                    await el.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        print(f"  検索後 URL: {page.url}")

        # ── Step 5: 検索結果テーブル詳細解析 ─────────────────────
        sep("検索結果テーブル詳細解析（D面・16:00 の特定）")

        # D面 または 16:00 を含むセルを全件出力
        cells = await page.query_selector_all("td, th")
        for i, cell in enumerate(cells):
            txt  = (await cell.inner_text()).strip()
            cls  = await cell.get_attribute("class")   or ""
            oc   = await cell.get_attribute("onclick") or ""
            id_  = await cell.get_attribute("id")      or ""
            href_el = await cell.query_selector("a")
            href = ""
            if href_el:
                href = await href_el.get_attribute("href") or ""
            if "D面" in txt or "16:00" in txt or "18:00" in txt:
                print(
                    f"  CELL[{i:3}] "
                    f"id={id_!r:15} "
                    f"class={cls!r:20} "
                    f"onclick={oc!r:40} "
                    f"href={href!r:30} "
                    f"text={txt!r}"
                )

        await dump_tables(page)

        await browser.close()
        print(f"\n\n{'='*64}")
        print(f"解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print(f"{'='*64}")


if __name__ == "__main__":
    asyncio.run(analyze())
