# HQv2

Codex と Claude Code で共通に使う、開発の経験とノウハウをまとめた Plugin です。
開発で繰り返し使う手法を、必要に応じて選べる Skill として揃えていきます。
現在は次の二つを収録しています。各 Skill は単独で使用できます。

| Skill | 役割 |
| --- | --- |
| `sdd` | 壁打ちを通じてプロジェクトの大枠を決め、docs/ に判断基準として残す。後の方針見直しにも使う |
| `steering` | 具体的な作業の要求・設計・タスクを整理し、合意した範囲を実装・検証し、記録から再開する |

最新の責務と文書の粒度は [刷新の設計記録](.hq/v2/steering/20261013-skill-refresh/design.md) に整理しています。

## 基本の使い方

開発初期は sdd で目的・主要要求・基本設計・技術方針を相談します。その後は steering で一つの目的・範囲を持つ作業を具体化し、実装・検証を進めます。

| 場所 | 持つもの |
| --- | --- |
| docs/ | プロジェクト全体の判断基準。目的・主要要求・基本設計・方針・制約の SOT |
| `.hq/v2/steering/` | 作業単位の具体的な要求・設計・受け入れ条件・タスク、判断と結果 |
| 実装・テスト | 詳細な構造・動作と、その検証 |

作業単位はセッション単位ではありません。同じ作業を複数セッションで続けられます。

docs/ の大枠が変わる場合は相談・合意して更新します。大枠の中で決める詳細を逐一 docs/ へ転記する必要はありません。例えば、既存方針に沿ったインデックス追加は作業記録と実装に残し、検索対象や権限方針の変更は関連する大枠へ反映します。

各 Skill は単独で使えます。steering から大枠を変更する場合も、その変更を相談して docs/ に反映でき、sdd の呼び出しは必須ではありません。広い方針の見直しには sdd が使えます。

要求・設計はまとめて合意してから実装へ進みます。同じ範囲の合意を求め直さず、文書ごとの承認を標準にしません。相談・記録だけの依頼では実装へ進みません。

## 構成

```text
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
examples/project/                   利用先の指示ファイルの記載例
```

Plugin はリポジトリのルートにあります。両製品から同じ `skills/` を読み込みます。
Codex は `.codex-plugin/` の形式を使用します。ルートのポータブル形式の `plugin.json` は併用しません。

## 導入

以下のコマンドは利用者が必要なクライアントで実行します。
このリポジトリを作成しただけではインストールや有効化は行われません。

### Codex

このリポジトリのルートをカレントディレクトリにして実行します。

```bash
codex plugin marketplace add .
codex plugin add hqv2@hqv2-marketplace
```

Codex デスクトップでは登録した `hqv2-marketplace` を Plugin のブラウザーで選び、HQv2 をインストールできます。
インストール後は新しいチャットで、次のように依頼します。

```text
$sdd を使い、プロジェクトの目的・主要要求・基本設計を壁打ちしながら整理してください。
$steering を使い、合意した大枠に沿って検索機能の改善を相談・実装してください。
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
claude plugin install hqv2@hqv2-marketplace
```

新しいセッションで明示的に使う場合のコマンドは以下です。

```text
/hqv2:sdd
/hqv2:steering
```

`sdd` には「プロジェクトの大枠を相談したい」、
`steering` には「この機能追加の要求・設計を相談したい」「既存の作業記録から実装を再開したい」などと依頼します。

## 利用先プロジェクトの設定

Skill は明示的に呼び出して使えます。自動適用の方針やプロジェクト固有の指定を残したい場合は、
[AGENTS.md の記載例](examples/project/AGENTS.md) を既存ルールへ統合してください。
Claude Code では [CLAUDE.md の記載例](examples/project/CLAUDE.md) を使えます。
Skill の手順を指示ファイルへ複製する必要はありません。

大枠は PRD・FDS・ADD を基本とし、REPO・DEV・GLOSSARY は必要に応じて独立させます。
新規の標準名は `docs/{PRD,FDS,ADD}.md` です。既存の同等文書はそのまま使い、二重管理しません。
[文書の役割](skills/sdd/references/document-roles.md) に粒度と分担を定義しています。

作業記録は `.hq/v2/steering/YYYYMMDD-<作業名>/{requirements,design,tasks}.md` を標準とし、短い内容は `work.md` に節を分けて統合できます。ブランチ・PR・検証などの規約はプロジェクト側で定め、両 Skill はそれに従います。

アプリの要求・設計・進捗は Plugin に書き込まず、利用先リポジトリに保存します。
特定の技術スタック・パッケージマネージャーを前提にせず、コードや package.json の有無で合意を判断しません。

## 検証

リポジトリのルートで実行します。通常の構造・参照のチェックは以下です。

```bash
python3 scripts/validate.py
claude plugin validate . --strict
claude plugin validate .claude-plugin/plugin.json --strict
```

個人の設定を変更せず、Codex でカタログが読み込めることを確認できます。

```bash
codex -c "marketplaces.hqv2-marketplace.source=\"$(pwd)\"" \
  -c 'marketplaces.hqv2-marketplace.source_type="local"' \
  plugin list --marketplace hqv2-marketplace --available --json
```

JSON に `hqv2@hqv2-marketplace` が出ることを確認します。
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
| 相談・設計だけの完了 | 実装済みを完了条件にしない |
| 1ファイルの作業記録 | 要求・設計・タスクと合意状態を混同しない |
| 明確で軽微な修正 | 一律の文書作成を要求せず、プロジェクトの規約に従う |
| 非 JavaScript のプロジェクト | package.json や特定のフレームワークを前提にしない |

Hooks・MCP サーバー・製品固有のサブエージェント定義は含めていません。
`SKILL.md` の付属メタデータ用 `agents/` と、カスタムサブエージェントの定義は別のものです。

## 公式資料

- [Codex の Plugin パッケージ](https://developers.openai.com/plugins/build/plugins)
- [Claude Code の Plugin マニフェスト](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code の Marketplace](https://code.claude.com/docs/en/plugin-marketplaces)
