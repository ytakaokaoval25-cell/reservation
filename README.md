# まんまるよやく2 自動予約スクリプト

対象: https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2  
施設: **D面 16:00〜18:00**  
練習日: **令和08年06月19日**  
本番: 令和08年07月XX日（6月19日 朝5:00 に開放）

---

## 環境セットアップ

```bash
pip install playwright
playwright install chromium
```

---

## ファイル構成

| ファイル | 役割 |
|---|---|
| `analyze_site.py` | サイト構造解析（HTML・スクリーンショットを analysis_output/ に保存） |
| `reserve.py` | 本番自動予約スクリプト |

---

## Step 1: まず解析スクリプトを実行する（必須）

```bash
python analyze_site.py
```

`analysis_output/` に以下が生成される：

| ファイル | 内容 |
|---|---|
| `01_login_page.*` | ログインページ |
| `02_after_login.*` | ログイン後メニュー |
| `03_favorite_filter.*` | お気に入り絞り込み画面 |
| `04_search_results.*` | 検索結果（予約表テーブル） |

コンソールに出力される **FORM / INPUT / SELECT / OPTION / TABLE** の情報で
`reserve.py` のセレクターが合っているか確認する。

---

## Step 2: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

`screenshots/` に各ステップのスクリーンショットが保存される。

---

## Step 3: 本番実行

**朝4:50〜4:55頃にターミナルで実行する（朝5:00:00 ちょうどに自動スタート）**

```bash
python reserve.py --headful
```

スクリプトが内部で朝5:00:00.000 まで精密に待機し、
時刻到達と同時に 検索 → スロット選択 → 確定①② を自動実行する。

ヘッドレス（サーバー・cron）の場合:

```bash
python reserve.py
```

---

## 本番（7月分）への変更方法

`reserve.py` 上部の定数を変更する：

```python
TARGET_DATE_WAREKI     = "令和08年07月XX日"   # 7月の目標日
TARGET_DATE_ALT_VALUES = ["2026XXXX", ...]    # value値（analyze_site.pyで確認）
TARGET_DATE_ALT_TEXTS  = ["令和08年07月XX日", ...]
```

---

## スクリプトの動作フロー

```
【4:50頃に起動】
  1. ログイン (step_login)
  2. お気に入りクリック → 絞り込み画面 (step_favorite)
         ↓  ここで待機
  3. [朝5:00:00.000 到達]
         ↓
  4. 日付プルダウンで令和08年06月19日 を選択 → 検索 (step_select_date_and_search)
  5. D面 16:00〜18:00（赤丸）セルをクリック (step_select_slot)
  6. 確定① クリック (step_confirm1)
  7. 確定② クリック (step_confirm2)  ← window.confirm は自動 true
```

---

## トラブルシューティング

### ログインできない
- `analyze_site.py` の `01_login_page.html` でフィールドの `name` 属性を確認
- `reserve.py` の `step_login()` の `try_fill` セレクターリストを修正

### 日付が見つからない
- `03_favorite_filter.html` の SELECT/OPTION の `value` / テキストを確認
- `TARGET_DATE_ALT_VALUES` / `TARGET_DATE_ALT_TEXTS` に実際の値を追加

### D面セルが見つからない
- `04_search_results.html` でテーブル構造を確認
- `analyze_site.py` の「D面 / 16:00 関連セル詳細」出力を参照
- `step_select_slot()` のアプローチ①②③を修正

### 確定ボタンが見つからない
- `05_slot_selected.html` / `06_confirm1.html` でボタンの `value` を確認
- `step_confirm1()` / `step_confirm2()` のセレクターリストを修正
