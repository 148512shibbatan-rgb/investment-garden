# CLAUDE.md — 投資まとめサイト (investment-garden)

このプロジェクトは株式投資の「公開セカンドブレイン」。Obsidian的な wikilink でつながる
まとめサイトを **Quartz 5 + Vercel** で公開している。要件は `REQUIREMENTS.md`（v2）を正とする。
（※家族CFシミュレーター＝FP/LP は別プロジェクト。`~/dev/fp/` で別セッション管理。ここでは扱わない）

---

## 基本情報
- ローカル: `~/dev/investment/investment-garden`
- エンジン: Quartz 5.0.0（Node 22+ 必須。手元は Node 24）
- 公開URL（本番）: https://investment-garden-delta.vercel.app
  - ※ `investment-garden.vercel.app` は取得済みのため `-delta` 付き。独自ドメイン/改名は任意
- Vercel: プロジェクト名 `investment-garden`。**GitHub未連携・Vercel CLI直デプロイ**
- 作成日: 2026-06-03

## コマンド
- ローカルプレビュー: `npx quartz build --serve` → http://localhost:8080
- ビルド: `npx quartz plugin install && npx quartz build`
  - 初回・プラグイン構成変更時は `plugin install` が必須（`.quartz/plugins` を生成）
- 公開更新: このディレクトリで `vercel --prod`

## デプロイの注意（重要・ハマりどころ）
- `vercel.json` の buildCommand は
  `rm -rf .quartz .quartz-cache && npx quartz plugin install && npx quartz build`。
  理由: Vercelのビルドキャッシュが古い `.quartz` を復元すると `plugin install` の更新が失敗する
  （"failed to update" 多発）。毎回クリーン生成で回避している。変更しないこと。
- `.vercelignore` で `docs/ .git/ node_modules public .quartz` 等を除外（アップロード中断対策）。

## 公開ルール（厳守・要件3.2）
- `explicit-publish` 有効 → **`publish: true` のノートだけ公開**。未設定/false は既定で非公開。
- 公開しないもの: 保有数量・評価額・口座情報・売買履歴、勤務先の業務機密（CCL/特許等）。
- 個別銘柄の売買を断定的に推奨しない。免責は全ページのフッターに自動表示（custom.scss）。
- 確認テスト用に `content/stocks/hidden-holdings.md`（publish:false）を置いてある。
  ビルド時に "Filtered out 1 files" となり、本番で 404 になることを確認済み。

## コンテンツ構成
- `content/` … 公開対象 Markdown（Quartzの入力）
  - `index.md`（トップMOC）, `daily/`, `stocks/`, `themes/`, `terms/`, `books/`
  - 各カテゴリに `index.md`（MOC）。新規ノートは該当カテゴリMOCとトップに `[[リンク]]` を追記。
- リンクは `[[NVIDIA]]` 形式（crawl-links: shortest）。スラッグは小文字化（NVIDIA→nvidia）。
- フロントマター標準形:
  ```yaml
  ---
  title: 記事タイトル
  date: 2026-06-03
  tags: [半導体, AIインフラ]
  publish: true
  ---
  ```

## デザイン（要件8章を再現。参照プロトHTMLは存在しなかったためトークンから再構成）
- `quartz.config.yaml`: 色トークン・フォント（Zen Kaku Gothic New）・baseUrl・`analytics: null`
- `quartz/styles/custom.scss`: 見出しの緑短罫 / 内部リンク緑下線 / 英語eyebrow（パンくずを大文字+字間）/
  ワードマーク / 免責フッター（`footer::before`）
- 主要色: bg `#F7F6F2` / 緑 `#0F7A55` / 緑濃 `#0A4F38` / 罫 `#E7E3D8`（詳細は REQUIREMENTS §8.3）
- 既知の妥協点: 英語eyebrowは **Archivo 未読込**（custom.scss では CSS `@import` が順序エラーになるため）。
  現状は見出しフォントの大文字+字間で代用。厳密化するならカスタム head コンポーネントで `<link>` 追加。

## 状態（MVP受け入れ基準 = REQUIREMENTS §13）
- [x] wikilink相互リンク / バックリンク表示
- [x] グラフビュー / 日本語検索
- [x] `publish:false` が公開されない
- [x] `.html` 無しURLで閲覧可能（cleanUrls）
- [x] デザイントークン反映（白基調・ゴシック・緑アクセント・英語eyebrow）
- [x] 免責文が全ページ表示
- TODO候補: 実コンテンツ投入 / サイト名確定（仮「Investment Garden」）/ Archivo厳密化 /
  独自ドメイン / GitHub連携（`npx quartz sync` 運用に移行）/ ポータル入口ページ

## 日次運用フロー
1. 本人のメモ（音声入力可）を受け取る
2. 既存ノートを参照し、関連語に `[[…]]` を付与。該当カテゴリMOCと `index.md` を更新
3. フロントマターを整形（`publish` を明示）
4. `vercel --prod` で公開（Vercelがビルド）
