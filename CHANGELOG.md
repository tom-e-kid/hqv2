# Changelog

利用者に影響する主な変更を記録する。形式は [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)、バージョンは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に従う。

## [Unreleased]

### Added

- README に利用先のセットアップ手順と、利用先のセッションに貼り付ける導入プロンプトを追加。利用先で必要な設定を項目ごとに状態確認・選択・再確認しながら導入・変更・取りやめでき、Plugin Hook と Git Hook の役割・動作箇所・対象外の操作を一覧にした。

- コミット前チェックの採用を共有設定の `commitSecurity.required` で宣言する設定。

- 利用先ごとのオプトインで AI Reviewer の指摘を待機・分類・修正・返信・Resolve・再確認する `pr-feedback` Skill、最大3回のバッチ管理と Codex・Claude Code 向け Hook。

- ステージ済みのローカルパス・env ファイル・秘密情報らしい値を検出するコミット前チェック、Git Hook の導入・更新・状態確認、チェックの前に利用先の処理（整形など）を走らせる `<Hook 名>.d/` と、Codex・Claude Code 向けの SessionStart Hook。

- プロジェクトの大枠を相談し、要求・設計の基準を残す `sdd` Skill。
- 具体的な作業を相談・実装・検証し、記録から再開する `steering` Skill。
- プロジェクト共通の落とし穴を参照・記録・整理する `gotchas` Skill。
- Git・GitHub の作業準備、コミット、PR・取り込みを支援する `git` Skill。
- PR のタイトル・本文を整理して作成・更新し、利用先の `.hq/v2/pr.md` の指示・書式を優先する `pr` Skill。
- CHANGELOG・バージョンの整理からリリース準備・公開を扱う `release` Skill。
- Codex・Claude Code 向けの共通 Plugin 構成と、利用先向けの規約・設定例。

### Changed

- コミット前チェックの `SessionStart` 通知で、未導入は採用を宣言したリポジトリでだけ通知するように変更。導入後の欠損・変更・外部管理経路の未確認・更新候補は従来どおり通知する。

- `setup_security.py` の `install`・`uninstall` を繰り返し実行できるように変更。導入済みでの `install` は成功し、HQ の以前の版の Hook、実行権限を失った HQ の Hook、欠けたコピーを現在の版に揃える。未導入での `uninstall` は変更せず成功する。HQ 以外の Hook や手編集した Hook があれば、従来どおり変更せず停止する。

- `gotchas` に対象領域・操作・症状から探せる分類・検索語・状態の整理と、手動・定期タスク共通の見直し手順・依頼例を追加。

- `pr-feedback` の macOS Hook 待機中のアイドルスリープ抑止・失敗通知と、取り残された待機の検出・報告・履歴を保った再開を追加。収束には期限到達時も静穏期間の成立を要求。

- README に `pr-feedback` の利用先セットアップ手順を追加し、共通設定と Codex・Claude Code ごとの読み込み・Hook・開始・停止の差異を明記。

- worktree の標準運用を、新規作業ごとの専用環境作成と再開時の再利用に統一。標準配置を基準 checkout の `.hq/v2/.ignore/worktrees/<作業名>/` とし、利用先の `AGENTS.md` または参照先の規約で項目ごとに上書き可能にした。転記できる規約と、長期開発系列・個別作業の使い分け、環境準備・整理の条件を整備し、README・設定説明・利用先例・検証手順を統一。Codex・Claude Code ごとの `.worktreeinclude` およびセットアップ方法は README に記載。

- README の前半を利用者向けの導入・使い方に整理し、コミット前チェックのチャット依頼例と手動導入・状態確認を追加。

- 作業記録の保存先を `.hq/v2/work/` に統一。旧保存先は廃止し、記録と参照を移動。

- 第2世代の Plugin 名を `hq`、初回リリース予定バージョンを `2.0.0` に統一。

- `pr-feedback` にレビュアーごとの `waitAfterPush` を追加。初回だけレビューする相手を push 後の待機から外せるようにし、文字列設定との互換性、追加指摘の取得、レビュー到着後の静穏期間を維持。
