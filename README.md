# HQ

Codex・Claude Code 向けに、開発の経験とノウハウ、開発を支援する機能をまとめた Plugin です。
既存の HQ を引き継ぎ、プラグイン名は `hq`、第2世代の開始バージョンは `2.0.0` とします。
共通の手法は Skill として提供し、Claude Code の agent など製品固有の機能も必要に応じて収録します。
現在は次の三つの共通 Skill を収録しています。各 Skill は単独で使用できます。

| Skill | 役割 |
| --- | --- |
| `sdd` | 壁打ちを通じてプロジェクトの大枠を決め、docs/ に判断基準として残す。後の方針見直しにも使う |
| `steering` | 具体的な作業の要求・設計・タスクを整理し、合意した範囲を実装・検証し、記録から再開する |
| `gotchas` | プロジェクトの落とし穴を参照・記録し、重複・古い回避策を整理する |

最新の責務と文書の粒度は [刷新の設計記録](.hq/v2/steering/20261013-skill-refresh/design.md) に整理しています。
Plugin の構成と配布名の見直しは [構成の見直し記録](.hq/v2/steering/20261013-plugin-structure/work.md) に残しています。

## 基本の使い方

開発初期は sdd で目的・主要要求・基本設計・技術方針を相談します。その後は steering で一つの目的・範囲を持つ作業を具体化し、実装・検証を進めます。

| 場所 | 持つもの |
| --- | --- |
| docs/ | プロジェクト全体の判断基準。目的・主要要求・基本設計・方針・制約の SOT |
| `.hq/v2/steering/active/YYYYMMDD-<作業名>/` | 取り組んでいる、または近いうちに再開する作業の要求・設計・受け入れ条件・タスク、判断と結果 |
| `.hq/v2/steering/archived/YYYYMMDD-<作業名>/` | 再開を見込む当面の保留や、継続して参照する価値がある作業記録 |
| `.hq/v2/references/gotchas.md` | Skill を跨いで共有する、プロジェクトの落とし穴と対処 |
| 実装・テスト | 詳細な構造・動作と、その検証 |

作業単位はセッション単位ではありません。同じ作業を複数セッションで続けられます。

steering は会話と依頼内容を中心に、ブランチ情報や記録の概要・状態から対応する作業を判断します。対象が明らかなら毎回の指定は不要で、候補を区別できない場合だけ確認します。通常は active の候補を絞って対象の記録を読み、archived は過去の判断の参照や再開に必要な場合に確認します。ブランチ名を作業選択の唯一の根拠にはしません。

docs/ の大枠が変わる場合は相談・合意して更新します。大枠の中で決める詳細を逐一 docs/ へ転記する必要はありません。例えば、既存方針に沿ったインデックス追加は作業記録と実装に残し、検索対象や権限方針の変更は関連する大枠へ反映します。

各 Skill は単独で使えます。steering から大枠を変更する場合も、その変更を相談して docs/ に反映でき、sdd の呼び出しは必須ではありません。広い方針の見直しには sdd が使えます。

要求・設計はまとめて合意してから実装へ進みます。同じ範囲の合意を求め直さず、文書ごとの承認を標準にしません。相談・記録だけの依頼では実装へ進みません。

## 構成

現在の構成です。

```text
AGENTS.md                           Plugin 自体の共通開発ルール
CLAUDE.md                           AGENTS.md をインポート
.codex-plugin/plugin.json            Codex 用マニフェスト
.claude-plugin/plugin.json           Claude Code 用マニフェスト
.agents/plugins/marketplace.json     Codex 用カタログ
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
examples/project/                   利用先の指示ファイルの記載例
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

## このリポジトリの開発

Codex はルートの [AGENTS.md](AGENTS.md)、Claude Code はそれをインポートする [CLAUDE.md](CLAUDE.md) から共通ルールを読みます。
これらはこのリポジトリでの開発用です。Plugin のインストール先へ適用する指示は Skill などの構成要素に持たせます。
`examples/project/` は利用先プロジェクト向けの例です。
新しい Skill には、開始時の確認事項に利用先の Gotchas を参照する短い案内を記載します。記録・選別・整理の手順は `gotchas` にまとめます。プロジェクト固有の知見は利用先に蓄積し、Skill 自体の問題は共通手順の改善として扱います。

## 導入

以下のコマンドは利用者が必要なクライアントで実行します。
このリポジトリを作成しただけではインストールや有効化は行われません。

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
```

`sdd` には「プロジェクトの大枠を相談したい」、
`steering` には「この機能追加の要求・設計を相談したい」「既存の作業記録から実装を再開したい」、
`gotchas` には「今回ハマった点を残したい」「過去の類似問題を確認したい」「古い回避策を整理したい」などと依頼します。

## 利用先プロジェクトの設定

Skill は明示的に呼び出して使えます。自動適用の方針やプロジェクト固有の指定を残したい場合は、
[AGENTS.md の記載例](examples/project/AGENTS.md) を既存ルールへ統合してください。
Claude Code では [CLAUDE.md の記載例](examples/project/CLAUDE.md) を使えます。
Skill の手順を指示ファイルへ複製する必要はありません。

大枠は PRD・FDS・ADD を基本とし、REPO・DEV・GLOSSARY は必要に応じて独立させます。
新規の標準名は `docs/{PRD,FDS,ADD}.md` です。既存の同等文書はそのまま使い、二重管理しません。
[文書の役割](skills/sdd/references/document-roles.md) に粒度と分担を定義しています。

新しい作業記録は `.hq/v2/steering/active/YYYYMMDD-<作業名>/{requirements,design,tasks}.md` を標準とし、短い内容は `work.md` に節を分けて統合できます。`tasks.md` または `work.md` の冒頭に短い概要と状態を残します。ブランチ・PR・検証などの規約はプロジェクト側で定め、両 Skill はそれに従います。

完了・取りやめの記録は、継続して必要な内容を関連文書へ反映し、最終内容を Git に残してから削除します。再開を見込む当面の保留や、継続して参照する価値がある記録は `archived/` に保持できます。終了時の整理手順は [steering の「検証と完了」](skills/steering/SKILL.md#検証と完了) にまとめています。旧配置の `.hq/v2/steering/YYYYMMDD-<作業名>/` やプロジェクト独自の保存方針は尊重し、一律の移行・整理は行いません。

作業記録はコードや関連文書とともに Git 管理します。本文は現在地と判断理由・検証結果を示し、変更の経緯は Git history に残します。コミットのタイミングと単位はプロジェクトの規約やユーザーの指示に従います。

Gotchas は利用先プロジェクトのルートを基準とする `.hq/v2/references/gotchas.md` に蓄積し、Skill を跨いで共有します。最初は一つのファイルで扱い、必要に応じて対象領域の見出しで整理します。既存の同等の保存先があれば優先し、Skill ごとの旧保存先も勝手に移動・重複作成しません。

`sdd`・`steering` は開始時の確認事項として関連項目を参照します。記録・選別・整理の手順は [gotchas](skills/gotchas/SKILL.md) にまとめ、単独で使って依頼できます。他の Skill からの呼び出しは必須ではありません。記録には発生条件・問題・対処・確認状況と根拠を残し、必要な知見が見つかった時に作成します。空ファイルは一律に作りません。

標準メモリは補助的な想起に任せ、共有する落とし穴の正本はプロジェクト内の記録とします。全文の複製や同期を必須にしません。調査経緯は個別の作業記録、恒久的なルールや正式な手順は AGENTS.md・開発文書に持たせます。Gotchas は合意済みの方針・要求を上書きするものとして扱いません。

アプリの要求・設計・進捗は Plugin に書き込まず、利用先リポジトリに保存します。
特定の技術スタック・パッケージマネージャーを前提にせず、コードや package.json の有無で合意を判断しません。

## 検証

リポジトリのルートで実行します。通常の構造・参照のチェックは以下です。

```bash
python3 scripts/validate.py
claude plugin validate .
claude plugin validate .claude-plugin/plugin.json
```

Claude Code はルートの `CLAUDE.md` がインストール先のプロジェクトコンテキストとして読み込まれない旨を警告します。このファイルは Plugin 自体の開発用なので、この警告は想定内です。それ以外の警告・エラーは内容を確認して解消してください。`--strict` を付けると、この想定内の警告もエラーになり検証に失敗します。

個人の設定を変更せず、Codex でカタログが読み込めることを確認できます。

```bash
codex -c "marketplaces.hq-marketplace.source=\"$(pwd)\"" \
  -c 'marketplaces.hq-marketplace.source_type="local"' \
  plugin list --marketplace hq-marketplace --available --json
```

JSON に `hq@hq-marketplace` が出ることを確認します。
カタログの読み込みと Skill の構造検証は、モデルが手順に従って作業することの保証ではありません。
配布前には新しいセッションで次のケースを確認します。

| ケース | 確認すること |
| --- | --- |
| sdd で大枠だけ相談 | 詳細を先回りして確定せず、実装へ進まず、合意状態と未決事項を残す |
| steering で未合意の機能追加 | 大枠を参照し、作業の要求・設計をまとめて相談してから実装する |
| 大枠の中の実装詳細 | 作業記録と実装・テストへ残し、docs/ に逐一転記しない |
| 大枠を変える作業 | 変更を相談・合意し、該当する docs/ と図表を更新する |
| steering だけの調査・実験 | sdd や docs/ を必須にせず、問いと終了条件を記録する |
| セッションを跨ぐ再開 | 同じ作業記録を使い、大枠・実装の変化を確認し、合意を求め直さない |
| 対象が明らかな作業の継続 | 会話と依頼内容から既存記録を選び、ブランチ名との一致や毎回の指定を必須にしない |
| 複数の active と多数の archived | active の概要・状態で候補を絞り、必要な記録だけ読む。候補を区別できない場合だけ確認する |
| 保留と archived からの再開 | 状態・理由を残し、セッション終了だけでは移動しない。再開は同じ記録を使い、移動で参照を壊さない |
| 完了・取りやめの記録整理 | 継続して必要な内容を反映し、最終記録のコミットを確認してから削除する。削除とリンク整理もコミットし、継続参照が必要な記録は保持できる |
| 旧配置の作業記録 | 既存記録を使い、一律の移行や重複作成をしない |
| 作業記録の Git 管理 | 本文から現在地を把握でき、判断理由・結果を残す。変更前の全文は Git history に任せ、関連するコミットに記録の更新・移動・削除も含める |
| 相談・設計だけの完了 | 実装済みを完了条件にしない |
| 1ファイルの作業記録 | 要求・設計・タスクと合意状態を混同しない |
| 明確で軽微な修正 | 一律の文書作成を要求せず、プロジェクトの規約に従う |
| 非 JavaScript のプロジェクト | package.json や特定のフレームワークを前提にしない |
| gotchas だけで記録 | 他の Skill を必須にせず、対象プロジェクトに発生条件・問題・対処・確認状況を残す |
| 類似問題の参照 | 症状だけで同じ原因と決めず、記録の適用条件を照合する。記録がなくても空ファイルを作らない |
| 未確認の原因・対処 | 仮説と確認済みの事実を区別し、記録の完了を問題の解消と扱わない |
| 重複・古い回避策の整理 | 根拠を確認して更新し、正式な手順や標準メモリと全文を二重管理しない |
| Skill ごとの旧 Gotchas | 既存の保存先を尊重し、無断の移動・統合・重複作成をしない |

現在の配布内容は共通 Skill のみです。agent・Hooks・MCP サーバーを追加した場合は、構造検証に加えて対象製品でその機能を検証します。

## 公式資料

- [Codex の Plugin パッケージ](https://developers.openai.com/plugins/build/plugins)
- [Claude Code の Plugin マニフェスト](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code の Marketplace](https://code.claude.com/docs/en/plugin-marketplaces)
