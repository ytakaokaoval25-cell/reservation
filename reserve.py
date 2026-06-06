#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

■ 実行フロー（重要）
  ① ブラウザ起動 → ログイン → お気に入り絞り込み画面まで移動  ← 4:55頃に完了
  ② 5:00:00.000 をミリ秒単位で待機
  ③ 日付プルダウン選択 → 検索 → D面16:00クリック → 確定①→ 確定②  ← 最速実行
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────── 設定 ────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# ── 予約対象日 ──
TARGET_DATE_WAREKI = "令和08年06月19日"
# 単一SELECTに表示されるテキスト候補（表記ゆれを網羅）
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日",
    "令和08年6月19日",  "令和8年06月19日",
    "令和０８年０６月１９日",
    "2026年06月19日",   "2026/06/19",
]
# 単一SELECTのvalue候補
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]

# 分割型プルダウン（年・月・日が別々のSELECT）の候補
# ※ 令和08年 = 2026年
YEAR_CANDIDATES  = ["2026", "令和8", "令和08", "R08", "R8", "8", "08",
                    "令和8年", "令和08年", "2026年"]
MONTH_CANDIDATES = ["6", "06", "6月", "06月", "６", "０６"]
DAY_CANDIDATES   = ["19", "１９", "19日"]

# ── 予約対象コート・時間 ──
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# ── 時報設定（朝5:00:00.000 に検索スタート）──
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# ── タイムアウト（ms）──
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# ── デバッグ用スクリーンショット保存先 ──
SS_DIR = "screenshots"
# ──────────────────────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


async def wait_until_open():
    """朝5:00:00.000 ぴったりまでミリ秒単位で待機するループ"""
    print(f"[時報待ち] {OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d} まで待機します...")
    while True:
        now = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0
        )
        diff = (target - now).total_seconds()

        if diff <= 0:
            print(f"[時報] 開始: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
            return
        elif diff > 300:   # 5分以上: 30秒間隔で表示
            print(f"[時報待ち] 残り {diff:.0f}秒 ({diff/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff > 10:    # 10秒〜5分: 1秒間隔
            await asyncio.sleep(1)
        elif diff > 0.1:   # 100ms〜10秒: 50ms間隔
            await asyncio.sleep(0.05)
        else:              # 100ms以内: 1ms間隔（フライング防止）
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    """デバッグ用スクリーンショット保存"""
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception as e:
        print(f"  [SS失敗] {e}")


async def try_click(page, selectors: list, label: str, timeout: int = 5000) -> bool:
    """複数セレクターを順番に試してクリック"""
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.click()
                print(f"  [OK] {label}: {sel}")
                return True
        except Exception:
            pass
    print(f"  [FAIL] {label}: セレクター一致なし")
    return False


async def try_fill(page, selectors: list, value: str, label: str, timeout: int = 5000) -> bool:
    """複数セレクターを順番に試して入力"""
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.fill(value)
                print(f"  [OK] {label}: {sel}")
                return True
        except Exception:
            pass
    print(f"  [FAIL] {label}: セレクター一致なし")
    return False


# ═══════════════════════════════════════════════════════════════
# Step 1: ログイン
# ═══════════════════════════════════════════════════════════════
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await page.wait_for_load_state("networkidle", timeout=15000)
    await save_ss(page, "01_login")

    # ── 利用者番号 ──
    # MNet/Seagull系では "userid" が最頻値。他の候補も順次試みる。
    filled = await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="loginUserId"]',
        'input[name="loginCd"]',
        'input[name="id"]',
        'input[id="userid"]',
        'input[placeholder*="利用者"]',
        'input[placeholder*="番号"]',
    ], USER_ID, "利用者番号")

    if not filled:
        # 最終手段: visibleなtext入力の最初のもの
        for inp in await page.query_selector_all('input[type="text"], input:not([type])'):
            try:
                if await inp.is_visible():
                    await inp.fill(USER_ID)
                    print("  [OK] 利用者番号（最初のtextフィールド）")
                    break
            except Exception:
                pass

    # ── パスワード ──
    await try_fill(page, [
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[name="loginPassword"]',
        'input[type="password"]',
    ], PASSWORD, "パスワード")

    # ── ログインボタン ──
    await try_click(page, [
        'input[value="ログイン"]',
        'input[value=" ログイン "]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  URL: {page.url}")


# ═══════════════════════════════════════════════════════════════
# Step 2: お気に入り → 絞り込み画面へ移動
# ═══════════════════════════════════════════════════════════════
async def step_navigate_to_favorite(page):
    print("\n[Step 2] お気に入りをクリック → 絞り込み画面へ...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        'a:text-matches("お気に入り")',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[href*="fav"]',
        '[href*="okini"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全探索フォールバック
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            try:
                txt = (await elem.inner_text()).strip()
                val = (await elem.get_attribute("value") or "").strip()
                if "お気に入り" in txt or "お気に入り" in val:
                    await elem.click()
                    print(f"  [OK] お気に入り（テキスト全探索）: {txt!r}")
                    clicked = True
                    break
            except Exception:
                pass

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行してページ構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  URL: {page.url}")


# ═══════════════════════════════════════════════════════════════
# Step 3: 日付選択 & 検索（5:00:00 到達後に最速実行）
# ═══════════════════════════════════════════════════════════════
async def step_select_date_and_search(page):
    """令和08年06月19日を選択して検索。最速優先のため待ちを最小化。"""
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    # ── パターンA: 1つのSELECTに「令和○○年○○月○○日」形式 ──────
    date_selected = False
    for sel_elem in await page.query_selector_all("select"):
        for opt in await sel_elem.query_selector_all("option"):
            v   = (await opt.get_attribute("value") or "").strip()
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                name = await sel_elem.get_attribute("name") or "?"
                await (sel_elem.select_option(value=v) if v
                       else sel_elem.select_option(label=txt))
                print(f"  [OK] 日付選択（単一SELECT）: name={name!r} val={v!r} txt={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── パターンB: 年・月・日が別々のSELECT ──────────────────────
    if not date_selected:
        print("  [試行] 年月日分割SELECT パターン...")
        year_done = month_done = day_done = False

        for sel_elem in await page.query_selector_all("select"):
            sel_name = (await sel_elem.get_attribute("name") or "").lower()
            sel_id   = (await sel_elem.get_attribute("id") or "").lower()

            for opt in await sel_elem.query_selector_all("option"):
                v   = (await opt.get_attribute("value") or "").strip()
                txt = (await opt.inner_text()).strip()

                if (not year_done and
                        any(v == p or txt == p or p in txt for p in YEAR_CANDIDATES)):
                    await sel_elem.select_option(value=v)
                    print(f"  [OK] 年: name={sel_name!r} val={v!r} txt={txt!r}")
                    year_done = True
                    break

                if (not month_done and
                        any(v == p or txt == p for p in MONTH_CANDIDATES)):
                    await sel_elem.select_option(value=v)
                    print(f"  [OK] 月: name={sel_name!r} val={v!r} txt={txt!r}")
                    month_done = True
                    date_selected = True
                    break

                if (not day_done and
                        any(v == p or txt == p for p in DAY_CANDIDATES)):
                    await sel_elem.select_option(value=v)
                    print(f"  [OK] 日: name={sel_name!r} val={v!r} txt={txt!r}")
                    day_done = True
                    break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 '{TARGET_DATE_WAREKI}' がプルダウンに見つかりません。\n"
            "analyze_site.py を実行して SELECT の name/value を確認してください。"
        )

    # ── 検索ボタン ──
    await try_click(page, [
        'input[value="検索"]',
        'input[value=" 検索 "]',
        'button:text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  URL: {page.url}")


# ═══════════════════════════════════════════════════════════════
# Step 4: D面 16:00〜18:00（赤丸）セルをクリック
# ═══════════════════════════════════════════════════════════════
async def step_select_slot(page):
    """
    検索結果テーブルから D面 × 16:00〜18:00 のセルを特定してクリック。

    テーブル構造パターン:
      横軸=時間帯 (列ヘッダーに "16:00〜18:00")、縦軸=施設 (行に "D面")
      ※ 逆パターン（横=施設、縦=時間）にも対応
    """
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} を特定...")

    clicked = False
    tables  = await page.query_selector_all("table")

    # ── アプローチ①: ヘッダー行から時間列インデックスを動的に特定 ──
    for table in tables:
        rows = await table.query_selector_all("tr")
        if len(rows) < 2:
            continue

        # ヘッダー行(先頭3行を確認)で "16:00〜18:00" の列インデックスを取得
        time_col_idx = -1
        for row in rows[:3]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                    time_col_idx = ci
                    print(f"  [INFO] '{TARGET_TIME_START}〜{TARGET_TIME_END}' 列={ci}: {txt!r}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行でその列のセルをクリック
        for row in rows:
            cells     = await row.query_selector_all("td, th")
            row_texts = [(await c.inner_text()).strip() for c in cells]
            if not any(TARGET_FACILITY in t for t in row_texts):
                continue

            print(f"  [INFO] {TARGET_FACILITY} 行: {row_texts[:8]}")

            if time_col_idx < len(cells):
                target_cell = cells[time_col_idx]
                tc_txt = (await target_cell.inner_text()).strip()
                tc_cls = await target_cell.get_attribute("class") or ""

                # <a> リンクがあればそちらを優先
                link = await target_cell.query_selector("a")
                if link:
                    await link.click()
                    print(f"  [OK] {TARGET_FACILITY}×{TARGET_TIME_START} (<a>): text={tc_txt!r}")
                else:
                    await target_cell.click()
                    print(f"  [OK] {TARGET_FACILITY}×{TARGET_TIME_START} (<td>): class={tc_cls!r}")
                clicked = True
                break

        if clicked:
            break

    # ── アプローチ②: 施設が列方向の逆パターン対応 ──────────────
    if not clicked:
        print("  [試行] 施設=列ヘッダー、時間=行ヘッダーパターン...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            if len(rows) < 2:
                continue

            # 先頭行からD面の列インデックスを取得
            facility_col_idx = -1
            header_cells = await rows[0].query_selector_all("td, th")
            for ci, cell in enumerate(header_cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_FACILITY in txt:
                    facility_col_idx = ci
                    print(f"  [INFO] '{TARGET_FACILITY}' 列={ci}")
                    break

            if facility_col_idx < 0:
                continue

            # 16:00〜18:00 の行を探す
            for row in rows[1:]:
                cells = await row.query_selector_all("td, th")
                if not cells:
                    continue
                row_head = (await cells[0].inner_text()).strip()
                if TARGET_TIME_START in row_head and TARGET_TIME_END in row_head:
                    if facility_col_idx < len(cells):
                        target_cell = cells[facility_col_idx]
                        link = await target_cell.query_selector("a")
                        if link:
                            await link.click()
                        else:
                            await target_cell.click()
                        print(f"  [OK] {TARGET_FACILITY}×{TARGET_TIME_START}（逆パターン）")
                        clicked = True
                    break
            if clicked:
                break

    # ── アプローチ③: onclick/href にD面+時間情報が含まれるリンク ──
    if not clicked:
        print("  [試行] onclick/href からリンクを探す...")
        for elem in await page.query_selector_all("a, [onclick]"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href
            if "16" in combined and ("D" in combined or "d" in combined):
                print(f"  [OK] onclick={onclick!r} href={href!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"'{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}' セルが見つかりません。\n"
            f"{SS_DIR}/04_search_results.png を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  URL: {page.url}")


# ═══════════════════════════════════════════════════════════════
# Step 5: 確定①（料金確認画面）
# ═══════════════════════════════════════════════════════════════
async def step_confirm1(page):
    print("\n[Step 5] 確定①（料金確認）...")
    await page.wait_for_selector(
        "input[type='submit'], button[type='submit'], input[type='button']",
        timeout=ELEM_TIMEOUT
    )
    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'button:text("確定")',
        'button:text("確認")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  URL: {page.url}")


# ═══════════════════════════════════════════════════════════════
# Step 6: 確定②（最終確定）
# ═══════════════════════════════════════════════════════════════
async def step_confirm2(page):
    """
    最終確定。
    Tampermonkey で window.confirm は無効化済みを前提とするが、
    念のため dialog イベントでも自動承認する。
    """
    print("\n[Step 6] 確定②（最終確定）...")
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    await page.wait_for_selector(
        "input[type='submit'], button[type='submit'], input[type='button']",
        timeout=ELEM_TIMEOUT
    )
    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value*="確定"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not clicked:
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  URL: {page.url}")

    body = await page.inner_text("body")
    keywords = ["予約完了", "受付完了", "受付番号", "予約番号", "申込完了", "完了"]
    if any(w in body for w in keywords):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。スクリーンショットを確認してください。")
    print(f"  本文先頭300字: {body[:300]}")


# ═══════════════════════════════════════════════════════════════
# メイン
# ═══════════════════════════════════════════════════════════════
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日:  {TARGET_DATE_WAREKI}")
    print(f"コート:  {TARGET_FACILITY}  {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード:  {'時報待ち (5:00)' if opts['wait_for_open'] else '即時実行'}"
          f" / {'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
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
        # window.confirm / alert を JS レベルで自動承認（Tampermonkey 補完）
        await context.add_init_script(
            "window.confirm = () => true; window.alert = () => {};"
        )
        page = await context.new_page()

        try:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 事前準備（5:00 より前に完了させる）
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            await step_login(page)
            await step_navigate_to_favorite(page)

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 5:00:00.000 まで待機
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if opts["wait_for_open"]:
                await wait_until_open()

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 5:00 以降に最速実行
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)

            print("\n✅ すべてのステップが完了しました。")

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
