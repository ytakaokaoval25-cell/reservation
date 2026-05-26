# まんまるよやく2 自動予約スクリプト

## ファイル構成

| ファイル | 役割 |
|---|---|
| `analyze_site.py` | サイト構造解析（各ステップのHTML/スクリーンショット保存） |
| `reserve.py` | 本番自動予約スクリプト |
| `requirements.txt` | 依存パッケージ |

---

## セットアップ

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## Step 1: 解析スクリプトで実際のセレクターを確認する

```bash
python analyze_site.py --headful
```

実行後、`analysis_output/` フォルダに以下が生成されます：

| ファイル | 内容 |
|---|---|
| `01_login_page.html/png` | ログインページ |
| `02_after_login.html/png` | ログイン後メニュー |
| `03_after_favorite.html/png` | お気に入り絞り込み画面 |
| `04_search_results.html/png` | 検索結果（予約表） |

コンソールに出力された `FORM / INPUT / SELECT / OPTION / TABLE` の情報でセレクターを確認し、
`reserve.py` の定数・セレクターリストを修正してください。

---

## Step 2: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

`screenshots/` フォルダに各ステップのスクリーンショットが保存されます。

---

## Step 3: 本番実行（5月19日 朝4:55頃に起動）

```bash
python reserve.py --headful
```

- 朝5:00:00 JST ぴったりまでミリ秒単位で待機
- 5:00:00 到達と同時に検索・予約処理を開始

サーバー/cronで実行する場合（ヘッドレス）:

```bash
python reserve.py
```

---

## 本番（7月分）への変更方法

`reserve.py` の上部定数を変更してください：

```python
# ── 本番用: 令和08年07月19日（2026-07-19） ──
TARGET_DATE_WAREKI = "令和08年07月19日"
TARGET_DATE_ALT_VALUES = [
    "20260719", "2026-07-19", "2026/07/19", "260719",
]
TARGET_DATE_ALT_TEXTS = [
    "令和08年07月19日", "令和8年7月19日",
    "令和０８年０７月１９日",
    "2026年07月19日", "2026/07/19",
]
```

---

## タイムゾーンについて

スクリプトは **JST（UTC+9）** を明示的に使用しています。
海外サーバーや時刻設定が異なる環境でも正確に5:00 JST を待ちます。

---

## トラブルシューティング

### セレクターが合わない場合
1. `analyze_site.py --headful` を実行
2. `analysis_output/*.html` をブラウザで開いて開発者ツールで確認
3. `reserve.py` の各 `try_click` / `try_fill` のセレクターリスト先頭に正しいセレクターを追加

### 日付が見つからない場合
- `analysis_output/03_after_favorite.html` で `<select>` タグと `<option>` を確認
- `TARGET_DATE_ALT_VALUES` / `TARGET_DATE_ALT_TEXTS` に実際のvalue/textを追加

### D面セルが見つからない場合
- `analysis_output/04_search_results.html` でテーブル構造を確認
- 実際のテーブル行・列の対応を確認して `step_select_slot()` を修正

### ダイアログが邪魔する場合
- `reserve.py` では `window.confirm = () => true` をJS注入済み
- Tampermonkeyスクリプトと合わせて二重対策済み
