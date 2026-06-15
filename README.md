# まんまるよやく2 自動予約スクリプト

対象施設: 銀のコート D面  
予約フロー: ログイン → お気に入り → 日付選択・検索 → D面16:00〜18:00クリック → 確定①② 

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
| `analyze_site.py` | サイト構造解析（実際のHTML・スクリーンショットを保存してセレクターを確認） |
| `reserve.py` | 本番自動予約スクリプト（時報待ち対応） |

---

## Step 1: まず解析スクリプトを実行してセレクターを確認

**ローカルPC（サイトにアクセスできる環境）で実行してください。**

```bash
python analyze_site.py
```

実行後、`analysis_output/` に以下が生成されます：

| ファイル | 内容 |
|---|---|
| `01_login_page.html/png` | ログインページのHTML・スクショ |
| `02_after_login.html/png` | ログイン後メニュー |
| `03_after_favorite.html/png` | お気に入り絞り込み画面 |
| `04_search_results.html/png` | 検索結果（予約表グリッド） |

コンソール出力の `INPUT / SELECT / OPTION / BTN` 情報でセレクターを確認し、
必要に応じて `reserve.py` の定数・セレクターリストを修正してください。

---

## Step 2: テスト実行（即時・ブラウザ表示あり）

```bash
# ブラウザを表示しながら即時実行（動作確認）
python reserve.py --now --headful

# ヘッドレスで即時実行
python reserve.py --now
```

`screenshots/` に各ステップのスクリーンショットが保存されます。

---

## Step 3: 本番実行（5月19日 朝4:50頃に起動してセット）

```bash
# 5:00:00 ぴったりまでミリ秒待機（ヘッドレス）
python reserve.py

# ブラウザ表示あり（監視しながら実行）
python reserve.py --headful
```

- 朝5:00:00.000 到達と同時に検索・予約処理を自動開始
- ブラウザは起動済みの状態で待機するため、開場後すぐに操作可能

---

## Step 4: 本番（7月分・8月分）への変更

`reserve.py` 上部の定数を変更するだけで対応できます：

```python
# 例: 7月19日に変更する場合
TARGET_DATE_TEXTS = [
    "令和08年07月19日",
    "令和8年7月19日",
    "2026年07月19日",
    "2026/07/19",
]
TARGET_DATE_VALUES = ["20260719", "2026-07-19", "260719"]

TARGET_YEAR_TEXTS  = ["令和08年", "令和8年", "2026年", "2026", "08", "8"]
TARGET_MONTH_TEXTS = ["07月", "7月", "7", "07"]
TARGET_DAY_TEXTS   = ["19日", "19"]
```

---

## トラブルシューティング

### ログイン失敗（利用者番号フィールドが見つからない）
1. `analyze_site.py` を実行し、`02_after_login.html` を確認
2. コンソールの `INPUT` 行から `name=` 属性を特定
3. `reserve.py` の `step_login()` のセレクターリストに追加

### 日付が見つからない（SELECT のオプションが合わない）
1. `analyze_site.py` のコンソール出力「全SELECT要素の詳細」を確認
2. 表示されている `value=` と `text=` を `TARGET_DATE_TEXTS` / `TARGET_DATE_VALUES` に追加
3. 年・月・日が別SELECTの場合は `TARGET_YEAR_TEXTS` 等を実際の値に合わせる

### D面セルが見つからない（検索結果テーブル構造が不明）
1. `analysis_output/04_search_results.html` をブラウザで開く
2. D面16:00のセルを右クリック → 検証 でHTMLを確認
3. `reserve.py` の `step_select_slot()` のセレクターを修正
   - `onclick` 属性があればアプローチ③が有効
   - テーブルのD面行が分かればアプローチ①②が有効

### window.confirm が邪魔をする
- `reserve.py` の `step_confirm2()` で Playwright の `dialog` ハンドラーが自動承認します
- Tampermonkey で `window.confirm = () => true` を設定済みであれば二重対策済み

### SSL証明書エラー
- `ignore_https_errors=True` で対処済みです（スクリプト内設定済み）
