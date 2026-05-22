"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方
  python reserve.py                   # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now             # 即時実行（テスト用）
  python reserve.py --headful         # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful   # テスト+ブラウザ表示
  python reserve.py --date 20260719   # 日付を上書き（本番7月用）

■ 準備
  pip install playwright
  playwright install chromium
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────
# タイムゾーン（JST固定 / pytz不要）
# ──────────────────────────────────────────────
JST = datetime.timezone(datetime.timedelta(hours=9))


def now_jst() -> datetime.datetime:
    return datetime.datetime.now(JST)


# ──────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# ── 予約対象日 ──────────────────────────────
# 練習: 令和08年06月19日 (2026-06-19)
# 本番: python reserve.py --date 20260719 で上書き、または下記を直接変更
TARGET_DATE_YYYYMMDD = "20260619"

# ── コート・時間 ────────────────────────────
TARGET_FACILITY  = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# ── 時報待ち設定（本番5:00:00 JST）──────────
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# ── タイムアウト（ミリ秒）──────────────────
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# ── スクリーンショット保存先 ──────────────
SS_DIR = "screenshots"
# ──────────────────────────────────────────────


def _wareki_from_yyyymmdd(yyyymmdd: str) -> list[str]:
    """YYYYMMDD → 和暦テキスト候補リスト（令和のみ対応）"""
    y, m, d = int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8])
    reiwa = y - 2018  # 令和元年=2019
    return [
        f"令和{reiwa:02d}年{m:02d}月{d:02d}日",
        f"令和{reiwa}年{m}月{d}日",
        f"令和０{reiwa}年０{m}月{d:02d}日" if reiwa < 10 and m < 10 else "",
        f"{y}年{m:02d}月{d:02d}日",
        f"{y}/{m:02d}/{d:02d}",
        f"{y}-{m:02d}-{d:02d}",
    ]


def _alt_values_from_yyyymmdd(yyyymmdd: str) -> list[str]:
    """YYYYMMDD → プルダウンvalue候補リスト"""
    y, m, d = yyyymmdd[:4], yyyymmdd[4:6], yyyymmdd[6:8]
    return [
        yyyymmdd,
        f"{y}-{m}-{d}",
        f"{y}/{m}/{d}",
        f"{y[2:]}{m}{d}",  # 260619
        f"{m}{d}",
    ]


def parse_args() -> dict:
    args = sys.argv[1:]
    date_override = None
    for i, a in enumerate(args):
        if a == "--date" and i + 1 < len(args):
            date_override = args[i + 1]
        elif a.startswith("--date="):
            date_override = a.split("=", 1)[1]

    yyyymmdd = date_override or TARGET_DATE_YYYYMMDD
    wareki_texts = [t for t in _wareki_from_yyyymmdd(yyyymmdd) if t]
    alt_values   = _alt_values_from_yyyymmdd(yyyymmdd)

    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now" not in args,
        "yyyymmdd":       yyyymmdd,
        "wareki_texts":   wareki_texts,
        "alt_values":     alt_values,
    }


# ──────────────────────────────────────────────
# 時報待ちロジック（JST 5:00:00.000 ぴったり）
# ──────────────────────────────────────────────

async def wait_until_open():
    """JST 朝5:00:00.000 ぴったりまでミリ秒単位で待機"""
    print("[時報待ち] JST 朝5:00:00.000 まで待機します...")
    while True:
        now = now_jst()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {now_jst().strftime('%H:%M:%S.%f')} JST")
            break
        elif diff_sec > 300:
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分) ...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            await asyncio.sleep(1)
        elif diff_sec > 0.1:
            await asyncio.sleep(0.05)
        else:
            # 残り100ms以内: 1msポーリング
            await asyncio.sleep(0.001)


# ──────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────

async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


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
    print(f"  [FAIL] {label}: 該当要素なし → analyze_site.py を実行して確認してください")
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
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


# ──────────────────────────────────────────────
# 各ステップ
# ──────────────────────────────────────────────

async def step_login(page):
    """Step1: ログイン"""
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号
    ok = await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")
    if not ok:
        raise RuntimeError("利用者番号フィールドが見つかりません。")

    # パスワード
    ok = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")
    if not ok:
        raise RuntimeError("パスワードフィールドが見つかりません。")

    # ログインボタン
    await try_click(page, [
        'input[value="ログイン"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
        'a:text("ログイン")',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


async def step_favorite(page):
    """Step2: お気に入りクリック → 絞り込み画面"""
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全走査フォールバック
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            try:
                txt = await elem.inner_text()
            except Exception:
                txt = ""
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in (txt or "") or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（フォールバック）: text={txt!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError("お気に入りリンクが見つかりません。analyze_site.py で解析してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


async def step_select_date_and_search(page, opts: dict):
    """Step3: 日付プルダウンで対象日を選択して検索（最速）"""
    yyyymmdd    = opts["yyyymmdd"]
    alt_texts   = opts["wareki_texts"]
    alt_values  = opts["alt_values"]
    print(f"\n[Step 3] 日付選択: {alt_texts[0]} ({yyyymmdd})")

    date_selected = False

    # ── 試行①: 結合型（1つのSELECTに「令和08年06月19日」等が入っている）──
    for sel_elem in await page.query_selector_all("select"):
        for opt in await sel_elem.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if any(t in txt for t in alt_texts) or v in alt_values:
                name = await sel_elem.get_attribute("name") or "?"
                await sel_elem.select_option(value=v if v else txt)
                print(f"  [OK] 日付選択（結合型）: name={name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── 試行②: 分割型（年・月・日が別々のSELECT）──────────────────────
    if not date_selected:
        print("  [試行②] 年月日が分割SELECTの可能性あり...")
        y, m, d = yyyymmdd[:4], yyyymmdd[4:6], yyyymmdd[6:8]
        reiwa   = int(y) - 2018
        year_pats  = [f"令和{reiwa:02d}", f"令和{reiwa}", str(reiwa), y, f"R{reiwa:02d}", f"R{reiwa}"]
        month_pats = [m, m.lstrip("0"), f"{m}月", f"{m.lstrip('0')}月"]
        day_pats   = [d, d.lstrip("0"), f"{d}日"]

        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(p == txt.strip() or p == v.strip() for p in year_pats):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 年選択: {txt!r}")
                    break

        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(p == txt.strip() or p == v.strip() for p in month_pats):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 月選択: {txt!r}")
                    date_selected = True
                    break

        for sel_elem in await page.query_selector_all("select"):
            for opt in await sel_elem.query_selector_all("option"):
                v   = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if any(p == txt.strip() or p == v.strip() for p in day_pats):
                    await sel_elem.select_option(value=v or txt)
                    print(f"  [OK] 日選択: {txt!r}")
                    break

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {alt_texts[0]} がプルダウンに見つかりません。"
            "analyze_site.py を実行してセレクターを確認してください。"
        )

    # 検索ボタン
    await try_click(page, [
        'input[value="検索"]',
        'button:text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


async def step_select_slot(page):
    """Step4: D面 16:00〜18:00 の予約可能（赤丸）セルをクリック"""
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    tables  = await page.query_selector_all("table")
    clicked = False

    # ── アプローチ①: ヘッダー行から「16:00〜18:00」列インデックスを特定し
    #                 D面行との交差セルをクリック ──────────────────────────
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行（先頭3行以内）で 16:00 列を探す
        for row in rows[:3]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_TIME_START in txt:
                    time_col_idx = ci
                    print(f"  [INFO] {TARGET_TIME_START} 列インデックス={ci}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面行を探してtime_col_idxのセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_texts = [(await c.inner_text()).strip() for c in cells]

            if TARGET_FACILITY in row_texts:
                print(f"  [INFO] {TARGET_FACILITY} 行発見: {row_texts[:6]}")
                if time_col_idx < len(cells):
                    target_cell = cells[time_col_idx]
                    tc_txt = (await target_cell.inner_text()).strip()
                    tc_cls = await target_cell.get_attribute("class") or ""
                    print(f"  [FOUND] D面×{TARGET_TIME_START}: text={tc_txt!r} class={tc_cls!r}")
                    await target_cell.click()
                    clicked = True
                break
        if clicked:
            break

    # ── アプローチ②: D面が行に存在しない場合、セル内テキストで直接探す ──
    if not clicked:
        print("  [試行②] セルテキストから直接探索...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                row_texts = [(await c.inner_text()).strip() for c in cells]
                combined  = " ".join(row_texts)
                if TARGET_FACILITY in combined and TARGET_TIME_START in combined:
                    for ci, (cell, txt) in enumerate(zip(cells, row_texts)):
                        if TARGET_TIME_START in txt:
                            cls = await cell.get_attribute("class") or ""
                            print(f"  [FOUND②] text={txt!r} class={cls!r}")
                            await cell.click()
                            clicked = True
                            break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick/href にD面+時間情報が含まれるリンク ──────
    if not clicked:
        print("  [試行③] onclick/href で探索...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            try:
                txt = await elem.inner_text()
            except Exception:
                txt = ""
            combined = onclick + href + (txt or "")
            if (TARGET_FACILITY in combined or "D" in combined) and "16" in combined:
                print(f"  [FOUND③] onclick={onclick!r} href={href!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。"
            "screenshots/04_search_results.png と analysis_output/ を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


async def step_confirm1(page):
    """Step5: 確定①（料金確認画面へ）"""
    print("\n[Step 5] 確定①クリック...")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'button:text("確定")',
        'button:text("確認")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'a:text("確定")',
        'a:text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


async def step_confirm2(page):
    """Step6: 確定②（最終確定）
    Tampermonkeyで window.confirm を無効化済みの前提だが、
    ブラウザ初期化時にも override してあるのでダイアログは発火しない。
    万一発火した場合のフォールバックとして dialog イベントも承認する。
    """
    print("\n[Step 6] 確定②クリック...")
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'input[value*="確定"]',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not clicked:
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    body_text = await page.inner_text("body")
    if any(w in body_text for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。スクリーンショットを確認してください。")
    print(f"  最終本文（先頭200字）: {body_text[:200]}")


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────

async def main():
    opts = parse_args()
    target_wareki = opts["wareki_texts"][0] if opts["wareki_texts"] else opts["yyyymmdd"]

    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {target_wareki}  施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else 'JST 時報待ち(5:00:00)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print(f"現在JST: {now_jst().strftime('%Y-%m-%d %H:%M:%S %Z')}")
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
        )

        # window.confirm を無効化（Tampermonkey と同等の処理）
        await context.add_init_script("window.confirm = () => true;")

        page = await context.new_page()

        try:
            await step_login(page)
            await step_favorite(page)
            await step_select_date_and_search(page, opts)
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
