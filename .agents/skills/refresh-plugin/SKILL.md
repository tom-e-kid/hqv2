---
name: refresh-plugin
description: HQ 開発リポジトリを develop の最新状態に切り替え、他のローカルリポジトリで使う Codex の HQ Plugin を再インストールする。HQ 自体のローカル反映を依頼されたときに使う。
---

# develop の HQ をローカルへ反映する

このリポジトリ専用の Skill。Codex・Claude Code のどちらから呼び出しても、更新対象は Codex の `hq@hq-marketplace` とする。

## checkout を確認し、develop を最新化する

1. CWD から `git rev-parse --show-toplevel` でルートを取得し、この Skill 本体がある HQ checkout と同じであることを確認する。シンボリックリンク経由では実体のパスで照合する。別のリポジトリなら停止する。
2. ルートの `AGENTS.md` を読み、`.hq/v2/references/gotchas.md` や既存の同等の記録があれば関連項目を参照する。`origin` が HQ のリポジトリを指すこと、現在のブランチ、未コミット変更と進行中の Git 操作を確認する。
3. 未追跡を含む未コミット変更、merge・rebase 等の進行中の操作があれば停止する。自動で stash・コミット・破棄しない。別 worktree が `develop` を使用している場合も、その checkout は操作せず停止する。
4. 以下をルートで一つずつ実行する。各コマンドが成功した場合だけ次へ進む。

   ```bash
   git switch develop
   git fetch origin
   git merge-base --is-ancestor develop origin/develop
   git merge --ff-only origin/develop
   ```

   ancestor の確認に失敗した場合、ローカルの先行・分岐または ref の問題があるため停止する。reset・rebase やマージコミットによる解消は行わない。切り替えに失敗しても、別 checkout への移動やブランチの強制解放はしない。
5. `HEAD` と `origin/develop` が同じコミットで、作業ツリーがクリーンであることを確認する。更新後の `AGENTS.md` を読み直し、次の反映手順に変更があれば従う。

## Codex の Plugin を再インストールする

ルートの `AGENTS.md` の「Codex で開発中のコードを利用先に反映する」に従い、最新化した checkout のルートで以下を一つずつ実行する。

```bash
git status --short --branch
git rev-parse HEAD
codex plugin marketplace add .
codex plugin add hq@hq-marketplace --json
codex plugin list --marketplace hq-marketplace --json
```

- 同じバージョンでも再インストールを行う。登録結果の `alreadyAdded` やバージョン表示だけで反映成功と判断しない。
- Marketplace の参照先がこの checkout であり、`hq@hq-marketplace` がインストール済み・有効であることを確認する。必要なら `codex plugin marketplace list --json` で参照先を確認する。
- インストール結果の `installedPath` を取得し、配布対象の Skill・参照文書・スクリプト・Hook 等をソースと照合する。不一致が残る場合は反映未完了として報告し、キャッシュの直接編集や削除で強制解決しない。
- コマンドや照合が失敗した場合は停止し、完了した段階と失敗内容を報告する。プラグイン更新のために他のリポジトリを巡回・変更しない。

## 結果を伝える

反映元のブランチ・コミット、未コミット変更の有無、インストール先と照合結果を簡潔に報告する。利用先リポジトリでは新しい Codex チャットまたは CLI セッションを開くよう案内し、利用先での動作確認とは区別する。

利用先にコピー済みの Git コミット前チェックは、この操作では更新されない。更新が必要なら [導入・更新手順](../../../docs/commit-security.md) を案内し、この Skill では変更しない。
