"""
まんまるよやく2 サイト構造解析スクリプト
各ステップのHTML・スクリーンショットを保存して正確なセレクターを確認する

【使い方】
  python analyze_site.py              # headlessモード
  python analyze_site.py --headful    # ブラウザ表示あり

【注意】このスクリプトはローカルマシンで実行してください。
       cloud環境はネットワーク制限でアクセス不可の場合があります。
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"
OUTPUT_DIR = "analysis_output"

HEADLESS = "--headful" not in sys.argv


async def save_step(page, step_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / {step_name}.html")


async def dump_form_elements(page, label: str):
    """ページ内のすべてのフォーム要素を出力"""
    print(f"\n=== {label} のフォーム要素 ===")

    # input要素
    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        print(f"  INPUT type={t} name={name!r} id={id_!r} class={cls!r} value={val!r}")

    # select要素（全optionのvalue・テキストを表示）
    selects = await page.query_selector_all("select")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        options = await sel.query_selector_all("option")
        print(f"\n  SELECT name={name!r} id={id_!r} class={cls!r} options={len(options)}件")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            print(f"    OPTION value={v!r}  text={txt!r}")

    # ボタン・サブミット
    buttons = await page.query_selector_all(
        "button, input[type=submit], input[type=button]"
    )
    for btn in buttons:
        t    = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        val  = await btn.get_attribute("value") or ""
        txt  = (await btn.inner_text()).strip()
        print(f"  BUTTON type={t} name={name!r} id={id_!r} value={val!r} text={txt!r}")

    # アンカーリンク
    links = await page.query_selector_all("a")
    print(f"\n  --- リンク一覧 ---")
    for link in links:
        href = await link.get_attribute("href") or ""
        cls  = await link.get_attribute("class") or ""
        txt  = (await link.inner_text()).strip()
        if txt:
            print(f"  A href={href!r} class={cls!r} text={txt!r}")

    # フォームのaction/method
    forms = await page.query_selector_all("form")
    print(f"\n  --- フォーム一覧 ({len(forms)}件) ---")
    for form in forms:
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        id_    = await form.get_attribute("id") or ""
        print(f"  FORM id={id_!r} action={action!r} method={method!r}")


async def dump_table_structure(page, label: str):
    """テーブル構造を詳細表示"""
    print(f"\n=== {label} のテーブル構造 ===")
    tables = await page.query_selector_all("table")
    print(f"  テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        id_  = await tbl.get_attribute("id") or ""
        cls  = await tbl.get_attribute("class") or ""
        print(f"\n  TABLE[{ti}] id={id_!r} class={cls!r} 行数={len(rows)}")

        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_data = []
            for ci, cell in enumerate(cells):
                txt     = (await cell.inner_text()).strip().replace("\n", "\\n")
                cls_c   = await cell.get_attribute("class") or ""
                id_c    = await cell.get_attribute("id") or ""
                onclick = await cell.get_attribute("onclick") or ""
                href    = ""
                # aタグが内包されているか
                a_tag = await cell.query_selector("a")
                if a_tag:
                    href = await a_tag.get_attribute("href") or ""
                info = f"{txt!r}[cls={cls_c!r}]"
                if onclick:
                    info += f"[onclick={onclick!r}]"
                if href:
                    info += f"[href={href!r}]"
                row_data.append(info)
            print(f"    ROW[{ri}]: {' | '.join(row_data[:10])}")
            if ri >= 10 and len(rows) > 12:
                print(f"    ... (残り {len(rows) - ri - 1} 行省略)")
                break


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
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

        # ── Step 1: ログインページ ──────────────────────────────────────
        print("\n" + "="*60)
        print("[Step 1] ログインページに移動...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        print(f"  URL: {page.url}")
        print(f"  Title: {await page.title()!r}")
        await save_step(page, "01_login_page")
        await dump_form_elements(page, "ログインページ")

        # ── Step 2: ログイン実行 ────────────────────────────────────────
        print("\n" + "="*60)
        print("[Step 2] ログイン実行...")

        # 利用者番号入力（候補順に試す）
        userid_selectors = [
            'input[name="userid"]', 'input[name="user_id"]',
            'input[name="memberNo"]', 'input[name="userno"]',
            'input[name="loginId"]', 'input[name="login_id"]',
            'input[name="id"]', '#userid',
            'input[type="text"]:first-of-type',
        ]
        for sel in userid_selectors:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
                await elem.fill(USER_ID)
                print(f"  [OK] 利用者番号入力: {sel}")
                break
            except Exception:
                pass

        # パスワード入力
        for sel in ['input[type="password"]', 'input[name="passwd"]',
                    'input[name="password"]', 'input[name="pass"]']:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
                await elem.fill(PASSWORD)
                print(f"  [OK] パスワード入力: {sel}")
                break
            except Exception:
                pass

        # ログインボタン
        for sel in [
            'input[value="ログイン"]', 'button:text("ログイン")',
            'input[type="submit"]', 'button[type="submit"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
                await elem.click()
                print(f"  [OK] サブミット: {sel}")
                break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        print(f"  ログイン後URL: {page.url}")
        await save_step(page, "02_after_login")
        await dump_form_elements(page, "ログイン後")

        # ── Step 3: お気に入りクリック ──────────────────────────────────
        print("\n" + "="*60)
        print("[Step 3] お気に入りリンクを探してクリック...")

        clicked = False
        for sel in [
            'a:text("お気に入り")', 'input[value="お気に入り"]',
            'button:text("お気に入り")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000, state="visible")
                txt = (await elem.inner_text()).strip()
                print(f"  [FOUND] セレクター: {sel!r} text={txt!r}")
                await elem.click()
                clicked = True
                break
            except Exception:
                pass

        if not clicked:
            # テキスト全走査フォールバック
            for elem in await page.query_selector_all("a, button, input"):
                val = await elem.get_attribute("value") or ""
                txt = ""
                try:
                    txt = (await elem.inner_text()).strip()
                except Exception:
                    pass
                if "お気に入り" in txt or "お気に入り" in val:
                    tag   = await elem.get_attribute("tagName") or (await page.evaluate("el => el.tagName", elem))
                    href  = await elem.get_attribute("href") or ""
                    cls   = await elem.get_attribute("class") or ""
                    print(f"  [FOUND-FB] tag={tag} text={txt!r} href={href!r} class={cls!r}")
                    await elem.click()
                    clicked = True
                    break

        if not clicked:
            print("  [WARNING] お気に入りが見つかりません！スクリーンショットを確認")

        await page.wait_for_load_state("networkidle", timeout=20000)
        print(f"  お気に入り後URL: {page.url}")
        await save_step(page, "03_after_favorite")
        await dump_form_elements(page, "絞り込み画面")

        # ── Step 4: 日付プルダウン詳細解析 ─────────────────────────────
        print("\n" + "="*60)
        print("[Step 4] 日付プルダウン詳細解析...")

        selects = await page.query_selector_all("select")
        for sel_elem in selects:
            name    = await sel_elem.get_attribute("name") or ""
            id_     = await sel_elem.get_attribute("id") or ""
            options = await sel_elem.query_selector_all("option")
            print(f"\n  SELECT name={name!r} id={id_!r} → {len(options)}件のオプション")
            for opt in options:
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"    value={v!r}  text={txt!r}")

        # ── Step 5: 日付選択・検索 ──────────────────────────────────────
        print("\n" + "="*60)
        print("[Step 5] 令和08年06月19日を選択して検索...")

        date_target_values = ["20260619", "2026-06-19", "2026/06/19", "260619"]
        date_target_texts  = [
            "令和08年06月19日", "令和8年6月19日",
            "令和０８年０６月１９日", "2026/06/19", "2026年06月19日",
        ]

        date_selected = False
        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if (any(t in txt for t in date_target_texts)
                        or v in date_target_values):
                    name = await sel_elem.get_attribute("name") or ""
                    await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                    print(f"  [OK] 日付選択: name={name!r} value={v!r} text={txt!r}")
                    date_selected = True
                    break
            if date_selected:
                break

        if not date_selected:
            print("  [WARNING] 日付が見つかりません。スクリーンショットで確認")

        # 検索ボタン
        for sel in [
            'input[value="検索"]', 'button:text("検索")',
            'input[value*="検索"]', 'input[type="submit"]',
            'button[type="submit"]', 'a:text("検索")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
                print(f"  [OK] 検索ボタン: {sel}")
                await elem.click()
                break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20000)
        print(f"  検索後URL: {page.url}")
        await save_step(page, "04_search_results")

        # ── Step 6: 検索結果テーブル詳細解析 ───────────────────────────
        print("\n" + "="*60)
        print("[Step 6] 検索結果テーブル解析...")
        await dump_table_structure(page, "検索結果")

        # D面 / 16:00 / 18:00 を含むセルをピンポイントで出力
        print("\n  --- D面・16:00・18:00 を含むセル ---")
        cells = await page.query_selector_all("td, th")
        for i, cell in enumerate(cells):
            txt     = (await cell.inner_text()).strip()
            if any(k in txt for k in ["D面", "16:00", "18:00", "赤"]):
                id_     = await cell.get_attribute("id") or ""
                cls     = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                a       = await cell.query_selector("a")
                href    = (await a.get_attribute("href") or "") if a else ""
                print(
                    f"  CELL[{i}] id={id_!r} class={cls!r} "
                    f"onclick={onclick!r} href={href!r} text={txt!r}"
                )

        await browser.close()
        print(f"\n\n解析完了。./{OUTPUT_DIR}/ フォルダのHTMLとスクリーンショットを確認してください。")
        print("→ セレクターを確認したら reserve.py のセレクター定数を修正してください。")


if __name__ == "__main__":
    asyncio.run(analyze())
