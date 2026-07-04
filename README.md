# 関東 釣船ファインダー 🎣

魚種を選ぶだけで、**今の季節に関東のどの漁港・どの釣船（船宿）から出船しているか**を確認できるスマホWebアプリ。
釣り船予約サイト [釣割（chowari.jp）](https://www.chowari.jp/search/?area=92) の関東エリアデータをベースに構築。

## 使い方（ローカル確認）

```
python -m http.server 8770 --directory docs
```
→ ブラウザで http://localhost:8770/ を開く（launch.json 登録名: `funayado-finder`）。

## 仕組み

- **データ源①**: 釣割 `search/?area=92`（関東）を全ページ巡回してスナップショット化。
  各釣船の 船名 / 県・市 / 漁港 / 評価・レビュー数 / 予約URL / 対象魚（プラン記載）を収集。
- **データ源②**: キャスティング船釣り予約（reserve.castingnet.jp）。釣割と船IDが共通の同系列サイトで、
  釣割検索に出ない「予約プラン非掲載」の船宿も地図APIに載っている。`tools/fetch_castingnet.py` が
  差分を検出し、港（castingnet API）＋市・対象魚（釣割の釣果ページFAQ）を補完して追記する（`"via":"castingnet"` フラグ付き）。
- **データ源③（手動）**: どの予約サイトにも載っていない船宿（電話予約のみ等）は `docs/data/manual_boats.json` に
  手動登録（`"via":"manual"`、idは`m`接頭辞）。アプリが実行時にマージするので**スクレイパ再実行でも消えない**。
  `merge_fish` で既存船に公式サイト由来の魚種を追加合成することもできる。
  現在: 船宿 吉野屋（浦安）・吉久（浦安）・伊藤遊船（江戸川放水路）＋岩田屋本店の魚種補強。
- **釣期判定**: 「今出船しているか」は関東の一般的な**釣期カレンダー**（手動キュレーション）で判定。
  釣割データは *魚種 ⇄ 漁港 ⇄ 船宿* の紐付けに使用する。
- **絞り込みはクライアント側**: 魚種を選ぶ → その魚を狙える船を漁港ごとに集約表示。
  現在月が釣期内なら「今が旬」バッジ、オフ期なら薄表示＋警告。県フィルタ・魚種検索付き。

## ファイル構成

```
funayado-finder/
├─ docs/                      ← GitHub Pages 公開用（そのまま /docs 配信可）
│  ├─ index.html             ← アプリ本体（自己完結・依存なし）
│  └─ data/
│     ├─ boats.json          ← 釣割スナップショット（tools/fetch_chowari.py が生成）
│     └─ seasons.json        ← 釣期カレンダー（手動キュレーション・48種）
├─ tools/
│  ├─ fetch_chowari.py       ← スクレイパ①（釣割・スナップショット更新用）
│  └─ fetch_castingnet.py    ← スクレイパ②（castingnet差分の追記用）
└─ .claude/launch.json
```

## データ更新（スナップショット再取得）

```
python tools/fetch_chowari.py      # 釣割掲載分を全面更新（castingnet追記分は消えるので↓を続けて実行）
python tools/fetch_castingnet.py   # castingnetにしかない船宿を差分追記
```
→ `docs/data/boats.json` を最新化。取得日は `generated` に記録。1req/秒でアクセス。
新しい魚名が出た場合は実行ログの `[WARN]` に未マッピング一覧が出るので `seasons.json` の `aliases` に追加する。

## メモ（技術）

- 釣船カードのコンテナは `<section class="search__shiplist_unit">`（div ではない）。
- 対象魚はプラン内 `..._info_sup_fishlist_item` の `<li>`。`ハナダイ（チダイ）` 等は括弧以降を落として集約。
- `area=92`=関東、`fish=NN`=魚種ID。robots.txt は一般クローラを禁止していない（特定ボットのみ Disallow）。
- 魚種の同義（アジ/マアジ、キス/シロギス、タイ/マダイ 等）は `seasons.json` の `aliases` で canonical へ集約。

## 免責

釣期は目安。実際の出船可否・空き状況・料金は各釣船の予約ページ（釣割）でご確認ください。
