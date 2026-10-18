# Claude Code GitHub Actions による PR レビュー

状態: 取りやめ（2026-10-18）

概要: HQ 自体の PR に独立した AI レビューを導入する。Plugin 利用先向けの pr-feedback と分離し、このリポジトリでレビューを投稿する workflow を追加する。

## 取りやめの判断

2026-10-18、ユーザーはこの公開リポジトリには自動レビューを導入せず、Plugin の検証を兼ねて別の private リポジトリで自動レビューを試すと決定した。この導入計画は取りやめる。Secret 登録・workflow の有効化・develop への取り込みは行わない。pr-feedback 本体の PR #6 と、別リポジトリでの導入検証の方針は維持する。

以下は取りやめた案と実施済み検証の記録であり、現在の導入手順・残作業ではない。

## 要求と設計

2026-10-18、ユーザーはコストとサブスク利用を確認した後、このリポジトリに Claude Code GitHub Actions を設定して PR レビューを行うよう依頼した。作業ブランチは `ci/claude-pr-review`、base は `develop`。既存の PR #6 とは別の変更として扱う。

- Claude サブスクの `CLAUDE_CODE_OAUTH_TOKEN` を repository secret で参照する。API 従量課金への自動切り替えはしない。
- GitHub 操作は `GITHUB_TOKEN` を明示的に渡す。追加の GitHub App や OIDC 権限を必須にしない。投稿者は github-actions[bot] になる。
- 同一リポジトリ内の、OWNER/MEMBER/COLLABORATOR による通常 PR を対象とする。draft・fork・bot の PR は自動レビューしない。手動起動でも対象を API で検証する。
- PR 作成・ready_for_review・reopen 時に起動する。修正 push ごとの起動はユーザーの選択待ち（workflow の初期案では synchronize も含めている）。
- base commit を checkout し、変更差分・head の内容は GitHub API で読む。head のスクリプトや Hook は実行しない。権限は contents:read と pull-requests:write に限定する。
- 15分・12ターンの上限と PR 単位の concurrency を設け、修正・push・merge・Resolve は行わない。必要な指摘と要約を日本語で PR に投稿する。
- review job をマージ必須チェックに設定しない。pr-feedback の自動修正も有効化しない。

## 受け入れ条件と検証

- workflow が GitHub Actions として有効であり、認証不足・対象外の PR を明示的に扱う。
- credential をチャット・Git・ログへ出力せず、repository secret だけで参照する。
- 構造・参照・配布設定・差分・セキュリティの必須検証を満たす。
- Secret 登録と workflow 反映後に、実行結果と PR 投稿を確認する。認証・マージ等の必要操作が残る場合は未完了として報告する。

## 現在地

Actions は有効、リポジトリの admin 権限あり。repository secret は未登録。ユーザーに `claude setup-token` と `gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo tom-e-kid/hqv2` による登録を依頼した。秘密値は取得していない。既存 GitHub App の列挙は現在の GitHub CLI 認証では権限不足のため確認できないが、今回の GITHUB_TOKEN 方式では必須ではない。

参照: [公式 GitHub Actions 手順](https://code.claude.com/docs/en/github-actions)、[公式 Action](https://github.com/anthropics/claude-code-action)。Action と checkout は確認した v1/v6 の commit SHA に固定する。

## 実施した検証と残作業

- actionlint 1.7.12 による workflow 検証に成功。公式配布のチェックサムを照合し、一時ディレクトリだけに展開した。
- workflow 内の事前判定を仮の API 応答・合成 credential で実行し、正常、Draft、closed、外部 author、bot、fork、不正 PR 番号、古い head のイベント、credential 有無の10ケースを確認した。実際の Secret やモデル呼び出しは使っていない。
- 構造・参照検証、Claude Code の root/manifest 検証、Codex のローカルカタログ認識に成功。Claude Code の既知のルート CLAUDE.md 警告以外の警告はない。
- 固定した Action commit の入力定義を取得し、使用する入力が存在することを確認した。
- この変更は HQ 開発用のレビュー workflow と運用文書のみで、配布 Plugin の動作を変えないため CHANGELOG の更新対象外とした。

PR 作成・修正 push ごとのレビューを初期案として用意したが、認証 Secret の登録・実レビューの実行前に取りやめた。Secret 名の一覧を再確認し、未登録であることを確認した。認証情報の削除・失効操作は実施していない。

## PR と引き継ぎ

[Draft PR #7](https://github.com/tom-e-kid/hqv2/pull/7) を `ci/claude-pr-review` から develop 向けに作成した（実装 commit: `38761c3`）。GitHub 上で Draft・base/head を確認し、workflow run `39092647882` が Draft のため skipped となることを確認した。これはレビュー実行・投稿の成功確認ではない。

PR #7 を取り込まずに閉じる。設定案と検証結果は作業ブランチの Git history に残し、別リポジトリへの転用が必要になった場合に参照できるよう、この記録を archived に保持する。このリポジトリでの後続の認証登録・有効化作業はない。
