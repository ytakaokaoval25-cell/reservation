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

## タイミング設計（重要）

```
04:50頃  スクリプト起動
          → ログイン
          → お気に入りクリック
          → 絞り込み画面で日付を選択（ここまで5時前に完了）
05:00:00 ← 検索ボタンをクリック（ミリ秒精度で待機）
05:00:xx   D面 16:00〜18:00 を選択
           確定① → 確定② → 予約完了
```

---

## Step 1: まず解析スクリプトを実行してセレクターを確認する

```bash
python analyze_site.py
```

実行後、`analysis_output/` フォルダに以下が生成されます：

| ファイル | 内容 |
|---|---|
| `01_login_page.html/png` | ログインページ |
| `02_after_login.html/png` | ログイン後メニュー |
| `03_after_favorite.html/png` | お気に入り絞り込み画面 |
| `04_search_results.html/png` | 検索結果（予約表） |

コンソールに出力された `FORM / INPUT / SELECT / OPTION / BUTTON / A` の情報で
セレクターを確認し、必要であれば `reserve.py` の定数・セレクターリストを修正してください。

---

## Step 2: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

`screenshots/` フォルダに各ステップのスクリーンショットが保存されます：

| ファイル | ステップ |
|---|---|
| `01_login.png` | ログインページ表示 |
| `02_after_login.png` | ログイン後メニュー |
| `03_favorite_filter.png` | お気に入り絞り込み画面 |
| `03b_date_selected.png` | 日付選択後 |
| `04_search_results.png` | 検索結果（予約表） |
| `05_slot_selected.png` | D面セルクリック後 |
| `06_confirm1.png` | 確定①後（料金確認） |
| `07_final_result.png` | 確定②後（最終完了） |

---

## Step 3: 本番実行（当日 朝4:50頃にスクリプト起動）

```bash
# ブラウザ表示あり（推奨: 最初は目視確認しながら実行）
python reserve.py --headful

# ヘッドレス（サーバー/cron向け）
python reserve.py
```

スクリプトは自動的に `5:00:00.000` まで待機し、
その瞬間に検索ボタンをクリックします。

---

## 本番（7月分）への変更方法

`reserve.py` の上部定数を変更してください：

```python
TARGET_DATE_WAREKI    = "令和08年07月XX日"
TARGET_DATE_ALT_VALUES = ["2026XXXX", "2026-07-XX", ...]
TARGET_DATE_ALT_TEXTS  = ["令和08年07月XX日", ...]
TARGET_YEAR_VALUES     = ["令和08", "08", "2026", ...]
TARGET_MONTH_VALUES    = ["07", "7", "７月", ...]
TARGET_DAY_VALUES      = ["XX", ...]
```

---

## トラブルシューティング

### セレクターが合わない場合
1. `python analyze_site.py` を実行して `analysis_output/*.html` を確認
2. `reserve.py` 内の各 `try_click` / `try_fill` のセレクターリストを修正

### 日付が見つからない場合
- `analyze_site.py` の「日付プルダウン詳細解析」出力で `value=` と `text=` を確認
- `TARGET_DATE_ALT_VALUES` / `TARGET_DATE_ALT_TEXTS` に実際の値を追加

### D面セルが見つからない場合
- `analysis_output/04_search_results.html` でテーブル構造を確認
- `reserve.py` の `step_select_slot()` 内のアプローチ①〜③のロジックを修正

### window.confirm が邪魔をする場合
- `reserve.py` は `add_init_script` で全ページの `window.confirm` を無効化済み
- さらに `page.on("dialog", ...)` でダイアログも自動承認する

### 接続エラー / SSL エラーが出る場合
```python
# context 作成時に以下が設定されているか確認
ignore_https_errors=True
```
