# 引き継ぎメモ（investment-garden）

最終更新: 2026-06-12 / 新しいセッションはまずこれを読む。

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

## 未対応タスク
1. **ジョブのリンク形式修正（再発防止・重要）**: 2本のジョブのプロンプトを「日付リンクは必ず `daily/`・`us/` 付き」に直す。既存ファイルの一括修正は perl で可能（`content/daily/*.md` は `daily/`、`content/us/*.md` は `us/` を前置）。
2. **トップ「最新のまとめ（日米）」の自動維持**: 現在は手動で日米交互に並べた（`content/index.md`）。両ジョブがこの欄を維持するようプロンプト調整が必要。旧JPジョブは見出し「## 最新の日次」を探すので、新見出し「## 最新のまとめ（日米）」に追従させる。
3. **チャート埋め込み**: 各記事に日経 / S&P500 のチャート。Quartz が生HTML/script を通すか未検証（テストは削除済み）。要検証 → 通れば TradingView 埋め込み、ダメなら画像方式。
4. **Fear & Greed Index をトップに**: チャートと同じく HTML 埋め込み可否次第。
5. step6（vercel トークンデプロイ）をジョブから削除。

## セキュリティ（要対応）
- チャット上に GitHub fine-grained token（`github_pat_…` Contents R/W, 本リポジトリ限定）と Vercel token（`vcp_…`）が露出した。落ち着いたら無効化→再発行推奨。
- これらのトークンは現在、2本のジョブのプロンプト内に埋め込まれている（GitHub clone 用と step6 用）。ローテーション時はジョブのプロンプトも差し替えること。
- **このファイルや公開リポジトリにトークン実値を書かないこと**（Public のため）。

## 文体・記事ルール（CLAUDE.md準拠）
- 日本語・です/ます調・強調の `**` は使わない
- frontmatter: `title / date / tags / publish: true`、末尾に「AI自動生成・一次情報確認・売買推奨でない」注記
- 銘柄リンク: 日本企業=日本語名、NVIDIA 等=英名小文字スラッグ
