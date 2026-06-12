"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 5:00 タイミング戦略
  4:59:30 ごろ : ブラウザ起動・ログイン・お気に入りページ遷移・日付プリセット
  5:00:00.000  : 検索ボタンをクリック（ミリ秒単位の時報待ちで実行）
  5:00:00 直後 : D面 16:00〜18:00 セルをクリック → 確定① → 確定②

■ 準備
  pip install playwright
  playwright install chromium
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────────────
# 設定値（ここだけ変更すればOK）
# ──────────────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日（練習: 令和08年06月19日 = 2026-06-19）
# 本番（7月分）に変えるときはここを修正
TARGET_DATE_WAREKI     = "令和08年06月19日"
TARGET_DATE_ALT_VALUES = ["20260619", "2026-06-19", "2026/06/19", "260619"]
TARGET_DATE_ALT_TEXTS  = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日",  "2026/06/19",
]

# 予約対象コート・時間帯
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報待ち設定
OPEN_HOUR, OPEN_MINUTE, OPEN_SECOND = 5, 0, 0
PRELOAD_SECONDS = 30   # 5:00 の何秒前にブラウザ起動するか

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# スクリーンショット保存ディレクトリ
SS_DIR = "screenshots"
# ──────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────

def parse_args() -> dict:
    args = sys.argv[1:]
    return {
        "headless":      "--headful" not in args,
        "wait_for_open": "--now"    not in args,
    }


def _next_open_time(now: datetime.datetime) -> datetime.datetime:
    """次の 5:00:00 を返す（既に過ぎていたら翌日）"""
    t = now.replace(
        hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
    )
    if t <= now:
        t += datetime.timedelta(days=1)
    return t


async def wait_until_preload():
    """開始 PRELOAD_SECONDS 秒前まで粗いスリープ"""
    print(f"[事前待機] 5:00:00 の {PRELOAD_SECONDS}秒前までスリープ...")
    while True:
        now  = datetime.datetime.now()
        diff = (_next_open_time(now) - now).total_seconds() - PRELOAD_SECONDS
        if diff <= 0:
            break
        await asyncio.sleep(min(diff, 30))
    print(f"[事前待機] 完了 → ブラウザ起動: {datetime.datetime.now():%H:%M:%S.%f}")


async def wait_until_open():
    """5:00:00.000 ぴったりまでミリ秒単位で精密待機"""
    print("[時報待ち] 5:00:00.000 まで精密待機...")
    while True:
        now  = datetime.datetime.now()
        diff = (_next_open_time(now) - now).total_seconds()
        if diff <= 0:
            print(f"[時報] 到達: {now:%H:%M:%S.%f}")
            break
        elif diff > 5:
            await asyncio.sleep(1)
        elif diff > 0.1:
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    """スクリーンショット保存（デバッグ用）"""
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception as e:
        print(f"  [SS ERROR] {e}")


async def try_click(page, selectors: list, label: str, timeout: int = 5000) -> bool:
    """複数セレクターを順番に試してクリック"""
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
            print(f"  [SKIP] {sel}: {e}")
    print(f"  [FAIL] {label}: 該当なし")
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
        except PWTimeout:
            pass
        except Exception as e:
            print(f"  [SKIP] {sel}: {e}")
    print(f"  [FAIL] {label}: 該当なし")
    return False


# ──────────────────────────────────────────────────────
# ステップ関数
# ──────────────────────────────────────────────────────

async def step_login(page):
    """Step 1: ログインページへ移動してログイン実行"""
    print("\n[Step 1] ログイン...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # 利用者番号（name属性の候補を網羅）
    await try_fill(page, [
        'input[name="userno"]',
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userno',
        '#userid',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")

    # パスワード
    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")

    # ログインボタン
    await try_click(page, [
        'input[value="ログイン"]',
        'input[value*="ログイン"]',
        'button:has-text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  URL: {page.url}")


async def step_favorite(page):
    """Step 2: お気に入りボタンをクリックして絞り込み検索画面へ"""
    print("\n[Step 2] お気に入りクリック...")

    clicked = await try_click(page, [
        'a:has-text("お気に入り")',
        'input[value="お気に入り"]',
        'input[value*="お気に入り"]',
        'button:has-text("お気に入り")',
        '[onclick*="okini"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
        'td:has-text("お気に入り")',
    ], "お気に入り", timeout=ELEM_TIMEOUT)

    # テキストフォールバック（上記が全滅した場合）
    if not clicked:
        for elem in await page.query_selector_all("a, button, input, td, span"):
            try:
                txt = (await elem.inner_text()).strip()
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    id_  = await elem.get_attribute("id") or ""
                    cls  = await elem.get_attribute("class") or ""
                    href = await elem.get_attribute("href") or ""
                    print(f"  [OK] お気に入り(fallback): id={id_!r} cls={cls!r} href={href!r} text={txt!r}")
                    await elem.click()
                    clicked = True
                    break
            except Exception:
                pass

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。\n"
            "  → screenshots/02_after_login.png を確認して、正しいセレクターを特定してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite")
    print(f"  URL: {page.url}")


async def _select_date(page) -> bool:
    """
    日付プルダウンで令和08年06月19日を選択する共通処理。
    成功 True / 未発見 False を返す（Falseでも例外は投げない）。
    """
    # ── 一体型 SELECT（例: value="20260619" or text="令和08年06月19日"）──
    for sel_elem in await page.query_selector_all("select"):
        for opt in await sel_elem.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                name = await sel_elem.get_attribute("name") or ""
                if v:
                    await sel_elem.select_option(value=v)
                else:
                    await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択: name={name!r} value={v!r} text={txt!r}")
                return True

    # ── 分割型 SELECT（年 / 月 / 日 が別々）──
    print("  [試行] 分割 SELECT（年/月/日）...")
    year_ok = month_ok = day_ok = False

    year_keywords  = ["令和08", "令和8", "2026", "R08", "R8", "08", "8"]
    month_keywords = ["06", "6", "６", "06月", "6月", "６月"]
    day_keywords   = ["19", "１９", "19日"]

    for sel_elem in await page.query_selector_all("select"):
        opts_data = []
        for opt in await sel_elem.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            opts_data.append((v, txt))

        for v, txt in opts_data:
            if not year_ok and any(k == txt or k == v for k in year_keywords):
                name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v if v else txt)
                print(f"  [OK] 年 select name={name!r}: {txt!r}")
                year_ok = True
                break
        for v, txt in opts_data:
            if not month_ok and any(k == txt or k == v for k in month_keywords):
                name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v if v else txt)
                print(f"  [OK] 月 select name={name!r}: {txt!r}")
                month_ok = True
                break
        for v, txt in opts_data:
            if not day_ok and any(k == txt or k == v for k in day_keywords):
                name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v if v else txt)
                print(f"  [OK] 日 select name={name!r}: {txt!r}")
                day_ok = True
                break

    return month_ok  # 月が選択できれば「日付選択成功」と見なす


async def step_preselect_date(page):
    """
    Step 3-prep: 5:00前に日付を事前セット（検索は押さない）。
    日付が非表示/未公開でも警告のみで続行する。
    """
    print(f"\n[Step 3-prep] 日付プリセット: {TARGET_DATE_WAREKI}")

    ok = await _select_date(page)
    if not ok:
        print(
            f"  [WARN] {TARGET_DATE_WAREKI} が未確認。"
            "5:00前は非表示の可能性があります。5:00後の step_search で再試行します。"
        )
    await save_ss(page, "03b_date_preset")


async def step_search(page):
    """
    Step 3-exec: 5:00:00 ぴったりに呼ぶ。日付を再確認してから検索ボタンをクリック。
    """
    print(f"\n[Step 3-exec] 検索実行: {datetime.datetime.now():%H:%M:%S.%f}")

    # 日付が未セットなら再試行
    await _select_date(page)

    await try_click(page, [
        'input[value="検索"]',
        'input[value*="検索"]',
        'button:has-text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:has-text("検索")',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_results")
    print(f"  URL: {page.url}  時刻: {datetime.datetime.now():%H:%M:%S.%f}")


async def step_select_slot(page):
    """
    Step 4: D面 16:00〜18:00 の赤丸セルをクリック。
    テーブル構造が不明なため、4つのアプローチを順番に試みる。
    """
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} クリック...")
    clicked = False
    tables  = await page.query_selector_all("table")

    # ── アプローチ①: D面が行ヘッダー、時間が列ヘッダーの場合 ──────────
    for table in tables:
        rows = await table.query_selector_all("tr")
        for row in rows:
            cells = await row.query_selector_all("td, th")
            texts = [(await c.inner_text()).strip() for c in cells]

            if TARGET_FACILITY not in texts:
                continue

            print(f"  [INFO] D面行を発見 cells={texts[:6]}")
            for i, cell in enumerate(cells):
                if texts[i] == TARGET_FACILITY:
                    continue
                txt     = texts[i]
                cls     = await cell.get_attribute("class") or ""
                onclick = await cell.get_attribute("onclick") or ""
                bg      = await cell.get_attribute("bgcolor") or ""
                style   = await cell.get_attribute("style") or ""

                is_time_match = TARGET_TIME_START in txt or TARGET_TIME_START in onclick
                is_red = (
                    "red"  in cls.lower() or "aka"  in cls.lower()
                    or "red"  in style.lower() or "#ff" in style.lower()
                    or "red"  in bg.lower()    or "ff0000" in bg.lower()
                    or "r_"   in cls           or "_r"   in cls
                    or "○"   in txt            or "〇"   in txt
                )
                is_clickable = bool(onclick) or await cell.query_selector("a") is not None

                if is_time_match or (is_red and is_clickable):
                    print(f"  [FOUND①] text={txt!r} cls={cls!r} onclick={onclick[:40]!r}")
                    await cell.click()
                    clicked = True
                    break
            if clicked:
                break
        if clicked:
            break

    # ── アプローチ②: ヘッダー行で「16:00〜18:00」列インデックス → D面行 ──
    if not clicked:
        for table in tables:
            rows     = await table.query_selector_all("tr")
            time_col = -1
            for row in rows[:5]:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                        time_col = ci
                        print(f"  [INFO] 時間列インデックス={ci}: {txt!r}")
                        break
                if time_col >= 0:
                    break
            if time_col < 0:
                continue

            for row in rows:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    if TARGET_FACILITY in (await cell.inner_text()).strip():
                        if time_col < len(cells):
                            tc  = cells[time_col]
                            txt = (await tc.inner_text()).strip()
                            print(f"  [FOUND②] D面行×列{time_col}: {txt!r}")
                            await tc.click()
                            clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: 転置（行=時間帯、列=施設）の場合 ──────────────
    if not clicked:
        for table in tables:
            rows  = await table.query_selector_all("tr")
            d_col = -1
            for row in rows[:5]:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    if TARGET_FACILITY in (await cell.inner_text()).strip():
                        d_col = ci
                        print(f"  [INFO] D面列インデックス={ci}")
                        break
                if d_col >= 0:
                    break
            if d_col < 0:
                continue

            for row in rows:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_TIME_START in txt:
                        if d_col < len(cells):
                            tc = cells[d_col]
                            print(f"  [FOUND③] 時間行×D面列{d_col}: {(await tc.inner_text()).strip()!r}")
                            await tc.click()
                            clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ④: onclick / href にD面+16:00の情報が含まれる要素 ──
    if not clicked:
        for elem in await page.query_selector_all("[onclick], a, td"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if TARGET_FACILITY in combined and TARGET_TIME_START in combined:
                print(f"  [FOUND④] onclick={onclick[:40]!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"D面 16:00〜18:00 のセルが見つかりませんでした。\n"
            f"  → {SS_DIR}/04_results.png を確認してください。\n"
            f"  正しいセレクターが判明したら step_select_slot 内を修正してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot")
    print(f"  URL: {page.url}  時刻: {datetime.datetime.now():%H:%M:%S.%f}")


async def step_confirm1(page):
    """Step 5: 確定①（料金確認画面へ進む）"""
    print("\n[Step 5] 確定①（料金確認画面）...")
    await save_ss(page, "05b_pre_confirm1")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'input[value*="次へ"]',
        'button:has-text("確定")',
        'button:has-text("確認")',
        'button:has-text("次へ")',
        'a:has-text("確定")',
        'a:has-text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①")

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  URL: {page.url}")


async def step_confirm2(page):
    """
    Step 6: 確定②（最終確定）。
    ・Playwright レベルで window.confirm を事前上書き済み（context.add_init_script）。
    ・dialog イベントもフォールバックで自動承認。
    ・Tampermonkey で confirm 無効化済みの前提でも、本スクリプト単体で動作する。
    """
    print("\n[Step 6] 確定②（最終確定）...")
    await save_ss(page, "06b_pre_confirm2")

    # 画面遷移で init_script が効いていない場合の保険（evaluate で直接上書き）
    try:
        await page.evaluate(
            "() => { window.confirm = () => true; window.alert = () => undefined; }"
        )
    except Exception:
        pass

    # dialog イベントフォールバック
    async def auto_accept(dialog):
        print(f"  [DIALOG] type={dialog.type} msg={dialog.message!r} → accept")
        await dialog.accept()
    page.on("dialog", auto_accept)

    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="最終確定"]',
        'input[value*="確定"]',
        'button:has-text("予約確定")',
        'button:has-text("確定")',
        'a:has-text("予約確定")',
        'a:has-text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②")

    if not clicked:
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final")
    print(f"  URL: {page.url}")

    body = await page.inner_text("body")
    if any(w in body for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージ未確認。スクリーンショットを確認してください。")
    print(f"  本文先頭: {body[:300]!r}")


# ──────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────

async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"  対象日: {TARGET_DATE_WAREKI}")
    print(f"  施設:   {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    mode_str = "即時実行" if not opts["wait_for_open"] else f"時報待ち({OPEN_HOUR:02d}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d})"
    disp_str = "ヘッドフル" if not opts["headless"] else "ヘッドレス"
    print(f"  モード: {mode_str} / {disp_str}")
    print("=" * 60)

    # ── 事前待機: 5:00 の PRELOAD_SECONDS 秒前まで粗スリープ ──
    if opts["wait_for_open"]:
        await wait_until_preload()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
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
        )
        # window.confirm / alert を全ページで事前上書き
        await context.add_init_script(
            "window.confirm = () => true; window.alert = () => undefined;"
        )

        page = await context.new_page()

        try:
            # ── 5:00 前に完了させる前処理 ────────────────────
            await step_login(page)
            await step_favorite(page)
            await step_preselect_date(page)

            # ── 精密時報待ち（5:00:00.000 まで待つ）────────────
            if opts["wait_for_open"]:
                await wait_until_open()

            # ── 5:00:00 以降 ──────────────────────────────────
            await step_search(page)
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
