# まんまるよやく2 自動予約スクリプト

対象サイト: https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2  
目的: D面 16:00〜18:00 を朝5:00:00.000 ちょうどに予約確定する

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
| `analyze_site.py` | サイト構造解析（HTML・スクリーンショット保存） |
| `reserve.py` | 本番自動予約スクリプト |

---

## 実行フロー（重要）

```
スクリプト起動（4:55頃推奨）
    ↓
Step 1: ログイン
    ↓
Step 2: お気に入りをクリック → 絞り込み画面へ
    ↓
⏰ 朝 5:00:00.000 まで 1ms 単位でビジーウェイト
    ↓ ← サイトが5:00に更新（新日付追加）
Step 3: 日付選択 → 検索クリック（最速）
    ↓
Step 4: D面 16:00〜18:00 の赤丸セルをクリック
    ↓
Step 5: 確定①（料金確認画面へ）
    ↓
Step 6: 確定②（最終確定）← window.confirm は無効化済み前提
```

**ポイント**: ログインとお気に入り画面への移動は5:00 AM前に完了させ、
サイト更新と同時に日付選択・検索を実行することで最速予約を実現します。

---

## Step 1: 解析スクリプトで実際のセレクターを確認する

本番前に一度実行してください（実際にログイン・操作します）。

```bash
python analyze_site.py
```

`analysis_output/` フォルダに以下が生成されます：

| ファイル | 内容 |
|---|---|
| `01_login_page.html/png` | ログインページのHTML・スクリーンショット |
| `02_after_login.html/png` | ログイン後メニュー |
| `03_after_favorite.html/png` | お気に入り絞り込み画面 |
| `04_search_results.html/png` | 検索結果（予約表） |
| `console_output.txt` | 全フォーム要素・SELECT・OPTIONS の詳細ログ |

`console_output.txt` に出力された `OPTION value=...` の実際の値を確認し、
必要であれば `reserve.py` の定数を修正してください。

---

## Step 2: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

`screenshots/` フォルダに各ステップのスクリーンショットが保存されます。  
エラーが出た場合は `screenshots/ERROR_*.png` を確認してください。

---

## Step 3: 本番実行（6月19日 朝4:55頃に起動）

```bash
# ブラウザ表示あり（推奨・状況確認できる）
python reserve.py --headful

# ヘッドレス（サーバー・cron 等）
python reserve.py
```

- 朝 5:00:00.000 ぴったりまでミリ秒単位で待機します
- 到達と同時に日付選択 → 検索クリックを実行します

---

## 本番（8月分）への変更方法

`reserve.py` 上部の定数を変更してください：

```python
TARGET_DATE_WAREKI = "令和08年08月XX日"   # 8月の目標日に変更

TARGET_DATE_VALUES = [
    "20260819",          # ← 実際の value を analyze_site.py で確認して入れる
    "2026-08-19",
]
TARGET_DATE_TEXTS = [
    "令和08年08月19日",   # ← 実際の text を confirm
]
```

---

## トラブルシューティング

### ログインできない
1. `analysis_output/01_login_page.html` でフォームの `name` 属性を確認
2. `reserve.py` の `step_login()` のセレクターリストに正しい `name` を追加

### お気に入りが見つからない
1. `analysis_output/02_after_login.html` でメニューのリンクテキストを確認
2. `reserve.py` の `step_favorite()` のセレクターリストを修正

### 日付が見つからない
1. `analysis_output/console_output.txt` の「日付プルダウン詳細解析」を確認
2. `TARGET_DATE_VALUES` / `TARGET_DATE_TEXTS` に実際の value / text を追加
3. 年・月・日が別 SELECT の場合: `TARGET_YEAR_VALUES` 等を確認

### D面セルが見つからない
1. `analysis_output/04_search_results.html` でテーブル構造を確認
2. `screenshots/04_search_results.png` で画面を目視確認
3. `reserve.py` の `step_select_slot()` を修正（アプローチ①〜③を参照）

### window.confirm が出てしまう
- `reserve.py` の `context.add_init_script` で `window.confirm = () => true` を設定済み
- Tampermonkey との二重対策になっています
