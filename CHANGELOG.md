# Changelog

利用者に影響する主な変更を記録する。形式は [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)、バージョンは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に従う。

## [Unreleased]

### Added

- 利用先ごとのオプトインで AI Reviewer の指摘を待機・分類・修正・返信・Resolve・再確認する `pr-feedback` Skill、最大3回のバッチ管理と Codex・Claude Code 向け Hook。

- ステージ済みのローカルパス・env ファイル・秘密情報らしい値を検出するコミット前チェック、Git Hook の導入・更新・状態確認と、Codex・Claude Code 向けの SessionStart Hook。

- プロジェクトの大枠を相談し、要求・設計の基準を残す `sdd` Skill。
- 具体的な作業を相談・実装・検証し、記録から再開する `steering` Skill。
- プロジェクト共通の落とし穴を参照・記録・整理する `gotchas` Skill。
- Git・GitHub の作業準備、コミット、PR・取り込みを支援する `git` Skill。
- PR のタイトル・本文を整理して作成・更新し、利用先の `.hq/v2/pr.md` の指示・書式を優先する `pr` Skill。
- CHANGELOG・バージョンの整理からリリース準備・公開を扱う `release` Skill。
- Codex・Claude Code 向けの共通 Plugin 構成と、利用先向けの規約・設定例。

### Fixed

- PR フィードバックのバッチ内で指摘が変化した場合の復旧、Copilot の login 照合と総評による回数消費、許可外の追記による再処理、セッションの監視取り残しを修正。登録失敗の通知、SSH URL と Git・CLI のエラー案内も改善。

### Changed

- README に `pr-feedback` の利用先セットアップ手順を追加し、共通設定と Codex・Claude Code ごとの読み込み・Hook・開始・停止の差異を明記。

- README の前半を利用者向けの導入・使い方に整理し、コミット前チェックのチャット依頼例と手動導入・状態確認を追加。

- 作業記録の保存先を `.hq/v2/work/` に統一。旧保存先は廃止し、記録と参照を移動。

- 第2世代の Plugin 名を `hq`、初回リリース予定バージョンを `2.0.0` に統一。
