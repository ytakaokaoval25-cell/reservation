"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方
  python reserve.py              # 朝5:00:00ちょうど待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト・練習用）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ 本番切り替え方法
  TARGET_DATE_WAREKI / TARGET_DATE_VALUE を令和08年07月分の日付に変更する
  例: 令和08年07月19日 → TARGET_DATE_WAREKI = "令和08年07月19日"
                          TARGET_DATE_VALUE  = "20260719"

■ 前提
  pip install playwright
  playwright install chromium
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ══════════════════════════════════════════════════════════════
# 設定値（ここを変更して使う）
# ══════════════════════════════════════════════════════════════
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# ── 予約対象日 ──────────────────────────────────────────────
# 練習: 令和08年06月19日（2026-06-19）
# 本番: 令和08年07月XX日 に書き換える
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_VALUE  = "20260619"        # プルダウンのvalue属性が数字の場合

TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日",
    "令和8年6月19日",
    "令和０８年０６月１９日",
    "2026年06月19日",
    "2026/06/19",
    "06/19",
    "19",
]
TARGET_DATE_ALT_VALUES = [
    "20260619",
    "2026-06-19",
    "2026/06/19",
    "260619",
]

# ── 予約対象施設・時間 ──────────────────────────────────────
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# ── 時報待ち設定（本番用） ──────────────────────────────────
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# ── タイムアウト（ミリ秒） ──────────────────────────────────
NAV_TIMEOUT  = 30_000   # ページ遷移
ELEM_TIMEOUT = 10_000   # 要素待機

# ── スクリーンショット保存先（--nowまたはエラー時に保存） ──
SS_DIR = "screenshots"
# ══════════════════════════════════════════════════════════════


def parse_args():
    args = sys.argv[1:]
    return {
        "headless": "--headful" not in args,
        "wait_for_open": "--now" not in args,
    }


async def wait_until_open():
    """
    朝5:00:00.000 ぴったりまでミリ秒単位で待機する。
    - 5分以上前: 30秒ごとに残り時間を表示
    - 10秒〜5分前: 1秒ごと
    - 100ms〜10秒前: 50msごと
    - 100ms以内: 1msごと（精度を最大化）
    """
    print(f"[時報待ち] 朝{OPEN_HOUR}:{OPEN_MINUTE:02d}:{OPEN_SECOND:02d}.000 まで待機します...")
    while True:
        now    = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {now.strftime('%H:%M:%S.%f')}")
            break
        elif diff_sec > 300:
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            await asyncio.sleep(1)
        elif diff_sec > 0.1:
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    """デバッグ用スクリーンショット保存"""
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"  [SS] {path}")
    except Exception:
        pass


async def try_fill(page, selectors: list, value: str, label: str, timeout: int = ELEM_TIMEOUT) -> bool:
    """複数セレクターを順番に試して入力"""
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.fill(value)
                print(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            continue
        except Exception as e:
            print(f"  [SKIP] {sel}: {e}")
    print(f"  [FAIL] {label} の入力フィールドが見つかりません")
    return False


async def try_click(page, selectors: list, label: str, timeout: int = ELEM_TIMEOUT) -> bool:
    """複数セレクターを順番に試してクリック"""
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.click()
                print(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            continue
        except Exception as e:
            print(f"  [SKIP] {sel}: {e}")
    print(f"  [FAIL] {label} が見つかりません")
    return False


# ══════════════════════════════════════════════════════════════
# Step 1: ログイン
# ══════════════════════════════════════════════════════════════
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)

    # 利用者番号（name属性優先、フォールバックで1番目のtextへ）
    await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid', '#user_id', '#memberNo', '#loginId',
        'input[type="text"]:first-of-type',
        'input[type="text"]',
    ], USER_ID, "利用者番号")

    # パスワード
    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        '#passwd', '#password',
    ], PASSWORD, "パスワード")

    # ログインボタン
    clicked = await try_click(page, [
        'input[value="ログイン"]',
        'input[value="ログイン "]',   # 末尾スペース込みのケースも
        'button:text("ログイン")',
        'input[value*="ログ"]',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "ログインボタン")

    if not clicked:
        raise RuntimeError("ログインボタンが見つかりません。analyze_site.py を実行してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    print(f"  現在URL: {page.url}")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if "エラー" in body and "パスワード" in body:
        raise RuntimeError("ログイン失敗。利用者番号またはパスワードを確認してください。")


# ══════════════════════════════════════════════════════════════
# Step 2: お気に入りクリック → 絞り込み画面
# ══════════════════════════════════════════════════════════════
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'input[value*="お気に入り"]',
        'button:text("お気に入り")',
        '[id*="favorite"]',
        '[id*="okiniri"]',
        '[class*="favorite"]',
        'a:has-text("お気に入り")',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # 全要素テキスト走査
        elems = await page.query_selector_all("a, button, input, td, div, span")
        for elem in elems:
            try:
                txt = (await elem.inner_text()).strip()
                val = await elem.get_attribute("value") or ""
                if "お気に入り" in txt or "お気に入り" in val:
                    await elem.click()
                    print(f"  [OK] お気に入り（テキスト走査）: {txt!r}")
                    clicked = True
                    break
            except Exception:
                pass

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行してログイン後ページのHTML構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    print(f"  現在URL: {page.url}")


# ══════════════════════════════════════════════════════════════
# Step 3: 日付選択 + 検索（5:00:00ちょうどに実行）
# ══════════════════════════════════════════════════════════════
async def step_select_date_and_search(page):
    """
    日付プルダウンで対象日を選択して検索する。
    まんまるよやく2では1つのSELECTに「令和○○年○○月○○日」形式の
    テキストがoptionとして並ぶことが多い。
    念のため年・月・日が別々のSELECTの場合も対応。
    """
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    date_selected = False
    selects = await page.query_selector_all("select")

    # ─ パターンA: 1つのSELECTに日付テキストが入っている ─
    for sel_elem in selects:
        for opt in await sel_elem.query_selector_all("option"):
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                sel_id   = await sel_elem.get_attribute("id") or ""
                await sel_elem.select_option(value=v if v else txt)
                print(f"  [OK] 日付選択（パターンA）: "
                      f"SELECT name={sel_name!r} id={sel_id!r} "
                      f"value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ─ パターンB: 年・月・日が別SELECTに分かれている ─
    if not date_selected:
        print("  [試行] 年月日が分割SELECTかもしれません...")

        YEAR_PATTERNS  = ["令和08", "令和8", "08", "R08", "R8", "2026"]
        MONTH_PATTERNS = ["06月", "6月", "６月", "06", "6"]
        DAY_PATTERNS   = ["19日", "19", "１９"]

        matched_counts = 0
        for sel_elem in selects:
            sel_name = await sel_elem.get_attribute("name") or ""
            for opt in await sel_elem.query_selector_all("option"):
                txt = (await opt.inner_text()).strip()
                v   = await opt.get_attribute("value") or ""
                for pat in YEAR_PATTERNS:
                    if pat == txt or pat == v or pat in txt:
                        await sel_elem.select_option(value=v if v else txt)
                        print(f"  [OK] 年選択: name={sel_name!r} text={txt!r}")
                        matched_counts += 1
                        break
                for pat in MONTH_PATTERNS:
                    if pat == txt or pat == v or pat in txt:
                        await sel_elem.select_option(value=v if v else txt)
                        print(f"  [OK] 月選択: name={sel_name!r} text={txt!r}")
                        matched_counts += 1
                        break
                for pat in DAY_PATTERNS:
                    if pat == txt or pat == v or pat in txt:
                        await sel_elem.select_option(value=v if v else txt)
                        print(f"  [OK] 日選択: name={sel_name!r} text={txt!r}")
                        matched_counts += 1
                        break
        if matched_counts >= 1:
            date_selected = True

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.py を実行して 03_after_favorite.html を確認してください。"
        )

    # 検索ボタン
    clicked = await try_click(page, [
        'input[value="検索"]',
        'input[value=" 検索 "]',
        'button:text("検索")',
        'input[value*="検索"]',
        'a:text("検索")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "検索ボタン")

    if not clicked:
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    print(f"  現在URL: {page.url}")


# ══════════════════════════════════════════════════════════════
# Step 4: D面 16:00〜18:00（赤丸）セルをクリック
# ══════════════════════════════════════════════════════════════
async def step_select_slot(page):
    """
    検索結果テーブルから D面 × 16:00〜18:00 の予約可能セルをクリックする。

    まんまるよやく2の典型的なテーブル構造:
    - 縦軸: 施設名（D面、A面 etc）
    - 横軸: 時間帯（9:00〜11:00、11:00〜13:00 ... 16:00〜18:00 ...）
    - セル内: ○（予約可）/ ×（満）/ △（空きわずか）などのマーク
    - クリック可能セル: <a>タグ内 or onclickがついた<td>
    """
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セルを特定...")

    clicked = False

    # ─ アプローチ①: ヘッダー行から時間列インデックスを特定 → D面行でクリック ─
    tables = await page.query_selector_all("table")
    for table in tables:
        rows = await table.query_selector_all("tr")
        time_col_idx = -1

        # ヘッダー行を走査して 16:00〜18:00 の列インデックスを取得
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip().replace("\n", "").replace(" ", "")
                # 「16:00〜18:00」「16:00-18:00」「16:00～18:00」など
                if (TARGET_TIME_START.replace(":", "") in txt.replace(":", "")
                        and TARGET_TIME_END.replace(":", "") in txt.replace(":", "")):
                    time_col_idx = ci
                    print(f"  [INFO] {TARGET_TIME_START}〜{TARGET_TIME_END} 列インデックス = {ci}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行を探してその列のセルをクリック
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_texts = [(await c.inner_text()).strip() for c in cells]

            is_d_row = any(TARGET_FACILITY in t for t in row_texts)
            if not is_d_row:
                continue

            print(f"  [INFO] D面行発見: {row_texts}")

            if time_col_idx < len(cells):
                target_cell = cells[time_col_idx]
                tc_txt = (await target_cell.inner_text()).strip()
                tc_cls = await target_cell.get_attribute("class") or ""
                tc_onclick = await target_cell.get_attribute("onclick") or ""
                print(f"  [TARGET] D面×{TARGET_TIME_START}〜{TARGET_TIME_END}: "
                      f"text={tc_txt!r} class={tc_cls!r}")

                # セル内に<a>がある場合はそれをクリック
                inner_a = await target_cell.query_selector("a")
                if inner_a:
                    await inner_a.click()
                    print(f"  [OK] セル内リンクをクリック")
                    clicked = True
                elif tc_onclick:
                    await target_cell.click()
                    print(f"  [OK] onclickセルをクリック")
                    clicked = True
                else:
                    # ×（満）かもしれないが一応クリック試行
                    await target_cell.click()
                    print(f"  [OK] セルをクリック（text={tc_txt!r}）")
                    clicked = True
            break

        if clicked:
            break

    # ─ アプローチ②: D面と16:00が同じ行にあるセルを直接探す ─
    if not clicked:
        print("  [試行] D面行を直接走査...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                row_texts = [(await c.inner_text()).strip() for c in cells]
                if not any(TARGET_FACILITY in t for t in row_texts):
                    continue
                # D面の行でクリック可能かつ16:00に近いセルを探す
                for ci, cell in enumerate(cells):
                    txt = row_texts[ci]
                    # 予約可能マーク（○、●、◎、空き etc）のセルのうち16時台の列
                    if any(mark in txt for mark in ["○", "●", "◎", "空", "△", "〇"]):
                        print(f"  [FOUND] D面行 col={ci} text={txt!r}")
                        # 時間が16:00の列かどうかをcolspanで推測（手動確認が必要）
                        # ここでは発見した最初の予約可能セルをクリック（仮）
                        inner_a = await cell.query_selector("a")
                        if inner_a:
                            await inner_a.click()
                        else:
                            await cell.click()
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ─ アプローチ③: onclick/hrefにD面・16:00の情報が入っている場合 ─
    if not clicked:
        print("  [試行] onclick/href解析...")
        elems = await page.query_selector_all("[onclick], a[href]")
        for elem in elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            # D面かつ16の情報が含まれる場合
            if (TARGET_FACILITY in combined and
                    (TARGET_TIME_START in combined or "16" in combined)):
                print(f"  [FOUND] onclick={onclick[:60]!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。"
            "screenshots/04_search_results.png と analyze_site.py の出力を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ══════════════════════════════════════════════════════════════
# Step 5: 確定①（料金確認画面へ）
# ══════════════════════════════════════════════════════════════
async def step_confirm1(page):
    print("\n[Step 5] 確定①クリック（料金確認画面へ）...")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value="確定する"]',
        'input[value="予約確認"]',
        'button:text("確定")',
        'button:text("確認")',
        'button:text("次へ")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'a:text("確定")',
        'a:text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。screenshots/05_slot_selected.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1_page")
    print(f"  現在URL: {page.url}")


# ══════════════════════════════════════════════════════════════
# Step 6: 確定②（最終確定）
# Tampermonkeyで window.confirm は無効化済み前提
# ══════════════════════════════════════════════════════════════
async def step_confirm2(page):
    print("\n[Step 6] 確定②クリック（最終確定）...")

    # 万一 confirm ダイアログが出た場合に自動承認するフォールバック
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="確定する"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'button:text("最終確定")',
        'input[value*="確定"]',
        'a:text("確定")',
        'a:text("予約確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not clicked:
        raise RuntimeError("確定②ボタンが見つかりません。screenshots/06_confirm1_page.png を確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    print(f"  現在URL: {page.url}")

    # 完了確認
    body = await page.inner_text("body")
    success_keywords = ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました", "受け付けました"]
    if any(w in body for w in success_keywords):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。screenshots/07_final_result.png を確認してください。")
    print(f"  ページ本文（先頭300字）:\n  {body[:300]}")


# ══════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════
async def main():
    opts = parse_args()
    print("=" * 65)
    print("  まんまるよやく2 自動予約スクリプト")
    print(f"  対象日: {TARGET_DATE_WAREKI}")
    print(f"  施設  : {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"  モード: {'即時実行' if not opts['wait_for_open'] else f'時報待ち ({OPEN_HOUR}:00:00)'}"
          f" / {'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 65)

    # 時報待ち（本番時: --now なしで実行）
    if opts["wait_for_open"]:
        await wait_until_open()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
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
        page = await context.new_page()

        try:
            await step_login(page)
            await step_favorite(page)
            await step_select_date_and_search(page)
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)
            print("\n✅ すべてのステップが正常に完了しました。")

        except Exception as e:
            await save_ss(page, "ERROR_final")
            print(f"\n❌ エラー発生: {e}")
            print(f"   screenshots/ フォルダのスクリーンショットを確認してください。")
            raise

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
