"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00

■ 動作戦略（最速化）
  ┌─ 5:00前 ─────────────────────────────────────────────┐
  │  1. ログイン                                          │
  │  2. お気に入りクリック → 絞り込み画面                 │
  │  3. 日付プルダウンで令和08年06月19日を選択（検索まだ）│
  │  4. 5:00:00.000 まで 1ms 精度でビジーウェイト         │
  └──────────────────────────────────────────────────────┘
  ┌─ 5:00:00.000 ────────────────────────────────────────┐
  │  5. 「検索」ボタンクリック                            │
  │  6. D面 16:00〜18:00 セルクリック（赤丸）             │
  │  7. 確定①（料金確認画面）                            │
  │  8. 確定②（最終確定）                                │
  └──────────────────────────────────────────────────────┘

■ 使い方
  python reserve.py              # 時報待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト・練習）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ）
  python reserve.py --now --headful

■ 準備
  pip install playwright
  playwright install chromium
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ═══════════════════════════════════════════════════
#  設定値（本番時は TARGET_DATE_* を 07月分に書き換え）
# ═══════════════════════════════════════════════════
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 日付（練習: 令和08年06月19日 / 本番: 07月XX日 に変更）
TARGET_DATE_TEXTS = [
    "令和08年06月19日",
    "令和8年6月19日",
    "令和０８年０６月１９日",
    "2026年06月19日",
    "2026/06/19",
]
TARGET_DATE_VALUES = ["20260619", "2026-06-19", "2026/06/19", "260619"]

# 年・月・日が別 SELECT の場合
YEAR_PATTERNS  = ["令和08年", "令和8年", "令和08", "令和8", "08", "2026", "R08", "R8"]
MONTH_PATTERNS = ["06月", "6月", "06", "6", "６月", "6"]
DAY_PATTERNS   = ["19日", "19", "１９"]

# 予約コート・時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 予約開放時刻
OPEN_HOUR, OPEN_MINUTE, OPEN_SECOND = 5, 0, 0

# タイムアウト（ms）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

SS_DIR = "screenshots"
# ═══════════════════════════════════════════════════


# ───────────────────────── ユーティリティ ──────────────────────────

def parse_args() -> dict:
    args = sys.argv[1:]
    return {
        "headless":      "--headful" not in args,
        "wait_for_open": "--now"    not in args,
    }


async def wait_until_open():
    """OPEN_HOUR:00:00.000 ぴったりまでミリ秒精度で待機"""
    target_str = f"{OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d}.000"
    print(f"[時報待ち] {target_str} まで待機します...")

    while True:
        now    = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0,
        )
        diff = (target - now).total_seconds()

        if diff <= 0:
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")
            print(f"[時報] 開始時刻到達: {ts}")
            return
        elif diff > 300:          # 5 分超 → 30 秒おきに残り時間を表示
            print(f"  あと {diff / 60:.1f} 分 ({diff:.0f} 秒)...")
            await asyncio.sleep(30)
        elif diff > 10:           # 10 秒〜5 分 → 1 秒おき
            await asyncio.sleep(1)
        elif diff > 1:            # 1〜10 秒 → 10 ms おき
            await asyncio.sleep(0.01)
        elif diff > 0.1:          # 100 ms〜1 秒 → 2 ms おき
            await asyncio.sleep(0.002)
        else:                     # 最後の 100 ms → 1 ms おき（ビジーウェイト）
            await asyncio.sleep(0.001)


async def ss(page, name: str):
    """スクリーンショット保存"""
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def click_first(page, selectors: list, label: str, timeout: int = 5000) -> bool:
    """セレクターリストを順番に試し、最初に見つかった要素をクリック"""
    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                await el.click()
                print(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            print(f"  [SKIP] {sel}: {e}")
    print(f"  [FAIL] {label}: 見つかりません ({selectors[0]}...)")
    return False


async def fill_first(page, selectors: list, value: str, label: str, timeout: int = 5000) -> bool:
    """セレクターリストを順番に試し、最初に見つかった入力欄に値を入力"""
    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                await el.fill(value)
                print(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            print(f"  [SKIP] {sel}: {e}")
    print(f"  [FAIL] {label}: 見つかりません")
    return False


# ───────────────────────── 各ステップ ─────────────────────────────

async def step_login(page):
    """Step 1/7: ログイン"""
    print("\n[Step 1/7] ログイン...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "01_login")

    await fill_first(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="userno"]',
        'input[name="memberNo"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")

    await fill_first(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")

    await click_first(page, [
        'input[value="ログイン"]',
        'input[type="submit"]',
        'button:text("ログイン")',
        'button[type="submit"]',
        'a:text("ログイン")',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "02_after_login")
    print(f"  URL: {page.url}")


async def step_favorite(page):
    """Step 2/7: お気に入りクリック → 絞り込み画面"""
    print("\n[Step 2/7] お気に入りクリック...")

    clicked = await click_first(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
    ], "お気に入り", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキストスキャンフォールバック
        for el in await page.query_selector_all("a, input[type=submit], input[type=button], button"):
            txt = (await el.inner_text() or "").strip()
            val = (await el.get_attribute("value") or "").strip()
            if "お気に入り" in txt or "お気に入り" in val:
                await el.click()
                print("  [OK] お気に入り（テキストスキャン）")
                clicked = True
                break

    if not clicked:
        await ss(page, "ERROR_no_favorite")
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行して解析してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "03_favorite")
    print(f"  URL: {page.url}")


async def step_preselect_date(page) -> bool:
    """
    Step 3/7: 日付プルダウンで目標日を選択（5:00前に実行）
    検索ボタンは押さない。Returns True if successful.
    """
    print(f"\n[Step 3/7] 日付プリセレクト: {TARGET_DATE_TEXTS[0]}")

    selects = await page.query_selector_all("select")
    if not selects:
        print("  [WARN] SELECT 要素が見つかりません")
        return False

    # ── パターン A: 1つの SELECT に日付がすべて入っている ──────────
    for sel_el in selects:
        opts = await sel_el.query_selector_all("option")
        for opt in opts:
            v   = (await opt.get_attribute("value") or "").strip()
            txt = (await opt.inner_text()).strip()
            if any(t in txt for t in TARGET_DATE_TEXTS) or v in TARGET_DATE_VALUES:
                name = await sel_el.get_attribute("name") or ""
                if v:
                    await sel_el.select_option(value=v)
                else:
                    await sel_el.select_option(label=txt)
                print(f"  [OK] 日付選択（統合型）: name={name!r} value={v!r} text={txt!r}")
                return True

    # ── パターン B: 年・月・日が別々の SELECT ──────────────────────
    print("  [INFO] 分割型 SELECT（年/月/日）を探索...")
    matched = {"year": False, "month": False, "day": False}

    for sel_el in selects:
        opts  = await sel_el.query_selector_all("option")
        pairs = [(await o.inner_text()).strip(), (await o.get_attribute("value") or "").strip()
                 for o in opts]
        # pairs はリストにならない（ジェネレータの内包は不可）→ 修正
        pairs = []
        for o in opts:
            t = (await o.inner_text()).strip()
            v = (await o.get_attribute("value") or "").strip()
            pairs.append((t, v))

        for i, (t, v) in enumerate(pairs):
            if not matched["year"] and any(p in t or p == v for p in YEAR_PATTERNS):
                await sel_el.select_option(index=i)
                print(f"  [OK] 年選択: {t!r}")
                matched["year"] = True
                break
        for i, (t, v) in enumerate(pairs):
            if not matched["month"] and any(p == t or p == v for p in MONTH_PATTERNS):
                await sel_el.select_option(index=i)
                print(f"  [OK] 月選択: {t!r}")
                matched["month"] = True
                break
        for i, (t, v) in enumerate(pairs):
            if not matched["day"] and any(p == t or p == v for p in DAY_PATTERNS):
                await sel_el.select_option(index=i)
                print(f"  [OK] 日選択: {t!r}")
                matched["day"] = True
                break

    if any(matched.values()):
        print(f"  [INFO] 分割型 結果: {matched}")
        return True

    await ss(page, "ERROR_date_not_found")
    print(f"  [WARN] 日付 {TARGET_DATE_TEXTS[0]} が見つかりませんでした。")
    return False


async def step_search(page):
    """Step 4/7: 5:00:00 ちょうどに検索ボタンをクリック"""
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")
    print(f"\n[Step 4/7] 検索クリック @ {ts}")

    clicked = await click_first(page, [
        'input[value="検索"]',
        'input[value*="検索"]',
        'button:text("検索")',
        'input[value="絞り込み"]',
        'input[value*="絞"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ], "検索ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        await ss(page, "ERROR_no_search_btn")
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, "04_results")
    print(f"  URL: {page.url}")


async def step_select_slot(page):
    """Step 5/7: D面 16:00〜18:00 のセルをクリック（赤丸）"""
    print(f"\n[Step 5/7] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} 選択...")

    tables = await page.query_selector_all("table")

    # ── アプローチ A: ヘッダー行で列インデックス特定 → D面行の同列をクリック ──
    for tbl in tables:
        rows = await tbl.query_selector_all("tr")

        # 時間列のインデックスを取得
        time_col = -1
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                t = (await cell.inner_text()).strip()
                if TARGET_TIME_START in t and TARGET_TIME_END in t:
                    time_col = ci
                    break
                if TARGET_TIME_START in t:
                    time_col = ci
            if time_col >= 0:
                break

        # D面行を探す
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_texts = [(await c.inner_text()).strip() for c in cells]

            if not any(TARGET_FACILITY in t for t in row_texts):
                continue

            print(f"  [INFO] D面行: {row_texts[:8]}")

            if time_col >= 0 and time_col < len(cells):
                target_cell = cells[time_col]
            else:
                # 列が特定できない場合: 予約可を示す記号（○◎●）を含むセルを探す
                target_cell = None
                for ci, txt in enumerate(row_texts):
                    if "○" in txt or "◎" in txt or "●" in txt or "16" in txt:
                        target_cell = cells[ci]
                        time_col = ci
                        break
                if target_cell is None:
                    continue

            tc_txt = (await target_cell.inner_text()).strip()
            tc_cls = (await target_cell.get_attribute("class") or "")
            tc_onc = (await target_cell.get_attribute("onclick") or "")
            print(f"  [FOUND] 列{time_col}: text={tc_txt!r} class={tc_cls!r}")

            # セル内にリンクがある場合はリンクをクリック
            inner_a = await target_cell.query_selector("a")
            if inner_a:
                await inner_a.click()
            else:
                await target_cell.click()

            await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
            await ss(page, "05_slot_selected")
            print(f"  URL: {page.url}")
            return

    # ── アプローチ B: onclick / href に D面・16 が含まれる要素 ──────────────
    print("  [試行B] onclick/href スキャン...")
    for el in await page.query_selector_all("[onclick], a[href]"):
        onclick = (await el.get_attribute("onclick") or "")
        href    = (await el.get_attribute("href") or "")
        txt     = (await el.inner_text() or "").strip()
        combined = onclick + href + txt
        if ("D面" in combined or "D" in combined) and "16" in combined:
            print(f"  [FOUND] onclick={onclick[:80]!r}")
            await el.click()
            await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
            await ss(page, "05_slot_selected")
            print(f"  URL: {page.url}")
            return

    await ss(page, "ERROR_slot_not_found")
    raise RuntimeError(
        f"D面 16:00〜18:00 のセルが見つかりません。"
        f"screenshots/04_results.png を確認してください。"
    )


async def step_confirm(page, step_label: str, ss_name: str):
    """確定ボタンをクリック（確定①・確定②共用）"""
    print(f"\n[{step_label}] 確定ボタンクリック...")

    # dialog が来た場合は自動承認（Playwright は clean ブラウザなので保険として）
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    clicked = await click_first(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="確認"]',
        'input[value*="確定"]',
        'input[value*="予約"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], f"{step_label}確定ボタン", timeout=ELEM_TIMEOUT)

    if not clicked:
        await ss(page, f"ERROR_{ss_name}")
        raise RuntimeError(f"[{step_label}] 確定ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await ss(page, ss_name)
    print(f"  URL: {page.url}")


# ─────────────────────────── メイン ───────────────────────────────

async def main():
    opts = parse_args()
    print("=" * 60)
    print("  まんまるよやく2 自動予約スクリプト")
    print(f"  対象: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"  日付: {TARGET_DATE_TEXTS[0]}")
    print(f"  モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00)'}"
          f" / {'表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=opts["headless"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await ctx.new_page()

        try:
            # ── 5:00 前の事前処理（ここまでは時刻に関係なく実行）──
            await step_login(page)
            await step_favorite(page)
            date_selected = await step_preselect_date(page)

            if not date_selected:
                print("\n[WARN] 日付プリセレクトに失敗しました。")
                print("       5:00:00 に到達してから検索と日付選択を行います。")

            # ── 5:00:00.000 まで待機 ───────────────────────────────
            if opts["wait_for_open"]:
                await wait_until_open()

            # ── 5:00:00.000 ちょうどに検索 ────────────────────────
            # 日付プリセレクト失敗時は再度試みる
            if not date_selected:
                await step_preselect_date(page)

            await step_search(page)

            # ── セル選択 → 確定 ───────────────────────────────────
            await step_select_slot(page)
            await step_confirm(page, "Step 6/7 確定①（料金確認）", "06_confirm1")
            await step_confirm(page, "Step 7/7 確定②（最終確定）", "07_confirm2")

            # ── 完了確認 ──────────────────────────────────────────
            body = await page.inner_text("body")
            keywords = ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました", "完了"]
            if any(w in body for w in keywords):
                print("\n✅ 予約完了を確認しました！")
            else:
                print("\n⚠️  完了メッセージが不明確。screenshots/ フォルダを確認してください。")
            print(f"  本文先頭200字: {body[:200]}")

        except Exception as e:
            await ss(page, "ERROR_final")
            print(f"\n❌ エラー: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
