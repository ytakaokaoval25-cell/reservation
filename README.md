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
| `analyze_site.py` | サイト構造解析（HTML/スクリーンショット保存） |
| `reserve.py` | 本番自動予約スクリプト |

---

## 運用フロー（全体像）

```
[練習] 今すぐ → 令和08年06月19日 D面16:00〜18:00 を手動テスト
    ↓ スクリプトが正常動作したら
[本番] 6月19日 朝4:55頃にPCを起動してスクリプトをセット
    → 5:00:00 JST ぴったりに令和08年07月XX日 D面16:00〜18:00 を自動予約
```

---

## Step 1: サイト構造を解析する（初回必須）

```bash
python analyze_site.py
```

`analysis_output/` フォルダに以下が生成されます：

| ファイル | 内容 |
|---|---|
| `01_login_page.html/png` | ログインページ |
| `02_after_login.html/png` | ログイン後メニュー |
| `03_after_favorite.html/png` | お気に入り絞り込み画面 |
| `04_search_results.html/png` | 検索結果（予約表） |

コンソール出力の `FORM / INPUT / SELECT / OPTION` を確認し、
セレクターが合わない場合は `reserve.py` の各 `try_fill` / `try_click` リストを修正します。

---

## Step 2: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

`screenshots/` フォルダに各ステップのスクリーンショットが保存されます。  
ステップごとに動作確認してください。

---

## Step 3: 本番実行（6月19日 朝5:00:00 JST）

### 7月の対象日を指定して起動

```bash
# 例: 令和08年07月19日 D面16:00〜18:00 を予約する場合
python reserve.py --date 20260719
```

- JST 朝5:00:00.000 ぴったりまでミリ秒単位で待機
- 到達と同時に検索・予約処理を開始

### ブラウザ表示ありで実行（視覚確認しながら）

```bash
python reserve.py --date 20260719 --headful
```

### ヘッドレス（サーバー・バックグラウンド実行）

```bash
python reserve.py --date 20260719
```

---

## コマンドライン引数まとめ

| 引数 | 効果 |
|---|---|
| `--now` | 時報待ちをスキップして即時実行（テスト用） |
| `--headful` | ブラウザウィンドウを表示（デバッグ用） |
| `--date YYYYMMDD` | 予約対象日を上書き（例: `--date 20260719`） |

---

## トラブルシューティング

### セレクターが合わない場合
1. `analyze_site.py` を実行して `analysis_output/*.html` を確認
2. `reserve.py` の各 `try_click` / `try_fill` のセレクターリストを修正

### 日付プルダウンが選択されない場合
- `analyze_site.py` の「日付プルダウン詳細解析」出力を確認
- `reserve.py` の `_alt_values_from_yyyymmdd` / `_wareki_from_yyyymmdd` に実際のvalue/textパターンを追加

### D面セルが見つからない場合
- `screenshots/04_search_results.png` と `analysis_output/04_search_results.html` でテーブル構造を確認
- `reserve.py` の `step_select_slot()` 内アプローチ①②③を調整

### window.confirm が表示されてしまう場合
- Tampermonkey の `window.confirm = () => true` に加え、スクリプト内でも `context.add_init_script` で無効化済み
- それでも発火する場合は `page.on("dialog", ...)` のフォールバックが自動承認します
