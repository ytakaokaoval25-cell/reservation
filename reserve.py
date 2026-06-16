#!/usr/bin/env python3
"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 準備
  pip install playwright
  playwright install chromium
  # Python 3.9+ の場合は zoneinfo が標準搭載。3.8以下は pip install pytzinfo
"""

import asyncio
import datetime
import sys
import os

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ─────────────────────────────────────────────────
# タイムゾーン（JST固定）
# ─────────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo
    JST = ZoneInfo("Asia/Tokyo")
except ImportError:
    import pytz
    JST = pytz.timezone("Asia/Tokyo")

def now_jst() -> datetime.datetime:
    return datetime.datetime.now(JST)

# ─────────────────────────────────────────────────
# 設定値
# ─────────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日",  "2026/06/19",
]

# 予約対象コート＆時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報設定（朝5:00:00.000 JST）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

NAV_TIMEOUT  = 30_000   # ページ遷移タイムアウト (ms)
ELEM_TIMEOUT = 10_000   # 要素待機タイムアウト (ms)

SS_DIR = "screenshots"  # スクリーンショット保存先

# ─────────────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────────────

def parse_args() -> dict:
    args = sys.argv[1:]
    return {
        "headless":      "--headful" not in args,
        "wait_for_open": "--now"     not in args,
    }


async def wait_until_open():
    """JST 朝5:00:00.000 ぴったりまでミリ秒単位で待機"""
    print("[時報待ち] JST 朝5:00:00.000 まで待機します...")
    while True:
        now    = now_jst()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0
        )
        diff = (target - now).total_seconds()

        if diff <= 0:
            print(f"[時報] 開始時刻到達: {now.strftime('%H:%M:%S.%f')[:-3]} JST")
            return

        if diff > 300:
            print(f"[時報待ち] あと {diff:.0f}秒 ({diff/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff > 10:
            await asyncio.sleep(1)
        elif diff > 0.1:
            await asyncio.sleep(0.05)
        else:
            # 最後の 100ms: 1ms ポーリング
            while now_jst() < target:
                await asyncio.sleep(0.001)
            print(f"[時報] {now_jst().strftime('%H:%M:%S.%f')[:-3]} JST — GO!")
            return


async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_click(
    page,
    selectors: list[str],
    label: str,
    timeout: int = ELEM_TIMEOUT,
) -> bool:
    """セレクターリストを順に試してクリック。成功したら True"""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=timeout)
            await loc.click()
            print(f"  [OK] {label}: {sel}")
            return True
        except Exception as e:
            print(f"  [SKIP] {label} ({sel}): {type(e).__name__}")
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


async def try_fill(
    page,
    selectors: list[str],
    value: str,
    label: str,
    timeout: int = ELEM_TIMEOUT,
) -> bool:
    """セレクターリストを順に試して値を入力。成功したら True"""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=timeout)
            await loc.fill(value)
            print(f"  [OK] {label}入力: {sel}")
            return True
        except Exception as e:
            print(f"  [SKIP] {label} ({sel}): {type(e).__name__}")
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


# ─────────────────────────────────────────────────
# 各ステップ
# ─────────────────────────────────────────────────

async def step_login(page):
    """Step1: ログイン"""
    print(f"\n[Step 1] ログインページへ移動... ({LOGIN_URL})")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")
    print(f"  タイトル: {await page.title()}  URL: {page.url}")

    # 利用者番号
    await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="memberNo"]',
        'input[name="id"]',
        '#userid',
        'input[type="text"]:nth-of-type(1)',
    ], USER_ID, "利用者番号")

    # パスワード
    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[name="pw"]',
    ], PASSWORD, "パスワード")

    # ログインボタン
    await try_click(page, [
        'input[value="ログイン"]',
        'input[value="LOGIN"]',
        'input[value="ログイン する"]',
        'button:has-text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
        'a:has-text("ログイン")',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  ログイン後URL: {page.url}")


async def step_favorite(page):
    """Step2: お気に入りリンクをクリック → 絞り込み画面"""
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:has-text("お気に入り")',
        'input[value="お気に入り"]',
        'button:has-text("お気に入り")',
        'input[value*="お気に入り"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
        '[onclick*="favorite"]',
        '[onclick*="okiniiri"]',
        'img[alt*="お気に入り"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全スキャン フォールバック
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            try:
                txt = await elem.inner_text()
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in (txt or "") or "お気に入り" in val:
                    await elem.click()
                    print(f"  [OK] お気に入り（フォールバック）: text={txt!r}")
                    clicked = True
                    break
            except Exception:
                pass

    if not clicked:
        raise RuntimeError("お気に入りリンクが見つかりません。analyze_site.pyで解析してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  お気に入り後URL: {page.url}")


async def step_select_date_and_search(page):
    """Step3: 日付プルダウンで令和08年06月19日を選択し、検索"""
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False

    # ── パターンA: 単一プルダウンにすべての日付が入っている ──────
    for sel_elem in await page.query_selector_all("select"):
        for opt in await sel_elem.query_selector_all("option"):
            v   = (await opt.get_attribute("value") or "").strip()
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                try:
                    if v:
                        await sel_elem.select_option(value=v)
                    else:
                        await sel_elem.select_option(label=txt)
                    print(f"  [OK] 日付選択: name={sel_name!r} value={v!r} text={txt!r}")
                    date_selected = True
                except Exception as e:
                    print(f"  [WARN] select_option失敗: {e}")
                break
        if date_selected:
            break

    # ── パターンB: 年・月・日が別々のプルダウン ──────────────────
    if not date_selected:
        print("  [試行] 年月日が別SELECTの可能性...")
        all_selects = await page.query_selector_all("select")
        year_hit = month_hit = day_hit = False

        year_patterns  = {"令和08", "令和8", "08", "8", "2026", "R08", "R8"}
        month_patterns = {"06", "6", "6月", "06月"}
        day_patterns   = {"19", "１９", "19日"}

        for sel_elem in all_selects:
            options = await sel_elem.query_selector_all("option")
            vals_txts = [(await o.get_attribute("value") or "").strip(),
                         (await o.inner_text()).strip()
                         for o in options]
            # select 内に年らしい値があれば年SELECTと判定
            option_data = [
                ((await o.get_attribute("value") or "").strip(), (await o.inner_text()).strip())
                for o in options
            ]
            for v, txt in option_data:
                if v in year_patterns or txt in year_patterns:
                    try:
                        await sel_elem.select_option(value=v)
                        print(f"  [OK] 年選択: {v!r}")
                        year_hit = True
                    except Exception:
                        pass
                    break
                if v in month_patterns or txt in month_patterns:
                    try:
                        await sel_elem.select_option(value=v)
                        print(f"  [OK] 月選択: {v!r}")
                        month_hit = True
                    except Exception:
                        pass
                    break
                if v in day_patterns or txt in day_patterns:
                    try:
                        await sel_elem.select_option(value=v)
                        print(f"  [OK] 日選択: {v!r}")
                        day_hit = True
                    except Exception:
                        pass
                    break
        date_selected = month_hit  # 月が取れれば検索へ

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.py を実行してセレクターを確認してください。"
        )

    await save_ss(page, "03b_date_selected")

    # 検索ボタン
    await try_click(page, [
        'input[value="検索"]',
        'input[value*="検索"]',
        'button:has-text("検索")',
        'a:has-text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  検索後URL: {page.url}")


async def step_select_slot(page):
    """Step4: D面 16:00〜18:00（赤丸）セルをクリック

    日本の施設予約システムでは一般的に
      ・行=施設名（A面/B面/C面/D面）、列=時間帯
      ・または行=時間帯、列=施設名
    のテーブル構造を取る。
    各セルには ○/×/△ の画像やリンクが入っており、
    「赤丸（予約可）」はクリック可能な <a> や <img> として存在する。
    """
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} 赤丸セル選択...")

    # テーブルHTML をデバッグ保存
    tables_html = await page.evaluate(
        "() => [...document.querySelectorAll('table')].map(t=>t.outerHTML).join('\\n=====\\n')"
    )
    os.makedirs(SS_DIR, exist_ok=True)
    with open(f"{SS_DIR}/04_tables.html", "w", encoding="utf-8") as f:
        f.write(tables_html)
    print(f"  [DEBUG] テーブルHTML → {SS_DIR}/04_tables.html")

    clicked = False
    tables  = await page.query_selector_all("table")

    # ── アプローチ①:
    #   行のどこかに D面 が含まれ、
    #   その行内でリンク・ボタン・画像がある列が 16:00 と対応する ─────────
    for table in tables:
        rows = await table.query_selector_all("tr")
        # ヘッダー行から "16:00〜18:00" が何列目か調べる
        time_col_idx = -1
        for row in rows[:4]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt:
                    time_col_idx = ci
                    print(f"  [INFO] '{TARGET_TIME_START}' = 列{ci}")
                    break
            if time_col_idx >= 0:
                break

        for row in rows:
            cells     = await row.query_selector_all("td, th")
            row_texts = [(await c.inner_text()).strip() for c in cells]

            if TARGET_FACILITY not in row_texts and not any(TARGET_FACILITY in t for t in row_texts):
                continue

            print(f"  [INFO] D面行発見: {row_texts}")

            # D面が見つかった行で対象セルを特定
            target_cell = None
            if time_col_idx >= 0 and time_col_idx < len(cells):
                target_cell = cells[time_col_idx]
            else:
                # 時間列インデックス不明 → 行内で "16" を含むセルを探す
                for ci, cell in enumerate(cells):
                    t = (await cell.inner_text()).strip()
                    if TARGET_TIME_START in t or ("16" in t and "18" in t):
                        target_cell = cell
                        break

            if target_cell is None:
                continue

            tc_txt = (await target_cell.inner_text()).strip()
            tc_cls = (await target_cell.get_attribute("class") or "")
            print(f"  [FOUND] 対象セル: text={tc_txt!r} class={tc_cls!r}")

            # セル内の<a>リンク、<input>、<img>（クリック可能要素）を探す
            link = await target_cell.query_selector("a")
            if link:
                href = await link.get_attribute("href") or ""
                alt  = await link.get_attribute("title") or ""
                print(f"  [CLICK] <a> href={href!r} title={alt!r}")
                await link.click()
                clicked = True
                break

            btn = await target_cell.query_selector("input[type=submit], button")
            if btn:
                await btn.click()
                clicked = True
                break

            img = await target_cell.query_selector("img")
            if img:
                img_src = await img.get_attribute("src") or ""
                print(f"  [CLICK] <img> src={img_src!r}")
                await img.click()
                clicked = True
                break

            # セル自体をクリック（onclickが付いている場合）
            onclick = (await target_cell.get_attribute("onclick") or "")
            if onclick or tc_txt not in ("×", "－", ""):
                print(f"  [CLICK] セル自体 onclick={onclick!r}")
                await target_cell.click()
                clicked = True
                break

        if clicked:
            break

    # ── アプローチ②: onclick / href にD面+16 が含まれる要素 ──────────────
    if not clicked:
        print("  [試行②] onclick/href スキャン...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if ("D面" in combined or "D%E9%9D%A2" in combined) and (
                "16" in combined or "1600" in combined
            ):
                print(f"  [CLICK②] onclick={onclick!r}  href={href!r}  text={txt!r}")
                await elem.click()
                clicked = True
                break

    # ── アプローチ③: 赤丸画像（src に red / maru / circle を含む）───────────
    if not clicked:
        print("  [試行③] 赤丸画像スキャン...")
        for img in await page.query_selector_all("img"):
            src = (await img.get_attribute("src") or "").lower()
            alt = (await img.get_attribute("alt") or "")
            if any(kw in src for kw in ["red", "maru", "circle", "marui", "aka"]) or alt in ("○", "●", "◎"):
                parent = await img.evaluate_handle("el => el.closest('a') || el.closest('td') || el")
                parent_elem = parent.as_element()
                if parent_elem:
                    p_txt = (await parent_elem.inner_text()).strip()
                    print(f"  [CLICK③] 赤丸img parent text={p_txt!r} src={src!r}")
                    await parent_elem.click()
                    clicked = True
                    break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。\n"
            f"  → {SS_DIR}/04_tables.html と {SS_DIR}/04_search_results.png を確認し\n"
            "    実際の selector を reserve.py に直書きしてください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  スロット選択後URL: {page.url}")


async def step_confirm1(page):
    """Step5: 確定①（料金確認画面へ進む）"""
    print("\n[Step 5] 確定①クリック...")
    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確定①"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value="予約する"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'button:has-text("確定")',
        'button:has-text("確認")',
        'button:has-text("次へ")',
        'a:has-text("確定")',
        'a:has-text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。スクリーンショットを確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  確定①後URL: {page.url}")


async def step_confirm2(page):
    """Step6: 確定②（最終確定）
    Tampermonkey で window.confirm が無効化されている前提。
    万一 dialog が発火した場合は自動承認するハンドラーも登録済み。
    """
    print("\n[Step 6] 確定②クリック...")

    # ページ内の window.confirm を再度上書き（フォールバック）
    await page.evaluate("() => { window.confirm = () => true; window.alert = () => {}; }")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確定②"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="登録"]',
        'input[value*="確定"]',
        'button:has-text("確定")',
        'button:has-text("予約確定")',
        'a:has-text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not clicked:
        raise RuntimeError("確定②ボタンが見つかりません。スクリーンショットを確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")

    body = await page.inner_text("body")
    if any(w in body for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。スクリーンショットを確認してください。")
    print(f"  最終URL: {page.url}")
    print(f"  本文（先頭200字）: {body[:200]}")


# ─────────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────────

async def main():
    opts = parse_args()

    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"  対象日: {TARGET_DATE_WAREKI}")
    print(f"  施設:   {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    now = now_jst()
    print(f"  現在時刻 (JST): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  モード: {'即時実行' if not opts['wait_for_open'] else 'JST朝5:00待ち'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

    if opts["wait_for_open"]:
        await wait_until_open()

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
            timezone_id="Asia/Tokyo",
        )

        # window.confirm / window.alert を全ページで無効化（Tampermonkey 前提のバックアップ）
        await context.add_init_script(
            "window.confirm = () => true; window.alert = () => {};"
        )

        page = await context.new_page()

        # dialog イベントハンドラ（念のため）
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        try:
            await step_login(page)
            await step_favorite(page)
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)
            print("\n✅ すべてのステップが完了しました。")
        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー発生: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
