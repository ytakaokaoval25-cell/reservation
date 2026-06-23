# まんまるよやく2 自動予約スクリプト

## 環境セットアップ

```bash
pip install playwright
playwright install chromium
```

## ファイル構成

| ファイル | 役割 |
|---|---|
| `analyze_site.py` | サイト構造解析（各ステップのHTML/スクリーンショット保存） |
| `reserve.py` | 本番自動予約スクリプト |

---

## Step 1: まず解析スクリプトを実行してセレクターを確認する

```bash
python analyze_site.py
# ブラウザを見ながら確認したい場合
python analyze_site.py --headful
```

実行後、`analysis_output/` フォルダに以下が生成されます：

| ファイル | 内容 |
|---|---|
| `01_login_page.png/html` | ログインページ |
| `02_after_login.png/html` | ログイン後メニュー |
| `03_favorite_filter.png/html` | お気に入り絞り込み画面 |
| `04_search_results.png/html` | 検索結果（予約表） |

コンソール出力の `FORM / INPUT / SELECT / OPTION / CELL` の情報で実際のセレクターを確認し、
必要であれば `reserve.py` の定数・セレクターリストを修正してください。

---

## Step 2: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

`screenshots/` フォルダに各ステップのスクリーンショットが保存されます。
実際には予約確定まで進むので、**テスト時は確定②の直前でCtrl+Cするか、
`step_confirm2()` の呼び出しをコメントアウトしてください。**

---

## Step 3: 本番実行

7月分の予約開放日（朝5:00）の前日深夜〜当日早朝に起動してください：

```bash
# ブラウザを見ながら（推奨：初回）
python reserve.py --headful

# ヘッドレス（cronやサーバー実行）
python reserve.py
```

### タイムライン（最速化モード）

| 時刻 | 処理内容 |
|---|---|
| 4:58:30 頃 | ログイン実行 |
| 4:59:00 頃 | お気に入り→絞り込み画面へ移動 |
| 4:59:30 頃 | 日付プルダウン設定完了・待機 |
| **5:00:00.000** | **検索ボタンクリック** |
| 5:00:01〜 | D面 16:00〜18:00 セルクリック → 確定① → 確定② |

> **注意**: `PRE_LOGIN_SECONDS = 90` で事前開始タイミングを調整できます（デフォルト：90秒前）

---

## 本番（7月分）への変更方法

`reserve.py` 上部の定数を変更してください：

```python
# 例：令和08年07月15日を予約する場合
TARGET_DATE_WAREKI    = "令和08年07月15日"
TARGET_DATE_VALUE     = "20260715"
TARGET_DATE_ALT_VALUES = ["20260715", "2026-07-15", "2026/07/15", "260715"]
TARGET_DATE_ALT_TEXTS  = [
    "令和08年07月15日", "令和8年7月15日",
    "2026年07月15日", "2026/07/15",
]
```

---

## トラブルシューティング

### セレクターが合わない場合
1. `analyze_site.py` を実行して `analysis_output/*.html` をブラウザで開いて確認
2. `reserve.py` の各 `try_click` / `try_fill` のセレクターリストを修正

### 日付が見つからない場合
- `analyze_site.py` の「日付プルダウン詳細」コンソール出力を確認
- 実際の `value` 値と `text` 値を `TARGET_DATE_ALT_VALUES` / `TARGET_DATE_ALT_TEXTS` に追加

### D面セルが見つからない場合
- `analysis_output/04_search_results.html` をブラウザで開き、
  D面×16:00のセルの `class`・`onclick` 属性を確認
- `reserve.py` の `step_select_slot()` のアプローチ①②のセレクターを修正

### window.confirm ダイアログが出る場合
スクリプトは以下の2段階で対処済みです：
1. `context.add_init_script("window.confirm = () => true;")` — JS レベルで常に true
2. `page.on("dialog", ...)` — Playwright ダイアログハンドラで自動承認

Tampermonkey側でも無効化されている前提ですが、上記により Playwright 単体でも問題ありません。
