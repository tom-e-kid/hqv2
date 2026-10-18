# HQ 開発リポジトリの Claude PR レビュー

このリポジトリの PR を Claude Code GitHub Actions でレビューします。Plugin を導入した利用先には、この workflow や設定は適用されません。pr-feedback による自動修正・返信・Resolve は有効化しません。

## 認証の登録

Claude のサブスクを持つ管理者が、ローカルのターミナルで次を実行します。

```bash
claude setup-token
gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo tom-e-kid/hqv2
```

1つ目で発行したトークンを、2つ目の対話入力に登録します。トークンはチャット、workflow、作業メモ、コマンド引数や Git 管理ファイルに貼り付けません。登録済みの Secret の値は表示できませんが、名前の存在は確認できます。

```bash
gh secret list --repo tom-e-kid/hqv2
```

workflow は `claude_code_oauth_token` でサブスク枠を使用します。API キーへのフォールバックはしません。通常の Claude Code と利用枠を共有し、GitHub Actions の実行時間も消費します。認証期限切れ・失効時は再発行して同じ Secret を更新してください。[公式の認証・料金説明](https://code.claude.com/docs/en/github-actions)

GitHub の操作には実行時の `GITHUB_TOKEN` を渡すため、Claude GitHub App の追加インストールと専用 PAT は不要です。投稿者は `github-actions[bot]` になります。Secret 未登録の場合は、課金されるモデル呼び出しの前に理由を示して失敗します。

## 起動する PR と投稿内容

[workflow](../.github/workflows/claude-review.yml) は、同一リポジトリ内で OWNER・MEMBER・COLLABORATOR が作成した通常 PR を対象にします。fork、draft、bot による PR は対象外です。PR 作成、再オープン、Draft 解除、修正 push 時に自動起動します。

base 側の AGENTS.md に従って、差分と周辺の head の内容を GitHub API から確認し、正しさ・安全性・失敗時の回復・Plugin の配布設定を中心に日本語でレビューします。変更行に対する指摘と要約を PR へ投稿します。PR head が確認中に変わった場合は古い内容へ投稿しないよう指示します。

修正・commit/push・Resolve・Approve・merge は行いません。既存コメントで指摘済みの問題は重複させないようにします。AI の指摘は人間が根拠を確認して判断し、レビュー成功や指摘なしをコードの正しさの保証にしません。

## 手動レビュー

workflow が既定ブランチ develop に反映された後、GitHub の Actions から `Claude PR Review` → `Run workflow` を選び、対象 PR 番号を指定します。CLI でも起動できます。

```bash
gh workflow run claude-review.yml --repo tom-e-kid/hqv2 --ref develop -f pr_number=6
```

手動の場合も、実行時の PR の open・draft 状態、head の repository、作成者を API で検証します。対象外の PR を Secret 付きでレビューしません。

実行結果は Actions の `Claude PR Review` と PR コメントで確認します。失敗・期限切れ・コメント未投稿は、レビュー済みとして扱いません。

## リソースと権限

- PR 単位の concurrency により、同じ PR の古い実行は新しい実行で中止します。
- 1ジョブ15分、Claude は最大12ターンに制限します。サブスク利用枠の消費量を固定する上限ではありません。
- `contents: read` と `pull-requests: write` のみ付与します。GitHub App 用の OIDC 権限は使いません。
- base commit を checkout し、checkout の認証情報は Git 設定に残しません。head 側のスクリプト・Hook・MCP 設定はロードせず、レビュー対象のコードを実行するようには指示しません。
- このレビューはマージ必須チェックにしません。必須の構造検証・セキュリティチェックは [Git 規約](../.hq/v2/git.md) に従います。

停止する場合は GitHub の Actions 画面で workflow を無効化します。恒久的に解除するときは workflow を削除し、他用途がないことを確認して `CLAUDE_CODE_OAUTH_TOKEN` Secret も削除します。
