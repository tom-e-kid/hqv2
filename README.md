# HQv2

Codex と Claude Code で共通に使う、開発の経験とノウハウをまとめた Plugin です。
開発で繰り返し使う手法を、必要に応じて選べる Skill として揃えていきます。
現在は次の二つを収録しています。各 Skill は単独で使用できます。

| Skill | 役割 |
| --- | --- |
| `sdd` | 要求・設計を合意し、仕様に基づいて実装・検証し、永続的な仕様文書（SOT）を維持する |
| `steering` | 相談・調査・実験・開発の作業を記録し、セッションを跨いで再開する |

Plugin と Skill の設計方針は [今回の設計記録](.hq/v2/steering/20261012-plugin-design/design.md) で整理しています。

## sdd の基本方針

要求・設計を実装と検証の基準にし、合意した変更を SOT に反映します。
各ファイルごとの承認は標準では求めません。すでに得た合意は引き継ぎ、仕様策定だけの依頼ではコード生成へ進みません。

## steering の基本方針

標準の保存先は `.hq/v2/steering/YYYYMMDD-<作業名>/` です。
要求・設計・タスクを分けて記録し、短い作業は1ファイル内で節を分けても構いません。
作業の現在地と次の作業を残し、再開時に参照します。`sdd` の実行や仕様文書の存在を必須にしません。

## 構成

```text
.codex-plugin/plugin.json            Codex 用マニフェスト
.claude-plugin/plugin.json           Claude Code 用マニフェスト
.agents/plugins/marketplace.json     Codex 用カタログ
.claude-plugin/marketplace.json      Claude Code 用カタログ
skills/sdd/
  SKILL.md                          共通の入口
  references/                       初期仕様・変更開発・文書ルール
  assets/docs/                      全体仕様の雛形
skills/steering/
  SKILL.md                          作業記録と再開
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
$sdd を使い、このプロジェクトの初期仕様を整理してください。
$steering を使い、この作業の相談結果と次の作業を記録してください。
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

`sdd` には「今回の機能追加について要求と設計を作成してください」、
`steering` には「既存の作業記録を読んで現在地を整理してください」などと依頼します。

## 利用先プロジェクトの設定

Skill は明示的に呼び出して使えます。自動適用の方針やプロジェクト固有の指定を残したい場合は、
[AGENTS.md の記載例](examples/project/AGENTS.md) を既存ルールへ統合してください。
Claude Code では [CLAUDE.md の記載例](examples/project/CLAUDE.md) を使えます。
Skill の手順を指示ファイルへ複製する必要はありません。

SOT は PRD・FDS・ADD を必須の役割とし、REPO・DEV・GLOSSARY は必要に応じて独立させます。
新規の標準名は `docs/{PRD,FDS,ADD}.md` です。既存の同等文書はそのまま使い、二重管理しません。
作業記録は `.hq/v2/steering/YYYYMMDD-<作業名>/{requirements,design,tasks}.md` を標準とし、
1ファイルの場合は `work.md` の中で要求・設計・タスクを区別します。
アプリの要求・設計・進捗は Plugin に書き込まず、利用先リポジトリに保存します。

ブランチ・PR・検証などの規約はプロジェクト側で定め、両 Skill はそれに従います。
`package.json` の有無だけで開発段階を判定しません。

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
| 初期仕様だけを依頼 | コード生成せず要求・設計の案を作る |
| 未合意の機能追加 | 要求・設計をまとめて提示して合意を待つ |
| steering だけで調査を記録・再開 | SOT や sdd を必須にせず既存記録を使う |
| sdd だけで合意済みの変更を実装 | steering を必須にせず、合意を求め直さない |
| 1ファイルの作業記録 | 要求・設計・タスクと合意状態を混同しない |
| 仕様と無関係な誤字修正 | プロジェクトの例外規定に沿って軽く扱う |
| 非 JavaScript のプロジェクト | package.json や Next.js を前提にしない |

Hooks・MCP サーバー・製品固有のサブエージェント定義は含めていません。
`SKILL.md` の付属メタデータ用 `agents/` と、カスタムサブエージェントの定義は別のものです。

## 公式資料

- [Codex の Plugin パッケージ](https://developers.openai.com/plugins/build/plugins)
- [Claude Code の Plugin マニフェスト](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code の Marketplace](https://code.claude.com/docs/en/plugin-marketplaces)
