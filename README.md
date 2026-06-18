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
| `analyze_site.py` | サイト構造解析（各ステップのHTML/スクリーンショット保存） |
| `reserve.py` | 本番自動予約スクリプト |

---

## 必ず最初にやること：解析スクリプトで実際のセレクターを確認する

```bash
python analyze_site.py --headful
```

実行後、`analysis_output/` フォルダに以下が生成されます：

| ファイル | 内容 |
|---|---|
| `01_login_page.html/png` | ログインページ |
| `02_after_login.html/png` | ログイン後メニュー |
| `03_after_favorite.html/png` | お気に入り絞り込み画面 |
| `04_search_results.html/png` | 検索結果（予約表）|

コンソール出力の `INPUT / SELECT / BUTTON / LINK` 情報で正確なセレクターを確認し、
必要なら `reserve.py` の定数・セレクターリストを修正してください。

### 特に確認すること

1. **ログインフォーム**（`01_login_page.html`）
   - 利用者番号のフィールド `name=` 属性（例: `loginno`, `userid`, `riyousyano`）
   - パスワードのフィールド `name=` 属性（例: `passwd`, `password`）

2. **日付プルダウン**（`03_after_favorite.html`）
   - SELECT の `name=` 属性
   - 「令和08年06月19日」に対応する OPTION の `value=` 値

3. **D面 16:00〜18:00 のセル**（`04_search_results.html`）
   - D面行のどの列が16:00〜18:00か
   - セルの `class=`, `onclick=`, または内部 `<a>` の `href=`

---

## Step 2: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

各ステップのスクリーンショットが `screenshots/` フォルダに保存されます。
エラーが出た場合は `screenshots/ERROR_*.png` を確認してください。

---

## Step 3: 本番実行（6月19日 朝4:55頃にコマンドを打ってスタンバイ）

```bash
python reserve.py --headful
```

- 朝5:00:00.000 ぴったりまでミリ秒単位でスリープしながら待機
- 5:00:00 到達と同時に検索・予約処理を自動開始

サーバー・cronで動かす場合（ヘッドレス）：
```bash
python reserve.py
```

---

## 実行フロー

```
ログイン（ID: 12015873 / PW: 0508）
  ↓
お気に入りクリック → 絞り込み画面
  ↓
令和08年06月19日 をプルダウンで選択 → 検索
  ↓
D面 × 16:00〜18:00（赤丸）セルをクリック
  ↓
確定①（料金確認画面）
  ↓
確定②（最終確定）← window.confirm は Tampermonkey/JS で無効化済み想定
  ↓
予約完了
```

---

## 本番（7月分）への変更方法

`reserve.py` の上部定数を変更：

```python
TARGET_DATE_WAREKI     = "令和08年07月XX日"
TARGET_DATE_ALT_VALUES = ["2026XXXX", "2026-07-XX", ...]
TARGET_DATE_ALT_TEXTS  = ["令和08年07月XX日", ...]
```

実際のOPTION value は `analyze_site.py` の出力で確認してください。

---

## トラブルシューティング

### ログインできない
- `analysis_output/01_login_page.html` で `<input>` の `name=` 属性を確認
- `reserve.py` の `step_login()` 内セレクターリストに追加

### 日付が選択されない
- `analysis_output/03_after_favorite.html` で `<select>` と `<option>` を確認
- `TARGET_DATE_ALT_VALUES` / `TARGET_DATE_ALT_TEXTS` に実際の値を追加

### D面セルがクリックされない
- `analysis_output/04_search_results.html` でテーブル構造を確認
- セルに `onclick` があるか、内部に `<a>` リンクがあるかを確認

### 確定ボタンが押せない
- `screenshots/05_slot_selected.png` または `06_confirm1.png` を確認
- ボタンの `value=` または `text=` を確認して `reserve.py` に追加
