"""
まんまるよやく2 サイト構造解析スクリプト
─────────────────────────────────────────────
【使い方】
  pip install playwright
  playwright install chromium
  python analyze_site.py

実行後、analysis_output/ フォルダに
  01_login.html / 01_login.png
  02_after_login.html / 02_after_login.png
  03_favorite_filter.html / 03_favorite_filter.png
  04_search_results.html / 04_search_results.png
が保存されます。

これらの HTML を確認して reserve.py の
CONFIRMED_* セレクター変数を設定してください。
─────────────────────────────────────────────
"""

import asyncio
import os
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"
OUTPUT_DIR = "analysis_output"

# 解析する対象日
TARGET_DATE_TEXTS = [
    "令和08年06月19日", "令和8年06月19日",
    "令和08年06月", "令和8年6月",
    "2026年06月19日", "2026/06/19",
]
TARGET_DATE_VALUES = ["20260619", "2026-06-19", "260619"]


# ──────────────────────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────────────────────
async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    png  = f"{OUTPUT_DIR}/{step_name}.png"
    html = f"{OUTPUT_DIR}/{step_name}.html"
    await page.screenshot(path=png, full_page=True)
    content = await page.content()
    with open(html, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [保存] {png}  {html}")


async def dump_elements(page, label: str):
    """ページ内の全フォーム要素・リンクを標準出力へダンプ"""
    print(f"\n{'='*60}")
    print(f"  {label}  URL={page.url}")
    print(f"{'='*60}")

    # INPUT / SELECT / BUTTON / TEXTAREA
    for el in await page.query_selector_all("input, select, button, textarea"):
        tag  = await el.evaluate("el => el.tagName.toLowerCase()")
        name = await el.get_attribute("name") or ""
        id_  = await el.get_attribute("id") or ""
        typ  = await el.get_attribute("type") or ""
        val  = await el.get_attribute("value") or ""
        cls  = await el.get_attribute("class") or ""
        ph   = await el.get_attribute("placeholder") or ""
        try:
            txt = (await el.inner_text()).strip()[:40]
        except Exception:
            txt = ""

        if tag == "select":
            print(f"  <SELECT> name={name!r} id={id_!r} class={cls!r}")
            for opt in await el.query_selector_all("option"):
                ov  = await opt.get_attribute("value") or ""
                otx = (await opt.inner_text()).strip()
                sel = " ← ★" if any(t in otx for t in TARGET_DATE_TEXTS) \
                              or ov in TARGET_DATE_VALUES else ""
                print(f"    OPTION value={ov!r} text={otx!r}{sel}")
        else:
            print(f"  <{tag.upper()}> type={typ!r} name={name!r} id={id_!r} "
                  f"value={val!r} placeholder={ph!r} class={cls!r} text={txt!r}")

    # FORM
    print()
    for form in await page.query_selector_all("form"):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        id_    = await form.get_attribute("id") or ""
        print(f"  <FORM> action={action!r} method={method!r} id={id_!r}")

    # リンク
    print()
    for link in await page.query_selector_all("a"):
        href = await link.get_attribute("href") or ""
        txt  = (await link.inner_text()).strip()
        if txt:
            flag = " ← ★お気に入り" if "お気に入り" in txt else ""
            print(f"  <A> href={href!r} text={txt!r}{flag}")


async def dump_table_structure(page, label: str):
    """検索結果テーブルの行・セル構造を出力"""
    print(f"\n{'─'*60}")
    print(f"  テーブル構造: {label}")
    print(f"{'─'*60}")

    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")

    for ti, table in enumerate(tables):
        rows = await table.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] {len(rows)}行")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for ci, cell in enumerate(cells):
                txt    = (await cell.inner_text()).strip()
                cls    = await cell.get_attribute("class") or ""
                id_    = await cell.get_attribute("id") or ""
                onclick = await cell.get_attribute("onclick") or ""
                summary = f"[{ci}]{txt[:20]}"
                if cls:
                    summary += f"(cls={cls})"
                if onclick:
                    summary += f"(onclick={onclick[:30]})"
                # D面 / 16:00 に関係するセルを強調
                if "D面" in txt or "16:00" in txt or "18:00" in txt:
                    summary = "★" + summary
                row_info.append(summary)
            if row_info:
                print(f"    ROW[{ri}]: " + " | ".join(row_info))


# ──────────────────────────────────────────────────────────────────────
# メイン解析フロー
# ──────────────────────────────────────────────────────────────────────
async def analyze():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
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
        page = await context.new_page()

        # ── Step 1: ログインページ ─────────────────────────────────
        print("\n[Step 1] ログインページ取得...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login")
        await dump_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ───────────────────────────────────
        print("\n[Step 2] ログイン実行...")
        # テキスト入力欄（1番目）に利用者番号を入れる
        text_inputs = await page.query_selector_all(
            'input[type="text"], input:not([type])'
        )
        if text_inputs:
            await text_inputs[0].fill(USER_ID)
            name = await text_inputs[0].get_attribute("name") or "?"
            print(f"  利用者番号入力: name={name!r}")
        else:
            print("  ⚠ テキスト入力欄が見つかりません")

        pw_inputs = await page.query_selector_all('input[type="password"]')
        if pw_inputs:
            await pw_inputs[0].fill(PASSWORD)
            name = await pw_inputs[0].get_attribute("name") or "?"
            print(f"  パスワード入力: name={name!r}")
        else:
            print("  ⚠ パスワード欄が見つかりません")

        submits = await page.query_selector_all(
            'input[type="submit"], button[type="submit"], button'
        )
        if submits:
            val = await submits[0].get_attribute("value") or ""
            txt = (await submits[0].inner_text()).strip()
            print(f"  サブミットクリック: value={val!r} text={txt!r}")
            await submits[0].click()
        else:
            print("  ⚠ サブミットボタンが見つかりません")

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "02_after_login")
        await dump_elements(page, "ログイン後メニュー")
        print(f"  ログイン後URL: {page.url}")

        # ── Step 3: お気に入りクリック ─────────────────────────────
        print("\n[Step 3] お気に入りクリック...")
        clicked = False
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            try:
                txt = (await elem.inner_text()).strip()
                val = await elem.get_attribute("value") or ""
                href = await elem.get_attribute("href") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    print(f"  クリック: text={txt!r} href={href!r}")
                    await elem.click()
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            print("  ⚠ お気に入りが見つかりません。02_after_login.html を確認してください。")

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "03_favorite_filter")
        await dump_elements(page, "絞り込み（お気に入り）画面")

        # ── Step 4: 日付選択・検索 ────────────────────────────────
        print(f"\n[Step 4] 日付選択: {TARGET_DATE_TEXTS[0]}")
        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                if (any(t in txt for t in TARGET_DATE_TEXTS)
                        or v in TARGET_DATE_VALUES):
                    sel_name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v if v else txt)
                    print(f"  日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break
        if not date_selected:
            print("  ⚠ 日付が見つかりません。03_favorite_filter.html を確認してください。")

        # 検索ボタン
        for sel in ['input[value="検索"]', 'button:text("検索")',
                    'input[type="submit"]', 'button[type="submit"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    print(f"  検索ボタンクリック: {sel}")
                    await elem.click()
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        await save_step(page, "04_search_results")
        await dump_elements(page, "検索結果画面")
        await dump_table_structure(page, "検索結果テーブル")

        await browser.close()
        print(f"\n\n✅ 解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
        print("  reserve.py の CONFIRMED_* 変数に正しいセレクターを設定してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
