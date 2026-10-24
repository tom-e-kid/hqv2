# PR 作成前の作業記録確認

Codex・Claude Code の `PreToolUse` Plugin Hook は、PR 作成前に作業記録の確認が必要なら、その呼び出しを一旦止めます。エージェントが最後の PR かを判断し、必要な対応の後に再実行します。状態・完了・複数 PR への分割を機械で判断しません。共通の手順は [作業記録の形式と整理](work-records.md) に従います。

## 対象と停止条件

検出対象は `gh pr create` と、名前が `create_pull_request` または `pull_request_create` で終わる MCP ツールです。Plugin Hook の対象外の作成経路・ホストでの Hook 無効化・Hook の未信頼を含め、すべての作成操作を止める仕組みではありません。Hook に依存せず Skill の手順でも確認します。

シェルでは、単独の `gh pr create --repo [host/]owner/repo --base <branch> --head <branch>` として対象を明示します。本文は `--body-file` で渡せます。省略値、環境変数展開、複合コマンド・ラッパー・未対応の引数形式から対象を推測せず、別の単独呼び出しへ分けるよう伝えて停止します。MCP は `owner`・`repo` または `repository_full_name` と、`base`・`head`（`base_branch`・`head_branch` も可）から読みます。ホストの省略は github.com を意味します。現在は同じリポジトリ内のブランチを対象とし、fork の head や `head_repo` を指定する経路は未対応として停止します。

対象リポジトリをホスト込みでローカルの remote と照合し、`gh api` で remote の base/head のコミットを取得します。必要なコミットは事前に fetch してください。設定 `wip.path` と記録は head のコミットから読み、merge base からの変更に含まれる記録を確認します。SSOT の有無に依存しません。削除された記録は完了判断の対象外です。

- 記録なし、または全記録が `done`: このチェックでは止めません。Done When の内容まで確認済みという意味ではありません。
- `active`・`paused` がある: 最後の PR かの確認が必要として止めます。
- 対象不明、取得失敗、不正な設定、状態の欠落・不正: 未確認として止めます。判断理由の保存では通せません。

ローカルの未 push の修正は remote の PR に含まれないため判定へ混ぜません。修正は commit・push してから再実行します。API・通信を含む Hook 自体のタイムアウト等ではホストが呼び出しを続ける場合があり、完全な強制境界としては扱いません。

## 停止後の対応と再実行

最後の PR なら、各条件の根拠と残作業を読み、`done` と最終記録を commit・push してから作成を再実行します。中間 PR なら状態は維持し、残作業と今回の PR が最後でない理由を作業記録へ残します。その記録を commit・push した対象に対して、次のコマンドで判断理由をローカルに保存してから再実行します。Hook の停止理由にも実際の対象を使うコマンドが示されます。

```bash
python3 "<HQ_ROOT>/hooks/pr_preflight.py" --repo "<対象>" \
  --repository "github.com/owner/repo" --base "develop" --head "feat/example" \
  --reviewed --reason "中間 PR。次の PR で残る移行処理と検証を行う"
```

`--reviewed` を付けなければ対象・状態の読み取りだけを行います。作成・push・状態変更はどちらのモードでも行いません。理由が空、状態が不正、取得できない対象は保存できません。保存は人間の承認の代替ではなく、エージェントが判断した記録です。

判断結果は worktree ごとの Git 管理領域 `hq/pr-preflight/` に原子的に保存します。リポジトリ・ホスト・ブランチ・base/head のコミット・記録に結び付け、別の対象やコミットには使いません。コミットが同じなら失敗した作成操作を再実行でき、base/head が更新されたら再確認します。本文は保存せず、理由に秘密情報を含めないでください。Plugin の再インストール後も同じ対象の判断結果を利用できます。

## 利用するツールの仕様と未確認範囲

[Claude Code の PreToolUse](https://code.claude.com/docs/en/hooks#pretooluse-decision-control) は `permissionDecision: deny` と `permissionDecisionReason` で実行前に停止して理由をエージェントへ返します。`additionalContext` だけではツール結果とともに届くため、作成前の見直しには使いません。[Codex の Hooks](https://learn.chatgpt.com/docs/hooks) もこの deny 形式をサポートします（2026-10-24 確認）。既存の作成後 SSOT 確認と AI レビュー監視の Hook はそれぞれの責務のまま維持します。

自動テストは入出力と Git・API の境界を確認します。利用するツール内での停止・理由の配送・再実行は [検証チェックリスト](../ssot/validation-checklist.md#s52-pr-作成前の作業記録確認) で別に確認します。
