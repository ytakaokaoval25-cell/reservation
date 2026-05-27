"""
まんまるよやく2 サイト構造解析スクリプト

reserve.py を実行する前にこのスクリプトを1回動かしてください。
各ステップの HTML とスクリーンショットを analysis_output/ に保存します。

■ 使い方
  python analyze_site.py

■ 出力
  analysis_output/01_login_page.html/.png    ログインページ
  analysis_output/02_after_login.html/.png   ログイン後メニュー
  analysis_output/03_after_favorite.html/.png  お気に入り絞り込み画面
  analysis_output/04_search_results.html/.png  検索結果（日付選択後）
  analysis_output/console_output.txt          全フォーム要素の詳細ログ
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"


# ─── ユーティリティ ──────────────────────────────────────────────

def log(msg: str):
    """コンソールとログファイルに同時出力"""
    print(msg)
    with open(f"{OUTPUT_DIR}/console_output.txt", "a", encoding="utf-8") as f:
        f.write(msg + "\n")


async def save_step(page, step_name: str):
    """HTML とスクリーンショットを保存"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    log(f"[SAVED] {step_name}.png / {step_name}.html")


async def dump_all_elements(page, label: str):
    """ページ内のすべてのフォーム要素・リンクを詳細出力"""
    log(f"\n{'='*60}")
    log(f"  {label} のフォーム要素")
    log(f"{'='*60}")

    # ── FORM ──
    forms = await page.query_selector_all("form")
    for i, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        name   = await form.get_attribute("name")   or ""
        id_    = await form.get_attribute("id")     or ""
        log(f"\n  FORM[{i}] action={action!r} method={method!r} name={name!r} id={id_!r}")

    # ── INPUT ──
    log("\n  --- INPUT ---")
    for inp in await page.query_selector_all("input"):
        t      = await inp.get_attribute("type")  or "text"
        name   = await inp.get_attribute("name")  or ""
        id_    = await inp.get_attribute("id")    or ""
        cls    = await inp.get_attribute("class") or ""
        val    = await inp.get_attribute("value") or ""
        ph     = await inp.get_attribute("placeholder") or ""
        log(f"    INPUT type={t!r} name={name!r} id={id_!r} class={cls!r} value={val!r} placeholder={ph!r}")

    # ── SELECT（全オプションを表示）──
    log("\n  --- SELECT ---")
    for sel in await page.query_selector_all("select"):
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id")   or ""
        cls  = await sel.get_attribute("class") or ""
        log(f"\n    SELECT name={name!r} id={id_!r} class={cls!r}")
        for opt in await sel.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            sel_flag = "★SELECTED" if await opt.get_attribute("selected") else ""
            log(f"      OPTION value={v!r}  text={txt!r}  {sel_flag}")

    # ── BUTTON / SUBMIT ──
    log("\n  --- BUTTON/SUBMIT ---")
    for btn in await page.query_selector_all("button, input[type=submit], input[type=button]"):
        t    = await btn.get_attribute("type")  or ""
        name = await btn.get_attribute("name")  or ""
        id_  = await btn.get_attribute("id")    or ""
        val  = await btn.get_attribute("value") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        log(f"    BTN type={t!r} name={name!r} id={id_!r} value={val!r} text={txt!r}")

    # ── LINK ──
    log("\n  --- LINK (テキストあり) ---")
    for a in await page.query_selector_all("a"):
        href = await a.get_attribute("href")    or ""
        cls  = await a.get_attribute("class")   or ""
        onclick = await a.get_attribute("onclick") or ""
        try:
            txt = (await a.inner_text()).strip()
        except Exception:
            txt = ""
        if txt:
            log(f"    A text={txt!r} href={href!r} class={cls!r} onclick={onclick[:60]!r}")

    # ── TABLE 構造（最初の5行）──
    log("\n  --- TABLE 構造 ---")
    tables = await page.query_selector_all("table")
    log(f"  テーブル数: {len(tables)}")
    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        log(f"\n  TABLE[{ti}]  行数={len(rows)}")
        for ri, row in enumerate(rows[:8]):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for cell in cells:
                txt = (await cell.inner_text()).strip()
                cls = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                id_ = await cell.get_attribute("id") or ""
                row_info.append(f"{txt!r}(cls={cls},id={id_},onclick={onclick[:30]!r})")
            log(f"    ROW[{ri}]: {' | '.join(row_info[:8])}")


async def safe_try(selectors: list, page, label: str) -> bool:
    """複数セレクタを試してクリック、成功したら True"""
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000)
            if elem:
                await elem.click()
                log(f"  [OK] {label}: {sel}")
                return True
        except Exception:
            pass
    log(f"  [WARNING] {label}: 見つかりません")
    return False


# ─── 解析メイン ─────────────────────────────────────────────────

async def analyze():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # ログファイル初期化
    with open(f"{OUTPUT_DIR}/console_output.txt", "w", encoding="utf-8") as f:
        f.write("まんまるよやく2 サイト解析ログ\n\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()

        # ── Step 1: ログインページ ────────────────────────────────
        log("\n[Step 1] ログインページ解析...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        await dump_all_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ─────────────────────────────────
        log("\n[Step 2] ログイン実行...")

        # 利用者番号
        userid_ok = False
        for sel in [
            'input[name="userid"]', 'input[name="user_id"]', 'input[name="memberNo"]',
            'input[name="userno"]', 'input[name="loginId"]', 'input[name="login_id"]',
            '#userid', 'input[type="text"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.fill(USER_ID)
                    log(f"  [OK] 利用者番号入力: {sel}")
                    userid_ok = True
                    break
            except Exception:
                pass
        if not userid_ok:
            log("  [WARNING] 利用者番号フィールドが見つかりません！HTMLを確認してください。")

        # パスワード
        for sel in [
            'input[type="password"]', 'input[name="passwd"]',
            'input[name="password"]', 'input[name="pass"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.fill(PASSWORD)
                    log(f"  [OK] パスワード入力: {sel}")
                    break
            except Exception:
                pass

        # ログインボタン
        await safe_try([
            'input[value="ログイン"]', 'input[value*="ログイン"]',
            'button:text("ログイン")', 'input[type="submit"]',
            'button[type="submit"]',
        ], page, "ログインボタン")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        await dump_all_elements(page, "ログイン後メニュー")
        log(f"  現在URL: {page.url}")

        # ── Step 3: お気に入りクリック ───────────────────────────
        log("\n[Step 3] お気に入りクリック...")
        fav_ok = False
        for sel in [
            'a:text("お気に入り")', 'input[value*="お気に入り"]',
            'button:text("お気に入り")', '*:text("お気に入り")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                if elem:
                    txt = (await elem.inner_text()).strip()
                    log(f"  [OK] お気に入り: {sel} text={txt!r}")
                    await elem.click()
                    fav_ok = True
                    break
            except Exception:
                pass

        if not fav_ok:
            # 全リンク・ボタンのテキスト一覧
            log("  [WARNING] お気に入りが見つかりません。全リンク一覧:")
            for a in await page.query_selector_all("a, button, input"):
                try:
                    txt = (await a.inner_text()).strip()
                    val = await a.get_attribute("value") or ""
                    href = await a.get_attribute("href") or ""
                    if txt or val:
                        log(f"    {txt!r} / value={val!r} / href={href!r}")
                except Exception:
                    pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        await dump_all_elements(page, "お気に入り絞り込み画面")
        log(f"  現在URL: {page.url}")

        # ── Step 4: 日付 SELECT の全 OPTIONS を出力 ─────────────
        log("\n[Step 4] 日付プルダウン 詳細解析...")
        for sel_elem in await page.query_selector_all("select"):
            name = await sel_elem.get_attribute("name") or ""
            id_  = await sel_elem.get_attribute("id")   or ""
            opts = await sel_elem.query_selector_all("option")
            log(f"\n  SELECT name={name!r} id={id_!r} ({len(opts)}件):")
            for opt in opts:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                log(f"    value={v!r}  text={txt!r}")

        # ── Step 5: 令和08年06月19日 を選択して検索 ─────────────
        log("\n[Step 5] 令和08年06月19日を選択して検索...")
        date_target_texts  = ["令和08年06月19日", "令和8年6月19日", "2026年06月19日"]
        date_target_values = ["20260619", "2026-06-19", "260619"]

        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(t in txt for t in date_target_texts) or v in date_target_values:
                    name = await sel_elem.get_attribute("name") or ""
                    try:
                        await sel_elem.select_option(value=v)
                        log(f"  [OK] 日付選択: name={name!r} value={v!r} text={txt!r}")
                        date_selected = True
                    except Exception as e:
                        log(f"  [WARN] select_option失敗: {e}")
                    break
            if date_selected:
                break

        if not date_selected:
            log("  [WARNING] 日付が見つかりませんでした。")

        await safe_try([
            'input[type="submit"]', 'button[type="submit"]',
            'input[value*="検索"]', 'button:text("検索")',
        ], page, "検索ボタン")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        log(f"  現在URL: {page.url}")

        # ── Step 6: 検索結果テーブル詳細解析 ─────────────────────
        log("\n[Step 6] 検索結果テーブル詳細解析...")
        await dump_all_elements(page, "検索結果ページ")

        # D面・16:00・18:00 を含むセルを重点的に出力
        log("\n  --- D面 / 16:00 / 18:00 を含む要素 ---")
        for i, cell in enumerate(await page.query_selector_all("td, th, a, input")):
            txt     = (await cell.inner_text()).strip()
            cls     = await cell.get_attribute("class")   or ""
            onclick = await cell.get_attribute("onclick") or ""
            href    = await cell.get_attribute("href")    or ""
            id_     = await cell.get_attribute("id")      or ""
            if any(k in txt for k in ["D面", "16:00", "18:00", "16", "D"]):
                tag = await cell.evaluate("el => el.tagName")
                log(f"  CELL[{i}] <{tag}> id={id_!r} class={cls!r} onclick={onclick[:60]!r} "
                    f"href={href!r} text={txt!r}")

        await browser.close()

    print(f"\n解析完了！ {OUTPUT_DIR}/ フォルダを確認してください。")
    print(f"  - console_output.txt: フォーム要素の詳細ログ")
    print(f"  - *.html / *.png:    各ステップの画面キャプチャ")


if __name__ == "__main__":
    asyncio.run(analyze())
