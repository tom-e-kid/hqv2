---
name: refresh-plugin
description: HQ 開発リポジトリを develop の最新状態に切り替え、他のローカルリポジトリで使う Codex・Claude Code の HQ Plugin を反映する。HQ 自体のローカル反映を依頼されたときに使う。
---

# develop の HQ をローカルへ反映する

このリポジトリ専用の Skill。標準では Codex・Claude Code 両方の `hq@hq-marketplace` を反映する。依頼で製品を限定した場合はその対象だけを扱う。対象 CLI がなければ、その製品は未実施として報告する。

## checkout を確認し、develop を最新化する

1. CWD から `git rev-parse --show-toplevel` でルートを取得し、この Skill 本体がある HQ checkout と同じであることを確認する。シンボリックリンク経由では実体のパスで照合する。別のリポジトリなら停止する。
2. ルートの `AGENTS.md` を読み、`GOTCHAS.md` や既存の同等の記録があれば関連項目を参照する。`origin` が HQ のリポジトリを指すこと、現在のブランチ、未コミット変更と進行中の Git 操作を確認する。
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

## 製品ごとに Plugin を反映する

各対象製品の反映前に、ブランチ・HEAD・作業ツリーが上で確認した状態を保っていることを確認する。コマンドや照合が失敗した場合は停止し、製品ごとの完了段階を報告する。

### Codex

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

### Claude Code

ローカルパスの Marketplace と、この HQ の相対パス `source: "./"` を使う。ルートの `AGENTS.md` の「Claude Code で開発中のコードを利用先に反映する」に従う。

1. `claude plugin marketplace list --json` と `claude plugin list --json` で既存の登録元・インストール scope・有効状態を確認する。同名 Marketplace が別のソースを指す場合、または HQ が project・local・managed scope のみで管理されている場合は、無断で登録元や適用範囲を変えず停止する。既存の無効設定も勝手に有効化しない。
2. 他のリポジトリでも使う user scope を対象に、最新化したルートで以下を一つずつ実行する。未導入の場合も user scope に導入する。

   ```bash
   claude plugin marketplace add .
   claude plugin marketplace update hq-marketplace
   claude plugin install hq@hq-marketplace --scope user
   claude plugin marketplace list --json
   claude plugin list --json
   ```

3. Marketplace のローカル参照先と、HQ の実際の読み込み元がこの checkout であることを確認する。現行 CLI の一覧では `readFromFolder` が実際の読み込み元を示す。`installPath` は別のキャッシュパスを示す場合があり、それだけで読み込み元を判断しない。フィールドがない版では、CLI が示す読み込み元とソースの内容を照合し、確認できなければ未確認として停止する。
4. ローカルの相対パス Plugin はソースから直接読み込むため、同じバージョンでも再インストールやキャッシュ削除は不要。Git・リモート Marketplace 等のキャッシュ型インストールはこの手順と混同しない。`plugin update` の「最新」表示だけで内容反映済みと扱わず、アンインストールやキャッシュの直接編集で強制解決しない。
5. 利用先で新しい Claude Code セッションを開くよう案内する。既存セッションでの `/reload-plugins` も選べるが、設定・信頼確認の結果を未確認のまま動作確認済みとは扱わない。

## 結果を伝える

反映元のブランチ・コミット、未コミット変更の有無、製品ごとのインストール先・実際の読み込み元と照合結果を簡潔に報告する。利用先リポジトリでは各製品の新しいチャット・セッションを開くよう案内し、利用先での動作確認とは区別する。

利用先にコピー済みの Git コミット前チェックは、この操作では更新されない。更新が必要なら [導入・更新手順](../../../docs/commit-security.md) を案内し、この Skill では変更しない。
