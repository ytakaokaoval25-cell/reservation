# まんまるよやく2 自動予約スクリプト

## ファイル構成

| ファイル | 役割 |
|---|---|
| `analyze_site.py` | サイト構造解析（HTML/スクリーンショット保存）|
| `reserve.py` | 本番自動予約スクリプト |

---

## 環境セットアップ

```bash
pip install playwright
playwright install chromium
```

---

## 使用手順

### Step 1: 解析スクリプトでセレクターを確認する

```bash
python analyze_site.py
```

ブラウザが起動し、ログイン → お気に入り → 検索 を自動実行します。  
`analysis_output/` フォルダに以下が保存されます：

| ファイル | 内容 |
|---|---|
| `01_login_page.html/png` | ログインページ |
| `02_after_login.html/png` | ログイン後メニュー |
| `03_after_favorite.html/png` | お気に入り絞り込み画面 |
| `04_search_results.html/png` | 検索結果（予約表）|

コンソール出力で **INPUT / SELECT / TABLE / LINK** の属性情報を確認し、  
`reserve.py` のセレクターと照合してください。

---

### Step 2: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

`screenshots/` フォルダに各ステップのスクリーンショットが保存されます。

---

### Step 3: 本番実行（当日朝4:50頃に起動）

```bash
python reserve.py --headful
```

**動作の流れ（5AM待機設計）:**

```
ブラウザ起動（例: 朝4:55）
  ↓
ログイン完了
  ↓
お気に入りページに遷移
  ↓
ここで 5:00:00.000 AM までミリ秒単位で待機
  ↓ ← 5:00:00.000 到達
ページリロード（最新の空き情報を取得）
  ↓
日付プルダウン選択（JS直接操作で最速）
  ↓
検索実行
  ↓
D面 16:00〜18:00（赤丸）セルをクリック
  ↓
確定① → 確定②（window.confirm は自動承認）
```

> **ポイント**: ログインとお気に入りへの遷移は **5AMより前**に完了させます。  
> 5AMになってからブラウザを起動する設計より大幅に高速です。

ヘッドレス実行（サーバー/cron向け）:

```bash
python reserve.py
```

---

## 本番（7月分）への変更方法

`reserve.py` 上部の定数を変更してください：

```python
TARGET_DATE_WAREKI     = "令和08年07月XX日"      # 7月の目標日
TARGET_DATE_ALT_TEXTS  = ["令和08年07月XX日", ...]
TARGET_DATE_ALT_VALUES = ["2026XXXX", ...]        # analyze_site.py で確認したvalue値
```

---

## トラブルシューティング

### セレクターが合わない場合
1. `python analyze_site.py` を実行
2. コンソール出力と `analysis_output/*.html` でセレクターを確認
3. `reserve.py` の `try_click` / `try_fill` のリストに追加

### 日付が見つからない場合
`analyze_site.py` の「SELECT 要素」出力を確認し、  
`TARGET_DATE_ALT_VALUES` / `TARGET_DATE_ALT_TEXTS` に実際の value / text を追加

### D面セルが見つからない場合
`analysis_output/04_search_results.html` でテーブル構造を確認し、  
`reserve.py` の `step_select_slot()` 内の JS セレクターを調整

### window.confirm が出る場合
`reserve.py` は `add_init_script` + `dialog` イベントの二重対策を設定済みです。  
それでも止まる場合は `context.add_init_script(...)` の内容を確認してください。
