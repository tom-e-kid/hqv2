# Changelog

利用者に影響する主な変更を記録する。形式は [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)、バージョンは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に従う。

## [Unreleased]

### Added

- ステージ済みのローカルパス・env ファイル・秘密情報らしい値を検出するコミット前チェック、Git Hook の導入・更新・状態確認と、Codex・Claude Code 向けの SessionStart Hook。

- プロジェクトの大枠を相談し、要求・設計の基準を残す `sdd` Skill。
- 具体的な作業を相談・実装・検証し、記録から再開する `steering` Skill。
- プロジェクト共通の落とし穴を参照・記録・整理する `gotchas` Skill。
- Git・GitHub の作業準備、コミット、PR・取り込みを支援する `git` Skill。
- PR のタイトル・本文を整理して作成・更新し、利用先の `.hq/v2/pr.md` の指示・書式を優先する `pr` Skill。
- CHANGELOG・バージョンの整理からリリース準備・公開を扱う `release` Skill。
- Codex・Claude Code 向けの共通 Plugin 構成と、利用先向けの規約・設定例。

### Changed

- `git` Skill の worktree 命名規則と既存 checkout の再利用優先を撤廃し、作成・再利用と配置・命名を利用先の運用やツールに委ねる。他セッションの作業保全とローカル設定の引き継ぎは維持。

- README の前半を利用者向けの導入・使い方に整理し、コミット前チェックのチャット依頼例と手動導入・状態確認を追加。

- 作業記録の保存先を `.hq/v2/work/` に統一。旧保存先は廃止し、記録と参照を移動。

- 第2世代の Plugin 名を `hq`、初回リリース予定バージョンを `2.0.0` に統一。
