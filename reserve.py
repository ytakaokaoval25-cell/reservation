"""
まんまるよやく2 自動予約スクリプト（完成版）
==================================================
■ 使い方
  python reserve.py              # 朝5:00:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 戦略
  5:00の前にログイン＆お気に入り画面まで移動して待機。
  5:00:00.000ぴったりに日付選択＋検索→セル選択→確定①→確定②を最速実行。

■ 準備
  pip install playwright
  playwright install chromium

■ 練習 → 本番の切り替え
  TARGET_DATE_WAREKI / TARGET_DATE_ALT_* を令和08年07月分に変更する。
"""

import asyncio
import datetime
import sys
import os
import re
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────────────────────
LOGIN_URL  = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID    = "12015873"
PASSWORD   = "0508"

# 予約対象日（練習: 令和08年06月19日）
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日",
    "令和０８年０６月１９日", "令和０８年６月１９日",
    "2026年06月19日", "2026/06/19", "2026-06-19",
]
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19",
    "260619", "060619", "0619",
]
# 年/月/日が分割SELECTの場合
TARGET_YEAR_TEXTS  = ["令和08", "令和8", "R08", "R8", "2026", "08", "8"]
TARGET_MONTH_TEXTS = ["06", "6", "６", "06月", "6月", "６月"]
TARGET_DAY_TEXTS   = ["19", "１９", "19日", "１９日"]

# 予約コート・時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報設定
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト（ms）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

SS_DIR = "screenshots"
# ──────────────────────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


# ──────────────────────────────────────────────────────────────
# 時報待ちロジック（ミリ秒単位）
# ──────────────────────────────────────────────────────────────
async def wait_until_open():
    """朝5:00:00.000 ぴったりまで段階的に待機する"""
    now = datetime.datetime.now()
    target = now.replace(
        hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
    )
    # 既に今日の5:00を過ぎていたら次の5:00は無いので即実行
    if (target - now).total_seconds() < 0:
        print(f"[時報] 既に開始時刻を過ぎています ({now.strftime('%H:%M:%S')})。即実行します。")
        return

    print(f"[時報待ち] {target.strftime('%Y-%m-%d %H:%M:%S')} まで待機します...")
    while True:
        now = datetime.datetime.now()
        diff_ms = (target - now).total_seconds() * 1000

        if diff_ms <= 0:
            print(f"[時報] 開始時刻到達: {datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
            break
        elif diff_ms > 300_000:  # 5分以上
            print(f"[時報待ち] あと {diff_ms/1000:.0f}秒 ({diff_ms/60000:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_ms > 10_000:  # 10秒〜5分
            await asyncio.sleep(1)
        elif diff_ms > 100:    # 100ms〜10秒
            await asyncio.sleep(0.05)
        else:                   # 100ms以内: 1msループ
            await asyncio.sleep(0.001)


# ──────────────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────────────
async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception as e:
        print(f"  [SS FAIL] {name}: {e}")


async def save_html(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    try:
        html = await page.content()
        with open(f"{SS_DIR}/{name}.html", "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass


async def try_click(page, selectors: list, label: str, timeout: int = 5000) -> bool:
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.click()
                print(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: 全セレクター不一致")
    return False


async def try_fill(page, selectors: list, value: str, label: str, timeout: int = 5000) -> bool:
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.fill(value)
                print(f"  [OK] {label}入力: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            print(f"  [SKIP] {label} ({sel}): {e}")
    print(f"  [FAIL] {label}: 全セレクター不一致")
    return False


# ──────────────────────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")
    await save_html(page, "01_login")

    # ── 利用者番号 ──
    filled = await try_fill(page, [
        # よくある name 属性
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="userno"]',
        'input[name="memberNo"]',
        'input[name="memberID"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        'input[name="uid"]',
        'input[name="usernm"]',
        'input[name="username"]',
        # よくある id 属性
        '#userid', '#user_id', '#userno', '#loginId',
        # type=text の最初の要素
        'input[type="text"]:nth-of-type(1)',
        'input:not([type="password"]):not([type="hidden"]):not([type="submit"]):first-of-type',
    ], USER_ID, "利用者番号")

    if not filled:
        # JS で全inputを探してfill
        await page.evaluate(f"""
            (function() {{
                var inputs = document.querySelectorAll('input[type="text"], input:not([type])');
                if (inputs.length > 0) inputs[0].value = '{USER_ID}';
            }})();
        """)
        print("  [FALLBACK] JS で利用者番号入力試行")

    # ── パスワード ──
    filled_pw = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[name="pw"]',
        '#passwd', '#password',
    ], PASSWORD, "パスワード")

    if not filled_pw:
        await page.evaluate(f"""
            (function() {{
                var inputs = document.querySelectorAll('input[type="password"]');
                if (inputs.length > 0) inputs[0].value = '{PASSWORD}';
            }})();
        """)
        print("  [FALLBACK] JS でパスワード入力試行")

    # ── ログインボタン ──
    clicked = await try_click(page, [
        'input[value="ログイン"]',
        'button:text("ログイン")',
        'input[value*="ログイン"]',
        'input[value="LOGIN"]',
        'button[type="submit"]',
        'input[type="submit"]',
        'input[name="submit"]',
        'a:text("ログイン")',
        'button:text("login")',
        'input[value="login"]',
    ], "ログインボタン")

    if not clicked:
        # Enterキーで送信
        await page.keyboard.press("Enter")
        print("  [FALLBACK] Enterキーでフォーム送信")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    await save_html(page, "02_after_login")

    url = page.url
    print(f"  現在URL: {url}")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if "エラー" in body or "error" in body.lower() or "パスワード" in body and "正しく" in body:
        print(f"  [WARNING] ログインエラーの可能性: {body[:200]}")


# ──────────────────────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面
# ──────────────────────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        # テキストベース
        'a:text("お気に入り")',
        'button:text("お気に入り")',
        'input[value="お気に入り"]',
        'input[value*="お気に入り"]',
        # 部分テキスト
        'a:text-is("お気に入り")',
        '*[onclick*="okiniri"]',
        '*[onclick*="okini"]',
        '*[onclick*="favorite"]',
        '*[onclick*="fav"]',
        # id/class
        '[id*="favorite"]', '[id*="okiniri"]', '[id*="okini"]',
        '[class*="favorite"]', '[class*="okiniri"]',
        # href
        'a[href*="favorite"]', 'a[href*="okiniri"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全走査フォールバック
        elems = await page.query_selector_all("a, button, input[type=button], input[type=submit], span, td")
        for elem in elems:
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（全走査）: text={txt!r}")
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_favorite_not_found")
        raise RuntimeError(
            "お気に入りリンクが見つかりません。\n"
            f"スクリーンショット: {SS_DIR}/ERROR_favorite_not_found.png\n"
            "analyze_site.pyを実行してページ構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    await save_html(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────────────
# 日付選択サブルーチン（SELECT要素を走査）
# ──────────────────────────────────────────────────────────────
async def _select_date_in_element(sel_elem, label="") -> bool:
    """単一のSELECT要素から対象日付を選択。成功したらTrueを返す"""
    options = await sel_elem.query_selector_all("option")
    for opt in options:
        v   = (await opt.get_attribute("value") or "").strip()
        txt = (await opt.inner_text()).strip()
        if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                or v in TARGET_DATE_ALT_VALUES):
            if v:
                await sel_elem.select_option(value=v)
            else:
                await sel_elem.select_option(label=txt)
            name = await sel_elem.get_attribute("name") or label
            print(f"  [OK] 日付選択: name={name!r} value={v!r} text={txt!r}")
            return True
    return False


async def _select_year_month_day(selects) -> bool:
    """年・月・日が別SELECTの場合の選択"""
    year_done = month_done = day_done = False
    for sel_elem in selects:
        opts = await sel_elem.query_selector_all("option")
        texts = [(await o.inner_text()).strip() for o in opts]
        vals  = [(await o.get_attribute("value") or "").strip() for o in opts]
        all_texts = texts + vals

        for yt in TARGET_YEAR_TEXTS:
            if yt in all_texts:
                idx = all_texts.index(yt)
                v = vals[idx] if idx < len(vals) else texts[idx]
                await sel_elem.select_option(value=v if v else None, label=texts[idx] if not v else None)
                print(f"  [OK] 年選択: {yt!r}")
                year_done = True
                break
        if year_done:
            continue

        for mt in TARGET_MONTH_TEXTS:
            if mt in all_texts:
                idx = all_texts.index(mt)
                v = vals[idx] if idx < len(vals) else texts[idx]
                await sel_elem.select_option(value=v if v else None, label=texts[idx] if not v else None)
                print(f"  [OK] 月選択: {mt!r}")
                month_done = True
                break
        if month_done:
            continue

        for dt in TARGET_DAY_TEXTS:
            if dt in all_texts:
                idx = all_texts.index(dt)
                v = vals[idx] if idx < len(vals) else texts[idx]
                await sel_elem.select_option(value=v if v else None, label=texts[idx] if not v else None)
                print(f"  [OK] 日選択: {dt!r}")
                day_done = True
                break

    return year_done or month_done or day_done


# ──────────────────────────────────────────────────────────────
# Step 3: 日付選択 + 検索（★ここが5:00:00に実行される★）
# ──────────────────────────────────────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False
    selects = await page.query_selector_all("select")

    # 方法①: 一体型SELECT（令和08年06月19日 が1つのoptionにある）
    for sel_elem in selects:
        if await _select_date_in_element(sel_elem):
            date_selected = True
            break

    # 方法②: 年・月・日が分割SELECT
    if not date_selected:
        print("  [試行] 年月日分割SELECTを試みます...")
        date_selected = await _select_year_month_day(selects)

    # 方法③: JS で直接value設定
    if not date_selected:
        print("  [試行] JSでSELECT valueを強制設定...")
        for val in TARGET_DATE_ALT_VALUES:
            result = await page.evaluate(f"""
                (function() {{
                    var sels = document.querySelectorAll('select');
                    for (var s of sels) {{
                        for (var o of s.options) {{
                            if (o.value === '{val}') {{
                                s.value = '{val}';
                                s.dispatchEvent(new Event('change'));
                                return '{val}';
                            }}
                        }}
                    }}
                    return null;
                }})();
            """)
            if result:
                print(f"  [OK] JS強制選択: value={result!r}")
                date_selected = True
                break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        await save_html(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。\n"
            "analyze_site.pyを実行してoption値を確認し、TARGET_DATE_ALT_VALUESを修正してください。"
        )

    # ── 検索ボタン ──
    await try_click(page, [
        'input[value="検索"]',
        'button:text("検索")',
        'input[value*="検索"]',
        'input[value="空き状況"]',
        'input[value*="空き"]',
        'button:text("空き状況")',
        'input[value="照会"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    await save_html(page, "04_search_results")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────────────
# Step 4: D面 16:00〜18:00 の赤丸セルをクリック
# ──────────────────────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")
    clicked = False

    # ── 方法①: ヘッダー行で列インデックス特定 → D面行のその列をクリック ──
    tables = await page.query_selector_all("table")
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1
        d_row = None

        # 先頭3行でヘッダーを探す
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                # 16:00 と 18:00 の両方が同一セルにある場合
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_idx = ci
                    print(f"  [INFO] 時間ヘッダー列={ci}: {txt!r}")
                    break
                # 16:00のみ
                if txt.startswith(TARGET_TIME_START):
                    time_col_idx = ci
                    print(f"  [INFO] 時間ヘッダー列={ci}: {txt!r}")
                    break
            if time_col_idx >= 0:
                break

        # D面の行を探す
        for row in rows:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_FACILITY in txt:
                    d_row = (row, cells)
                    print(f"  [INFO] D面行発見: 列{ci}={txt!r}")
                    break
            if d_row:
                break

        if time_col_idx >= 0 and d_row:
            _, cells = d_row
            if time_col_idx < len(cells):
                target_cell = cells[time_col_idx]
                tc_txt = (await target_cell.inner_text()).strip()
                tc_cls = await target_cell.get_attribute("class") or ""
                print(f"  [FOUND] D面×列{time_col_idx}: text={tc_txt!r} class={tc_cls!r}")
                await target_cell.click()
                clicked = True
                break

    # ── 方法②: D面行のセルを全走査してクリック可能な要素を探す ──
    if not clicked:
        print("  [試行] D面行の全セル走査...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                texts = [(await c.inner_text()).strip() for c in cells]
                if TARGET_FACILITY not in texts:
                    continue
                # D面行: 各セルで16:00を含むか、リンク/onclick持ちを探す
                for i, cell in enumerate(cells):
                    txt = texts[i]
                    onclick = await cell.get_attribute("onclick") or ""
                    href    = (await cell.query_selector("a") or  # noqa
                               await cell.query_selector_all("a"))
                    cls = await cell.get_attribute("class") or ""
                    # 16:00を含む or onclickがある空き時間セルっぽいもの
                    if (TARGET_TIME_START in txt or "16" in txt
                            or onclick
                            or "16" in onclick):
                        print(f"  [FOUND] D面行セル[{i}]: text={txt!r} onclick={onclick[:60]!r}")
                        await cell.click()
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── 方法③: onclick / href 全走査でD面+16の組み合わせ ──
    if not clicked:
        print("  [試行] onclick全走査でD面+16:00を探す...")
        all_clickable = await page.query_selector_all("a, td, input[type=button], button")
        for elem in all_clickable:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            # D面かつ16の文字を含む
            if "D" in combined and "16" in combined:
                print(f"  [FOUND] onclick={onclick[:80]!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    # ── 方法④: ページ全体からXPathで赤丸（○）かつD面に近いセルを探す ──
    if not clicked:
        print("  [試行] XPathで赤丸セルを探す...")
        try:
            # 赤丸 = ○ or ◎ の文字を持つtdで16:00を含む
            cell = await page.query_selector(
                "xpath=//td[contains(text(),'16') and (contains(text(),'○') "
                "or contains(text(),'◎') or contains(text(),'●'))]"
            )
            if cell:
                tc_txt = (await cell.inner_text()).strip()
                print(f"  [FOUND] XPath赤丸セル: {tc_txt!r}")
                await cell.click()
                clicked = True
        except Exception as e:
            print(f"  [SKIP] XPath試行: {e}")

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        await save_html(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。\n"
            f"スクリーンショット: {SS_DIR}/ERROR_slot_not_found.png\n"
            "04_search_results.html でテーブル構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    await save_html(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ──────────────────────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①クリック...")
    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="次へ"]',
        'input[value="確認"]',
        'input[value="予約する"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'input[value*="次"]',
        'button:text("確定")',
        'button:text("次へ")',
        'button:text("確認")',
        'a:text("確定")',
        'a:text("次へ")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        await save_ss(page, "ERROR_confirm1")
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1_done")
    await save_html(page, "06_confirm1_done")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# ──────────────────────────────────────────────────────────────
async def step_confirm2(page):
    print("\n[Step 6] 確定②クリック...")

    # Tampermonkeyでconfirm無効化済みの前提だが、念のためPlaywrightでも自動承認
    page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))

    # 追加: JS でwindow.confirmを無効化（二重保険）
    await page.evaluate("window.confirm = function() { return true; };")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="予約する"]',
        'input[value*="確定"]',
        'input[value*="予約"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'button:text("最終確定")',
        'a:text("確定")',
        'a:text("予約確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        await save_ss(page, "ERROR_confirm2")
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    await save_html(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了確認
    body_text = await page.inner_text("body")
    keywords_ok  = ["予約完了", "受付完了", "受付番号", "予約番号", "申込完了", "完了しました"]
    keywords_err = ["エラー", "失敗", "取消", "既に予約"]
    if any(w in body_text for w in keywords_ok):
        print("\n✅ 予約完了を確認しました！")
    elif any(w in body_text for w in keywords_err):
        print("\n⚠️  エラーメッセージを検出しました。スクリーンショットを確認してください。")
    else:
        print("\n⚠️  完了/エラーメッセージが見つかりません。スクリーンショットを確認してください。")
    print(f"  本文（先頭300字）: {body_text[:300]}")


# ──────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 65)
    print("  まんまるよやく2 自動予約スクリプト")
    print(f"  対象日  : {TARGET_DATE_WAREKI}")
    print(f"  施設    : {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"  モード  : {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00:00)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 65)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
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
        # window.confirm を全ページで自動承認
        await context.add_init_script("window.confirm = function() { return true; };")

        page = await context.new_page()

        try:
            # ── フェーズ1: 5:00前にログイン＆お気に入り画面まで移動 ──
            await step_login(page)
            await step_favorite(page)

            # ── 時報待ち（お気に入り画面で待機）──
            if opts["wait_for_open"]:
                await wait_until_open()

            # ── フェーズ2: 5:00:00に検索〜確定 ──
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)

            print("\n✅ すべてのステップが完了しました。")
        except Exception as e:
            await save_ss(page, "FATAL_ERROR")
            print(f"\n❌ エラー発生: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
