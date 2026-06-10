"""
まんまるよやく2 サイト構造解析スクリプト
ローカルマシンで実行し、各ステップのHTML・スクリーンショットを保存して
正確なセレクターを確認する。

■ 実行方法
  python analyze_site.py              # ヘッドレス（画面なし）
  python analyze_site.py --headful    # ブラウザ表示あり（推奨）
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUT        = "analysis_output"
HEADLESS   = "--headful" not in sys.argv


# ──────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────
async def save(page, name: str):
    os.makedirs(OUT, exist_ok=True)
    await page.screenshot(path=f"{OUT}/{name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUT}/{name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {OUT}/{name}.png  ({len(html)} bytes)")


async def dump_all(page, label: str):
    """ページ内の全フォーム要素・リンクを列挙"""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  URL: {page.url}")
    print(f"  Title: {await page.title()!r}")

    # INPUT
    inputs = await page.query_selector_all("input")
    print(f"\n  ── INPUT ({len(inputs)}件) ──")
    for inp in inputs:
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"    <input type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r}>")

    # SELECT / OPTION
    selects = await page.query_selector_all("select")
    print(f"\n  ── SELECT ({len(selects)}件) ──")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        options = await sel.query_selector_all("option")
        print(f"    <select name={name!r} id={id_!r} class={cls!r}> ── {len(options)}件")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            print(f"      <option value={v!r}> {txt!r}")

    # BUTTON / SUBMIT
    buttons = await page.query_selector_all(
        "button, input[type=submit], input[type=button], input[type=image]"
    )
    print(f"\n  ── BUTTON/SUBMIT ({len(buttons)}件) ──")
    for btn in buttons:
        t    = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        val  = await btn.get_attribute("value") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"    <{await btn.get_property('tagName')!s} type={t!r} name={name!r} id={id_!r} value={val!r}> {txt!r}")

    # ANCHOR
    links = await page.query_selector_all("a")
    print(f"\n  ── A LINK ({len(links)}件) ──")
    for lnk in links:
        href   = await lnk.get_attribute("href") or ""
        onclick= await lnk.get_attribute("onclick") or ""
        cls    = await lnk.get_attribute("class") or ""
        try:
            txt = (await lnk.inner_text()).strip()
        except Exception:
            txt = ""
        if txt:
            print(f"    <a href={href!r} onclick={onclick[:60]!r} class={cls!r}> {txt!r}")

    # FORM
    forms = await page.query_selector_all("form")
    print(f"\n  ── FORM ({len(forms)}件) ──")
    for frm in forms:
        action = await frm.get_attribute("action") or ""
        method = await frm.get_attribute("method") or ""
        name   = await frm.get_attribute("name") or ""
        print(f"    <form name={name!r} action={action!r} method={method!r}>")


async def dump_table(page, label: str):
    """テーブル構造を詳細表示"""
    tables = await page.query_selector_all("table")
    print(f"\n  ── TABLE ({len(tables)}件) [{label}] ──")
    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        id_  = await tbl.get_attribute("id") or ""
        cls  = await tbl.get_attribute("class") or ""
        print(f"\n  TABLE[{ti}] id={id_!r} class={cls!r} ── {len(rows)}行")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_data = []
            for cell in cells:
                txt    = (await cell.inner_text()).strip()
                cls_c  = await cell.get_attribute("class") or ""
                style  = await cell.get_attribute("style") or ""
                onclick= await cell.get_attribute("onclick") or ""
                bg     = style[:40] if style else ""
                row_data.append(
                    f"{txt!r}"
                    + (f"[cls={cls_c!r}]" if cls_c else "")
                    + (f"[bg={bg!r}]" if bg else "")
                    + (f"[onclick=...{onclick[-30:]!r}]" if onclick else "")
                )
            print(f"    ROW[{ri}]: {' | '.join(row_data[:10])}")


# ──────────────────────────────────────────────────────
# メイン解析フロー
# ──────────────────────────────────────────────────────
async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            ignore_https_errors=True,
        )
        page = await ctx.new_page()

        # ── Step 1: ログインページ ──────────────────────────
        print("\n[Step 1] ログインページ...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save(page, "01_login_page")
        await dump_all(page, "ログインページ")

        # ── Step 2: ログイン ────────────────────────────────
        print("\n[Step 2] ログイン実行...")
        userid_ok = False
        for sel in [
            'input[name="userid"]', 'input[name="user_id"]', 'input[name="uid"]',
            'input[name="memberNo"]', 'input[name="userno"]',
            'input[name="loginId"]', '#userid', '#uid',
            'input[type="text"]:first-of-type',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                await elem.fill(USER_ID)
                print(f"  [OK] 利用者番号: {sel}")
                userid_ok = True
                break
            except Exception:
                pass
        if not userid_ok:
            print("  [WARN] 利用者番号フィールド未検出")

        passwd_ok = False
        for sel in [
            'input[type="password"]',
            'input[name="passwd"]', 'input[name="password"]', 'input[name="pass"]',
            '#passwd', '#password',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                await elem.fill(PASSWORD)
                print(f"  [OK] パスワード: {sel}")
                passwd_ok = True
                break
            except Exception:
                pass
        if not passwd_ok:
            print("  [WARN] パスワードフィールド未検出")

        for sel in [
            'input[value="ログイン"]', 'input[type="submit"]',
            'button[type="submit"]', 'button:has-text("ログイン")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                print(f"  [OK] ログインボタン: {sel}")
                await elem.click()
                break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save(page, "02_after_login")
        await dump_all(page, "ログイン後（メニュー画面）")

        # ── Step 3: お気に入り ──────────────────────────────
        print("\n[Step 3] お気に入りをクリック...")
        fav_clicked = False
        for sel in [
            'a:has-text("お気に入り")',
            'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                txt = (await elem.inner_text()).strip()
                print(f"  [OK] お気に入り要素: {sel} text={txt!r}")
                await elem.click()
                fav_clicked = True
                break
            except Exception:
                pass
        if not fav_clicked:
            print("  [WARN] お気に入り要素が見つかりません。ページを確認してください")

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save(page, "03_after_favorite")
        await dump_all(page, "お気に入り後（絞り込み画面）")

        # ── Step 4: 日付プルダウン全列挙 ────────────────────
        print("\n[Step 4] 日付プルダウン全列挙...")
        date_selects = await page.query_selector_all("select")
        for sel in date_selects:
            nm  = await sel.get_attribute("name") or ""
            id_ = await sel.get_attribute("id") or ""
            opts = await sel.query_selector_all("option")
            print(f"\n  SELECT name={nm!r} id={id_!r} ── {len(opts)}件")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r}  text={txt!r}")

        # 令和08年06月19日 を選択して検索
        date_values = ["20260619", "2026-06-19", "260619"]
        date_texts  = ["令和08年06月19日", "令和8年6月19日", "2026/06/19"]
        date_done = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in date_texts) or v in date_values:
                    nm = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v) if v else \
                        await sel_elem.select_option(label=txt)
                    print(f"\n  [OK] 日付選択: name={nm!r} value={v!r} text={txt!r}")
                    date_done = True
                    break
            if date_done:
                break
        if not date_done:
            print("  [WARN] 令和08年06月19日 が見つかりませんでした")

        for sel in [
            'input[value="検索"]', 'input[value*="検索"]', 'input[value*="照会"]',
            'input[type="submit"]', 'button[type="submit"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                print(f"  [OK] 検索ボタン: {sel}")
                await elem.click()
                break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save(page, "04_search_results")
        await dump_all(page, "検索結果ページ")
        await dump_table(page, "検索結果テーブル")

        # ── Step 5: D面 / 16:00 セルの詳細解析 ────────────
        print("\n[Step 5] D面 16:00〜18:00 セル詳細解析...")
        all_cells = await page.query_selector_all("td, th")
        for i, cell in enumerate(all_cells):
            txt    = (await cell.inner_text()).strip()
            id_    = await cell.get_attribute("id") or ""
            cls    = await cell.get_attribute("class") or ""
            style  = await cell.get_attribute("style") or ""
            onclick= await cell.get_attribute("onclick") or ""
            if any(k in txt for k in ["D面", "Ｄ面", "16:00", "18:00", "16時", "18時"]):
                print(f"\n  CELL[{i}] text={txt!r}")
                print(f"    id={id_!r}  class={cls!r}")
                print(f"    style={style!r}")
                print(f"    onclick={onclick!r}")

        await browser.close()
        print(f"\n\n✅ 解析完了。{OUT}/ フォルダを確認してください。")
        print(f"   HTMLファイルをブラウザで開くか、テキストエディタで確認できます。")


if __name__ == "__main__":
    asyncio.run(analyze())
