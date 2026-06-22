# まんまるよやく2 自動予約スクリプト

対象施設: **D面 16:00〜18:00**  
対象日（練習）: **令和08年06月19日**  
本番: 令和08年05月19日 朝5:00に7月分を予約

---

## 環境セットアップ

```bash
pip install playwright pytz
playwright install chromium
```

---

## ファイル構成

| ファイル | 役割 |
|---|---|
| `analyze_site.py` | サイト構造解析（HTML/スクリーンショット保存 + セレクター出力） |
| `reserve.py` | 本番自動予約スクリプト |

---

## 動作フロー

```
[前日までに準備]
  ↓
[当日 4:55 頃] python reserve.py --headful
  │
  ├─ Step 1: ログイン（gin_menu2）
  ├─ Step 2: 「お気に入り」クリック → 絞り込み画面へ
  ├─ Step 3a: 日付プルダウンで「令和08年06月19日」を選択（5AM前に完了）
  │
  ├─ ⏱ 5:00:00.000 JST まで待機（ミリ秒精度）
  │
  ├─ Step 3b: 🚀 検索ボタンをクリック（5AM ぴったり）
  ├─ Step 4: D面 16:00〜18:00 の空き枠セルをクリック
  ├─ Step 5: 確定① クリック（料金確認画面）
  └─ Step 6: 確定② クリック（最終確定）
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

コンソールに出力された `FORM / INPUT / SELECT / OPTION / BUTTON / TABLE` の情報で  
セレクターを確認し、必要であれば `reserve.py` の定数・セレクターリストを修正してください。

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

- ログイン〜日付選択まで事前に完了させて待機
- **朝5:00:00.000 JST ぴったりに検索ボタンをクリック**
- 空き枠を即座に選択して予約確定

ヘッドレス実行（サーバー/cronなど）:

```bash
python reserve.py
```

---

## コマンドオプション一覧

| オプション | 効果 |
|---|---|
| `--now` | 時報待ちをスキップして即時実行（テスト用） |
| `--headful` | ブラウザウィンドウを表示（デバッグ用） |
| *(なし)* | 朝5:00:00 JST 待ち + ヘッドレス（本番） |

---

## 本番（7月分）への変更方法

`reserve.py` 上部の定数を変更してください：

```python
TARGET_DATE_WAREKI    = "令和08年07月XX日"   # 7月の目標日に変更
TARGET_DATE_ALT_VALUES = ["2026XXXX", ...]   # analyze_site.py で確認した value 値
TARGET_DATE_ALT_TEXTS  = ["令和08年07月XX日", ...]
```

---

## トラブルシューティング

### セレクターが合わない場合
1. `python analyze_site.py` を実行
2. `analysis_output/*.html` と コンソール出力でセレクターを確認
3. `reserve.py` の各 `try_click` / `try_fill` のセレクターリストを修正

### 日付が見つからない場合
- `analyze_site.py` 実行時の「SELECT/OPTION 一覧」を確認
- `TARGET_DATE_ALT_VALUES` / `TARGET_DATE_ALT_TEXTS` に実際の value/text を追加

### D面セルが見つからない場合
- `analysis_output/04_search_results.html` でテーブル構造を確認
- コンソールの「TABLE 構造」出力でセル位置・class・onclick を確認
- `reserve.py` の `step_select_slot()` 内のアプローチ①②③を修正

### `window.confirm` ダイアログが止まる場合
- `reserve.py` は `context.add_init_script("window.confirm = () => true;")` で  
  Tampermonkeyと同等に自動承認済み
- さらに `page.on("dialog", ...)` でPlaywright側でも自動承認しています
