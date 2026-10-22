# HQ

Codex・Claude Code 向けに、開発の経験とノウハウ、開発を支援する機能をまとめた Plugin です。
共通の手法は Skill として提供し、Claude Code の agent など製品固有の機能も必要に応じて収録します。
現在は次の七つの共通 Skill を収録しています。各 Skill は単独で使用できます。

| Skill | 役割 |
| --- | --- |
| `sdd` | 壁打ちを通じてプロジェクトの大枠を決め、docs/ に判断基準として残す。後の方針見直しにも使う |
| `steering` | 具体的な作業の要求・設計・タスクを整理し、合意した範囲を実装・検証し、記録から再開する |
| `gotchas` | プロジェクトの落とし穴を参照・記録し、重複・古い回避策を整理する |
| `git` | Git・GitHub の作業準備、検証を伴うコミット、PR 作成・取り込みを進める |
| `pr` | PR のタイトル・本文を整理し、利用先の指示・書式に従って作成・更新する |
| `pr-feedback` | AI Reviewer の指摘の待機・分類・修正・理由付き返信・Resolve と再確認を上限付きで行う |
| `release` | CHANGELOG・バージョン・公開対象を整理し、リリース準備・公開を進める |

[導入](#導入) · [基本の使い方](#基本の使い方) · [AI レビュー対応の設定](#ai-レビューへの自動対応) · [コミット前チェックの導入](#コミット前のセキュリティチェック) · [利用先の設定](#利用先プロジェクトの設定)

## 導入

使うクライアントに合わせて HQ Plugin をインストールします。以下の登録コマンドは、ローカルに取得した **HQ リポジトリのルート**で実行してください。

インストール後は、**HQ を利用したいプロジェクトのリポジトリ**を開いて新しいチャット・セッションを開始します。コミット前チェックは、その利用先で別途有効化します。

### Codex

このリポジトリのルートをカレントディレクトリにして実行します。

```bash
codex plugin marketplace add .
codex plugin add hq@hq-marketplace
```

Codex デスクトップでは登録した `hq-marketplace` を Plugin のブラウザーで選び、HQ をインストールできます。
インストール後は新しいチャットで、次のように依頼します。

```text
$sdd を使い、プロジェクトの目的・主要要求・基本設計を壁打ちしながら整理してください。
$steering を使い、合意した大枠に沿って検索機能の改善を相談・実装してください。
$gotchas を使い、今回ハマった点をプロジェクトの知見として残してください。
$git を使い、この変更を必要な検証の後にコミットしてください。
$pr を使い、このブランチの変更を develop 向けの PR にまとめてください。
$pr-feedback を使い、この PR の AI レビュー指摘に対応してください。
$release を使い、今回の公開対象とバージョンを整理してリリース準備をしてください。
```

利用する CLI の対応コマンドは `codex plugin --help` で確認してください。

### Claude Code

ローカルの Plugin を一時的に読み込んで確認する場合は、リポジトリのルートで実行します。

```bash
claude --plugin-dir .
```

別のプロジェクトから使う場合は、そのプロジェクトをカレントディレクトリにし、
`--plugin-dir` にこのリポジトリの絶対パスを渡します。
永続的に登録する場合は、このリポジトリのルートで実行します。

```bash
claude plugin marketplace add .
claude plugin install hq@hq-marketplace
```

新しいセッションで明示的に使う場合のコマンドは以下です。

```text
/hq:sdd
/hq:steering
/hq:gotchas
/hq:git
/hq:pr
/hq:pr-feedback
/hq:release
```

`sdd` には「プロジェクトの大枠を相談したい」、
`steering` には「この機能追加の要求・設計を相談したい」「既存の作業記録から実装を再開したい」、
`gotchas` には「今回ハマった点を残したい」「過去の類似問題を確認したい」「古い回避策を整理したい」、
`git` には「作業ブランチを準備したい」「検証してコミットしたい」「この変更の PR を作成したい」、
`pr` には「PR 本文を下書きしたい」「既存 PR の説明を現在の差分に合わせたい」、
`release` には「次のリリースの対象とバージョンを整理したい」「リリース準備をしたい」などと依頼します。

## 基本の使い方

開発初期は sdd で目的・主要要求・基本設計・技術方針を相談します。その後は steering で一つの目的・範囲を持つ作業を具体化し、実装・検証を進めます。

| 場所 | 持つもの |
| --- | --- |
| docs/ | プロジェクト全体の判断基準。目的・主要要求・基本設計・方針・制約の SOT |
| `.hq/v2/work/active/YYYYMMDD-<作業名>/` | 取り組んでいる、または近いうちに再開する作業の要求・設計・受け入れ条件・タスク、判断と結果 |
| `.hq/v2/work/archived/YYYYMMDD-<作業名>/` | 再開を見込む当面の保留や、継続して参照する価値がある作業記録 |
| `.hq/v2/references/gotchas.md` | Skill を跨いで共有する、プロジェクトの落とし穴と対処 |
| 実装・テスト | 詳細な構造・動作と、その検証 |

作業単位はセッション単位ではありません。同じ作業を複数セッションで続けられます。

steering は会話と依頼内容を中心に、ブランチ情報や記録の概要・状態から対応する作業を判断します。対象が明らかなら毎回の指定は不要で、候補を区別できない場合だけ確認します。通常は active の候補を絞って対象の記録を読み、archived は過去の判断の参照や再開に必要な場合に確認します。ブランチ名を作業選択の唯一の根拠にはしません。

docs/ の大枠が変わる場合は相談・合意して更新します。大枠の中で決める詳細を逐一 docs/ へ転記する必要はありません。例えば、既存方針に沿ったインデックス追加は作業記録と実装に残し、検索対象や権限方針の変更は関連する大枠へ反映します。

各 Skill は単独で使えます。steering から大枠を変更する場合も、その変更を相談して docs/ に反映でき、sdd の呼び出しは必須ではありません。広い方針の見直しには sdd が使えます。

要求・設計はまとめて合意してから実装へ進みます。同じ範囲の合意を求め直さず、文書ごとの承認を標準にしません。相談・記録だけの依頼では実装へ進みません。

## AI レビューへの自動対応

`pr-feedback` は AI Reviewer の指摘をまとめて受け取り、必要な修正・検証・commit/push、理由付き返信、適切な Resolve と再確認を最大3回行います。**HQ のインストールと、利用先リポジトリでの有効化の両方が必要です。** 待機中はスクリプトだけを動かし、セッション終了後の常駐監視は行いません。

以下の `<HQ_ROOT>` は `pr-feedback` を含む HQ の取得先、`<TARGET_REPO>` は利用先リポジトリの絶対パスへ置き換えます。すでに HQ を導入済みの場合も、この機能を含む版が読み込まれていることを確認してください。

### 1. 利用先の前提を確認する（共通）

- macOS または Linux で、Python 3.10 以上・Git・GitHub CLI (`gh`) を利用できること。エージェントと Hook の実行環境からも、これらのコマンドと認証情報を利用できる必要があります。
- github.com のリポジトリで、`origin` がそのリポジトリを指していること。初版は同じリポジトリ内のブランチを対象とし、fork PR・GitHub Enterprise は対象外です。
- Copilot や自前の AI Reviewer が、PR 作成後・必要なら修正 push 後に起動する設定になっていること。**HQ は AI Reviewer 自体の設定・起動を行いません。**

利用先のルートで確認します。未認証なら `gh auth login --hostname github.com` を行い、対象 PR の読み取り・返信・Resolve とブランチへの push に必要な権限を用意します。

```bash
cd "<TARGET_REPO>"
python3 --version
git remote get-url origin
gh auth status --hostname github.com
```

### 2. HQ を読み込む（製品別）

#### Codex

HQ のルートで Marketplace を登録し、Plugin をインストールします。[通常の導入手順](#codex)で導入済みなら、この操作は省略できます。

```bash
cd "<HQ_ROOT>"
codex plugin marketplace add .
codex plugin add hq@hq-marketplace
```

利用先で新しい Codex セッションを開きます。デスクトップの場合も、利用先リポジトリをプロジェクトとして開いて新しいチャットを開始します。

```bash
cd "<TARGET_REPO>"
codex
```

Codex CLI の `/hooks` で HQ の Hook の内容を確認し、未信頼の定義を信頼します。**Plugin のインストールだけでは Hook は実行されません。** 定義が更新された場合も再確認が必要です。デスクトップで信頼確認を案内された場合は、その案内に従ってください。[公式の Hook 信頼手順](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks)

#### Claude Code

利用先から HQ を指定して、新しいセッションを起動します。一時利用では Marketplace 登録は不要です。

```bash
cd "<TARGET_REPO>"
claude --plugin-dir "<HQ_ROOT>"
```

毎回 `--plugin-dir` を指定しない運用では、HQ のルートで永続インストールしてから、利用先で `claude` を起動します。

```bash
cd "<HQ_ROOT>"
claude plugin marketplace add .
claude plugin install hq@hq-marketplace
cd "<TARGET_REPO>"
claude
```

`/hooks` で HQ の Hook が読み込まれていることを確認します。利用先の信頼・権限について確認が出た場合は内容を確認してください。すでに永続インストールした HQ がある場合は、一時読み込みと重ねず、使用する版と経路を一つに揃えます。[公式の Plugin 導入手順](https://code.claude.com/docs/en/discover-plugins)

### 3. 利用先で有効化する（共通）

**利用先リポジトリ**に `.hq/v2/pr-feedback.json` を作成します。すでに存在する場合は内容を確認して編集し、上書きしません。次は Copilot を対象に、修正・push・返信・Resolve を許可する例です。

```json
{
  "version": 1,
  "enabled": true,
  "repository": "OWNER/REPOSITORY",
  "reviewers": [
    {"login": "copilot-pull-request-reviewer", "waitAfterPush": true}
  ],
  "ignoreReviewBodies": ["copilot-pull-request-reviewer"],
  "maxRounds": 3,
  "quietSeconds": 120,
  "waitSeconds": 600,
  "pollSeconds": 30,
  "actions": {"fix": true, "push": true, "reply": true, "resolve": true}
}
```

`repository` は利用先の `OWNER/REPOSITORY` に置き換えます。`reviewers` は GitHub GraphQL API が返す投稿アカウントの `login` です。Copilot は `copilot-pull-request-reviewer` を指定します。末尾の `[bot]` と大文字・小文字の違いは照合時に正規化します。`ignoreReviewBodies` は総評を対応対象から除く login です。省略時は Copilot の総評を除き、個別スレッドとレビュー完了の検出は維持します。本文にも指摘を載せるレビュアーでは除外しないでください。自前レビュアーや複数のレビュアーでは対象の login を配列に指定します。未設定・`enabled: false` のリポジトリでは監視しません。[無効状態の設定例](examples/project/.hq/v2/pr-feedback.json)も参照できます。

`waitAfterPush: true` は push のたびに新しいレビューを待ち、false はその PR の初回レビューだけ待ちます。省略時は true です。従来の文字列指定も引き続き使えます。false のレビュアーから監視中に届いた追加指摘も取得します。複数レビュアーを混在させる例と入力条件は [運用手順](docs/pr-feedback.md) を参照してください。

同じチャットで、許可する操作を明示します。次の依頼文は両製品で使えます。

```text
このリポジトリで HQ の pr-feedback を有効にする。
.hq/v2/pr-feedback.json の対象レビュアーについて、この PR の範囲内の修正・検証・
コミット・push・理由付き返信・解決と判断できるスレッドの Resolve を許可する。
判断・対応は最大3回。別 PR 候補は Issue 案まで作成し、起票前に確認して。
```

設定は Git 管理してリポジトリで共有できます。報告ファイルの保存先 `.hq/v2/.ignore/` は、既存の `.gitignore` に追加して管理対象外にします。Plugin Hook は Plugin から読み込むため、利用先への Hook ファイルのコピーや Git の `core.hooksPath` 設定は不要です。コミット前セキュリティチェックの導入は別の操作です。

### 4. PR を作成して監視を開始する

有効化したセッション内で、通常どおり PR を作成します。`gh pr create` など対応する作成経路の完了後に `HQ pr-feedback registered PR #...` の通知が出れば、監視が登録されています。**セッションを開いたまま**にしてください。ターン終了時の Hook がレビューを待ち、FB の対応または終了報告のために処理を継続します。

既存 PR、ブラウザ・別ターミナルで作成した PR、登録通知が出ない経路では、対象のブランチを開いたセッションで明示的に依頼します。

| 製品 | チャットでの依頼例 |
| --- | --- |
| Codex | `$pr-feedback を使って PR #123 の監視を登録し、AI レビューの指摘に対応して。` |
| Claude Code | `/hq:pr-feedback PR #123 の監視を登録し、AI レビューの指摘に対応して。` |

### 停止方法と製品差

| 項目 | Codex | Claude Code |
| --- | --- | --- |
| Plugin の呼び出し | `$pr-feedback` | `/hq:pr-feedback` |
| Hook 定義 | `hooks/codex.json`。定義ごとの信頼確認が必要 | `hooks/hooks.json`。Plugin 読み込み時に登録 |
| 待機 | 同期 Stop Hook。既定は最大10分、待機中のモデル呼び出しなし | 同左 |
| 中断 | Interrupt Hook が監視の中断を記録 | 中断後に監視をやめる場合は明示的な停止または無効化が必要 |
| セッション終了 | 監視を停止。終了後の自動処理なし | 同左 |

監視を停止する場合は、チャットで「この PR の pr-feedback の監視を停止して」と依頼します。以後の自動登録も無効にする場合は、利用先の設定を `enabled: false` に変更します。再開・手動コマンド・待機期限と Cap 到達時の扱いは [運用手順](docs/pr-feedback.md) を参照してください。

macOS では Hook の待機中だけアイドルスリープを抑止します。手動スリープや Hook の強制終了などで監視が取り残された場合は、次の状態確認・Hook 実行で中断の疑いを示します。`wait-interrupted` はレビュー未確認を意味し、明示的に再開しても対応回数は保持します。セッション停止中の即時通知は行いません。

## コミット前のセキュリティチェック

ステージ済みファイルの具体的なローカルパス、env 系ファイル、API キー・トークン等と思われる値を検出し、問題があればコミットを止めます。Python 3.10 以上と Git 2.31 以上を使用し、追加の Python パッケージは不要です。

### チャットで導入を依頼する

コミット前チェックを含む HQ Plugin をインストールした後、**利用先リポジトリ**を開いた新しいチャット・セッションで、次のように依頼します。Codex・Claude Code のどちらでも同じ内容で依頼できます。

```text
HQ の git Skill を使って、このリポジトリにコミット前セキュリティチェックを導入して。

既存の Git Hooks や core.hooksPath は上書きせず、既存の仕組みがあればそこへ組み込んで。
導入後は状態を確認し、自動チェックが有効になったか、未確認の点があるかを報告して。
```

既存 Hook がなければ、検証コードを利用先の Git 管理領域へコピーし、Git Hooks を設置します。状態が `ready` であれば、自動実行する Hook とコピーが揃っています。既存 Hook や `core.hooksPath` がある場合は、自動導入を停止して既存の仕組みへ組み込みます。手動組み込みは状態表示だけでは動作を保証できないため、確認状況も報告させます。整形などの処理をチェックの前に走らせる場合は、HQ の Hook を書き換えず `<Hook 名>.d/`（例: `.git/hooks/pre-commit.d/`）に実行ファイルを置きます。

### コマンドで導入する

手動の場合は、利用先リポジトリのルートで次を実行します。`<HQ_ROOT>` はインストールした HQ Plugin のルートへ置き換えます。

```bash
python3 "<HQ_ROOT>/scripts/setup_security.py" install --repo .
python3 "<HQ_ROOT>/scripts/setup_security.py" status --repo .
```

導入後は通常のコミットで自動実行します。新しく clone したリポジトリでは再導入が必要です。同じ Git 管理領域を使う worktree では共有します。コピーは Plugin の移動・削除後も残り、更新は明示的に行います。

Plugin のインストールだけでは Git Hook は有効になりません。Codex・Claude Code の `SessionStart` Hook は未導入や設定切れをエージェントへ通知する補助機能です。Codex では Hook 定義への信頼も必要です。チェックの前に走らせる処理、既存 Hook への組み込み、更新・解除、検出範囲・例外・制約は [コミット前チェックの詳細](docs/commit-security.md) を参照してください。

## 利用先プロジェクトの設定

Skill は明示的に呼び出して使えます。自動適用の方針やプロジェクト固有の指定を残したい場合は、
[AGENTS.md の記載例](examples/project/AGENTS.md) を既存ルールへ統合してください。
Claude Code では [CLAUDE.md の記載例](examples/project/CLAUDE.md) を使えます。
Skill の手順を指示ファイルへ複製する必要はありません。

大枠は PRD・FDS・ADD を基本とし、REPO・DEV・GLOSSARY は必要に応じて独立させます。
新規の標準名は `docs/{PRD,FDS,ADD}.md` です。既存の同等文書はそのまま使い、二重管理しません。
[文書の役割](skills/sdd/references/document-roles.md) に粒度と分担を定義しています。

新しい作業記録は `.hq/v2/work/active/YYYYMMDD-<作業名>/{requirements,design,tasks}.md` を標準とし、短い内容は `work.md` に節を分けて統合できます。`tasks.md` または `work.md` の冒頭に短い概要と状態を残します。ブランチ・PR・検証などの規約はプロジェクト側で定め、各 Skill はそれに従います。

Git・GitHub の共通手順は [git](skills/git/SKILL.md) にまとめています。両製品で単独利用でき、steering の記録やブランチとの一対一対応を必須にしません。作業ブランチで変更し、新規ブランチは `feat/add-notifications` のような `<type>/<short-description>` とします。type は Conventional Commits と揃え、作成ツール名の接頭辞は付けません。コミットのタイトルは Conventional Commits の簡潔な一行、取り込みは PR を原則とします。worktree は新規作業ごとに作成し、再開では対応する既存環境を使います。標準配置は基準 checkout の `.hq/v2/.ignore/worktrees/<作業名>/` です。利用先の `AGENTS.md` または参照先の規約で項目ごとに上書きでき、未指定の項目には標準運用を適用します。

利用先の AGENTS.md には適用方針と参照先を残し、検証・PR 省略条件は [.hq/v2/git.md の例](examples/project/.hq/v2/git.md) を既存文書へ統合します。lint・型チェック・クリーンビルド・単体テストなどを一律に必須とせず、プロジェクトごとに適用条件と実在するコマンドを定めます。環境・テスト・配布ツールという分類だけで PR を省略しません。

ベースの remote・ブランチなどの共有既定値は [.hq/v2/settings.json の例](examples/project/.hq/v2/settings.json) を使って Git 管理し、checkout／worktree 固有の指定は `.hq/v2/.ignore/settings.json` へ分離して Git 管理対象外にします。[ローカル設定例](examples/project/.hq/v2/settings.local.example.json) と [.gitignore の例](examples/project/.gitignore) を必要な範囲で統合してください。`origin`・`develop` は例示です。既存の同等設定はそのまま使えます。既定ベースと進行中の作業の取り込み先を分け、開始時に確定した取り込み先を保持します。読み方と優先順位は [設定の説明](skills/git/references/settings.md) にまとめています。

PR のタイトル・本文の整理と作成・更新は [pr](skills/pr/SKILL.md) で扱います。独自書式がなければ [標準本文](skills/pr/assets/pr-body.md) を使い、利用先に `.hq/v2/pr.md` があればその指示・書式を優先します。指定がない部分だけ既存の PR テンプレートや標準書式で補い、独自書式へ標準の見出しを重ねません。[利用先向けの記載例](examples/project/.hq/v2/pr.md) は必要な場合に統合し、指示ファイルの作成や他の Skill の実行を必須にしません。

リリースの共通手順は [release](skills/release/SKILL.md) にまとめています。git や steering を先に使う必要はありません。CHANGELOG の整理、互換性に基づくバージョン判断、検証、リリース PR、タグ・公開を扱い、準備の依頼だけで公開へ進みません。利用先のブランチ名や配布基盤を固定せず、[リリース規約例](examples/project/.hq/v2/release.md) と [設定の説明](skills/release/references/settings.md) に沿って適用します。

完了・取りやめの記録は、継続して必要な内容を関連文書へ反映し、最終内容を Git に残してから削除します。再開を見込む当面の保留や、継続して参照する価値がある記録は `archived/` に保持できます。終了時の整理手順は [steering の「検証と完了」](skills/steering/SKILL.md#検証と完了) にまとめています。保存先は `.hq/v2/work/` に統一し、Skill 名は steering のままとします。記録の移動時は関連する参照も更新し、旧保存先に同じ記録を残しません。

作業記録はコードや関連文書とともに Git 管理します。本文は現在地と判断理由・検証結果を示し、変更の経緯は Git history に残します。コミットのタイミングと単位はプロジェクトの規約やユーザーの指示に従います。

Gotchas は利用先プロジェクトのルートを基準とする `.hq/v2/references/gotchas.md` に蓄積し、Skill を跨いで共有します。最初は一つのファイルで扱い、必要に応じて対象領域の見出しで整理します。既存の同等の保存先があれば優先し、Skill ごとの旧保存先も勝手に移動・重複作成しません。

`sdd`・`steering`・`git`・`pr`・`pr-feedback`・`release` は開始時の確認事項として関連項目を参照します。記録・選別・整理の手順は [gotchas](skills/gotchas/SKILL.md) にまとめ、単独で使って依頼できます。他の Skill からの呼び出しは必須ではありません。記録には発生条件・問題・対処・確認状況と根拠を残し、必要な知見が見つかった時に作成します。空ファイルは一律に作りません。

Gotchas は対象領域で分類し、見出しや本文に操作・技術名・症状・エラー文を含め、作業時に関連項目を検索しやすくします。有効・未確認・解消済みなどの状態は分類と分けて管理します。手動・定期タスク共通の [定期見直し手順と依頼例](skills/gotchas/references/maintenance.md) を用意しています。スケジューラは利用環境で設定し、HQ が自動登録することはありません。分類の整理だけで内容の確認日を更新せず、変更や新しい要確認事項がない実行は通知を繰り返しません。

標準メモリは補助的な想起に任せ、共有する落とし穴の正本はプロジェクト内の記録とします。全文の複製や同期を必須にしません。調査経緯は個別の作業記録、恒久的なルールや正式な手順は AGENTS.md・開発文書に持たせます。Gotchas は合意済みの方針・要求を上書きするものとして扱いません。

アプリの要求・設計・進捗は Plugin に書き込まず、利用先リポジトリに保存します。
特定の技術スタック・パッケージマネージャーを前提にせず、コードや package.json の有無で合意を判断しません。

### worktree の標準運用をプロジェクトに合わせる

[標準運用と上書き](skills/git/references/worktree.md) に、利用先の `AGENTS.md` へそのまま転記・編集できる規約を用意しています。[AGENTS.md の例](examples/project/AGENTS.md#worktree-運用) にも同じ標準運用を載せています。全項目をコピーする必要はなく、作成方針や配置など変更したい項目だけ指定できます。例えば、毎回の作成を「状況に応じて判断する」に変更しても、未指定の配置や再開方針は標準のまま使えます。

長期開発系列を維持する worktree と、ベースブランチへ取り込む個別作業用の worktree を区別します。両者は併用でき、長期系列のベースから個別作業を分岐できます。系列用の worktree は保持し、個別作業用は取り込みと利用終了を確認して整理します。セッション単位ではなく作業単位で扱い、今回の作業用に CLI やアプリが既に用意した専用 worktree も再利用します。

標準配置は Git 管理対象外にします。[.gitignore の例](examples/project/.gitignore) を統合し、Git の情報から基準 checkout を確認して配置を固定します。新規作成には指定パスを扱える方法を使い、CLI やアプリ固有の管理先は利用先で指定した場合に使います。以下の製品別手順は、各作成方法を選んだ場合の環境準備を説明しています。

### worktree に開発用のローカル設定を用意する

worktree の環境準備は、利用先プロジェクトで指定した手順を使います。HQ がコピー用の Hook を自動導入することはありません。開発用 `.env` などのコピーは可能ですが、必要なファイルを列挙し、コピー先でも Git 管理対象外であることを確認してください。秘密情報の値は文書・ログへ出力せず、既存の設定は上書きしません。接続先の DB やデータ保存先を共有すると並行作業が干渉する場合は、設定値を作業ごとに分けます。

| 利用環境 | ファイルのコピー | 追加の環境準備 |
| --- | --- | --- |
| Codex デスクトップアプリのローカル管理 worktree | `.worktreeinclude` | Local environments の Setup script |
| Claude Code が標準の Git 処理で作成する worktree | `.worktreeinclude` | 作成後に利用先のセットアップ手順を実行 |
| 手動の `git worktree add` | 利用先のコピー・セットアップ手順を実行 | 必要なら Git Hook と連携 |

#### コピー対象を指定する

利用先リポジトリのルートに `.worktreeinclude` を置きます。次は `.env` と `.env.local` が必要な場合の例です。必要な行だけを採用してください。

```gitignore
.env
.env.local
```

両製品とも `.gitignore` 形式のパターンを使い、一致したファイルのうち Git で除外されているものをコピーします。`.worktreeinclude` にはファイル名だけを記載して共有でき、設定値そのものは Git 管理しません。未追跡ファイル全体や `.hq/v2/.ignore/` 全体を対象にせず、必要な設定ファイルを限定してください。HQ の作業ブランチごとの取り込み先は、コピーした既定値から推測せず、[設定の説明](skills/git/references/settings.md) に従って確認・記録します。

#### Codex

デスクトップアプリで Worktree を選んで作業を開始すると、ローカル管理 worktree に `.worktreeinclude` の対象がコピーされます。コピー元がシンボリックリンクのものはスキップされ、コピー先に既にあるファイルは上書きされません。remote worktree や手動の `git worktree add` には適用されません。詳細は [Codex の worktree 公式ドキュメント](https://learn.chatgpt.com/docs/environments/git-worktrees) を参照してください。

依存関係の導入や設定の生成・加工も必要なら、アプリの設定で Local environments の Setup script を用意し、利用先のセットアップスクリプトを呼び出します。新しいチャットの開始時に worktree を作成すると自動実行されます。設定はプロジェクトの `.codex/` 配下に保存されます。[Local environments の公式ドキュメント](https://learn.chatgpt.com/docs/environments/local-environment) に沿って設定してください。

#### Claude Code

`claude --worktree`、`EnterWorktree`、デスクトップアプリなどで Claude Code が標準の Git 処理を使って worktree を作成する場合も、同じ `.worktreeinclude` が使えます。コピー後、依存関係の導入や設定の生成は、作成先で利用先のセットアップ手順を実行するか Claude に依頼します。[Claude Code の worktree 公式ドキュメント](https://code.claude.com/docs/en/worktrees#copy-gitignored-files-into-worktrees) を参照してください。

`WorktreeCreate` Hook は作成後の追加処理ではなく、標準の worktree 作成処理全体を置き換えます。ファイルのコピーだけなら `.worktreeinclude` を使います。作成自体を独自管理するために Hook を導入する場合は、作成と必要な設定のコピーをスクリプト内で行い、作成先のパスを返す必要があります。この場合 `.worktreeinclude` は自動処理されません。仕様は [WorktreeCreate の公式ドキュメント](https://code.claude.com/docs/en/hooks#worktreecreate) を参照してください。

#### Git から手動で作成する場合

`git worktree add` 自体は `.worktreeinclude` を処理しないため、作成先で利用先のコピー・セットアップ手順を実行します。自動化には `post-checkout` Hook も使えますが、通常の checkout・switch・clone でも呼ばれ、`--no-checkout` では実行されません。導入する場合は既存 Hook と共存させ、初回作成を判別し、再実行しても既存設定を壊さない処理にします。[Git の Hook 仕様](https://git-scm.com/docs/githooks#_post_checkout) を確認してください。

## このリポジトリの開発

ここからは HQ Plugin 自体を開発・保守する方向けの説明です。利用先への導入には、前半の手順を使用してください。

既存の HQ を引き継ぎ、プラグイン名は `hq`、第2世代の開始バージョンは `2.0.0` とします。

Codex はルートの [AGENTS.md](AGENTS.md)、Claude Code はそれをインポートする [CLAUDE.md](CLAUDE.md) から共通ルールを読みます。
これらはこのリポジトリでの開発用です。Plugin のインストール先へ適用する指示は Skill などの構成要素に持たせます。
`examples/project/` は利用先プロジェクト向けの例です。
ローカル開発中の変更を Codex の利用先リポジトリで試す際は、[開発中のコードの反映手順](AGENTS.md#codex-で開発中のコードを利用先に反映する) に従い、Marketplace の再登録・Plugin の再インストールと反映確認を行ってから、新しいチャットで動作を確認します。
このリポジトリは `develop` から作業ブランチを作り、PR で `develop` へ取り込みます。利用者に影響する変更は [CHANGELOG.md](CHANGELOG.md) の `Unreleased` に含めます。リリース準備の更新も `develop` へ反映し、公開対象とバージョンを確定してからリリース PR で `main` へ取り込み、その検証済みコミットへタグを付けて公開します。詳細は [Git 規約](.hq/v2/git.md)・[リリース規約](.hq/v2/release.md)、設定値は [.hq/v2/settings.json](.hq/v2/settings.json) を参照してください。初回リリースは `2.0.0` とし、開発中の CHANGELOG は `Unreleased` で管理します。

新しい Skill には、開始時の確認事項に利用先の Gotchas を参照する短い案内を記載します。記録・選別・整理の手順は `gotchas` にまとめます。プロジェクト固有の知見は利用先に蓄積し、Skill 自体の問題は共通手順の改善として扱います。

開発専用の [refresh-plugin](.agents/skills/refresh-plugin/SKILL.md) は、Codex の `$refresh-plugin`、Claude Code の `/refresh-plugin` で呼び出せます。`develop` への切り替え、fetch と fast-forward による最新化後、標準では両製品の HQ Plugin を反映します。Codex は再インストールと内容照合、Claude Code はローカル Marketplace の登録・更新と実際の読み込み元の確認を行います。製品を指定した場合は対象を限定します。未コミット変更やローカルの先行・分岐があれば停止します。利用先では更新後に各製品の新しいチャット・セッションを開始してください。

本体は `.agents/skills/refresh-plugin/` に置き、Claude Code は `.claude/skills/refresh-plugin` の相対シンボリックリンクから同じ内容を読みます。Plugin として配布する共通 Skill には含めません。コピー済みの Git コミット前チェックは別途更新が必要です。

### 作業メモの週次整理（HQ 開発専用・試行）

開発専用の [work-maintenance](.agents/skills/work-maintenance/SKILL.md) は、HQ 自体の `.hq/v2/work/` を点検し、状態更新・active 維持・archived への移動・削除を判断します。変更があれば検証して develop 向け PR を作成・更新し、自動マージしません。Codex の `$work-maintenance`、Claude Code の `/work-maintenance` で手動実行もできます。Claude Code 用の入口は `.claude/skills/work-maintenance` の相対シンボリックリンクです。Plugin 利用先の巡回や、既存 worktree・ブランチの削除は含めません。

このリポジトリでは毎週日曜 3:00（日本時間）のローカル定期タスクで試行します。実行時にマシンとアプリが稼働し、GitHub の参照・push・PR 作成に必要な接続と権限が利用できることが前提です。Skill が develop に取り込まれるまでは整理を保留します。変更も新しい確認事項もなければ通知せず、初期の PR で分類・整理漏れ・通知頻度を評価します。定期タスクはローカル設定であり、clone や Plugin の導入では登録されません。汎用化と共通 Plugin への収録は試行後に判断します。

タスクには対象 checkout と、次の実行指示を設定します。評価・整理の基準は Skill に集約します。

> HQ checkout の develop に取り込まれた `.agents/skills/work-maintenance/SKILL.md` を読み、その手順で作業メモを点検・整理する。変更があれば検証し、develop 向け PR を作成・更新する。自動マージしない。Skill が未取り込みなら整理を保留する。変更も新しい確認事項もなければ通知しない。

Claude Code では、このローカル Marketplace の構成はソースを直接参照するため、同じバージョンでもソースの変更を新しいセッションで読み込みます。キャッシュ型の更新とは区別します。登録・確認方法は [Claude Code のローカル反映手順](AGENTS.md#claude-code-で開発中のコードを利用先に反映する) を参照してください。

最新の責務と文書の粒度は [刷新の設計記録](.hq/v2/work/archived/20261013-skill-refresh/design.md) に整理しています。
Plugin の構成と配布名の見直しは [構成の見直し記録](.hq/v2/work/archived/20261013-plugin-structure/work.md) に残しています。

## 構成

現在の構成です。

```text
AGENTS.md                           Plugin 自体の共通開発ルール
CLAUDE.md                           AGENTS.md をインポート
.codex-plugin/plugin.json            Codex 用マニフェスト
.claude-plugin/plugin.json           Claude Code 用マニフェスト
.agents/plugins/marketplace.json     Codex 用カタログ
.agents/skills/refresh-plugin/       開発専用のローカル反映 Skill
.claude/skills/refresh-plugin        上記への相対シンボリックリンク
.claude-plugin/marketplace.json      Claude Code 用カタログ
skills/sdd/
  SKILL.md                          共通の入口
  references/                       大枠の策定・見直し・文書ルール
  assets/docs/                      全体仕様の雛形
skills/steering/
  SKILL.md                          作業の具体化・実装・検証・再開
  assets/steering/                   作業文書の雛形
skills/gotchas/
  SKILL.md                          落とし穴の参照・記録・整理
skills/git/
  SKILL.md                          作業ブランチ・worktree・コミット・PR・取り込み
  references/settings.md            設定の読み方と取り込み先の記録
skills/pr/
  SKILL.md                          PR のタイトル・本文の整理と作成・更新
  assets/pr-body.md                 標準の PR 本文書式
skills/release/
  SKILL.md                          CHANGELOG・バージョン・リリース準備・公開
  references/settings.md            リリースの設定と適用例
skills/pr-feedback/
  SKILL.md                          AI レビュー指摘への対応・再確認
hooks/hooks.json                    Claude Code 用 Hook
hooks/codex.json                    Codex 用 Hook（中断イベントを含む）
hooks/pr_feedback.py                PR 作成検知・待機・処理継続
scripts/pr_feedback.py              GitHub 取得・バッチ・回数・返信・Resolve
docs/pr-feedback.md                 オプトインと運用・検証
hooks/git/pre-commit                Git Hook の配布用雛形
scripts/commit_security.py           コミット対象のセキュリティチェック
scripts/setup_security.py            Git Hook の導入・更新・状態確認
docs/commit-security.md              利用先への導入と検出範囲
examples/project/                   利用先の指示・Git・リリース規約・設定の記載例
```

Plugin はリポジトリのルートにあります。両製品から同じ `skills/` を読み込みます。
Codex は `.codex-plugin/` の形式を使用します。ルートのポータブル形式の `plugin.json` は併用しません。

### 構成要素の追加方針

共通 Skill に加え、対象製品が対応する機能を追加できます。定義や設定が必要になった時にディレクトリ・ファイルを作成します。

| 構成要素 | 配置・扱い |
| --- | --- |
| 共通 Skill | `skills/<skill-name>/SKILL.md`。両製品で単独利用できる手順とリソース |
| Claude Code の agent | ルートの `agents/<agent-name>.md`。Claude Code 向けの役割と実行条件 |
| Hooks | `hooks/` など対象製品の対応する配置。イベント・設定形式の互換性を確認し、必要なら製品別に設定 |
| MCP サーバー | 対応する設定ファイルと各製品のマニフェスト。共通利用できる部分を共有し、製品固有の接続設定は分離 |

Claude Code の agent は [標準の `agents/` 配置](https://code.claude.com/docs/en/plugins-reference#standard-layout) を使用します。共通 Skill は製品固有の agent や Hooks の存在を前提にせず、製品固有の機能の使い方・対応製品は追加時にここへ記載します。
`skills/<skill-name>/agents/` に置く Skill の付属メタデータは、ルートの agent 定義とは別のものです。

## 検証

リポジトリのルートで、構造・参照を確認します。

```bash
python3 scripts/validate.py
```

両製品の配布設定、Skill の専用検証と PyYAML の準備、リリース検証、モデルによる動作確認は [検証手順](docs/validation.md) にまとめています。実行する段階と必須条件は [Git 規約](.hq/v2/git.md) を参照してください。

agent・Hooks・MCP サーバー等を追加・変更した場合は、構造検証に加えて対象製品でその機能を検証します。

## 公式資料

- [Codex の Plugin パッケージ](https://developers.openai.com/plugins/build/plugins)
- [Claude Code の Plugin マニフェスト](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code の Marketplace](https://code.claude.com/docs/en/plugin-marketplaces)
