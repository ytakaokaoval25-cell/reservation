"""
まんまるよやく2 サイト構造解析スクリプト
─────────────────────────────────────────
各ステップのHTML・スクリーンショットを保存し、
reserve.py に設定すべき正確なセレクターを特定する。

■ 使い方
  python analyze_site.py

■ 出力先
  analysis_output/
    01_login_page.html/png          ← ログインページ
    02_after_login.html/png         ← ログイン後メニュー
    03_after_favorite.html/png      ← お気に入り絞り込み画面
    04_search_results.html/png      ← 検索結果（予約カレンダー）
    selectors_report.txt            ← 推奨セレクター一覧
"""

import asyncio
import datetime
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"

# 解析に使う仮日付（最初に見つかる日付を選ぶ）
PROBE_DATE_TEXTS = [
    "令和08年06月19日", "令和8年6月19日",
    "2026/06/19", "20260619",
]

JST = datetime.timezone(datetime.timedelta(hours=9))


def log(msg):
    ts = datetime.datetime.now(JST).strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}")


async def save_step(page, step_name: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    png_path  = f"{OUTPUT_DIR}/{step_name}.png"
    html_path = f"{OUTPUT_DIR}/{step_name}.html"
    await page.screenshot(path=png_path, full_page=True)
    html = await page.content()
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"  [SAVED] {step_name}.png / .html")
    return html


async def dump_inputs(page, label: str) -> dict:
    """ページ内の全フォーム要素を出力・辞書で返す"""
    print(f"\n{'='*55}")
    print(f"  {label} のフォーム要素")
    print(f"{'='*55}")

    result = {"inputs": [], "selects": [], "buttons": [], "links": []}

    # INPUT
    inputs = await page.query_selector_all("input")
    for inp in inputs:
        t     = await inp.get_attribute("type") or "text"
        name  = await inp.get_attribute("name") or ""
        id_   = await inp.get_attribute("id") or ""
        cls   = await inp.get_attribute("class") or ""
        val   = await inp.get_attribute("value") or ""
        ph    = await inp.get_attribute("placeholder") or ""
        info  = f"type={t} name={name!r} id={id_!r} class={cls!r} value={val!r} placeholder={ph!r}"
        print(f"  INPUT  {info}")
        result["inputs"].append({"type": t, "name": name, "id": id_, "class": cls, "value": val})

    # SELECT
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
            sel_val = await opt.get_attribute("selected")
            marker  = " ← selected" if sel_val is not None else ""
            print(f"    OPTION value={v!r:20s} text={txt!r}{marker}")
        result["selects"].append({
            "name": name, "id": id_,
            "options": [
                {"value": await o.get_attribute("value") or "",
                 "text":  (await o.inner_text()).strip()}
                for o in options
            ]
        })

    # BUTTON / SUBMIT
    buttons = await page.query_selector_all(
        "button, input[type=submit], input[type=button], input[type=image]"
    )
    print()
    for btn in buttons:
        t    = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        val  = await btn.get_attribute("value") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        onclick = await btn.get_attribute("onclick") or ""
        print(f"  BUTTON type={t} name={name!r} id={id_!r} value={val!r} "
              f"text={txt!r} onclick={onclick[:60]!r}")
        result["buttons"].append({"type": t, "name": name, "id": id_, "value": val, "text": txt})

    # FORM
    forms = await page.query_selector_all("form")
    print()
    for fi, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        name   = await form.get_attribute("name") or ""
        print(f"  FORM[{fi}] name={name!r} action={action!r} method={method!r}")

    # LINKS
    print("\n  --- リンク一覧 ---")
    links = await page.query_selector_all("a")
    for link in links:
        href    = await link.get_attribute("href") or ""
        onclick = await link.get_attribute("onclick") or ""
        cls     = await link.get_attribute("class") or ""
        try:
            txt = (await link.inner_text()).strip()
        except Exception:
            txt = ""
        if txt or href:
            print(f"  A  href={href!r:40s} onclick={onclick[:40]!r} class={cls!r} text={txt!r}")
            result["links"].append({"href": href, "onclick": onclick, "text": txt})

    return result


async def dump_table_structure(page, label: str):
    """テーブル構造を詳細出力"""
    print(f"\n{'='*55}")
    print(f"  {label} のテーブル構造")
    print(f"{'='*55}")
    tables = await page.query_selector_all("table")
    print(f"  テーブル総数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        print(f"\n  TABLE[{ti}] 行数={len(rows)}")
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for ci, cell in enumerate(cells):
                try:
                    txt = (await cell.inner_text()).strip().replace("\n", " ")[:30]
                except Exception:
                    txt = ""
                cls     = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                id_     = await cell.get_attribute("id") or ""
                tag     = await cell.evaluate("e => e.tagName")
                info    = f"{tag}[{ci}] {txt!r}"
                if cls:
                    info += f" .{cls}"
                if onclick:
                    info += f" onclick={onclick[:30]!r}"
                if id_:
                    info += f" #{id_}"
                row_info.append(info)
            print(f"    ROW[{ri:02d}]: {' | '.join(row_info)}")

    # D面 / 16:00 を含むセルを強調表示
    print("\n  --- D面 または 16:00 を含むセル ---")
    all_cells = await page.query_selector_all("td, th")
    for i, cell in enumerate(all_cells):
        try:
            txt = (await cell.inner_text()).strip()
        except Exception:
            txt = ""
        cls     = await cell.get_attribute("class") or ""
        onclick = await cell.get_attribute("onclick") or ""
        id_     = await cell.get_attribute("id") or ""
        if "D面" in txt or "16:00" in txt or "16〜18" in txt or "16～18" in txt:
            print(f"  CELL[{i}] id={id_!r} class={cls!r} "
                  f"onclick={onclick[:80]!r} text={txt!r}")
            # 親行テキストも出力
            try:
                row_txt = await cell.evaluate(
                    "e => e.closest('tr') ? "
                    "Array.from(e.closest('tr').querySelectorAll('td,th'))"
                    ".map(c=>c.innerText.trim()).join(' | ') : ''"
                )
                print(f"         親行: {row_txt[:200]}")
            except Exception:
                pass


async def generate_report(form_data: dict, output_path: str):
    """reserve.pyに設定すべきセレクターのレポートを生成"""
    lines = [
        "=" * 60,
        "reserve.py 推奨セレクター設定レポート",
        "=" * 60,
        "",
    ]

    # ログインフィールド
    text_inputs = [i for i in form_data.get("login", {}).get("inputs", [])
                   if i["type"] in ("text", "")]
    pw_inputs   = [i for i in form_data.get("login", {}).get("inputs", [])
                   if i["type"] == "password"]
    submit_btns = form_data.get("login", {}).get("buttons", [])

    if text_inputs:
        inp = text_inputs[0]
        sel = f'input[name="{inp["name"]}"]' if inp["name"] else f'input[id="{inp["id"]}"]'
        lines.append(f"[利用者番号フィールド] → {sel}")
    if pw_inputs:
        inp = pw_inputs[0]
        sel = 'input[type="password"]'
        if inp["name"]:
            sel = f'input[name="{inp["name"]}"]'
        lines.append(f"[パスワードフィールド] → {sel}")
    if submit_btns:
        btn = submit_btns[0]
        if btn["value"]:
            sel = f'input[value="{btn["value"]}"]'
        elif btn["text"]:
            sel = f'button:text("{btn["text"]}")'
        else:
            sel = 'input[type="submit"]'
        lines.append(f"[ログインボタン]       → {sel}")

    lines.append("")

    # お気に入りリンク
    fav_links = [l for l in form_data.get("after_login", {}).get("links", [])
                 if "お気に入り" in l.get("text", "")]
    if fav_links:
        lnk = fav_links[0]
        if lnk["href"]:
            lines.append(f"[お気に入りリンク]     → a[href=\"{lnk['href']}\"]")
        else:
            lines.append(f'[お気に入りリンク]     → a:text("お気に入り")')
    else:
        lines.append("[お気に入りリンク]     → (未確認) a:text(\"お気に入り\")")

    lines.append("")

    # 日付セレクト
    date_selects = form_data.get("after_favorite", {}).get("selects", [])
    if date_selects:
        lines.append("[日付セレクト候補]")
        for sel in date_selects:
            lines.append(f"  name={sel['name']!r} id={sel['id']!r}")
            for opt in sel["options"][:5]:
                lines.append(f"    value={opt['value']!r} text={opt['text']!r}")
    else:
        lines.append("[日付セレクト]         → (未確認)")

    lines += ["", "=" * 60]

    report = "\n".join(lines)
    print(report)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    log(f"  [SAVED] {output_path}")


async def try_select_date(page) -> bool:
    """最初に見つかる日付 or 令和08年06月19日 を選択（解析用）"""
    selects = await page.query_selector_all("select")
    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            # 令和08年06月19日 または最初の日付を選ぶ
            if any(t in txt for t in PROBE_DATE_TEXTS) or v in ("20260619",):
                await sel_elem.select_option(value=v if v else txt)
                log(f"  [解析用] 日付選択: name={await sel_elem.get_attribute('name')!r} "
                    f"value={v!r} text={txt!r}")
                return True
    # 見つからなければ最初のSELECTの最初の非空optionを選択
    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if v and v not in ("", "0", "00"):
                await sel_elem.select_option(value=v)
                log(f"  [解析用] 最初の有効日付を選択: value={v!r} text={txt!r}")
                return True
    return False


async def analyze():
    form_data = {}
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
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

        # ── Step 1: ログインページ ───────────────────────────
        log("\n[Step 1] ログインページに移動...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await save_step(page, "01_login_page")
        login_data = await dump_inputs(page, "ログインページ")
        form_data["login"] = login_data

        # ── Step 2: ログイン実行 ─────────────────────────────
        log("\n[Step 2] ログイン実行...")

        # 利用者番号
        filled_id = False
        for sel in [
            'input[name="userid"]', 'input[name="userId"]',
            'input[name="user_id"]', 'input[name="loginId"]',
            'input[name="login_id"]', 'input[name="memberNo"]',
            'input[name="userno"]', 'input[name="riyoId"]',
            'input[id="userid"]', 'input[id="userId"]',
            'form input[type="text"]:first-of-type',
            'input[type="text"]:first-of-type',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.fill(USER_ID)
                    log(f"  [OK] 利用者番号入力: {sel}")
                    filled_id = True
                    break
            except PWTimeout:
                pass
        if not filled_id:
            log("  [WARNING] 利用者番号フィールドが見つかりません")

        # パスワード
        for sel in [
            'input[type="password"]', 'input[name="passwd"]',
            'input[name="password"]', 'input[name="pass"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.fill(PASSWORD)
                    log(f"  [OK] パスワード入力: {sel}")
                    break
            except PWTimeout:
                pass

        # サブミット
        for sel in [
            'input[value="ログイン"]', 'input[type="submit"]',
            'button[type="submit"]', 'button:has-text("ログイン")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=1500)
                if elem:
                    await elem.click()
                    log(f"  [OK] サブミット: {sel}")
                    break
            except PWTimeout:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "02_after_login")
        after_login_data = await dump_inputs(page, "ログイン後ページ")
        form_data["after_login"] = after_login_data
        log(f"  現在URL: {page.url}")

        # ── Step 3: お気に入りクリック ──────────────────────
        log("\n[Step 3] お気に入りクリック...")
        fav_clicked = False
        for sel in [
            'a:has-text("お気に入り")', 'input[value*="お気に入り"]',
            'button:has-text("お気に入り")',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=3000)
                if elem:
                    txt = (await elem.inner_text()).strip()
                    href = await elem.get_attribute("href") or ""
                    log(f"  [OK] お気に入り: {sel} text={txt!r} href={href!r}")
                    await elem.click()
                    fav_clicked = True
                    break
            except PWTimeout:
                pass

        if not fav_clicked:
            log("  [WARNING] お気に入りが見つかりません。テキスト走査...")
            elems = await page.query_selector_all("a, button, input")
            for elem in elems:
                try:
                    txt = (await elem.inner_text()).strip()
                except Exception:
                    txt = ""
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    href = await elem.get_attribute("href") or ""
                    log(f"  [OK] お気に入り（走査）: text={txt!r} href={href!r}")
                    await elem.click()
                    fav_clicked = True
                    break

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "03_after_favorite")
        fav_data = await dump_inputs(page, "お気に入り絞り込み画面")
        form_data["after_favorite"] = fav_data
        log(f"  現在URL: {page.url}")

        # ── Step 4: 日付選択・検索 ───────────────────────────
        log("\n[Step 4] 日付選択・検索...")
        date_ok = await try_select_date(page)
        if not date_ok:
            log("  [WARNING] 日付選択失敗。SELECTボックスの内容を上記ログで確認してください。")

        # 検索ボタン
        for sel in [
            'input[value="検索"]', 'button:has-text("検索")',
            'input[value*="検索"]', 'input[type="submit"]',
            'button[type="submit"]', 'input[value="空き照会"]',
        ]:
            try:
                elem = await page.wait_for_selector(sel, timeout=2000)
                if elem:
                    val = await elem.get_attribute("value") or ""
                    log(f"  [OK] 検索ボタン: {sel} value={val!r}")
                    await elem.click()
                    break
            except PWTimeout:
                pass

        await page.wait_for_load_state("networkidle", timeout=15000)
        await save_step(page, "04_search_results")
        log(f"  現在URL: {page.url}")

        # テーブル構造の詳細解析
        await dump_table_structure(page, "検索結果")

        # ── レポート生成 ─────────────────────────────────────
        report_path = f"{OUTPUT_DIR}/selectors_report.txt"
        await generate_report(form_data, report_path)

        await browser.close()

    print(f"\n\n{'='*60}")
    print(f"解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
    print(f"  ・*.html  : 各ステップのHTMLソース")
    print(f"  ・*.png   : 各ステップのスクリーンショット")
    print(f"  ・{report_path} : セレクター推奨設定")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(analyze())
