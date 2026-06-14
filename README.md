# まんまるよやく2 自動予約スクリプト

対象サイト: https://www.manmaruyoyaku2.jp/mnet/reserve/gin_menu2  
練習ターゲット: **令和08年06月19日 / D面 16:00〜18:00**  
本番ターゲット: 令和08年07月XX日（5月19日 朝5:00に公開される枠）

---

## 動作フロー

```
[4:55頃] ログイン → お気に入り → 絞り込み画面 → 日付(06/19)選択
[5:00:00.000] ← ここで検索ボタンをクリック（ミリ秒精度で待機）
[5:00直後] D面 16:00〜18:00（赤丸）クリック → 確定① → 確定②
```

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
| `analyze_site.py` | サイト構造解析（HTML/スクリーンショット保存・セレクター特定） |
| `reserve.py` | 本番自動予約スクリプト |

---

## 手順1: 解析スクリプトでセレクターを確認する

```bash
python analyze_site.py --headful
```

`analysis_output/` に以下が生成されます：

| ファイル | 内容 |
|---|---|
| `01_login_page.*` | ログインページのHTML/スクリーンショット |
| `02_after_login.*` | ログイン後メニュー |
| `03_after_favorite.*` | お気に入り絞り込み画面 |
| `04_search_results.*` | 検索結果テーブル |

コンソールに出力された `INPUT / SELECT / OPTION / LINK` 情報を確認し、
必要であれば `reserve.py` のセレクターリストを修正してください。

---

## 手順2: テスト実行（即時・ブラウザ表示あり）

```bash
python reserve.py --now --headful
```

`screenshots/` に各ステップのスクリーンショットが保存されます。
エラーが出た場合は `ERROR_*.png` を確認してください。

---

## 手順3: 本番実行（5月19日 朝4:50〜4:55頃にセット）

```bash
python reserve.py --headful
```

- ログイン・日付選択まで即座に実行
- 朝 **5:00:00.000** ぴったりまでミリ秒単位で待機
- 5:00到達と同時に検索→予約を自動実行

ヘッドレス（サーバー/cronなど）:

```bash
python reserve.py
```

---

## 本番（7月分）への変更方法

`reserve.py` 上部の定数を書き換えてください：

```python
TARGET_DATE_WAREKI    = "令和08年07月XX日"
TARGET_DATE_ALT_TEXTS = ["令和08年07月XX日", "令和8年7月XX日", ...]
TARGET_DATE_ALT_VALUES = ["2026XXXX", ...]
```

---

## トラブルシューティング

### セレクターが合わない
1. `analyze_site.py --headful` を実行
2. コンソール出力・`analysis_output/*.html` でname/id/value を確認
3. `reserve.py` の `try_click` / `try_fill` のセレクターリストに追加

### 日付が選択されない
- コンソールの「SELECT name=... OPTION value=...」行を確認
- `TARGET_DATE_ALT_VALUES` / `TARGET_DATE_ALT_TEXTS` に実際の値を追加

### D面 16:00〜18:00 セルが見つからない
- `analysis_output/04_search_results.html` でテーブル構造を確認
- `step_select_slot()` 内のアプローチA/B/Cのうち、実際の構造に合うものを調整

### window.confirm が表示されて止まる
- Tampermonkey スクリプトが有効になっているか確認
- `reserve.py` は `page.add_init_script("window.confirm = () => true")` を二重設定済み
