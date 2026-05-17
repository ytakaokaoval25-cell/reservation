"""
サイト解析スクリプト: まんまるよやく
ログインから予約確定までの各ページのHTML構造を解析する
"""
import asyncio
import json
from playwright.async_api import async_playwright

LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID = "12015873"
PASSWORD = "0508"


async def dump_page_structure(page, label: str):
    """ページのフォーム・入力要素・ボタンを全て出力"""
    print(f"\n{'='*60}")
    print(f"[{label}]")
    print(f"URL: {page.url}")
    print(f"Title: {await page.title()}")
    print("="*60)

    # フォーム
    forms = await page.evaluate("""() => {
        return Array.from(document.forms).map(f => ({
            id: f.id,
            name: f.name,
            action: f.action,
            method: f.method,
        }));
    }""")
    print(f"\n[FORMS] count={len(forms)}")
    for f in forms:
        print(f"  {json.dumps(f, ensure_ascii=False)}")

    # input要素
    inputs = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('input')).map(el => ({
            id: el.id,
            name: el.name,
            type: el.type,
            value: el.value,
            placeholder: el.placeholder,
            className: el.className,
        }));
    }""")
    print(f"\n[INPUTS] count={len(inputs)}")
    for inp in inputs:
        print(f"  {json.dumps(inp, ensure_ascii=False)}")

    # select要素
    selects = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('select')).map(el => ({
            id: el.id,
            name: el.name,
            className: el.className,
            options: Array.from(el.options).map(o => ({value: o.value, text: o.text})),
        }));
    }""")
    print(f"\n[SELECTS] count={len(selects)}")
    for sel in selects:
        print(f"  id={sel['id']} name={sel['name']} class={sel['className']}")
        for opt in sel['options']:
            print(f"    option value={opt['value']!r} text={opt['text']!r}")

    # ボタン・submit要素
    buttons = await page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button, input[type=submit], input[type=button], a[onclick]'));
        return btns.map(el => ({
            tag: el.tagName,
            id: el.id,
            name: el.name || '',
            type: el.type || '',
            value: el.value || '',
            text: el.innerText || el.textContent || '',
            href: el.href || '',
            onclick: el.getAttribute('onclick') || '',
            className: el.className,
        }));
    }""")
    print(f"\n[BUTTONS/SUBMITS] count={len(buttons)}")
    for btn in buttons:
        print(f"  {json.dumps(btn, ensure_ascii=False)}")

    # テーブル（検索結果グリッド用）
    tables = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('table')).map((t, i) => ({
            index: i,
            id: t.id,
            className: t.className,
            rows: t.rows.length,
            cols: t.rows[0] ? t.rows[0].cells.length : 0,
        }));
    }""")
    print(f"\n[TABLES] count={len(tables)}")
    for tbl in tables:
        print(f"  {json.dumps(tbl, ensure_ascii=False)}")

    # リンク（お気に入りなど）
    links = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a')).map(a => ({
            text: a.innerText.trim(),
            href: a.href,
            onclick: a.getAttribute('onclick') || '',
            id: a.id,
            className: a.className,
        })).filter(a => a.text || a.onclick);
    }""")
    print(f"\n[LINKS] count={len(links)}")
    for lnk in links:
        print(f"  {json.dumps(lnk, ensure_ascii=False)}")


async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox"],
            executable_path="/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
        )
        context = await browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            ignore_https_errors=True,
        )
        page = await context.new_page()

        # ── Step 1: ログインページ ──
        print("\n>>> Step 1: ログインページへアクセス")
        await page.goto(LOGIN_URL, wait_until="networkidle")
        await dump_page_structure(page, "STEP1: ログインページ")

        # HTMLも保存
        html = await page.content()
        with open("/home/user/reservation/step1_login.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("\n[HTML saved] step1_login.html")

        # ── Step 2: ログイン実行 ──
        print("\n>>> Step 2: ログイン実行")
        # IDフィールドを探す
        id_field = await page.query_selector('input[name*="id"], input[name*="ID"], input[id*="id"], input[type="text"]')
        pw_field = await page.query_selector('input[name*="pass"], input[name*="pw"], input[type="password"]')

        if id_field:
            await id_field.fill(USER_ID)
            print(f"  ID入力完了: {await id_field.get_attribute('name') or await id_field.get_attribute('id')}")
        else:
            print("  [ERROR] IDフィールドが見つかりません")

        if pw_field:
            await pw_field.fill(PASSWORD)
            print(f"  PW入力完了: {await pw_field.get_attribute('name') or await pw_field.get_attribute('id')}")
        else:
            print("  [ERROR] パスワードフィールドが見つかりません")

        submit = await page.query_selector('input[type="submit"], button[type="submit"], button')
        if submit:
            await submit.click()
            print(f"  ログインボタンクリック: {await submit.get_attribute('value') or await submit.inner_text()}")
        else:
            print("  [ERROR] ログインボタンが見つかりません")

        await page.wait_for_load_state("networkidle")
        await dump_page_structure(page, "STEP2: ログイン後トップ")

        html = await page.content()
        with open("/home/user/reservation/step2_after_login.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("\n[HTML saved] step2_after_login.html")

        # ── Step 3: お気に入りクリック ──
        print("\n>>> Step 3: お気に入りリンク探索")
        fav_link = await page.query_selector('a:has-text("お気に入り"), [onclick*="fav"], [href*="fav"]')
        if fav_link:
            await fav_link.click()
            await page.wait_for_load_state("networkidle")
            print("  お気に入りクリック完了")
        else:
            print("  [WARN] お気に入りリンクが見つかりません - 全リンクを確認してください")

        await dump_page_structure(page, "STEP3: お気に入り後（絞り込み画面）")

        html = await page.content()
        with open("/home/user/reservation/step3_search.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("\n[HTML saved] step3_search.html")

        await browser.close()
        print("\n\n>>> 解析完了")


if __name__ == "__main__":
    asyncio.run(analyze())
