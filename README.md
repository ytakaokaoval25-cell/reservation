# まんまるよやく2 自動予約スクリプト

銀河アリーナ（まんまるよやく2）のテニスコートD面 16:00〜18:00 を自動予約するスクリプトです。

> **重要**: このサイトは日本国内IPからのみアクセス可能です。**必ずローカルPCで実行してください。**

---

## ファイル構成

| ファイル | 役割 |
|---|---|
| `analyze_site.py` | ① サイト構造解析（最初に実行してセレクターを確認） |
| `reserve.py`      | ② 本番自動予約スクリプト |

---

## 環境セットアップ（初回のみ）

```bash
pip install playwright
playwright install chromium
```

---

## 手順1: 解析スクリプトで構造を確認する

```bash
python analyze_site.py
```

- ブラウザが立ち上がり、ログイン〜検索結果まで自動操作します
- `analysis_output/` フォルダにHTML・スクリーンショットを保存
- コンソールに全フォーム要素（INPUT/SELECT/BUTTON/FORM/リンク/テーブル）を出力

**確認ポイント:**
- ログインフォームの `input[name="?"]` は何か
- 日付SELECTの `name` 属性と、「令和08年06月19日」のoption `value` 値
- 検索結果テーブルのD面×16:00セルの `class` / `onclick` / `href` 属性

---

## 手順2: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

- `screenshots/` フォルダに各ステップのスクリーンショットを保存
- 実際に予約操作が走るので、確定②の直前で止めたい場合は `step_confirm2()` をコメントアウト

---

## 手順3: 本番実行（5月19日 朝4:55頃にセット）

```bash
python reserve.py --headful
```

動作フロー:
1. スクリプト起動直後から朝 **5:00:00.000 ぴったり**まで待機（ミリ秒精度）
2. 5時00分00秒到達と同時に検索・予約処理を開始
3. ログイン〜お気に入り〜日付選択〜検索〜セル選択〜確定①〜確定② の順に自動実行

ヘッドレスで実行（サーバー・タスクスケジューラー）:

```bash
python reserve.py
```

---

## 本番（7月分）への変更方法

`reserve.py` 上部の定数を書き換えてください:

```python
# 変更前（練習：6月19日）
TARGET_DATE_TEXTS  = ["令和08年06月19日", ...]
TARGET_DATE_VALUES = ["20260619", ...]

# 変更後（本番：7月XX日）
TARGET_DATE_TEXTS  = ["令和08年07月XX日", ...]
TARGET_DATE_VALUES = ["2026XXXX", ...]
```

---

## 実行オプション一覧

| オプション | 説明 |
|---|---|
| *(なし)* | 朝5:00:00まで待機してから実行（本番） |
| `--now` | 即時実行（テスト・デバッグ用） |
| `--headful` | ブラウザウィンドウを表示 |
| `--now --headful` | 即時実行＋ブラウザ表示（デバッグ最適） |

---

## Tampermonkeyとの連携

`window.confirm` はTampermonkeyで無効化済みの前提でコードを作成しています。  
万一ダイアログが発火した場合はPlaywright側で自動承認するフォールバックを実装済みです。

---

## トラブルシューティング

### セレクターが合わない場合
1. `analyze_site.py` を実行して `analysis_output/*.html` を確認
2. `reserve.py` の各 `try_click` / `try_fill` のセレクターリストを修正

### 日付が見つからない場合
- `analyze_site.py` 実行時のコンソール出力「日付プルダウン全optionを出力」を確認
- `TARGET_DATE_VALUES` / `TARGET_DATE_TEXTS` に実際のvalue/textを追加

### D面セルが見つからない場合
- `analysis_output/04_search_results.html` をブラウザで開きテーブル構造を確認
- `reserve.py` の `step_select_slot()` 内の条件を実際のclass/onclick値に合わせて修正

### SSL証明書エラー
- `ignore_https_errors=True` を設定済みのため通常は発生しません

---

## スクリーンショット保存先

| ファイル | タイミング |
|---|---|
| `screenshots/01_login.png` | ログインページ |
| `screenshots/02_after_login.png` | ログイン後メニュー |
| `screenshots/03_favorite_filter.png` | お気に入り絞り込み画面 |
| `screenshots/04_search_results.png` | 検索結果（予約表） |
| `screenshots/05_slot_selected.png` | D面×16:00セルクリック後 |
| `screenshots/06_confirm1.png` | 確定①（料金確認画面） |
| `screenshots/07_final_result.png` | 確定②後（完了画面） |
| `screenshots/ERROR_*.png` | エラー発生時 |
