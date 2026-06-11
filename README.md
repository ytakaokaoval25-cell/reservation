# まんまるよやく2 自動予約スクリプト

対象施設：D面 16:00〜18:00  
練習：令和08年06月19日 / 本番：令和08年07月分（6月19日朝5時に開放）

---

## 環境セットアップ

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## ファイル構成

| ファイル | 役割 |
|---|---|
| `analyze_site.py` | サイト構造解析（各ステップのHTML/スクリーンショット保存） |
| `reserve.py` | 本番自動予約スクリプト |
| `requirements.txt` | Python依存パッケージ |

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
| `01_login_page.html/png` | ログインページ |
| `02_after_login.html/png` | ログイン後メニュー |
| `03_after_favorite.html/png` | お気に入り絞り込み画面 |
| `04_search_results.html/png` | 検索結果（予約表） |

ターミナルには以下が出力されます：
- 全INPUT要素の `name` / `id` / `type` / `value`
- 全SELECT要素の `name` / `id` と全OPTIONの `value` / テキスト
- テーブルの行・列構造と各セルの `class` / `onclick` / リンク先
- 「D面」「16:00」を含むセルの詳細

---

## Step 2: セレクターを確認・修正する

`analyze_site.py` の出力を見て、`reserve.py` の定数部分を修正します。

### ログインフォーム

出力例：
```
INPUT  type=text       name='userid'   id='userid'
INPUT  type=password   name='passwd'   id='passwd'
BUTTON type=submit     value='ログイン'
```

`reserve.py` の `try_fill` / `try_click` リストの先頭に実際のセレクターを追加してください。

### 日付プルダウン

**パターンA（1つのSELECTに全日付）：**
```
SELECT name='yoyaku_date' id=''  (30件)
  value='20260619'  text='令和08年06月19日'
```
→ `TARGET_DATE_VALUE = "20260619"` を確認

**パターンB（年・月・日が別SELECT）：**
```
SELECT name='year'   option value='2026'  text='令和08年'
SELECT name='month'  option value='06'    text='6月'
SELECT name='day'    option value='19'    text='19日'
```
→ `YEAR_PATTERNS` / `MONTH_PATTERNS` / `DAY_PATTERNS` に実際の value/text を追加

### D面 16:00〜18:00 セル

```
CELL text='D面'  class='facility'  onclick=''
     a_href='?reserve&...&facility=D&time=16'
```
→ このパターンなら `step_select_slot()` の アプローチA か B で検出できます。

---

## Step 3: 本番実行

### テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

### 本番実行（朝5:00:00ぴったりに自動開始）

前日夜などに実行しておき、5時ちょうどに自動で処理が始まります：

```bash
python reserve.py
```

`--headful` を付けるとブラウザが画面に表示されます（動作確認用）：

```bash
python reserve.py --headful
```

---

## 実行フロー

```
[時報待ち] 朝5:00:00.000 まで待機
  ↓
[Step 1] ログイン
  ↓
[Step 2] お気に入りクリック → 絞り込み画面
  ↓
[Step 3] 令和08年06月19日 をプルダウンから選択 → 検索
  ↓
[Step 4] D面 16:00〜18:00（赤丸）セルをクリック
  ↓
[Step 5] 確定①（料金確認画面）
  ↓
[Step 6] 確定②（最終確定）
  ↓
✅ 予約完了
```

スクリーンショットが `screenshots/` に保存されるので、各ステップの状態を確認できます。

---

## トラブルシューティング

| エラー | 原因 | 対処 |
|---|---|---|
| `お気に入りリンクが見つかりません` | ログイン失敗またはセレクター不一致 | `02_after_login.png` を確認 |
| `日付がプルダウンに見つかりません` | optionのvalue/textが想定と異なる | `analyze_site.py` でSELECT全件を確認 |
| `D面セルが見つかりません` | テーブル構造が想定と異なる | `04_search_results.html` を直接確認 |
| `確定ボタンが見つかりません` | ページ遷移先が異なる | `05_slot_selected.png` を確認 |

---

## 本番七月分への切り替え

`reserve.py` の冒頭定数を変更します：

```python
# 七月分（例: 令和08年07月XX日）
TARGET_DATE_WAREKI = "令和08年07月XX日"
TARGET_DATE_VALUE  = "2026070XX"
TARGET_DATE_ALT_VALUES = ["2026070XX", ...]
```

`OPEN_HOUR = 5` はそのままで問題ありません。
