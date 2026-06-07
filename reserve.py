#!/usr/bin/env python3
"""
まんまるよやく2 自動予約スクリプト
対象: D面 16:00〜18:00 / 令和08年06月19日（練習）→ 本番は07月分に変更

■ 使い方
  python reserve.py              # 朝5:00ぴったり待ちモード（本番）
  python reserve.py --now        # 即時実行（テスト用: 5AM待ち省略）
  python reserve.py --headful    # ブラウザ表示あり（デバッグ用）
  python reserve.py --now --headful

■ タイミング設計
  --now なし（本番モード）:
    1. ブラウザ即起動 → ログイン → お気に入りページ遷移（5AM前に完了）
    2. お気に入りページで 5:00:00.000 ぴったりまでミリ秒待機
    3. ページリロード → 日付選択 → 検索 → スロット選択 → 確定①② (5AM以降)

  ※ 5AMになってからブラウザを起動するのではなく、事前に準備してページで待機する設計

■ 準備
  pip install playwright
  playwright install chromium
"""

import asyncio
import datetime
import sys
import os
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# 予約対象日（令和08年06月19日 = 2026-06-19 で練習。本番は変更）
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日", "令和０８年０６月１９日",
    "2026年06月19日", "2026/06/19", "2026-06-19",
]
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19", "260619",
]

# 予約対象コート & 時間
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# 時報設定（本番）
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# タイムアウト（ミリ秒）
NAV_TIMEOUT  = 30_000
ELEM_TIMEOUT = 10_000

# スクリーンショット保存先
SS_DIR = "screenshots"
# ──────────────────────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


async def wait_until_open():
    """ミリ秒精度で朝5:00:00.000まで待機するタイマーループ"""
    print("[時報待ち] 朝5:00:00.000 まで待機します（お気に入りページで待機中）...")
    while True:
        now = datetime.datetime.now()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            print(f"[時報] 開始時刻到達: {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
            break
        elif diff_sec > 300:
            print(f"[時報待ち] あと {diff_sec:.0f}秒 ({diff_sec/60:.1f}分)...")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            await asyncio.sleep(1)
        elif diff_sec > 0.5:
            await asyncio.sleep(0.1)
        elif diff_sec > 0.05:
            await asyncio.sleep(0.01)
        else:
            await asyncio.sleep(0.001)


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
    print(f"  [FAIL] {label}: 該当要素なし")
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


# ────────────────────────────────────────────────────────────
# Step 1: ログイン
# ────────────────────────────────────────────────────────────
async def step_login(page):
    print("\n[Step 1] ログイン...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    await try_fill(page, [
        'input[name="userid"]',
        'input[name="user_id"]',
        'input[name="memberNo"]',
        'input[name="userno"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="id"]',
        '#userid', '#user_id', '#loginId',
        'form input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")

    await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[name="pw"]',
    ], PASSWORD, "パスワード")

    await try_click(page, [
        'input[value="ログイン"]',
        'input[value="ログインする"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("ログイン")',
    ], "ログインボタン")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    print(f"  現在URL: {page.url}")


# ────────────────────────────────────────────────────────────
# Step 2: お気に入りクリック → 絞り込み画面
# ────────────────────────────────────────────────────────────
async def step_favorite(page):
    print("\n[Step 2] お気に入りクリック...")

    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        'td:text("お気に入り") a',
        '[onclick*="okiniri"]',
        '[onclick*="favorite"]',
        '[class*="favorite"]',
        '[id*="favorite"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    if not clicked:
        elems = await page.query_selector_all("a, button, input[type=button], input[type=submit]")
        for elem in elems:
            txt = (await elem.inner_text()).strip()
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                print(f"  [OK] お気に入り（フォールバック）: {txt!r}")
                clicked = True
                break

    if not clicked:
        raise RuntimeError("お気に入りリンクが見つかりません。analyze_site.pyで解析してください。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    print(f"  現在URL: {page.url}")


# ────────────────────────────────────────────────────────────
# Step 3 (5AM後): 日付選択 → 検索
# JS直接操作を最優先にして最速実行
# ────────────────────────────────────────────────────────────
async def step_select_date_and_search(page):
    print(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI} → 検索")

    # ── アプローチA: JS経由（最速）──────────────────────────
    selected_val = await page.evaluate(
        """(altTexts, altValues) => {
            for (const sel of document.querySelectorAll('select')) {
                for (const opt of Array.from(sel.options)) {
                    const matched =
                        altTexts.some(t => opt.text.includes(t)) ||
                        altValues.some(v => opt.value === v);
                    if (matched) {
                        sel.value = opt.value;
                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                        return opt.value + '|' + opt.text.trim();
                    }
                }
            }
            return null;
        }""",
        TARGET_DATE_ALT_TEXTS,
        TARGET_DATE_ALT_VALUES,
    )

    if selected_val:
        print(f"  [OK] JS日付選択: {selected_val}")
        # フォームをJS送信（ボタンクリックより高速）
        submitted = await page.evaluate(
            """() => {
                const form = document.querySelector('form');
                if (form) { form.submit(); return true; }
                return false;
            }"""
        )
        if submitted:
            await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
        else:
            # submit()が使えない場合は検索ボタンをクリック
            await try_click(page, [
                'input[value="検索"]', 'button:text("検索")',
                'input[value*="検索"]', 'input[type="submit"]',
                'button[type="submit"]',
            ], "検索ボタン(JS送信失敗のフォールバック)")
            await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    else:
        # ── アプローチB: 分割SELECT（年・月・日が別の場合）──
        print("  [試行] 分割SELECTの可能性あり...")
        year_done = month_done = day_done = False
        selects = await page.query_selector_all("select")
        for sel_elem in selects:
            options = await sel_elem.query_selector_all("option")
            for opt in options:
                v = await opt.get_attribute("value") or ""
                t = (await opt.inner_text()).strip()
                if not year_done and any(p in t or p == v for p in ["令和08","令和8","2026","R08","R8"]):
                    await sel_elem.select_option(value=v or t)
                    print(f"  [OK] 年選択: {t!r}")
                    year_done = True
                    break
                if not month_done and any(p == t or p == v for p in ["06","6","６","06月","6月"]):
                    await sel_elem.select_option(value=v or t)
                    print(f"  [OK] 月選択: {t!r}")
                    month_done = True
                    break
                if not day_done and any(p == t or p == v for p in ["19","１９","19日"]):
                    await sel_elem.select_option(value=v or t)
                    print(f"  [OK] 日選択: {t!r}")
                    day_done = True
                    break

        if not (year_done or month_done or day_done):
            await save_ss(page, "ERROR_date_not_found")
            raise RuntimeError(
                f"日付 {TARGET_DATE_WAREKI} がプルダウンに見つかりません。"
                "analyze_site.py を実行してセレクターを確認してください。"
            )

        await try_click(page, [
            'input[value="検索"]', 'button:text("検索")',
            'input[value*="検索"]', 'input[type="submit"]',
            'button[type="submit"]',
        ], "検索ボタン")
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)

    await save_ss(page, "04_search_results")
    print(f"  現在URL: {page.url}")


# ────────────────────────────────────────────────────────────
# Step 4: D面 16:00〜18:00（赤丸）セルをクリック
# ────────────────────────────────────────────────────────────
async def step_select_slot(page):
    print(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}（赤丸）選択...")

    # ── アプローチA: JS一括処理（最速）──────────────────────
    result = await page.evaluate(
        """(facility, timeStart, timeEnd) => {
            const rows = Array.from(document.querySelectorAll('tr'));

            // ── ① ヘッダー行から 16:00〜18:00 列インデックスを特定 ──
            let timeColIdx = -1;
            for (const row of rows) {
                const cells = Array.from(row.querySelectorAll('td, th'));
                for (let ci = 0; ci < cells.length; ci++) {
                    const txt = cells[ci].textContent.trim();
                    if (txt.includes(timeStart) && (txt.includes(timeEnd) || txt.includes('18'))) {
                        timeColIdx = ci;
                        break;
                    }
                }
                if (timeColIdx >= 0) break;
            }

            // ── ② D面の行を探してターゲットセルをクリック ──
            for (const row of rows) {
                const cells = Array.from(row.querySelectorAll('td, th'));
                // D面が最初～2番目のセルに含まれる行を特定
                const isFacilityRow = cells.slice(0, 2).some(
                    c => c.textContent.trim().includes(facility)
                );
                if (!isFacilityRow) continue;

                let targetCell = null;
                if (timeColIdx >= 0 && timeColIdx < cells.length) {
                    targetCell = cells[timeColIdx];
                } else {
                    // 列インデックス不明の場合: 行内で○/赤丸/onclickを持つセルを探す
                    targetCell = cells.find(c => {
                        const txt = c.textContent.trim();
                        const cls = c.className;
                        const oc  = c.getAttribute('onclick') || '';
                        return (
                            txt === '○' || txt === '〇' || txt === '◯' || txt === '●' ||
                            cls.includes('maru') || cls.includes('enable') ||
                            cls.includes('open')  || cls.includes('available') ||
                            (oc !== '' && (oc.includes('16') || oc.includes('1600')))
                        );
                    }) || null;
                }

                if (!targetCell) continue;

                const cls = targetCell.className;
                const oc  = targetCell.getAttribute('onclick') || '';
                const txt = targetCell.textContent.trim();

                // 予約可能（赤丸）かどうか判定
                const isBookable = (
                    txt === '○' || txt === '〇' || txt === '◯' ||
                    cls.includes('maru') || cls.includes('enable') ||
                    cls.includes('open') || cls.includes('available') ||
                    cls.includes('red')  || oc !== ''
                );

                if (isBookable) {
                    const link = targetCell.querySelector('a');
                    if (link) { link.click(); return 'a>' + link.href; }
                    targetCell.click();
                    return `td: txt=${txt} cls=${cls} oc=${oc.substring(0,60)}`;
                }
            }

            // ── ③ onclickにD面+16を含む要素フォールバック ──
            for (const el of document.querySelectorAll('[onclick], a[href]')) {
                const oc   = el.getAttribute('onclick') || '';
                const href = el.getAttribute('href')    || '';
                const txt  = el.textContent.trim();
                const all  = oc + href + txt;
                if (all.includes('16') &&
                    (all.includes('D面') || all.toLowerCase().includes('d_') ||
                     all.toLowerCase().includes('d面'))) {
                    el.click();
                    return 'onclick fallback: ' + oc.substring(0, 60);
                }
            }
            return null;
        }""",
        TARGET_FACILITY,
        TARGET_TIME_START,
        TARGET_TIME_END,
    )

    if result:
        print(f"  [OK] JS経由でセルクリック: {result}")
    else:
        # ── アプローチB: Playwright経由のフォールバック ──────
        print("  [試行] Playwright経由でセル探索...")
        clicked = False
        tables = await page.query_selector_all("table")
        for table in tables:
            rows = await table.query_selector_all("tr")
            time_col_idx = -1

            for row in rows[:5]:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    txt = (await cell.inner_text()).strip()
                    if TARGET_TIME_START in txt:
                        time_col_idx = ci
                        break
                if time_col_idx >= 0:
                    break

            for row in rows:
                cells = await row.query_selector_all("td, th")
                for ci, cell in enumerate(cells):
                    if ci >= 2:
                        break
                    txt = (await cell.inner_text()).strip()
                    if TARGET_FACILITY not in txt:
                        continue
                    if time_col_idx >= 0 and time_col_idx < len(cells):
                        tgt = cells[time_col_idx]
                    else:
                        tgt = None
                        for c in cells:
                            ctxt = (await c.inner_text()).strip()
                            ccls = await c.get_attribute("class") or ""
                            if (ctxt in {"○", "〇", "◯"} or
                                    any(k in ccls for k in ["maru","open","enable","available"])):
                                tgt = c
                                break
                    if tgt:
                        tc_txt = (await tgt.inner_text()).strip()
                        print(f"  [FOUND] D面×16:00 text={tc_txt!r}")
                        await tgt.click()
                        clicked = True
                    break
                if clicked:
                    break
            if clicked:
                break

        if not clicked:
            await save_ss(page, "ERROR_slot_not_found")
            raise RuntimeError(
                "D面 16:00〜18:00 のセルが見つかりません。"
                "analyze_site.py を実行してテーブル構造を確認してください。"
            )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    print(f"  現在URL: {page.url}")


# ────────────────────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ）
# ────────────────────────────────────────────────────────────
async def step_confirm1(page):
    print("\n[Step 5] 確定①（料金確認画面へ）...")
    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value="次へ進む"]',
        'button:text("確定")',
        'button:text("次へ")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'a:text("確定")',
        'a:text("次へ")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①")

    if not clicked:
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1")
    print(f"  現在URL: {page.url}")


# ────────────────────────────────────────────────────────────
# Step 6: 確定②（最終確定）
# window.confirm は add_init_script + dialog handler で自動承認済み
# ────────────────────────────────────────────────────────────
async def step_confirm2(page):
    print("\n[Step 6] 確定②（最終確定）...")

    clicked = await try_click(page, [
        'input[value="確定"]',
        'input[value="予約確定"]',
        'input[value="最終確定"]',
        'input[value="この内容で予約する"]',
        'button:text("確定")',
        'button:text("予約確定")',
        'input[value*="確定"]',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②")

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


# ────────────────────────────────────────────────────────────
# メイン
# ────────────────────────────────────────────────────────────
async def main():
    opts = parse_args()
    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}  "
          f"施設: {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(5:00AM)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            viewport=None,
        )
        # ── window.confirm / alert を自動承認（Tampermonkey相当）──
        # add_init_script により、以降のすべてのページ読み込みで有効
        await context.add_init_script(
            "window.confirm = () => true;"
            "window.alert   = () => undefined;"
            "window.prompt  = (m, d) => (d !== undefined ? d : '');"
        )

        page = await context.new_page()
        # ダイアログイベントも念のため自動承認（二重対策）
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        try:
            # ── Step 1: ログイン（5AM前に完了） ──
            await step_login(page)

            # ── Step 2: お気に入り遷移（5AM前に完了） ──
            await step_favorite(page)

            # ── Step 3: 5:00:00 AM 待機（お気に入りページで待機）──
            if opts["wait_for_open"]:
                print("\n[待機] お気に入りページで 5:00:00 AM を待ちます...")
                await wait_until_open()
                # 5AM到達後ページをリロードして最新データを取得
                print("[リロード] 5:00AM 到達。ページを更新して最新の空き情報を取得します...")
                await page.reload(wait_until="networkidle", timeout=NAV_TIMEOUT)

            # ── Step 4: 日付選択 → 検索（5AM以降・最速実行）──
            await step_select_date_and_search(page)

            # ── Step 5: D面 16:00〜18:00 スロット選択 ──
            await step_select_slot(page)

            # ── Step 6: 確定① ──
            await step_confirm1(page)

            # ── Step 7: 確定②（最終確定）──
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
