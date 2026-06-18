# 引き継ぎメモ（investment-garden）

最終更新: 2026-06-14 / 新しいセッションはまずこれを読む。

## プロジェクト
- ローカル: `~/dev/investment/investment-garden`
- GitHub: https://github.com/148512shibbatan-rgb/investment-garden （**Public**）
- 公開URL: https://investment-garden-delta.vercel.app
- エンジン: Quartz 5 + Vercel（GitHub連携で push→自動デプロイ）
- ルールは `CLAUDE.md` と `REQUIREMENTS.md` を正とする

## 完成・稼働中（重要）
- **自動公開が動作**: main に push すると Vercel が自動デプロイし公開URLが更新される。
  - これは **リポジトリを Public にした** ことで成立（bot のコミットも弾かれない）。
- **毎日の自動記事**: クラウドのリモートエージェント(routine)が2本稼働中。
  - 日本株 日次: 平日17:00 JST（cron `0 8 * * 1-5`）id `trig_014cr3odNGPfEp3SCYF1iPQw`
  - 米国株 日次: JST火〜土8:00（cron `0 23 * * 1-5`）id `trig_01Vo3pzsa51o9SqgEdQAvMZG`
  - 各ジョブ: Web調査 → 記事生成 → main へ push（→ 自動公開）。管理: https://claude.ai/code/routines
- コンテンツ: `content/daily/`(日本株) `content/us/`(米国株) `content/stocks/`(銘柄) `content/themes/` `content/terms/` `content/books/`

## 重要な技術メモ（ハマりどころ）
- **クラウドのジョブは Vercel への通信が遮断されている**（api.vercel.com が 403 / "Host not in allowlist"）。GitHub への push は可。
  → だからデプロイは「Public化した GitHub 連携の自動デプロイ」に依存している。ジョブ内で `vercel` を叩く方式は使えない。
- ジョブのプロンプトに残っている **「step6: vercel --prod でデプロイ」は無効**（実行しても失敗するだけ）。削除推奨。
- 日付リンクの罠: `daily/` と `us/` に同名 `YYYY-MM-DD.md` があるため、フォルダ無しの `[[YYYY-MM-DD]]` は曖昧で 404 になる。必ず `[[daily/YYYY-MM-DD|表示]]` / `[[us/YYYY-MM-DD|表示]]` と書く。
- スラッグは小文字化（NVIDIA→`/stocks/nvidia`）。日本語ファイル名はそのまま（URLエンコード）。
- チャート埋め込みの教訓（2026-06-14 検証済み）:
  - Quartz は生HTML/iframe を**そのまま通す**。ただし `<script>` は SPA 遷移（ページ内リンク移動）で**再実行されない**ため、TradingView の script 方式ウィジェットや素の `<script>` は「リンクから飛ぶと空白・リロードで出る」になる。→ チャートは **iframe 方式**、JS が要るもの（センチメントゲージ）は `nav` イベントに乗せて描画する。
  - TradingView の埋め込み口 `https://s.tradingview.com/widgetembed/?symbol=...` は**匿名だと指数シンボル（`SP:SPX`・`TVC:*`）がデータ権限で表示できず既定の AAPL にフォールバック**する。実際に表示できた無料シンボル: 日経=`OANDA:JP225USD`、S&P500=`FOREXCOM:SPX500`。個別株は `TSE:証券コード`（日本）/ `NASDAQ:ティッカー`・`NYSE:ティッカー`（米国）でOK。コロンは `%3A` にエンコード。

## 完了済み（2026-06-14〜15）
1. ~~ジョブのリンク形式修正（再発防止）~~ ✅ 既存11箇所を `[[daily/…|…]]` に修正。両ジョブに「日付リンクは必ず daily/・us/ 付き」ルール追加。
3. ~~チャート埋め込み~~ ✅ 日次16本＋6/13に指数チャート、個別株に各銘柄チャート。両ジョブのプロンプトに自動挿入を追加。
   - 追記: **日本の個別株は TradingView が埋め込み配信不可（公式版でもAAPLにフォールバック）**。日本株12ページは「Yahoo!ファイナンスでチャートを見る →」リンクに変更（`https://finance.yahoo.co.jp/quote/<証券コード>.T`）。両ジョブも「米国企業=TradingView iframe／日本企業=Yahooリンク／非上場=なし」に修正済み。US株・指数(CFD)は埋め込み維持。
4. ~~Fear & Greed / センチメント指数ウィジェット~~ ✅ **公開済み・自動更新稼働中**。`sentiment.py`（FRED/yfinance→過去2年分位で0-100の5段階。FRED不達時はVIXを`^VIX`でフォールバック、取得不足はstale流用）、`quartz/static/sentiment.html`（iframeゲージ＝半円ゲージ＋色帯付き推移グラフ＋国旗）を `content/index.md` トップに埋め込み（配信は `/static/sentiment.json`）。`.github/workflows/update-sentiment.yml` が毎日23:00UTC(JST朝8時)で自動生成→commit（GitHub Web UIで追加・既定GITHUB_TOKEN）。
   - 実データ生成はユーザーのローカルで: `python3 -m pip install --user -r requirements.txt && python3 sentiment.py --emit-json quartz/static/sentiment.json`（サンドボックスはFRED到達不可・Yahoo429のため）。
- サイト名を「**北浜の風見鶏**」に変更＋タイトル書体 **Zen Antique**（`quartz.config.yaml` の `typography.title`＋custom.scss の `.page-title` を `--titleFont` 使用に）。トップは記事タイトル見出し/日付/読了時間を非表示（`body[data-slug="index"]`）、イントロは1行に短縮。
- カテゴリ目次を 日本株→米国株→テーマ→銘柄→書評→用語 に整理。`content/daily/index.md`(日本株MOC)を新規作成。左Explorerの並びも同順に（explorerプラグインの `options.sortFn` 文字列）。

### 2026-06-16 追加
- ~~トップ「最新のまとめ（日米）」に米国株が載らない件~~ ✅ 原因=米国株ボットが index を更新しない設計だった。米国株ボットのプロンプトに「記事を (1)`content/index.md` の『## 最新のまとめ（日米）』 (2)`us/index.md` の最新一覧 に追加」を追記。トップに米国株6/16を手動追加済み。日本株ボットは元々 index.md+daily/index.md を更新していた（だから日本株はOKだった）。

## 未対応タスク
5. **step6（vercel トークンデプロイ）をジョブから削除**: 両ジョブの「【6. 本番デプロイ】vercel --prod」はクラウドから api.vercel.com 遮断で必ず失敗。削除推奨（未対応）。
- 補足: 日本株ボットのプロンプトはまだ旧見出し「## 最新の日次」を参照しているが、実際は「## 最新のまとめ（日米）」を正しく更新できている（動作OK・優先度低）。

## 着手中・本番化待ち：セクター資金フロー機能（MVP=米国）
要件書はチャット履歴参照。決定事項: リターン=トータルリターン(配当込み・yfinance auto_adjust)／フロントは自作／構成銘柄は私がドラフト作成。**フロントは完成しユーザー承認済み**。あとは実データ化＋公開のみ。
- 作成済み(未コミット): `sector_returns.py`（US11/JP17セクターETF→各期間リターン1d/7d/1m/3m/6m/12m＋12ヶ月終値→JSON・stale・合成データで検証済）、`quartz/static/sector-constituents-us.json`（構成銘柄ドラフト）、`quartz/static/us-sectors.html`（ヒートマップ1日/7日トグル＋折れ線〈期間切替・凡例ホバー/クリック固定・線ホバーでツールチップ〉＋ヒートマップ直下インライン構成銘柄パネル）、`content/us-sectors.md`（iframe埋め込み・ルート /us-sectors）、`.github/workflows/update-sectors.yml`（毎日US+JP更新・要Web UI追加）。
- **次回の公開手順**: ① 実データ生成（ユーザーのローカル）: `python3 sector_returns.py --market us --out quartz/static/sector-returns-us.json` と `--market jp ... sector-returns-jp.json`。② 上記ファイル一式＋実JSONをコミット＆push。③ `update-sectors.yml` を GitHub Web UI で追加（トークンworkflow権限の都合）。
- 注意: プレビュー用の合成 `sector-returns-us.json` は今回削除済み。再開時は実データ生成 or 合成で再作成してからプレビュー。フロントの `<iframe>` 内 `position:fixed` は iframe下端に出るため、構成銘柄はボトムシートでなくヒートマップ直下インラインにしてある。
- v2以降: 7日ヒートマップ(実装済)・日本ページ(/jp-sectors のHTMLは未作成)・サマリー拡充・構成銘柄に騰落率/ノートリンク・トップからの導線。

## 今後やりたいこと（ユーザー要望・次回以降）
- **つながりの可視化（マインドマップ的な地図）**: グラフビュー改善は **ペンディング**。設定値は検証済み（`options.localGraph: {depth:2,scale:1.1,repelForce:0.7,linkDistance:38,fontSize:0.75,focusOnHover:true}` / `globalGraph: {depth:-1,scale:0.9,repelForce:0.8,linkDistance:45,fontSize:0.6,focusOnHover:true,enableRadial:true}` を graph プラグインの `options:` に入れる）。カテゴリ別の色分けは簡単設定では不可。
- **加熱感の可視化**: 「どの話題が加熱しているか」を知りたい（具体像はユーザー検討中。センチメント指数やセクター機能の応用、タグ集計などが候補）。

## セキュリティ（要対応）
- チャット上に GitHub fine-grained token（`github_pat_…` Contents R/W, 本リポジトリ限定）と Vercel token（`vcp_…`）が露出した。落ち着いたら無効化→再発行推奨。
- これらのトークンは現在、2本のジョブのプロンプト内に埋め込まれている（GitHub clone 用と step6 用）。ローテーション時はジョブのプロンプトも差し替えること。
- **このファイルや公開リポジトリにトークン実値を書かないこと**（Public のため）。

## 文体・記事ルール（CLAUDE.md準拠）
- 日本語・です/ます調・強調の `**` は使わない
- frontmatter: `title / date / tags / publish: true`、末尾に「AI自動生成・一次情報確認・売買推奨でない」注記
- 銘柄リンク: 日本企業=日本語名、NVIDIA 等=英名小文字スラッグ
