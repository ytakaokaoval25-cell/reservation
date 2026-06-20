"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用）
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

# ──────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日
# ★本番（7月分）に変更するときはここを書き換える
TARGET_DATE_WAREKI     = "令和08年06月19日"
TARGET_DATE_VALUE      = "20260619"
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "令和08年 06月19日", "令和 8年 6月19日",
    "2026年06月19日", "2026/06/19", "2026-06-19",
]

# 予約対象コート＆時間
TARGET_FACILITY  = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報待ち設定（本番）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# JST（UTC+9）
JST = datetime.timezone(datetime.timedelta(hours=9))

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# スクリーンショット保存先
SS_DIR = "screenshots"

# Chromium実行バイナリ（環境によって変更）
# Noneにすると playwright が自動で探す
CHROMIUM_EXECUTABLE = None
# ──────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"    not in args,
    }


async def wait_until_open():
    """朝5:00:00.000 JST まで精密待機（ミリ秒単位）"""
    print("[時報待ち] 朝5:00:00.000 JST まで待機します...")
    while True:
        now    = datetime.datetime.now(tz=JST)
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE,
            second=OPEN_SECOND, microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {now.strftime('%H:%M:%S.%f')} JST")
            return
        elif diff_sec > 300:
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            await asyncio.sleep(1)
        elif diff_sec > 0.1:
            await asyncio.sleep(0.05)
        else:
            # 最後の100ms以内: 1msごとにポーリング
            await asyncio.sleep(0.001)


async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"  [SS] {path}")


async def try_click(page, selectors: list[str], label: str, timeout: int = 5000) -> bool:
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
    print(f"  [FAIL] {label}: 該当要素なし")
    return False


async def try_fill(page, selectors: list[str], value: str, label: str, timeout: int = 5000) -> bool:
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
# Step 1: ログイン
# ──────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="userId"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid', '#userId', '#loginId',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")

    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        '#passwd', '#password',
    ], PASSWORD, "パスワード")

    await try_click(page, [
        'input[value="ログイン"]',
        'input[value="LOGIN"]',
        'input[value="ログイン "]',      # 末尾スペースがある場合
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
        'a:text("ログイン")',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 2: お気に入り → 絞り込み画面
# ──────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りをクリック...")
    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        'td:has-text("お気に入り") a',
        'td:has-text("お気に入り") input',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[href*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        # テキスト全走査フォールバック
        elems = await page.query_selector_all("a, button, input[type=button], input[type=submit]")
        for elem in elems:
            txt = (await elem.inner_text()).strip()
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（テキスト走査）: {txt!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.py を実行してセレクターを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 3: 日付選択 → 検索ボタン（5:00 到達後に実行）
# ──────────────────────────────────────────────
async def step_select_date(page):
    """日付プルダウンで令和08年06月19日を選択（検索ボタンは別関数）"""
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")
    await save_ss(page, "03b_before_date_select")

    # ── 方式A: 単一SELECTに日付がまとまっている場合 ────────────
    date_selected = False
    selects = await page.query_selector_all("select")

    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = (await opt.get_attribute("value") or "").strip()
            txt = (await opt.inner_text()).strip()
            if (any(t in txt for t in TARGET_DATE_ALT_TEXTS)
                    or v in TARGET_DATE_ALT_VALUES):
                sel_name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v) if v else await sel_elem.select_option(label=txt)
                print(f"  [OK] 日付選択(単一): name={sel_name!r} value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── 方式B: 年・月・日が別SELECTに分かれている場合 ──────────
    if not date_selected:
        print("  [試行] 年月日が分割SELECTの可能性あり...")
        year_patterns  = {"令和08", "令和8", "R08", "R8", "2026", "08", "8"}
        month_patterns = {"06", "6", "6月", "06月", "６月"}
        day_patterns   = {"19", "19日", "１９"}

        async def select_by_patterns(patterns, label):
            for sel_elem in await page.query_selector_all("select"):
                options = await sel_elem.query_selector_all("option")
                for opt in options:
                    v   = (await opt.get_attribute("value") or "").strip()
                    txt = (await opt.inner_text()).strip()
                    if v in patterns or txt in patterns or any(p in txt for p in patterns):
                        nm = await sel_elem.get_attribute("name") or ""
                        await sel_elem.select_option(value=v)
                        print(f"  [OK] {label}選択: name={nm!r} value={v!r} text={txt!r}")
                        return True
            return False

        y = await select_by_patterns(year_patterns, "年")
        m = await select_by_patterns(month_patterns, "月")
        d = await select_by_patterns(day_patterns, "日")
        date_selected = y and m and d

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
            "analyze_site.py を実行して実際の option value/text を確認してください。"
        )

    await save_ss(page, "04_date_selected")


async def step_search(page):
    """検索ボタンをクリック（5:00 到達直後に呼ぶ）"""
    print("\n[Step 4] 検索ボタンクリック...")
    await try_click(page, [
        'input[value="検索"]',
        'input[value="空き照会"]',
        'input[value="照会"]',
        'input[value="絞り込み"]',
        'input[value="表示"]',
        'button:text("検索")',
        'button:text("空き照会")',
        'a:text("検索")',
        'a:text("空き照会")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "検索ボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_search_results")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 4: D面 16:00〜18:00 セルをクリック
# ──────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 5] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} (赤丸) セル選択...")

    # ── アプローチ①: JS でテーブルを走査して行列交差点を特定 ────
    result = await page.evaluate(r"""
    () => {
        const facility = "D面";
        const timeStart = "16:00";
        const timeEnd   = "18:00";

        for (const table of document.querySelectorAll("table")) {
            const rows = [...table.querySelectorAll("tr")];
            let timeColIdx = -1;

            // --- ヘッダー行から時間の列インデックスを探す ---
            for (let ri = 0; ri < Math.min(5, rows.length); ri++) {
                const cells = [...rows[ri].querySelectorAll("td, th")];
                for (let ci = 0; ci < cells.length; ci++) {
                    const t = cells[ci].textContent.trim();
                    if (t.includes(timeStart) && t.includes(timeEnd)) {
                        timeColIdx = ci;
                        break;
                    }
                    // 「16:00」だけでも列として採用
                    if (t.startsWith(timeStart) || t === timeStart) {
                        timeColIdx = ci;
                    }
                }
                if (timeColIdx >= 0) break;
            }

            // --- D面 の行を探す ---
            for (let ri = 0; ri < rows.length; ri++) {
                const cells = [...rows[ri].querySelectorAll("td, th")];
                let dFaceIdx = -1;
                for (let ci = 0; ci < cells.length; ci++) {
                    const t = cells[ci].textContent.trim();
                    if (t.includes(facility) || t === "D" || t === "Ｄ面") {
                        dFaceIdx = ci;
                        break;
                    }
                }
                if (dFaceIdx < 0) continue;

                if (timeColIdx >= 0 && timeColIdx < cells.length) {
                    // 列インデックスが分かっている場合
                    const target = cells[timeColIdx];
                    const link   = target.querySelector("a, input[type=image], input[type=button]");
                    const info   = {
                        text:    target.textContent.trim(),
                        imgSrc:  target.querySelector("img")?.src || "",
                        hasLink: !!link,
                        href:    link?.href || link?.getAttribute("onclick") || "",
                    };
                    if (link) link.click();
                    else       target.click();
                    return { found: true, method: "header+row", info };
                } else {
                    // 時間列が特定できなかった場合: D面行から16:00のセルを探す
                    for (let ci = dFaceIdx + 1; ci < cells.length; ci++) {
                        const t = cells[ci].textContent.trim();
                        if (t.includes(timeStart) || t.includes("16")) {
                            const link = cells[ci].querySelector("a, input[type=image]");
                            if (link) link.click();
                            else      cells[ci].click();
                            return { found: true, method: "row-only", text: t };
                        }
                    }
                }
            }
        }
        return { found: false };
    }
    """)

    if result.get("found"):
        print(f"  [OK] セルクリック(JS): {result}")
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
        await save_ss(page, "06_slot_selected")
        print(f"  現在URL: {page.url}")
        return

    # ── アプローチ②: 時間が列ヘッダーではなく行ヘッダーの場合 ──
    print("  [試行②] 時間=行ヘッダー, 施設=列ヘッダー の形式を試す...")
    result2 = await page.evaluate(r"""
    () => {
        const facility  = "D面";
        const timeStart = "16:00";
        const timeEnd   = "18:00";

        for (const table of document.querySelectorAll("table")) {
            const rows = [...table.querySelectorAll("tr")];
            let facilityColIdx = -1;

            // ヘッダー行から D面 の列を探す
            for (let ri = 0; ri < Math.min(5, rows.length); ri++) {
                const cells = [...rows[ri].querySelectorAll("td, th")];
                for (let ci = 0; ci < cells.length; ci++) {
                    const t = cells[ci].textContent.trim();
                    if (t.includes(facility) || t === "D" || t === "Ｄ面") {
                        facilityColIdx = ci;
                        break;
                    }
                }
                if (facilityColIdx >= 0) break;
            }
            if (facilityColIdx < 0) continue;

            // 16:00〜18:00 の行を探す
            for (let ri = 0; ri < rows.length; ri++) {
                const cells = [...rows[ri].querySelectorAll("td, th")];
                let isTimeRow = false;
                for (let ci = 0; ci < cells.length; ci++) {
                    const t = cells[ci].textContent.trim();
                    if (t.includes(timeStart) && t.includes(timeEnd)) { isTimeRow = true; break; }
                    if (t.startsWith(timeStart)) { isTimeRow = true; break; }
                }
                if (!isTimeRow) continue;

                if (facilityColIdx < cells.length) {
                    const target = cells[facilityColIdx];
                    const link   = target.querySelector("a, input[type=image]");
                    if (link) link.click();
                    else      target.click();
                    return {
                        found: true, method: "col-header",
                        text:  target.textContent.trim(),
                        href:  link?.href || "",
                    };
                }
            }
        }
        return { found: false };
    }
    """)

    if result2.get("found"):
        print(f"  [OK] セルクリック(JS②): {result2}")
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
        await save_ss(page, "06_slot_selected")
        print(f"  現在URL: {page.url}")
        return

    # ── アプローチ③: onclick/href で D面 と 16 が両方含まれる要素 ──
    print("  [試行③] onclick/href からD面16:00を探す...")
    all_elems = await page.query_selector_all("[onclick], a[href]")
    for elem in all_elems:
        onclick = await elem.get_attribute("onclick") or ""
        href    = await elem.get_attribute("href") or ""
        txt     = (await elem.inner_text()).strip()
        combined = onclick + href + txt
        if ("D面" in combined or "d面" in combined.lower()) and "16" in combined:
            print(f"  [OK] onclick={onclick!r} href={href!r} text={txt!r}")
            await elem.click()
            await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
            await save_ss(page, "06_slot_selected")
            return

    await save_ss(page, "ERROR_slot_not_found")
    raise RuntimeError(
        f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。\n"
        "screenshots/05_search_results.png と analyze_site.py の出力でテーブル構造を確認してください。"
    )


# ──────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ──────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 6] 確定①クリック...")
    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value="予約する"]',
        'input[value="予約へ進む"]',
        'input[value="料金確認へ"]',
        'button:text("確定")',
        'button:text("確認")',
        'button:text("次へ")',
        'a:text("確定")',
        'a:text("次へ")',
        'a:text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン")

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。スクリーンショットを確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_confirm1")
    print(f"  現在URL: {page.url}")


# ──────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# ──────────────────────────────────────────────
async def step_confirm2(page):
    """
    Tampermonkey で window.confirm を無効化済みのため
    confirmダイアログは発火しない前提。
    万一来た場合の保険として dialog イベントで自動承認する。
    """
    print("\n[Step 7] 確定②クリック...")

    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

    clicked = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="確定"]',
        'input[value="最終確定"]',
        'input[value="予約を確定する"]',
        'button:text("予約確定")',
        'button:text("確定")',
        'a:text("予約確定")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン")

    if not clicked:
        raise RuntimeError("確定②ボタンが見つかりません。スクリーンショットを確認してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "08_final_result")
    print(f"  現在URL: {page.url}")

    body_text = await page.inner_text("body")
    if any(w in body_text for w in ["予約完了", "受付完了", "受付番号", "予約番号", "完了しました"]):
        print("\n✅ 予約完了を確認しました！")
    else:
        print("\n⚠️  完了メッセージが見つかりません。screenshots/08_final_result.png を確認してください。")
    print(f"  最終本文（先頭200字）: {body_text[:200]}")


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────
async def main():
    opts = parse_args()
    now_jst = datetime.datetime.now(tz=JST)

    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"現在時刻(JST): {now_jst.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00 JST)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

    # --- 時報待ち（ログイン完了後に5:00を迎える想定）---
    # Step3の検索ボタン直前で wait_until_open() を呼ぶ構成にしているため
    # ここでは待たない。ただし --now なしの場合、5分前以降の起動を推奨。

    launch_opts = dict(
        headless=opts["headless"],
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    if CHROMIUM_EXECUTABLE:
        launch_opts["executable_path"] = CHROMIUM_EXECUTABLE

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_opts)
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
            await step_select_date(page)

            # ── ★ 5:00:00.000 JST まで待機してから検索 ──────────
            if opts["wait_for_open"]:
                await wait_until_open()

            await step_search(page)
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
