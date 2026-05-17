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
```

実行後、`analysis_output/` フォルダに以下が生成されます：

- `01_login_page.html/png` — ログインページ
- `02_after_login.html/png` — ログイン後メニュー
- `03_after_favorite.html/png` — お気に入り絞り込み画面
- `04_search_results.html/png` — 検索結果（予約表）

コンソールに出力された `FORM / INPUT / SELECT / OPTION` の情報でセレクターを確認し、
必要であれば `reserve.py` の定数・セレクターリストを修正してください。

---

## Step 2: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

`screenshots/` フォルダに各ステップのスクリーンショットが保存されます。

---

## Step 3: 本番実行（5月19日 朝4:55頃にセット）

```bash
python reserve.py --headful
```

- 朝5:00:00 ぴったりまでミリ秒単位で待機
- 5:00:00 到達と同時に検索・予約処理を開始

ヘッドレスで実行する場合（サーバー/cronなど）:

```bash
python reserve.py
```

---

## 本番（7月分）への変更方法

`reserve.py` の上部定数を変更してください：

```python
TARGET_DATE_WAREKI    = "令和08年07月XX日"   # 7月の目標日に変更
TARGET_DATE_VALUE     = "2026XXXX"           # 対応するvalue値
TARGET_DATE_ALT_VALUES = ["2026XXXX", ...]   # 同上
TARGET_DATE_ALT_TEXTS  = ["令和08年07月XX日", ...]
```

---

## トラブルシューティング

### セレクターが合わない場合
1. `analyze_site.py` を実行して `analysis_output/*.html` を確認
2. `reserve.py` の各 `try_click` / `try_fill` のセレクターリストを修正

### 日付が見つからない場合
- `analyze_site.py` の「日付プルダウン詳細解析」出力を確認
- `TARGET_DATE_ALT_VALUES` / `TARGET_DATE_ALT_TEXTS` に実際のvalue/textを追加

### D面セルが見つからない場合
- `analysis_output/04_search_results.html` でテーブル構造を確認
- `reserve.py` の `step_select_slot()` 内のアプローチ②③を修正
