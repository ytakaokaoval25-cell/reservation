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

# ──────────────────────────────────────────────
# タイムゾーン（日本標準時 UTC+9）
# サーバーのローカルタイムがUTCでも正しく動作する
# ──────────────────────────────────────────────
JST = datetime.timezone(datetime.timedelta(hours=9))

# ──────────────────────────────────────────────
# 設定値
# ──────────────────────────────────────────────
LOGIN_URL = "https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2"
USER_ID   = "12015873"
PASSWORD  = "0508"

# ── 予約対象日 ──────────────────────────────
# 練習: 令和08年06月19日（2026-06-19）
# 本番: 上の3変数を令和08年07月XX日の値に変更する
TARGET_DATE_WAREKI = "令和08年06月19日"
TARGET_DATE_VALUE  = "20260619"          # value属性が YYYYMMDD 形式の場合
TARGET_DATE_ALT_VALUES = [
    "20260619", "2026-06-19", "2026/06/19",
    "260619",   "60619",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年06月19日", "令和8年6月19日",
    "令和０８年０６月１９日", "R08.06.19",
    "2026年06月19日",   "2026/06/19",
]

# ── 予約対象施設 ─────────────────────────────
TARGET_FACILITY   = "D面"
TARGET_TIME_START = "16:00"
TARGET_TIME_END   = "18:00"

# ── 朝5時解禁タイミング（JST）────────────────
OPEN_HOUR   = 5
OPEN_MINUTE = 0
OPEN_SECOND = 0

# ── タイムアウト ─────────────────────────────
NAV_TIMEOUT  = 30_000   # ページ遷移
ELEM_TIMEOUT = 10_000   # 要素待機
FAST_TIMEOUT = 3_000    # 高速チェック用

# ── スクリーンショット保存先 ──────────────────
SS_DIR = "screenshots"
# ──────────────────────────────────────────────


def parse_args():
    args = sys.argv[1:]
    return {
        "headless":       "--headful" not in args,
        "wait_for_open":  "--now"     not in args,
    }


def now_jst() -> datetime.datetime:
    return datetime.datetime.now(JST)


def log(msg: str):
    ts = now_jst().strftime("%H:%M:%S.%f")[:-3]  # ミリ秒3桁まで
    print(f"[{ts}] {msg}")


# ──────────────────────────────────────────────
# 時報待ちロジック（ミリ秒精度）
# ──────────────────────────────────────────────
async def wait_until_open():
    """朝5:00:00.000 JST ぴったりまでミリ秒単位で待機"""
    log("=== 朝5:00:00.000 (JST) まで待機します ===")
    while True:
        now = now_jst()
        target = now.replace(
            hour=OPEN_HOUR, minute=OPEN_MINUTE, second=OPEN_SECOND, microsecond=0
        )
        diff_sec = (target - now).total_seconds()

        if diff_sec <= 0:
            # 朝5時を過ぎている → 翌日を待つ（通常は前日夜から起動しない想定だが念のため）
            log(f"注意: 既に目標時刻を過ぎています（{diff_sec:.3f}秒）。即座に開始します。")
            break

        if diff_sec > 300:
            log(f"待機中... あと {diff_sec/60:.1f}分 ({diff_sec:.0f}秒)")
            await asyncio.sleep(30)
        elif diff_sec > 10:
            await asyncio.sleep(1)
        elif diff_sec > 0.5:
            await asyncio.sleep(0.05)   # 50ms単位
        elif diff_sec > 0.05:
            await asyncio.sleep(0.005)  # 5ms単位
        else:
            await asyncio.sleep(0.001)  # 1ms単位（最終スパート）
            # diff が 0 以下になったら抜ける
            if (target - now_jst()).total_seconds() <= 0:
                break

    log(f"=== 目標時刻到達: {now_jst().strftime('%H:%M:%S.%f')} ===")


# ──────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────
async def save_ss(page, name: str):
    os.makedirs(SS_DIR, exist_ok=True)
    path = f"{SS_DIR}/{name}.png"
    await page.screenshot(path=path, full_page=True)
    log(f"  [SS] {path}")


async def try_click(page, selectors: list[str], label: str,
                    timeout: int = FAST_TIMEOUT) -> bool:
    """複数セレクターを試してクリック。成功したらTrueを返す。"""
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.click()
                log(f"  [OK] {label}: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            log(f"  [SKIP] {label} ({sel}): {e}")
    log(f"  [FAIL] {label}: 全セレクターで未発見")
    return False


async def try_fill(page, selectors: list[str], value: str,
                   label: str, timeout: int = FAST_TIMEOUT) -> bool:
    """複数セレクターを試して入力。成功したらTrueを返す。"""
    for sel in selectors:
        try:
            elem = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if elem:
                await elem.fill(value)
                log(f"  [OK] {label}入力: {sel}")
                return True
        except PWTimeout:
            pass
        except Exception as e:
            log(f"  [SKIP] {label} ({sel}): {e}")
    log(f"  [FAIL] {label}: 全セレクターで未発見")
    return False


# ──────────────────────────────────────────────
# Step 1: ログイン
# ──────────────────────────────────────────────
async def step_login(page):
    log("\n[Step 1] ログインページへ移動...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "01_login")

    # ── 利用者番号入力 ──
    # MNETシステムで確認されているフィールド名を優先順に列挙
    id_ok = await try_fill(page, [
        'input[name="userid"]',
        'input[name="userId"]',
        'input[name="user_id"]',
        'input[name="loginId"]',
        'input[name="login_id"]',
        'input[name="memberNo"]',
        'input[name="member_no"]',
        'input[name="userno"]',
        'input[name="riyoId"]',
        'input[name="riyoushaId"]',
        'input[id="userid"]',
        'input[id="userId"]',
        'input[id="loginId"]',
        # フォールバック: 最初のtextフィールド
        'form input[type="text"]:first-of-type',
        'input[type="text"]:first-of-type',
    ], USER_ID, "利用者番号")

    if not id_ok:
        await save_ss(page, "ERROR_login_id_field")
        raise RuntimeError(
            "利用者番号フィールドが見つかりません。"
            "analyze_site.pyを実行してフィールド名を確認してください。"
        )

    # ── パスワード入力 ──
    pw_ok = await try_fill(page, [
        'input[type="password"]',
        'input[name="passwd"]',
        'input[name="password"]',
        'input[name="pass"]',
        'input[name="userPw"]',
        'input[name="user_pw"]',
    ], PASSWORD, "パスワード")

    if not pw_ok:
        await save_ss(page, "ERROR_login_pw_field")
        raise RuntimeError("パスワードフィールドが見つかりません。")

    await save_ss(page, "01b_login_filled")

    # ── ログインボタン ──
    login_ok = await try_click(page, [
        'input[value="ログイン"]',
        'input[value="ログ イン"]',
        'button:text("ログイン")',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[name="submit"]',
        'a:text("ログイン")',
    ], "ログインボタン", timeout=ELEM_TIMEOUT)

    if not login_ok:
        await save_ss(page, "ERROR_login_button")
        raise RuntimeError("ログインボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "02_after_login")
    log(f"  現在URL: {page.url}")

    # ログイン失敗チェック
    body = await page.inner_text("body")
    if "パスワード" in body and ("違い" in body or "誤" in body or "エラー" in body):
        raise RuntimeError("ログイン失敗: パスワードまたは利用者番号が違います。")
    log("  ✅ ログイン成功")


# ──────────────────────────────────────────────
# Step 2: お気に入りクリック
# ──────────────────────────────────────────────
async def step_favorite(page):
    log("\n[Step 2] お気に入りをクリック...")

    # テキストベースのクリックを優先（最も安定）
    clicked = await try_click(page, [
        'a:text("お気に入り")',
        'a:text-is("お気に入り")',
        'input[value="お気に入り"]',
        'button:text("お気に入り")',
        'a:text-matches("お気に入り")',
        '[onclick*="favorite"]',
        '[onclick*="okiniri"]',
        '[onclick*="Favorite"]',
        'a[href*="fav"]',
        'a[href*="FAV"]',
        '[class*="fav"]',
        '[id*="fav"]',
    ], "お気に入りリンク", timeout=ELEM_TIMEOUT)

    # フォールバック: ページ内テキスト走査
    if not clicked:
        log("  [試行] テキスト走査でお気に入りを探索...")
        elems = await page.query_selector_all("a, button, input[type=button], input[type=submit]")
        for elem in elems:
            try:
                txt = (await elem.inner_text()).strip()
            except Exception:
                txt = ""
            val = await elem.get_attribute("value") or ""
            if "お気に入り" in txt or "お気に入り" in val:
                await elem.click()
                log(f"  [OK] お気に入り（テキスト走査）: text={txt!r}")
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_favorite")
        raise RuntimeError(
            "お気に入りリンクが見つかりません。"
            "analyze_site.pyを実行して02_after_login.htmlを確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "03_favorite_filter")
    log(f"  現在URL: {page.url}")
    log("  ✅ お気に入り絞り込み画面に遷移")


# ──────────────────────────────────────────────
# Step 3: 日付選択 → 検索（5:00:00 ちょうどに開始）
# ──────────────────────────────────────────────
async def step_select_date_and_search(page, wait_for_open: bool):
    log(f"\n[Step 3] 日付選択: {TARGET_DATE_WAREKI}")

    # ── 朝5時まで待機（ここが時報待ちの核心） ──
    if wait_for_open:
        await wait_until_open()

    # ── SELECT要素を全スキャン（統合型: 1つのSELECTで日付全体） ──
    date_selected = False
    selects = await page.query_selector_all("select")
    log(f"  SELECTボックス数: {len(selects)}")

    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            v   = await opt.get_attribute("value") or ""
            txt = (await opt.inner_text()).strip()

            if any(t in txt for t in TARGET_DATE_ALT_TEXTS) or v in TARGET_DATE_ALT_VALUES:
                sel_name = await sel_elem.get_attribute("name") or ""
                sel_id   = await sel_elem.get_attribute("id") or ""
                # value が空の場合はラベルで選択
                if v:
                    await sel_elem.select_option(value=v)
                else:
                    await sel_elem.select_option(label=txt)
                log(f"  [OK] 日付選択（統合型）: name={sel_name!r} id={sel_id!r} "
                    f"value={v!r} text={txt!r}")
                date_selected = True
                break
        if date_selected:
            break

    # ── 分割型（年 / 月 / 日 が別 SELECT）の場合 ──
    if not date_selected:
        log("  [試行] 年・月・日が分割SELECTの可能性あり...")
        year_patterns  = {"令和08", "令和8", "08", "2026", "R08", "R8", "８年", "8年"}
        month_patterns = {"06", "6", "6月", "06月", "６月", "６"}
        day_patterns   = {"19", "19日", "１９", "１９日"}

        year_ok  = _select_by_patterns(selects, year_patterns,  "年")
        month_ok = _select_by_patterns(selects, month_patterns, "月")
        day_ok   = _select_by_patterns(selects, day_patterns,   "日")
        date_selected = year_ok or month_ok or day_ok

    if not date_selected:
        await save_ss(page, "ERROR_date_not_found")
        raise RuntimeError(
            f"日付 [{TARGET_DATE_WAREKI}] がプルダウンに見つかりません。\n"
            "analyze_site.pyを実行して03_after_favorite.htmlの"
            "SELECTのvalue/textを確認してください。"
        )

    await save_ss(page, "03b_date_selected")

    # ── 検索ボタン ──
    search_ok = await try_click(page, [
        'input[value="検索"]',
        'input[value="検　索"]',
        'button:text("検索")',
        'input[value*="検索"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'a:text("検索")',
        'input[value="空き照会"]',
        'button:text("空き照会")',
    ], "検索ボタン", timeout=ELEM_TIMEOUT)

    if not search_ok:
        raise RuntimeError("検索ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "04_search_results")
    log(f"  現在URL: {page.url}")
    log("  ✅ 検索完了")


def _select_by_patterns(selects, patterns: set, label: str) -> bool:
    """（同期ヘルパー）SELECTを走査してパターン一致するOPTIONを選ぶ（非同期から呼ぶ用途には使えないので後述の非同期版で呼ぶ）"""
    # 実際の選択は非同期なので、この関数は下の _async_select_by_patterns で使う
    return False  # stub


async def _async_select_by_patterns(selects, patterns: set, label: str) -> bool:
    for sel_elem in selects:
        options = await sel_elem.query_selector_all("option")
        for opt in options:
            txt = (await opt.inner_text()).strip()
            v   = await opt.get_attribute("value") or ""
            if txt in patterns or v in patterns:
                sel_name = await sel_elem.get_attribute("name") or ""
                await sel_elem.select_option(value=v if v else txt)
                log(f"  [OK] {label}選択: name={sel_name!r} value={v!r} text={txt!r}")
                return True
    return False


# step_select_date_and_search の分割型を修正
async def _select_split_date(selects) -> bool:
    year_patterns  = {"令和08", "令和8", "08", "2026", "R08", "R8"}
    month_patterns = {"06", "6", "6月", "06月", "６"}
    day_patterns   = {"19", "19日", "１９"}

    y = await _async_select_by_patterns(selects, year_patterns,  "年")
    m = await _async_select_by_patterns(selects, month_patterns, "月")
    d = await _async_select_by_patterns(selects, day_patterns,   "日")
    return y or m or d


# ──────────────────────────────────────────────
# Step 4: D面 16:00〜18:00（赤丸）セルをクリック
# ──────────────────────────────────────────────
async def step_select_slot(page):
    log(f"\n[Step 4] {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} セルを検索...")

    clicked = False

    # ── アプローチ①: ヘッダー行から列インデックスを特定し、D面行と交差 ──
    tables = await page.query_selector_all("table")
    log(f"  テーブル数: {len(tables)}")

    for ti, table in enumerate(tables):
        rows = await table.query_selector_all("tr")
        if len(rows) < 2:
            continue

        # ヘッダー行から 16:00〜18:00 の列インデックスを探す
        time_col_idx = -1
        for row in rows[:5]:
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip().replace(" ", "").replace("\n", "")
                if TARGET_TIME_START in txt or "16〜18" in txt or "16～18" in txt:
                    time_col_idx = ci
                    log(f"  [INFO] TABLE[{ti}] 時間帯列: col={ci} text={txt!r}")
                    break
            if time_col_idx >= 0:
                break

        if time_col_idx < 0:
            continue

        # D面の行を探してそのtime_col_idxのセルをクリック
        for ri, row in enumerate(rows):
            cells = await row.query_selector_all("td, th")
            for ci, cell in enumerate(cells):
                txt = (await cell.inner_text()).strip()
                if TARGET_FACILITY in txt and ci < 3:  # 施設名は左3列以内にあるはず
                    log(f"  [INFO] D面行: TABLE[{ti}] ROW[{ri}] col={ci}")
                    if time_col_idx < len(cells):
                        target_cell = cells[time_col_idx]
                        tc_txt  = (await target_cell.inner_text()).strip()
                        tc_cls  = await target_cell.get_attribute("class") or ""
                        tc_on   = await target_cell.get_attribute("onclick") or ""
                        log(f"  [FOUND] セル: text={tc_txt!r} class={tc_cls!r}")
                        # 赤丸（予約可能）のセルか確認
                        # 空白・×・- は予約不可なので除外
                        if any(ng in tc_txt for ng in ["×", "✕", "－", "ー", "−"]):
                            log(f"  [SKIP] このセルは予約不可（{tc_txt!r}）")
                            break
                        await target_cell.click()
                        log(f"  [OK] D面 {TARGET_TIME_START}〜{TARGET_TIME_END} セルをクリック")
                        clicked = True
                    break
            if clicked:
                break
        if clicked:
            break

    # ── アプローチ②: D面行内でリンク/onclickを持つセルをスキャン ──
    if not clicked:
        log("  [試行] D面行のクリッカブルセルを全走査...")
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows:
                cells = await row.query_selector_all("td, th")
                row_texts = [
                    (await c.inner_text()).strip() for c in cells
                ]
                if TARGET_FACILITY not in row_texts:
                    continue
                log(f"  [INFO] D面行: {row_texts}")
                # D面行のセルのうち、時刻情報または赤丸クラスを持つものをクリック
                for ci, cell in enumerate(cells):
                    onclick = await cell.get_attribute("onclick") or ""
                    cls     = await cell.get_attribute("class") or ""
                    href_el = await cell.query_selector("a")
                    # クリッカブルかどうか判定
                    is_clickable = bool(onclick) or bool(href_el)
                    is_red       = ("red" in cls.lower() or "maru" in cls.lower()
                                    or "aki" in cls.lower() or "circle" in cls.lower())
                    if is_clickable or is_red:
                        # 列インデックスが16:00〜18:00付近か確認（最低限の検証）
                        txt = (await cell.inner_text()).strip()
                        if any(ng in txt for ng in ["×", "✕", "－"]):
                            continue
                        log(f"  [FOUND] D面クリッカブルセル[{ci}]: "
                            f"cls={cls!r} onclick={onclick[:60]!r}")
                        await cell.click()
                        clicked = True
                        break
                if clicked:
                    break
            if clicked:
                break

    # ── アプローチ③: onclick / href にD面+16の情報が含まれる要素 ──
    if not clicked:
        log("  [試行] onclick/href からD面16:00を探索...")
        all_elems = await page.query_selector_all("[onclick], a[href]")
        for elem in all_elems:
            onclick = await elem.get_attribute("onclick") or ""
            href    = await elem.get_attribute("href") or ""
            txt     = (await elem.inner_text()).strip()
            combined = onclick + href + txt
            if ("D面" in combined or "d面" in combined.lower()) and "16" in combined:
                log(f"  [FOUND] onclick={onclick[:80]!r} text={txt!r}")
                await elem.click()
                clicked = True
                break

    if not clicked:
        await save_ss(page, "ERROR_slot_not_found")
        raise RuntimeError(
            f"{TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END} のセルが見つかりません。\n"
            "analyze_site.pyを実行して04_search_results.htmlのテーブル構造を確認してください。"
        )

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "05_slot_selected")
    log(f"  現在URL: {page.url}")
    log("  ✅ 予約スロット選択完了")


# ──────────────────────────────────────────────
# Step 5: 確定①（料金確認画面へ進む）
# ──────────────────────────────────────────────
async def step_confirm1(page):
    log("\n[Step 5] 確定①クリック（料金確認画面へ）...")

    ok = await try_click(page, [
        'input[value="確定"]',
        'input[value="確　定"]',
        'input[value="確認"]',
        'input[value="次へ"]',
        'input[value="次　へ"]',
        'button:text("確定")',
        'button:text("確認")',
        'button:text("次へ")',
        'input[value*="確定"]',
        'input[value*="確認"]',
        'input[value*="次へ"]',
        'a:text("確定")',
        'a:text("確認")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定①ボタン", timeout=ELEM_TIMEOUT)

    if not ok:
        await save_ss(page, "ERROR_confirm1")
        raise RuntimeError("確定①ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "06_confirm1_page")
    log(f"  現在URL: {page.url}")
    log("  ✅ 確定①完了（料金確認画面）")


# ──────────────────────────────────────────────
# Step 6: 確定②（最終予約確定）
# ──────────────────────────────────────────────
async def step_confirm2(page):
    log("\n[Step 6] 確定②クリック（最終確定）...")

    # Tampermonkey で window.confirm 無効化済みだが、
    # Playwright 側でも念のためダイアログを自動承認するハンドラを設定
    async def _handle_dialog(dialog):
        log(f"  [dialog] type={dialog.type} msg={dialog.message!r} → 承認")
        await dialog.accept()

    page.on("dialog", _handle_dialog)

    # 確定②は料金確認後のページにある「予約確定」に相当するボタン
    ok = await try_click(page, [
        'input[value="予約確定"]',
        'input[value="予約する"]',
        'input[value="確定"]',
        'input[value="確　定"]',
        'input[value="最終確定"]',
        'button:text("予約確定")',
        'button:text("予約する")',
        'button:text("確定")',
        'input[value*="予約確定"]',
        'input[value*="予約する"]',
        'input[value*="確定"]',
        'a:text("予約確定")',
        'a:text("確定")',
        'input[type="submit"]',
        'button[type="submit"]',
    ], "確定②ボタン", timeout=ELEM_TIMEOUT)

    if not ok:
        await save_ss(page, "ERROR_confirm2")
        raise RuntimeError("確定②ボタンが見つかりません。")

    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
    await save_ss(page, "07_final_result")
    log(f"  現在URL: {page.url}")

    # 完了判定
    body = await page.inner_text("body")
    success_words = ["予約完了", "受付完了", "受付番号", "予約番号", "申込番号", "完了しました"]
    if any(w in body for w in success_words):
        log("  ✅ ✅ ✅  予約完了を確認しました！")
    else:
        log("  ⚠️  完了メッセージが未確認。07_final_result.pngを確認してください。")
    log(f"  最終ページ本文（先頭300字）:\n{body[:300]}")


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────
async def main():
    opts = parse_args()

    print("=" * 60)
    print("まんまるよやく2 自動予約スクリプト")
    print(f"対象日: {TARGET_DATE_WAREKI}")
    print(f"施設:   {TARGET_FACILITY} {TARGET_TIME_START}〜{TARGET_TIME_END}")
    print(f"モード: {'即時実行' if not opts['wait_for_open'] else '時報待ち(JST 5:00:00)'} / "
          f"{'ブラウザ表示あり' if not opts['headless'] else 'ヘッドレス'}")
    print(f"現在時刻(JST): {now_jst().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=opts["headless"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
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
        page = await context.new_page()

        try:
            await step_login(page)
            await step_favorite(page)
            await step_select_date_and_search(page, opts["wait_for_open"])
            await step_select_slot(page)
            await step_confirm1(page)
            await step_confirm2(page)
            log("\n✅ 全ステップ完了しました。")
        except Exception as e:
            await save_ss(page, "ERROR_final")
            log(f"\n❌ エラー発生: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
