# まんまるよやく2 自動予約スクリプト

D面 16:00〜18:00 の予約を朝5:00:00ちょうどに自動実行するためのPlaywrightスクリプトです。

---

## ファイル構成

| ファイル | 役割 |
|---|---|
| `reserve.py` | 本番自動予約スクリプト（メイン） |
| `analyze_site.py` | サイト構造解析スクリプト（セレクター調査用） |

---

## 環境セットアップ（ローカルPCで実行）

```bash
pip install playwright==1.56.0
playwright install chromium
```

---

## 手順1: まず解析スクリプトを実行してサイト構造を確認する

```bash
python analyze_site.py
```

実行後、`analysis_output/` フォルダに以下が保存されます：

| ファイル | 内容 |
|---|---|
| `01_login_page.html/png` | ログインページ |
| `02_after_login.html/png` | ログイン後メニュー |
| `03_after_favorite.html/png` | お気に入り絞り込み画面 |
| `04_search_results.html/png` | 検索結果（予約表） |

コンソールに出力された `INPUT / SELECT / OPTION / BUTTON` の情報で  
セレクターを確認し、必要であれば `reserve.py` を修正してください。

---

## 手順2: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

`screenshots/` フォルダに各ステップのスクリーンショットが保存されます。  
ステップごとに画面を確認して、動作を検証してください。

---

## 手順3: 本番実行（朝5:00ぴったりに開始したい場合）

前日夜か当日朝4:50頃にターミナルで実行しておく：

```bash
python reserve.py
# または ブラウザ確認用
python reserve.py --headful
```

- 朝5:00:00.000 ぴったりまでミリ秒単位で待機
- 5:00:00 到達と同時に検索・予約処理を開始

ヘッドレス（サーバー/cronなど）:
```bash
python reserve.py
```

---

## 本番（7月分）への変更方法

`reserve.py` の上部の定数1行だけ変更してください：

```python
# 練習: 令和08年06月19日
TARGET_DATE_WAREKI = "令和08年06月19日"

# ↓ 本番(7月)はここを変更
TARGET_DATE_WAREKI = "令和08年07月19日"
```

---

## 動作フロー

```
起動 → [時報待ち 5:00:00]
  → ログイン (利用者番号: 12015873)
  → お気に入りクリック
  → 令和08年06月19日を日付プルダウンから選択
  → 検索
  → D面 16:00〜18:00（赤丸）セルをクリック
  → 確定① クリック（料金確認画面）
  → 確定② クリック（最終確定） ← window.confirm は Tampermonkey で無効化済み前提
  → 完了確認（スクリーンショット保存）
```

各ステップで `screenshots/*.png` が保存されます。

---

## トラブルシューティング

### ログイン後に画面が変わらない
- `screenshots/02_after_login.png` を確認
- `analysis_output/02_after_login.html` で INPUT の name/id を確認
- `reserve.py` の `step_login()` のセレクターリストを修正

### 日付が見つからない
- `analysis_output/03_after_favorite.html` でSELECT/OPTIONを確認
- コンソールの `[DUMP] SELECT` 出力で実際の value と text を確認
- `reserve.py` の `_TARGET_DATE_VALUE_CANDIDATES` / `_TARGET_DATE_TEXT_CANDIDATES` を修正

### D面セルが見つからない
- `screenshots/ERROR_slot_not_found.png` を確認
- コンソールの `[DEBUG] 全td要素数` のダンプログを確認
- テーブル構造（ヘッダー行の列順序）を `analysis_output/04_search_results.html` で確認

### SSL証明書エラー
- `ignore_https_errors=True` が reserve.py に設定済みのため通常は不要

### window.confirm が出る場合
- Tampermonkey スクリプトが無効になっている可能性
- reserve.py は念のため `dialog.accept()` も設定済み
