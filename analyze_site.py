#!/usr/bin/env python3
"""
まんまるよやく2 サイト構造解析スクリプト

各ステップのHTML・スクリーンショットを analysis_output/ に保存して
正確なセレクターを確認するためのツール。
reserve.py が失敗したときにまず本スクリプトを実行し、
出力された HTML ファイルで実際の name / id / class / value を確認する。

■ 使い方
  python analyze_site.py
  python analyze_site.py --headful  # ブラウザを表示しながら確認
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"


def headful() -> bool:
    return "--headful" in sys.argv[1:]


async def save_step(page, name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [SAVED] {name}.png / {name}.html")


async def dump_all_form_elements(page, label: str):
    """ページ内のすべてのフォーム要素を詳細表示"""
    print(f"\n{'='*60}")
    print(f"  フォーム要素ダンプ: {label}")
    print(f"  URL: {page.url}")
    print(f"  タイトル: {await page.title()}")
    print(f"{'='*60}")

    # FORM
    for fi, form in enumerate(await page.query_selector_all("form")):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        name   = await form.get_attribute("name") or ""
        print(f"\n  FORM[{fi}] name={name!r} action={action!r} method={method!r}")

    # INPUT
    print("\n  --- INPUT 要素 ---")
    for inp in await page.query_selector_all("input"):
        t     = await inp.get_attribute("type") or "text"
        name  = await inp.get_attribute("name") or ""
        id_   = await inp.get_attribute("id") or ""
        cls   = await inp.get_attribute("class") or ""
        val   = await inp.get_attribute("value") or ""
        place = await inp.get_attribute("placeholder") or ""
        print(f"  INPUT  type={t!r:10} name={name!r:20} id={id_!r:20} class={cls!r:20} value={val!r} placeholder={place!r}")

    # SELECT（全オプション）
    print("\n  --- SELECT 要素 ---")
    for sel in await page.query_selector_all("select"):
        name  = await sel.get_attribute("name") or ""
        id_   = await sel.get_attribute("id") or ""
        cls   = await sel.get_attribute("class") or ""
        opts  = await sel.query_selector_all("option")
        print(f"\n  SELECT name={name!r} id={id_!r} class={cls!r}  ({len(opts)}件)")
        for opt in opts:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_attr = await opt.get_attribute("selected")
            mark = " ← selected" if sel_attr is not None else ""
            print(f"    OPTION value={v!r:20} text={txt!r}{mark}")

    # BUTTON / SUBMIT
    print("\n  --- BUTTON / SUBMIT 要素 ---")
    for btn in await page.query_selector_all("button, input[type=submit], input[type=button]"):
        t     = await btn.get_attribute("type") or ""
        name  = await btn.get_attribute("name") or ""
        id_   = await btn.get_attribute("id") or ""
        cls   = await btn.get_attribute("class") or ""
        val   = await btn.get_attribute("value") or ""
        txt   = (await btn.inner_text()).strip()
        onclick = await btn.get_attribute("onclick") or ""
        print(f"  BTN  type={t!r:8} name={name!r:20} id={id_!r:15} value={val!r:20} text={txt!r:15} onclick={onclick!r}")

    # ANCHOR（メニューナビ用）
    print("\n  --- A リンク ---")
    for a in await page.query_selector_all("a"):
        href    = await a.get_attribute("href") or ""
        txt     = (await a.inner_text()).strip()
        onclick = await a.get_attribute("onclick") or ""
        cls     = await a.get_attribute("class") or ""
        if txt:
            print(f"  A  href={href!r:40} class={cls!r:20} onclick={onclick!r:30} text={txt!r}")


async def dump_table_structure(page, label: str):
    """テーブル構造の詳細ダンプ（検索結果画面用）"""
    print(f"\n{'='*60}")
    print(f"  テーブル構造ダンプ: {label}")
    print(f"{'='*60}")

    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        id_  = await tbl.get_attribute("id") or ""
        cls  = await tbl.get_attribute("class") or ""
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] id={id_!r} class={cls!r}  行数={len(rows)}")

        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for ci, cell in enumerate(cells):
                txt     = (await cell.inner_text()).strip()
                cls_c   = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                id_c    = await cell.get_attribute("id") or ""

                # セル内のリンク
                links = await cell.query_selector_all("a")
                link_info = ""
                for link in links:
                    href   = await link.get_attribute("href") or ""
                    l_txt  = (await link.inner_text()).strip()
                    l_onclick = await link.get_attribute("onclick") or ""
                    link_info += f"[a href={href!r} onclick={l_onclick!r} text={l_txt!r}]"

                # セル内の画像
                imgs = await cell.query_selector_all("img")
                img_info = ""
                for img in imgs:
                    src = await img.get_attribute("src") or ""
                    alt = await img.get_attribute("alt") or ""
                    img_info += f"[img src={src!r} alt={alt!r}]"

                summary = f"({ci}) text={txt!r}"
                if cls_c:   summary += f" cls={cls_c!r}"
                if onclick: summary += f" onclick={onclick!r}"
                if id_c:    summary += f" id={id_c!r}"
                if link_info: summary += f" {link_info}"
                if img_info:  summary += f" {img_info}"
                row_info.append(summary)

            print(f"    ROW[{ri}]: " + " | ".join(row_info))


async def analyze():
    print("=" * 60)
    print("まんまるよやく2 サイト構造解析")
    print(f"出力先: {OUTPUT_DIR}/")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headful())
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
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        # ── Step 1: ログインページ ─────────────────────────────────────────
        print(f"\n[Step 1] ログインページ: {LOGIN_URL}")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_all_form_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ───────────────────────────────────────────
        print("\n[Step 2] ログイン実行...")
        filled_id = filled_pw = False
        for sel in [
            'input[name="userid"]', 'input[name="user_id"]', 'input[name="userno"]',
            'input[name="loginId"]', 'input[name="login_id"]', 'input[name="memberNo"]',
            'input[name="id"]', '#userid', 'input[type="text"]:nth-of-type(1)',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=1500)
                if e:
                    await e.fill(USER_ID)
                    print(f"  [OK] 利用者番号入力: {sel}")
                    filled_id = True
                    break
            except Exception:
                pass

        for sel in [
            'input[type="password"]', 'input[name="passwd"]',
            'input[name="password"]', 'input[name="pass"]',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=1500)
                if e:
                    await e.fill(PASSWORD)
                    print(f"  [OK] パスワード入力: {sel}")
                    filled_pw = True
                    break
            except Exception:
                pass

        if not filled_id:
            print("  ⚠️  利用者番号フィールドが見つかりません")
        if not filled_pw:
            print("  ⚠️  パスワードフィールドが見つかりません")

        for sel in [
            'input[value="ログイン"]', 'input[type="submit"]',
            'button[type="submit"]', 'button:has-text("ログイン")',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=1500)
                if e:
                    await e.click()
                    print(f"  [OK] ログインボタン: {sel}")
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "02_after_login")
        await dump_all_form_elements(page, "ログイン後メインメニュー")

        # ── Step 3: お気に入りクリック ─────────────────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        fav_clicked = False
        for sel in [
            'a:has-text("お気に入り")', 'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=3000)
                if e:
                    txt = (await e.inner_text()).strip()
                    print(f"  [OK] お気に入り: {sel!r}  text={txt!r}")
                    await e.click()
                    fav_clicked = True
                    break
            except Exception:
                pass

        if not fav_clicked:
            print("  ⚠️  お気に入りが見つかりません — テキストスキャン...")
            for e in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
                try:
                    txt = await e.inner_text()
                    val = await e.get_attribute("value") or ""
                    if "お気に入り" in (txt or "") or "お気に入り" in val:
                        await e.click()
                        print(f"  [OK] お気に入り（スキャン）: {txt!r}")
                        fav_clicked = True
                        break
                except Exception:
                    pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "03_after_favorite")
        await dump_all_form_elements(page, "お気に入り後（絞り込み画面）")

        # ── Step 4: 日付プルダウン詳細確認 ────────────────────────────────
        print("\n[Step 4] 日付プルダウン全オプション表示...")
        for sel in await page.query_selector_all("select"):
            name = await sel.get_attribute("name") or ""
            id_  = await sel.get_attribute("id") or ""
            opts = await sel.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r}  ({len(opts)}件)")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r:25} text={txt!r}")

        # ── Step 5: 日付選択 → 検索 ───────────────────────────────────────
        print("\n[Step 5] 令和08年06月19日を選択して検索...")
        target_texts  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19"]
        target_values = ["20260619", "2026-06-19", "260619"]
        date_ok = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = (await opt.get_attribute("value") or "").strip()
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in target_texts) or v in target_values:
                    name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v)
                    print(f"  [OK] 日付選択: name={name!r}  value={v!r}  text={txt!r}")
                    date_ok = True
                    break
            if date_ok:
                break

        if not date_ok:
            print("  ⚠️  対象日付が見つかりません")

        for sel in [
            'input[value="検索"]', 'input[value*="検索"]',
            'button:has-text("検索")', 'input[type="submit"]',
        ]:
            try:
                e = await page.wait_for_selector(sel, timeout=2000)
                if e:
                    print(f"  [OK] 検索ボタン: {sel}")
                    await e.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "04_search_results")

        # ── Step 6: 検索結果テーブル詳細解析 ──────────────────────────────
        print("\n[Step 6] 検索結果テーブル詳細解析...")
        await dump_table_structure(page, "検索結果")

        # D面・16:00 を含むセルを特別ピックアップ
        print("\n  --- D面 / 16:00 関連セル ---")
        for i, cell in enumerate(await page.query_selector_all("td, th")):
            txt     = (await cell.inner_text()).strip()
            cls_c   = await cell.get_attribute("class") or ""
            onclick = await cell.get_attribute("onclick") or ""
            id_c    = await cell.get_attribute("id") or ""
            if any(kw in txt for kw in ["D面", "16:00", "16", "18:00"]):
                links = await cell.query_selector_all("a")
                imgs  = await cell.query_selector_all("img")
                link_info = " ".join(
                    f"[a href={(await l.get_attribute('href') or ''):30} onclick={(await l.get_attribute('onclick') or ''):30}]"
                    for l in links
                )
                img_info = " ".join(
                    f"[img src={(await im.get_attribute('src') or ''):40} alt={(await im.get_attribute('alt') or '')!r}]"
                    for im in imgs
                )
                print(
                    f"  CELL[{i}] id={id_c!r} class={cls_c!r} onclick={onclick!r}\n"
                    f"           text={txt!r}\n"
                    f"           {link_info} {img_info}"
                )

        await browser.close()
        print(f"\n\n解析完了！ → {OUTPUT_DIR}/ フォルダのHTMLを確認し、"
              "reserve.py のセレクターを修正してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
