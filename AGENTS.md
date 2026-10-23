# HQ Plugin の開発・保守

## 目的

このリポジトリはアプリケーションではなく、開発ノウハウと支援機能を Codex・Claude Code 向けの Plugin として配布する。共通の Skill に加え、Claude Code の agent など、製品固有の機能も必要に応じて収録する。

プラグイン名は既存の HQ を引き継ぐ `hq`。第2世代の開始バージョンは `2.0.0` とする。
利用先プロジェクトの開発ルールは `examples/project/` にある。Plugin 自体の編集にその例を適用しない。
このリポジトリの共通ルールは本ファイルに置き、`CLAUDE.md` からインポートする。

## 構成と責務

- 共通 Skill は `skills/<skill-name>/` に置く。大枠の策定・見直しは `skills/sdd/`、具体的な作業の相談・実装・検証・再開は `skills/wip/`、プロジェクトの落とし穴の参照・記録・整理は `skills/gotchas/`、Git・GitHub の作業準備・コミット・取り込みは `skills/git/`、PR の作成・更新と書式は `skills/pr/`、AI Reviewer の指摘への対応・再確認は `skills/pr-feedback/`、CHANGELOG・バージョンの整理とリリースは `skills/release/` が担う。
- Claude Code の agent 定義はルートの `agents/` に置く。`skills/<skill-name>/agents/` に置く Skill の付属メタデータとは区別する。
- このリポジトリの開発専用 Skill は `.agents/skills/<skill-name>/` に置き、Claude Code 用に `.claude/skills/<skill-name>` から相対シンボリックリンクを張る。Plugin として配布する共通 Skill とは分ける。
- Hooks・MCP などの追加機能は、対象製品が対応する形式・配置を確認して追加する。製品ごとに形式が異なる場合は設定を分ける。使わない機能の空ディレクトリや仮の定義は作らない。
- Codex は `.codex-plugin/plugin.json`、Claude Code は `.claude-plugin/plugin.json` を使う。構成要素は Plugin のルートを基準に配置・参照する。
- 名前とバージョンは両マニフェストで揃える。リリース時は両方のバージョンを更新し、カタログ・README・呼び出し例も整合させる。

## 変更の方針

- 各 Skill は単独で使えるようにし、別 Skill の実行を前提にしない。
- 共通 Skill は製品固有のツール名・特定のモデル・agent・Hooks に依存させない。特定の技術スタック向けの内容は、対象を明示した Skill や製品固有の定義として追加する。
- 製品固有の機能は対象製品と役割を明記する。両製品に同じ機能があると仮定せず、共通 Skill の手順を複製しない。
- Skill の追加時は、開始時の確認事項に利用先の Gotchas を参照する短い案内を記載する。知見の保存先は利用先の `.hq/v2/settings.json` の `gotchas.path`、未指定ならルートの `GOTCHAS.md` とし、既存の同等の記録を尊重して Skill を跨いで共有する。案内には同じ設定キーと標準値を示す。記録・選別・整理の手順は `gotchas` にまとめ、他の Skill に複製しない。別 Skill の呼び出しは必須にしない。プロジェクト固有の知見は Plugin に蓄積せず、Skill 自体の問題は共通手順の改善として扱う。
- Skill が案内する開発手順では、要求・設計をまとめて合意してから実装へ進む標準を維持する。大枠と作業の詳細を混同しない。
- 手順の変更時は参照文書、テンプレート、プロジェクト側の記載例との整合性を確認する。構成要素の追加時は対応製品・配置・使い方を README に反映する。

## 検証

[検証手順](docs/validation.md) を使う。共通の構造・参照と各製品の配布設定を確認し、追加・変更した機能に応じて必要な検証を行う。
文書だけの変更でモデルを呼ぶ実行テストを必須にしない。製品固有の機能は、その対象製品で検証する。

### Codex で開発中のコードを利用先に反映する

ローカル開発中、利用先リポジトリで変更を試してもらう前に、検証対象の HQ checkout から Marketplace を再登録し、Plugin を再インストールする。ソースの更新や Marketplace の登録だけで、インストール済みキャッシュも更新されたと扱わない。同じバージョンのまま開発している場合も再インストールする。

検証対象のブランチ・コミットと未コミット変更を確認し、その checkout のルートで実行する。取り込み後の最新状態を試す場合は、最新化した `develop` を使う。

```bash
git status --short --branch
git rev-parse HEAD
codex plugin marketplace add .
codex plugin add hq@hq-marketplace --json
codex plugin list --marketplace hq-marketplace --json
```

- 一覧で `hq@hq-marketplace` がインストール済み・有効であり、Marketplace の参照先が意図した checkout であることを確認する。登録済みを示す `alreadyAdded` はキャッシュ更新の確認にはならない。
- インストール結果の `installedPath` にある、今回変更した Skill・参照文書・スクリプトなどをソースと照合する。バージョン表示だけで最新コードの反映を判断しない。
- 利用先リポジトリで新しい Codex チャットまたは CLI セッションを開いて確認してもらう。既存チャットが更新後の Skill を読み直したとは扱わない。Hook の変更で信頼確認を求められた場合は、内容を確認して信頼する。
- 利用先にコピー済みのコミット前チェックなどは Plugin の再インストールでは更新されない。対象も変更した場合は、[コミット前チェックの導入手順](docs/commit-security.md) に従って別途更新する。
- 一時的な worktree を登録した場合は、削除前に保持する checkout へ再登録・再インストールし、存在しないパスを参照させない。

反映元のブランチ・コミット、未コミット変更の有無、インストール先との照合結果を報告し、利用先での動作確認とは区別する。

### Claude Code で開発中のコードを利用先に反映する

HQ の checkout のルートをローカル Marketplace として登録し、user scope にインストールする。他のリポジトリからも同じ登録を利用できる。既存の登録元・scope・有効状態を先に確認し、同名 Marketplace が別のソースを指す場合や、既存の project・local・managed scope の管理・無効設定に干渉する場合は、そのまま変更しない。

```bash
claude plugin marketplace add ./
claude plugin marketplace update hq-marketplace
claude plugin install hq@hq-marketplace --scope user
claude plugin marketplace list --json
claude plugin list --json
```

- この構成は、ローカルパスの Marketplace と相対パス `source: "./"` を使うため、現行 Claude Code はソースを直接読み込む。同じバージョンのままでもキャッシュの再コピーは不要で、ソースの変更は次のセッション開始または `/reload-plugins` で読み込まれる。[公式の読み込み仕様](https://code.claude.com/docs/en/plugins/loading#in-place-and-copied-plugins)
- Marketplace のローカル参照先と、HQ の実際の読み込み元が意図した checkout であることを確認する。Claude Code 2.1.306 の一覧では `readFromFolder` が読み込み元を示し、`installPath` は別のキャッシュパスを示す場合がある。読み込み元を確認できない版は、同じ挙動と決めつけない。
- Git・リモート Marketplace 等のキャッシュ型インストールは別の経路。同じバージョンでは `plugin update` がコピーを更新しない場合があるため、このローカル直接参照の手順と混同しない。
- 利用先で新しい Claude Code セッションを開いて確認する。反映元のブランチ・コミット、未コミット変更の有無、登録元・実際の読み込み元を報告し、利用先での動作確認とは区別する。利用先にコピー済みの Git コミット前チェックは別途更新する。
- 一時的な worktree を登録した場合は、削除前に保持する checkout へ登録を戻す。読み込み元が開発 checkout なので、以後その checkout を別ブランチへ切り替えると、利用先の次のセッションにもその内容が反映される。

## Git・リリース方針

- 通常の作業とリリース準備は `develop` から作業ブランチを作り、PR で `develop` へ取り込む。変更を `develop`・`main` へ直接コミットしない。新規ブランチは `<type>/<short-description>` とし、type は Conventional Commits と揃える。作成ツール名の接頭辞は付けない。
- コミットのタイトルは Conventional Commits に従う簡潔な一行とする。通常の Git 作業は `git`、PR の作成・更新は `pr`、リリースは `release` の手順を使い、互いの実行を必須にしない。利用先の `.hq/v2/pr.md` があれば、その指示・書式を優先する。
- 利用者に影響する変更は、同じ作業で [CHANGELOG.md](CHANGELOG.md) の `Unreleased` を更新する。
- リリース時に公開対象とバージョンを確定し、CHANGELOG・関連ファイルを更新して `develop` へ反映する。リリース PR で `main` へ取り込み、その検証済みコミットへタグを付けて公開する。
- 設定値は [.hq/v2/settings.json](.hq/v2/settings.json)、必須検証と PR の扱いは [Git 規約](.hq/v2/git.md)、初回バージョン・公開条件は [リリース規約](.hq/v2/release.md) に記載する。ローカル固有の設定は `.hq/v2/.ignore/` に置き、Git 管理しない。

### worktree 運用

- 新規作業では、ファイル変更を始める前に `develop` から作業ブランチと専用 worktree を作成する。相談・参照だけの場合は作成しない。
- 既存作業の再開では、対応する作業ブランチと worktree を再利用する。今回の作業専用として用意済みの worktree も使い、セッションごとに重ねて作成しない。
- 作成先は Git の主作業ツリーを基準に `.hq/v2/.ignore/worktrees/<作業名>/` とし、作成した worktree 内には入れ子で作成しない。
- その他の命名・環境準備・整理は [worktree の標準運用](skills/git/references/worktree.md) に従う。Plugin の反映元として登録した worktree の整理では、本ファイルの反映手順に従って登録先を戻す。
