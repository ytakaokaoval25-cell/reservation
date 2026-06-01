# まんまるよやく2 自動予約スクリプト

## 環境セットアップ

```bash
pip install playwright
playwright install chromium
```

---

## ファイル構成

| ファイル | 役割 |
|---|---|
| `analyze_site.py` | **先に実行**。全ステップのHTML/スクリーンショット保存と推奨セレクター出力 |
| `reserve.py`      | 本番自動予約スクリプト（時報待ちロジック内蔵） |

---

## ステップ①: まず解析スクリプトを実行する

```bash
python analyze_site.py
```

`analysis_output/` に以下が生成されます:

| ファイル | 内容 |
|---|---|
| `01_login_page.html/png` | ログインページ |
| `02_after_login.html/png` | ログイン後メニュー |
| `03_after_favorite.html/png` | お気に入り絞り込み画面 |
| `04_search_results.html/png` | 検索結果（予約カレンダー） |
| `selectors_report.txt` | **推奨セレクター一覧** |

コンソールには `INPUT / SELECT / OPTION / TABLE` の詳細が出力されます。  
これを見て `reserve.py` の定数・セレクターが合っているか確認してください。

---

## ステップ②: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

`screenshots/` に各ステップのスクリーンショットが保存されます。  
エラーが出た場合は `ERROR_*.png/html` を確認してください。

---

## ステップ③: 本番実行（朝4:55頃にセット）

```bash
# ヘッドレス（サーバー・cron向け）
python reserve.py

# ブラウザ表示あり（目視確認しながら）
python reserve.py --headful
```

- **朝5:00:00.000 JST（日本標準時）ぴったり**まで、ミリ秒単位で待機
- 5:00:00 到達と同時に検索・予約処理を開始
- タイムゾーンはスクリプト内で `UTC+9` を明示しているため、  
  サーバーのローカルタイムがUTCでも正確に動作します

---

## 本番（7月分）への変更方法

`reserve.py` 冒頭の定数を変更してください:

```python
TARGET_DATE_WAREKI     = "令和08年07月XX日"     # 7月の予約日
TARGET_DATE_VALUE      = "20260719"             # 対応するvalue値（YYYYMMDDなど）
TARGET_DATE_ALT_VALUES = ["20260719", ...]
TARGET_DATE_ALT_TEXTS  = ["令和08年07月19日", ...]
```

---

## トラブルシューティング

### ログインできない
- `analyze_site.py` を実行し `01_login_page.html` でフィールド `name` 属性を確認
- `reserve.py` の `step_login()` 内のセレクターリストに追加

### 日付が見つからない
- `analysis_output/selectors_report.txt` の `[日付セレクト候補]` セクションを確認
- `reserve.py` の `TARGET_DATE_ALT_VALUES` / `TARGET_DATE_ALT_TEXTS` に実際の値を追加

### D面セルが見つからない
- `analysis_output/04_search_results.html` でテーブル構造を確認
- コンソールの `--- D面 または 16:00 を含むセル ---` 出力を確認
- `reserve.py` の `step_select_slot()` のアプローチ②③内のセレクターを修正

### 確定①/②ボタンが見つからない
- `screenshots/05_slot_selected.html` を確認してボタンの `value` または `text` を特定
- `step_confirm1()` / `step_confirm2()` のセレクターリストに追加

---

## タイムライン（本番想定）

| 時刻 | 操作 |
|---|---|
| 4:55 頃 | スクリプト起動、時報待ち開始 |
| 4:59:50 | ログイン・お気に入りクリックを事前実行 |
| 5:00:00.000 | 日付選択→検索→セル選択→確定①→確定② を最速実行 |
