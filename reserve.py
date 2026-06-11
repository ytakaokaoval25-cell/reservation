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
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日（練習: 令和08年06月19日 = 2026-06-19。本番は七月分に変更）
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_VALUE  = "20260619"
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日",  "2026/06/19",
    "令和08年 6月19日", "令和8年 6月19日",
]

# 分割SELECT用パターン（年・月・日それぞれ）
YEAR_PATTERNS  = ["令和08年", "令和8年", "令和08", "令和8", "08", "2026", "R08", "R8", "令和０８年"]
MONTH_PATTERNS = ["06月", "6月", "06", "6", "６月", "０６月"]
DAY_PATTERNS   = ["19日", "19", "１９日", "１９"]

# 予約対象コート＆時間
TARGET_FACILITY  = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報待ち設定（本番）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# スクリーンショット保存先
SS_DIR = "screenshots"
# ──────────────────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


async def wait_until_open():
    """
    朝 OPEN_HOUR:OPEN_MINUTE:OPEN_SECOND.000 ぴったりまでミリ秒単位で待機。
    段階的スリープで CPU 使用を最小化しつつ精度を確保する。
    """
    print("[時報待ち] 朝5:00:00.000 まで待機します...")
    while True:
        now    = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0,
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {now.strftime('%H:%M:%S.%f')}")
            return

        if diff_sec > 300:          # 5分以上前
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:         # 10秒〜5分前
            await asyncio.sleep(1)
        elif diff_sec > 0.5:        # 500ms〜10秒前
            await asyncio.sleep(0.05)
        elif diff_sec > 0.01:       # 10ms〜500ms前
            await asyncio.sleep(0.005)
        else:                       # 10ms以内
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    """スクリーンショット保存"""
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_click(page, selectors: list[str], label: str, timeout: int = 5_000) -> bool:
    """複数セレクターを順番に試してクリック。成功すれば True を返す。"""
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.click()
                print(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as exc:
            print(f"  [SKIP] {label} ({sel}): {exc}")
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


async def try_fill(page, selectors: list[str], value: str, label: str, timeout: int = 5_000) -> bool:
    """複数セレクターを順番に試してテキスト入力。成功すれば True を返す。"""
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.fill(value)
                print(f"  [OK] {label}入力: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as exc:
            print(f"  [SKIP] {label} ({sel}): {exc}")
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


# ──────────────────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    await try_fill(page, [
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

    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
    ], PASSWORD, "パスワード")

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


# ──────────────────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面
# ──────────────────────────────────────────────────────────
async def step_favorite(page):
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
        # テキスト全探索フォールバック
        for elem in await page.query_selector_all("a, button, input[type=button], input[type=submit]"):
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（フォールバック）: text={txt!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError("お気に入りリンクが見つかりません。analyze_site.py で解析してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────────
# Step 3: 日付プルダウン選択 → 検索
# ──────────────────────────────────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    selects = await page.query_selector_all("select")
    date_selected = False

    # ── パターンA: 日付が1つのSELECTにまとまっている場合 ──
    for sel_elem in selects:
        for opt in await sel_elem.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択(A): name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── パターンB: 年・月・日が別々のSELECT ──
    if not date_selected:
        print("  [試行] 年月日が分割SELECTの可能性あり...")

        async def pick_option(patterns):
            """patterns のいずれかに完全一致するoptionを選択する"""
            for sel_elem in selects:
                for opt in await sel_elem.query_selector_all("option"):
                    txt = (await opt.inner_text()).strip()
                    v   = (await opt.get_attribute("value") or "").strip()
                    for p in patterns:
                        if p == txt or p == v or txt.startswith(p) or v.startswith(p):
                            await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                            print(f"  [OK] 選択: text={txt!r} value={v!r} pattern={p!r}")
                            return True
            return False

        yr_ok    = await pick_option(YEAR_PATTERNS)
        month_ok = await pick_option(MONTH_PATTERNS)
        day_ok   = await pick_option(DAY_PATTERNS)
        date_selected = yr_ok or month_ok or day_ok

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
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


# ──────────────────────────────────────────────────────────
# Step 4: D面 16:00〜18:00（赤丸）セルをクリック
# ──────────────────────────────────────────────────────────
async def step_select_slot(page):
    """
    テーブル構造の主なパターン:
      A) 行ヘッダー=施設名、列ヘッダー=時間帯
      B) 行ヘッダー=時間帯、列ヘッダー=施設名
    いずれの場合も D面 × 16:00〜18:00 の交差セルをクリックする。
    セル内はリンク(<a>)または画像(<img>)が使われることが多い。
    """
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セル選択...")

    clicked = False
    tables  = await page.query_selector_all("table")

    async def click_cell(cell):
        """セルをクリック。内部にリンクや画像があればそちらを優先。"""
        link = await cell.query_selector("a")
        if link:
            await link.click()
        else:
            img = await cell.query_selector("input[type=image]")
            if img:
                await img.click()
            else:
                await cell.click()

    # ── アプローチA: 行テキストに D面 が含まれ、同行に 16:00 を含むセル ──
    for table in tables:
        rows = await table.query_selector_all("tr")
        for row in rows:
            cells = await row.query_selector_all("td, th")
            texts = [(await c.inner_text()).strip() for c in cells]

            row_combined = " ".join(texts)
            if TARGET_FACILITY not in row_combined:
                continue

            # D面 行を発見
            print(f"  [INFO] D面行発見: {texts[:6]}")
            for i, (cell, txt) in enumerate(zip(cells, texts)):
                if TARGET_TIME_START in txt or (
                    "16" in txt and TARGET_TIME_END in txt
                ):
                    cls     = await cell.get_attribute("class") or ""
                    onclick = await cell.get_attribute("onclick") or ""
                    print(f"  [FOUND-A] cell[{i}] class={cls!r} onclick={onclick!r} text={txt!r}")
                    await click_cell(cell)
                    clicked = True
                    break
            if clicked:
                break
        if clicked:
            break

    # ── アプローチB: ヘッダー行で 16:00〜18:00 の列インデックスを特定 ──
    if not clicked:
        print("  [試行B] ヘッダーから列インデックスで特定...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            col_idx = -1

            for row in rows[:4]:  # 最初の4行をヘッダー候補として走査
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_TIME_START in txt and TARGET_TIME_END in txt:
                        col_idx = ci
                        print(f"  [INFO] 16:00〜18:00 列インデックス={ci}")
                        break
                if col_idx >= 0:
                    break

            if col_idx < 0:
                continue

            for row in rows:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    if TARGET_FACILITY in (await cell.inner_text()).strip():
                        if col_idx < len(cells):
                            target_cell = cells[col_idx]
                            tc_txt = (await target_cell.inner_text()).strip()
                            tc_cls = await target_cell.get_attribute("class") or ""
                            print(f"  [FOUND-B] D面行×列{col_idx}: text={tc_txt!r} class={tc_cls!r}")
                            await click_cell(target_cell)
                            clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチC: onclick / href に D面 + 16 の情報が含まれる要素 ──
    if not clicked:
        print("  [試行C] onclick/href からD面16:00を探す...")
        for elem in await page.query_selector_all("[onclick], a[href]"):
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if (TARGET_FACILITY in combined or "d面" in combined.lower()) and "16" in combined:
                print(f"  [FOUND-C] onclick={onclick[:60]!r} href={href[:60]!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    # ── アプローチD: 画像のsrc/altに赤丸または○を示す要素 ──
    if not clicked:
        print("  [試行D] 画像（赤丸/○）+ 位置から特定...")
        # 最後の手段: スクリーンショットを撮って人間が確認できるようにする
        await save_ss(page, "DEBUG_slot_search")
        # ページ内のすべてのリンクをテキスト付きで出力
        for a in await page.query_selector_all("a[href], a[onclick]"):
            href    = await a.get_attribute("href") or ""
            onclick = await a.get_attribute("onclick") or ""
            txt     = (await a.inner_text()).strip()
            if not txt:
                # imgのalt属性を確認
                img = await a.query_selector("img")
                if img:
                    txt = await img.get_attribute("alt") or ""
            combined = href + onclick + txt
            if "16" in combined and ("D" in combined or "d" in combined):
                print(f"  [FOUND-D] href={href[:60]!r} onclick={onclick[:60]!r} text={txt!r}")
                await a.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            "D面 16:00〜18:00 のセルが見つかりません。\n"
            f"screenshots/04_search_results.png と DEBUG_slot_search.png を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ──────────────────────────────────────────────────────────
async def step_confirm1(page):
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


# ──────────────────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# ──────────────────────────────────────────────────────────
async def step_confirm2(page):
    """
    window.confirm は context.add_init_script で無効化済み（常にtrue）。
    万が一 Playwright がダイアログを検知した場合のフォールバックも設定する。
    """
    print("\n[Step 6] 確定②クリック...")
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="登録"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'button:text("登録")',
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
        print("\n⚠️  完了メッセージが見つかりません。screenshots/07_final_result.png を確認してください。")
    print(f"  最終本文（先頭300字）: {body_text[:300]}")


# ──────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(
        f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00)'}"
        f" / {'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}"
    )
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

        # window.confirm / window.alert を無効化（Playwright 自身のブラウザ上でも確実に）
        await context.add_init_script("""
            window.confirm = () => true;
            window.alert   = () => {};
            window.prompt  = () => "";
        """)

        page = await context.new_page()

        try:
            await step_login(page)
            await step_favorite(page)
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)
            print("\n✅ すべてのステップが完了しました。")
        except Exception as exc:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー: {exc}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
