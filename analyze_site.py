"""
まんまるよやく2 サイト構造解析スクリプト
── reserve.py が正常動作しない場合にまず実行 ──

各ステップのHTML・スクリーンショットを analysis_output/ に保存します。
保存されたファイルを確認し、reserve.py のセレクターを調整してください。

■ 使い方
  python analyze_site.py              # 朝5:00後に即実行
  python analyze_site.py --headful    # ブラウザを表示して動作確認
  python analyze_site.py --step LOGIN # ログインページだけ解析
"""

import asyncio
import os
import sys
import json
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

HEADFUL = "--headful" in sys.argv
STEP    = next((a.split("LOGIN")[1] if "LOGIN" in a else None
                for a in sys.argv), None)


# ──────────────────────────────────────────────
# 保存ユーティリティ
# ──────────────────────────────────────────────
def ensure_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


async def save_step(page, step_name: str):
    ensure_dir()
    ss_path   = f"{OUTPUT_DIR}/{step_name}.png"
    html_path = f"{OUTPUT_DIR}/{step_name}.html"
    await page.screenshot(path=ss_path, full_page=True)
    html = await page.content()
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [SAVED] {ss_path}  /  {html_path}")


async def safe_text(elem) -> str:
    try:
        return (await elem.inner_text()).strip()
    except Exception:
        return ""


# ──────────────────────────────────────────────
# 解析：フォーム要素
# ──────────────────────────────────────────────
async def dump_form_elements(page, label: str):
    print(f"\n{'='*60}")
    print(f"  {label} のフォーム要素")
    print('='*60)

    # INPUT
    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t    = await inp.get_attribute("type")  or "text"
        name = await inp.get_attribute("name")  or ""
        id_  = await inp.get_attribute("id")    or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT  type={t:<10} name={name!r:<20} id={id_!r:<20} "
              f"class={cls!r:<20} value={val!r}")

    # SELECT + OPTIONS
    selects = await page.query_selector_all("select")
    for sel in selects:
        name = await sel.get_attribute("name")  or ""
        id_  = await sel.get_attribute("id")    or ""
        cls  = await sel.get_attribute("class") or ""
        options = await sel.query_selector_all("option")
        print(f"\n  SELECT name={name!r} id={id_!r} class={cls!r} "
              f"({len(options)}件のオプション)")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_flag = "★" if "令和08" in txt or "20260619" == v else " "
            print(f"    {sel_flag} OPTION value={v!r:<20} text={txt!r}")

    # BUTTON / SUBMIT
    buttons = await page.query_selector_all(
        "button, input[type=submit], input[type=button]"
    )
    for btn in buttons:
        t    = await btn.get_attribute("type")  or ""
        name = await btn.get_attribute("name")  or ""
        id_  = await btn.get_attribute("id")    or ""
        val  = await btn.get_attribute("value") or ""
        txt  = await safe_text(btn)
        print(f"  BUTTON type={t:<10} name={name!r:<20} id={id_!r:<20} "
              f"value={val!r} text={txt!r}")

    # FORM attributes
    forms = await page.query_selector_all("form")
    for i, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        id_    = await form.get_attribute("id")     or ""
        print(f"\n  FORM[{i}] action={action!r} method={method!r} id={id_!r}")

    # アンカーリンク
    links = await page.query_selector_all("a")
    print(f"\n  --- リンク一覧 ({len(links)}件) ---")
    for link in links:
        href    = await link.get_attribute("href")    or ""
        onclick = await link.get_attribute("onclick") or ""
        cls     = await link.get_attribute("class")   or ""
        txt     = await safe_text(link)
        if txt or href:
            print(f"  A href={href!r:<40} onclick={onclick!r:<30} "
                  f"class={cls!r:<20} text={txt!r}")


# ──────────────────────────────────────────────
# 解析：テーブル構造（予約グリッド）
# ──────────────────────────────────────────────
async def dump_table_structure(page, label: str):
    print(f"\n{'='*60}")
    print(f"  {label} のテーブル構造")
    print('='*60)

    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        id_  = await tbl.get_attribute("id")    or ""
        cls  = await tbl.get_attribute("class") or ""
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] id={id_!r} class={cls!r}  行数={len(rows)}")

        for ri, row in enumerate(rows[:20]):  # 最大20行
            cells = await row.query_selector_all("td, th")
            row_info = []
            for ci, cell in enumerate(cells):
                txt     = await safe_text(cell)
                id_c    = await cell.get_attribute("id")      or ""
                cls_c   = await cell.get_attribute("class")   or ""
                onclick = await cell.get_attribute("onclick") or ""
                href_inner = ""
                link = await cell.query_selector("a")
                if link:
                    href_inner = await link.get_attribute("href") or ""

                flag = ""
                if "D面" in txt:
                    flag = "[D面]"
                if "16:00" in txt or "16" == txt:
                    flag += "[16時]"

                row_info.append(
                    f"[{ci}]{flag}{txt!r}"
                    + (f"(cls={cls_c})" if cls_c else "")
                    + (f"(onclick={onclick[:30]})" if onclick else "")
                    + (f"(href={href_inner[:30]})" if href_inner else "")
                )

            print(f"    ROW[{ri:02d}]: " + " | ".join(row_info[:10]))

    # D面 16:00 に関連するすべてのセルを抽出
    print(f"\n  --- D面 / 16:00 を含む要素 ---")
    cells = await page.query_selector_all("td, th, a, input, button")
    for cell in cells:
        txt     = await safe_text(cell)
        id_     = await cell.get_attribute("id")      or ""
        cls     = await cell.get_attribute("class")   or ""
        onclick = await cell.get_attribute("onclick") or ""
        href    = await cell.get_attribute("href")    or ""
        combined = txt + id_ + cls + onclick + href
        if "D面" in combined or "16:00" in combined or "1600" in combined:
            tag = await cell.evaluate("el => el.tagName.toLowerCase()")
            print(f"  <{tag}> id={id_!r} class={cls!r} onclick={onclick!r} "
                  f"href={href!r} text={txt!r}")


# ──────────────────────────────────────────────
# メイン解析フロー
# ──────────────────────────────────────────────
async def analyze():
    ensure_dir()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not HEADFUL)
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

        # ── Step 1: ログインページ ─────────────────────────────
        print("\n[Step 1] ログインページ解析...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
        await save_step(page, "01_login_page")
        await dump_form_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ──────────────────────────────
        print("\n[Step 2] ログイン実行...")
        userid_selectors = [
            'input[name="userid"]', 'input[name="user_id"]',
            'input[name="mid"]',    'input[name="loginId"]',
            'input[name="login_id"]', 'input[name="memberNo"]',
            'input[name="userno"]', '#userid',
            'form input[type="text"]:first-of-type',
        ]
        for sel in userid_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.fill(USER_ID)
                    print(f"  [OK] 利用者番号: {sel}")
                    break
            except PWTimeout:
                pass

        passwd_selectors = [
            'input[type="password"]', 'input[name="passwd"]',
            'input[name="password"]', 'input[name="pass"]',
            'input[name="mpw"]',      'input[name="loginpass"]',
        ]
        for sel in passwd_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.fill(PASSWORD)
                    print(f"  [OK] パスワード: {sel}")
                    break
            except PWTimeout:
                pass

        submit_selectors = [
            'input[value="ログイン"]', 'input[type="submit"]',
            'button[type="submit"]',   'button:has-text("ログイン")',
        ]
        for sel in submit_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.click()
                    print(f"  [OK] ログインボタン: {sel}")
                    break
            except PWTimeout:
                pass

        await page.wait_for_load_state("networkidle", timeout=20_000)
        await save_step(page, "02_after_login")
        await dump_form_elements(page, "ログイン後")
        print(f"  現在URL: {page.url}")

        # ── Step 3: お気に入りクリック ────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        fav_selectors = [
            'a:has-text("お気に入り")', 'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
        ]
        fav_clicked = False
        for sel in fav_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                if elem:
                    txt = await safe_text(elem)
                    print(f"  [OK] お気に入り: {sel} text={txt!r}")
                    await elem.click()
                    fav_clicked = True
                    break
            except PWTimeout:
                pass

        if not fav_clicked:
            # 全リンク・ボタンをスキャン
            for tag in ["a", "button", "input"]:
                elems = await page.query_selector_all(tag)
                for elem in elems:
                    txt = await safe_text(elem)
                    val = await elem.get_attribute("value") or ""
                    if "お気に入り" in txt or "お気に入り" in val:
                        href = await elem.get_attribute("href") or ""
                        onclick = await elem.get_attribute("onclick") or ""
                        print(f"  [FOUND] <{tag}> text={txt!r} val={val!r} "
                              f"href={href!r} onclick={onclick!r}")
                        await elem.click()
                        fav_clicked = True
                        break
                if fav_clicked:
                    break

        if not fav_clicked:
            print("  [WARNING] お気に入りリンクが見つかりません！")

        await page.wait_for_load_state("networkidle", timeout=20_000)
        await save_step(page, "03_after_favorite")
        await dump_form_elements(page, "お気に入り後（絞り込み画面）")
        print(f"  現在URL: {page.url}")

        # ── Step 4: 日付選択・検索 ───────────────────────────
        print("\n[Step 4] 日付SELECTの全OPTIONを表示...")
        selects = await page.query_selector_all("select")
        for sel_elem in selects:
            name = await sel_elem.get_attribute("name") or ""
            id_  = await sel_elem.get_attribute("id")   or ""
            options = await sel_elem.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r} ({len(options)}件)")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                mark = "★" if "令和08" in txt or "20260619" == v or "06月" in txt else " "
                print(f"  {mark}  value={v!r:<25} text={txt!r}")

        # 令和08年06月19日を選択して検索
        date_texts  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19",
                       "2026年06月19日", "06月19日"]
        date_values = ["20260619", "2026-06-19", "260619", "0619"]

        date_selected = False
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in date_texts) or v in date_values:
                    name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v if v else None,
                                                 label=txt if not v else None)
                    print(f"  [OK] 日付選択: name={name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません")

        # 検索ボタン
        for sel in ['input[type="submit"]', 'button[type="submit"]',
                    'input[value*="検索"]', 'button:has-text("検索")']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    print(f"  [OK] 検索ボタン: {sel}")
                    await elem.click()
                    break
            except PWTimeout:
                pass

        await page.wait_for_load_state("networkidle", timeout=20_000)
        await save_step(page, "04_search_results")
        await dump_table_structure(page, "検索結果")
        print(f"  現在URL: {page.url}")

        # ── Step 5: D面 16:00 セルのクリック解析 ─────────────
        print("\n[Step 5] D面 16:00〜18:00 セルのクリックを試みます...")
        tables = await page.query_selector_all("table")
        slot_clicked = False

        for table in tables:
            rows = await table.query_selector_all("tr")
            time_col = -1

            for row in rows[:5]:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = await safe_text(cell)
                    if "16:00" in txt and "18:00" in txt:
                        time_col = ci
                        print(f"  [INFO] 16:00〜18:00 列インデックス={ci}")
                        break
                if time_col >= 0:
                    break

            if time_col < 0:
                continue

            for row in rows:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = await safe_text(cell)
                    if "D面" in txt:
                        if time_col < len(cells):
                            tc = cells[time_col]
                            tc_txt = await safe_text(tc)
                            tc_cls = await tc.get_attribute("class") or ""
                            tc_id  = await tc.get_attribute("id")    or ""
                            print(f"  [TARGET] D面×{time_col}: "
                                  f"id={tc_id!r} class={tc_cls!r} text={tc_txt!r}")
                            await tc.screenshot(
                                path=f"{OUTPUT_DIR}/05_target_cell.png"
                            )
                            inner = await tc.query_selector("a, input[type=button], button")
                            if inner:
                                href = await inner.get_attribute("href") or ""
                                onclick = await inner.get_attribute("onclick") or ""
                                print(f"  [INNER] href={href!r} onclick={onclick!r}")
                                await inner.click()
                            else:
                                await tc.click()
                            slot_clicked = True
                        break
                if slot_clicked:
                    break
            if slot_clicked:
                break

        if not slot_clicked:
            print("  [WARNING] D面 16:00 セルが自動特定できませんでした。")
            print("  analysis_output/04_search_results.html を手動で確認してください。")
        else:
            await page.wait_for_load_state("networkidle", timeout=20_000)
            await save_step(page, "05_slot_selected")
            print(f"  現在URL: {page.url}")

            # 確定①
            print("\n[Step 6] 確定①ボタンを探します...")
            await dump_form_elements(page, "確定①画面")
            for sel in ['input[value="確定"]', 'input[value="確認"]',
                        'input[value="次へ"]', 'input[type="submit"]',
                        'button[type="submit"]']:
                try:
                    elem = await page.wait_for_selector(sel, timeout=2000)
                    if elem:
                        txt = await safe_text(elem)
                        val = await elem.get_attribute("value") or ""
                        print(f"  [FOUND] 確定①候補: {sel} value={val!r} text={txt!r}")
                        break
                except PWTimeout:
                    pass

        await browser.close()

        print(f"\n\n{'='*60}")
        print(f"  解析完了！{OUTPUT_DIR}/ フォルダを確認してください。")
        print(f"  PNG: ブラウザの各ステップのスクリーンショット")
        print(f"  HTML: 各ページの生HTML（セレクター確認用）")
        print('='*60)


if __name__ == "__main__":
    asyncio.run(analyze())
