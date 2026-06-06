#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
まんまるよやく2 サイト構造解析スクリプト

実行すると各ステップのHTML・スクリーンショットを analysis_output/ に保存し、
コンソールにフォーム要素・リンク・テーブル構造を詳細出力します。

reserve.py のセレクターを確認・修正する際に使用してください。

■ 使い方
  python analyze_site.py          # ヘッドレス（推奨：最初の解析）
  python analyze_site.py --headful  # ブラウザ表示あり
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"
OUTPUT_DIR = "analysis_output"


def parse_args():
    return {"headless": "--headful" not in sys.argv[1:]}


async def save_step(page, step_name: str):
    """スクリーンショット + HTML を保存"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=f"{OUTPUT_DIR}/{step_name}.png", full_page=True)
    html = await page.content()
    with open(f"{OUTPUT_DIR}/{step_name}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVED] {step_name}.png / .html")


async def dump_forms(page, label: str):
    """ページ内の全フォーム要素をコンソールに出力"""
    print(f"\n{'='*60}")
    print(f"  {label} — フォーム要素詳細")
    print(f"{'='*60}")

    # FORM
    forms = await page.query_selector_all("form")
    print(f"\n■ FORMタグ ({len(forms)}個)")
    for i, form in enumerate(forms):
        action = await form.get_attribute("action") or ""
        method = await form.get_attribute("method") or ""
        name   = await form.get_attribute("name") or ""
        id_    = await form.get_attribute("id") or ""
        print(f"  FORM[{i}] action={action!r} method={method!r} name={name!r} id={id_!r}")

    # INPUT
    inputs = await page.query_selector_all("input")
    print(f"\n■ INPUTタグ ({len(inputs)}個)")
    for inp in inputs:
        t    = await inp.get_attribute("type") or "text"
        name = await inp.get_attribute("name") or ""
        id_  = await inp.get_attribute("id") or ""
        cls  = await inp.get_attribute("class") or ""
        val  = await inp.get_attribute("value") or ""
        ph   = await inp.get_attribute("placeholder") or ""
        vis  = await inp.is_visible()
        print(f"  INPUT type={t:<10} name={name!r:<25} id={id_!r:<20} "
              f"value={val!r:<15} placeholder={ph!r:<15} visible={vis}")

    # SELECT
    selects = await page.query_selector_all("select")
    print(f"\n■ SELECTタグ ({len(selects)}個)")
    for sel in selects:
        name = await sel.get_attribute("name") or ""
        id_  = await sel.get_attribute("id") or ""
        cls  = await sel.get_attribute("class") or ""
        print(f"  SELECT name={name!r} id={id_!r} class={cls!r}")
        options = await sel.query_selector_all("option")
        for opt in options[:30]:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            print(f"    OPTION value={v!r:<20}  text={txt!r}")
        if len(options) > 30:
            print(f"    ... 他 {len(options)-30} 件")

    # BUTTON / SUBMIT
    buttons = await page.query_selector_all("button, input[type=submit], input[type=button]")
    print(f"\n■ ボタン ({len(buttons)}個)")
    for btn in buttons:
        t    = await btn.get_attribute("type") or ""
        name = await btn.get_attribute("name") or ""
        id_  = await btn.get_attribute("id") or ""
        val  = await btn.get_attribute("value") or ""
        try:
            txt = (await btn.inner_text()).strip()
        except Exception:
            txt = val
        print(f"  BUTTON type={t:<8} name={name!r:<20} id={id_!r:<20} value={val!r:<15} text={txt!r}")

    # LINK
    links = await page.query_selector_all("a")
    print(f"\n■ リンク ({len(links)}個)")
    for link in links:
        href    = await link.get_attribute("href") or ""
        onclick = await link.get_attribute("onclick") or ""
        try:
            txt = (await link.inner_text()).strip()
        except Exception:
            txt = ""
        if txt or onclick:
            print(f"  A href={href!r:<40} onclick={onclick!r:<30} text={txt!r}")


async def dump_tables(page, label: str, max_rows: int = 10):
    """ページ内の全テーブル構造をコンソールに出力"""
    print(f"\n{'='*60}")
    print(f"  {label} — テーブル構造")
    print(f"{'='*60}")

    tables = await page.query_selector_all("table")
    print(f"テーブル数: {len(tables)}")

    for ti, tbl in enumerate(tables):
        rows = await tbl.query_selector_all("tr")
        cls  = await tbl.get_attribute("class") or ""
        id_  = await tbl.get_attribute("id") or ""
        print(f"\n  TABLE[{ti}] id={id_!r} class={cls!r} 行数={len(rows)}")

        for ri, row in enumerate(rows[:max_rows]):
            cells = await row.query_selector_all("td, th")
            row_info = []
            for cell in cells:
                txt     = (await cell.inner_text()).strip().replace("\n", " ")
                cls_c   = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                tag     = await cell.evaluate("e => e.tagName")
                has_a   = bool(await cell.query_selector("a"))
                has_img = bool(await cell.query_selector("img"))
                info    = f"{txt[:20]}(cls={cls_c[:12]},a={has_a},img={has_img})"
                if onclick:
                    info += f"[onclick={onclick[:20]}]"
                row_info.append(f"<{tag}>{info}")
            print(f"    ROW[{ri}]: {' | '.join(row_info[:8])}")

        if len(rows) > max_rows:
            print(f"    ... 他 {len(rows)-max_rows} 行")


async def fill_best_effort(page, candidates: list, value: str, label: str):
    """セレクター候補を順番に試してfill"""
    for sel in candidates:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if elem:
                await elem.fill(value)
                print(f"  ✓ {label}: {sel}")
                return sel
        except Exception:
            pass
    print(f"  ✗ {label}: 見つからず ({candidates})")
    return None


async def click_best_effort(page, candidates: list, label: str):
    """セレクター候補を順番に試してclick"""
    for sel in candidates:
        try:
            elem = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if elem:
                await elem.click()
                print(f"  ✓ {label}: {sel}")
                return sel
        except Exception:
            pass
    print(f"  ✗ {label}: 見つからず ({candidates})")
    return None


async def analyze():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 サイト構造解析")
    print(f"出力先: {OUTPUT_DIR}/")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        await context.add_init_script(
            "window.confirm = () => true; window.alert = () => {};"
        )
        page = await context.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        try:
            # ─────────────────────────────────────
            # Step 1: ログインページ解析
            # ─────────────────────────────────────
            print("\n[Step 1] ログインページ...")
            await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
            await save_step(page, "01_login_page")
            await dump_forms(page, "ログインページ")

            # ─────────────────────────────────────
            # Step 2: ログイン実行
            # ─────────────────────────────────────
            print("\n[Step 2] ログイン実行...")
            used_uid_sel = await fill_best_effort(page, [
                'input[name="userid"]',
                'input[name="user_id"]',
                'input[name="memberNo"]',
                'input[name="userno"]',
                'input[name="loginId"]',
                'input[name="loginUserId"]',
                'input[name="loginCd"]',
                'input[name="id"]',
                'input[id="userid"]',
                'input[type="text"]:visible',
            ], USER_ID, "利用者番号")

            used_pw_sel = await fill_best_effort(page, [
                'input[name="passwd"]',
                'input[name="password"]',
                'input[name="pass"]',
                'input[name="loginPassword"]',
                'input[type="password"]',
            ], PASSWORD, "パスワード")

            used_submit_sel = await click_best_effort(page, [
                'input[value="ログイン"]',
                'button:text("ログイン")',
                'input[type="submit"]',
                'button[type="submit"]',
                'input[name="submit"]',
            ], "ログインボタン")

            await page.wait_for_load_state("networkidle", timeout=20000)
            await save_step(page, "02_after_login")
            print(f"  URL: {page.url}")

            print("\n【確定セレクター（reserve.py に反映してください）】")
            print(f"  利用者番号: {used_uid_sel!r}")
            print(f"  パスワード:  {used_pw_sel!r}")
            print(f"  ログインボタン: {used_submit_sel!r}")

            await dump_forms(page, "ログイン後メニューページ")

            # ─────────────────────────────────────
            # Step 3: お気に入りクリック
            # ─────────────────────────────────────
            print("\n[Step 3] お気に入りをクリック...")
            fav_sel = await click_best_effort(page, [
                'a:text("お気に入り")',
                'input[value="お気に入り"]',
                'button:text("お気に入り")',
            ], "お気に入り")

            if not fav_sel:
                # フォールバック: テキスト全探索
                for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
                    try:
                        txt = (await elem.inner_text()).strip()
                        val = (await elem.get_attribute("value") or "").strip()
                        if "お気に入り" in txt or "お気に入り" in val:
                            tag  = await elem.evaluate("e => e.tagName")
                            name = await elem.get_attribute("name") or ""
                            id_  = await elem.get_attribute("id") or ""
                            href = await elem.get_attribute("href") or ""
                            print(f"  ✓ お気に入り（フォールバック）: <{tag}> name={name!r} id={id_!r} href={href!r} text={txt!r}")
                            await elem.click()
                            fav_sel = f"{tag}[text={txt!r}]"
                            break
                    except Exception:
                        pass

            print(f"  お気に入りセレクター: {fav_sel!r}")
            await page.wait_for_load_state("networkidle", timeout=20000)
            await save_step(page, "03_favorite_filter")
            print(f"  URL: {page.url}")

            await dump_forms(page, "お気に入り絞り込み画面")

            # ─────────────────────────────────────
            # Step 4: 日付プルダウン全詳細表示
            # ─────────────────────────────────────
            print("\n[Step 4] 日付プルダウン詳細解析...")
            date_selects = await page.query_selector_all("select")
            print(f"SELECT要素数: {len(date_selects)}")
            for sel in date_selects:
                name = await sel.get_attribute("name") or ""
                id_  = await sel.get_attribute("id") or ""
                opts_elems = await sel.query_selector_all("option")
                print(f"\n  SELECT name={name!r} id={id_!r} — {len(opts_elems)}件")
                for opt in opts_elems:
                    v   = await opt.get_attribute("value") or ""
                    txt = (await opt.inner_text()).strip()
                    # 対象日に近いものをマーク
                    marker = " ★★★" if ("06月19日" in txt or "0619" in v or "19" in v) else ""
                    print(f"    value={v!r:<22} text={txt!r}{marker}")

            # ─────────────────────────────────────
            # Step 5: 令和08年06月19日を選択して検索
            # ─────────────────────────────────────
            print("\n[Step 5] 令和08年06月19日を選択して検索...")
            target_texts  = [
                "令和08年06月19日", "令和8年6月19日", "令和08年6月19日",
                "令和8年06月19日", "2026年06月19日", "2026/06/19",
            ]
            target_values = ["20260619", "2026-06-19", "260619"]

            date_selected = False
            for sel_elem in await page.query_selector_all("select"):
                for opt in await sel_elem.query_selector_all("option"):
                    v   = (await opt.get_attribute("value") or "").strip()
                    txt = (await opt.inner_text()).strip()
                    if any(t in txt for t in target_texts) or v in target_values:
                        name = await sel_elem.get_attribute("name") or ""
                        await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                        print(f"  ✓ 日付選択: name={name!r} value={v!r} text={txt!r}")
                        date_selected = True
                        break
                if date_selected:
                    break

            if not date_selected:
                print("  ✗ 単一SELECT で見つからず → 分割SELECT を試みる")
                # 年
                for sel_elem in await page.query_selector_all("select"):
                    for opt in await sel_elem.query_selector_all("option"):
                        v   = (await opt.get_attribute("value") or "").strip()
                        txt = (await opt.inner_text()).strip()
                        if any(p in txt or p == v for p in ["2026", "令和8", "令和08", "R08", "R8", "8"]):
                            name = await sel_elem.get_attribute("name") or ""
                            await sel_elem.select_option(value=v)
                            print(f"  ✓ 年: name={name!r} value={v!r} text={txt!r}")
                            break
                # 月
                for sel_elem in await page.query_selector_all("select"):
                    for opt in await sel_elem.query_selector_all("option"):
                        v   = (await opt.get_attribute("value") or "").strip()
                        txt = (await opt.inner_text()).strip()
                        if v in ["6", "06"] or txt in ["6", "06", "6月", "06月"]:
                            name = await sel_elem.get_attribute("name") or ""
                            await sel_elem.select_option(value=v)
                            print(f"  ✓ 月: name={name!r} value={v!r} text={txt!r}")
                            date_selected = True
                            break
                # 日
                for sel_elem in await page.query_selector_all("select"):
                    for opt in await sel_elem.query_selector_all("option"):
                        v   = (await opt.get_attribute("value") or "").strip()
                        txt = (await opt.inner_text()).strip()
                        if v == "19" or txt in ["19", "１９", "19日"]:
                            name = await sel_elem.get_attribute("name") or ""
                            await sel_elem.select_option(value=v)
                            print(f"  ✓ 日: name={name!r} value={v!r} text={txt!r}")
                            break

            # 検索ボタン
            await click_best_effort(page, [
                'input[value="検索"]',
                'button:text("検索")',
                'input[type="submit"]',
                'button[type="submit"]',
            ], "検索ボタン")

            await page.wait_for_load_state("networkidle", timeout=30000)
            await save_step(page, "04_search_results")
            print(f"  URL: {page.url}")

            # ─────────────────────────────────────
            # Step 6: 検索結果テーブル解析
            # ─────────────────────────────────────
            print("\n[Step 6] 検索結果テーブル詳細解析...")
            await dump_tables(page, "検索結果ページ", max_rows=20)

            print("\n■ D面 / 16:00 / 18:00 を含むセル詳細:")
            cells = await page.query_selector_all("td, th")
            for i, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if "D面" in txt or "16:00" in txt or "18:00" in txt:
                    id_     = await cell.get_attribute("id") or ""
                    cls     = await cell.get_attribute("class") or ""
                    onclick = await cell.get_attribute("onclick") or ""
                    tag     = await cell.evaluate("e => e.tagName")
                    has_a   = bool(await cell.query_selector("a"))
                    link_href = ""
                    if has_a:
                        a_elem = await cell.query_selector("a")
                        link_href = await a_elem.get_attribute("href") or ""
                    print(f"  CELL[{i}] <{tag}> id={id_!r} class={cls!r} "
                          f"onclick={onclick!r} has_a={has_a} href={link_href!r} text={txt!r}")

            print(f"\n\n解析完了。{OUTPUT_DIR}/ フォルダを確認してください。")
            print("スクリーンショット: 01〜04_search_results.png")

        except Exception as e:
            print(f"\n[ERROR] {e}")
            try:
                await save_step(page, "ERROR")
            except Exception:
                pass
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(analyze())
