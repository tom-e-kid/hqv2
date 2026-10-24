# Changelog

利用者に影響する主な変更を記録する。形式は [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)、バージョンは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に従う。

## [Unreleased]

### Added

- PR 作成前に作業記録の完了判断を促す Codex・Claude Code の `PreToolUse` Hook。共有設定 `wip.prPreflight: true` のリポジトリでのみ有効化し、Plugin の導入だけでは停止しない。確認が必要な作成呼び出しを一旦止め、最後の PR なら `done` を含め、中間 PR なら判断理由を対象コミットに結び付けて保存して再実行できる。有効化した範囲で対象の不明・取得失敗は未確認として停止し、状態は自動変更しない。改行・heredoc 終端後・変数代入の前置き・既知のラッパー内にある作成候補も検出する。本文の記号・改行による停止は `--body-file` を案内する。単語内の `#` を保持してブランチの取り違えを防ぎ、コマンド置換等の検出を保証しない範囲は明記する。

- SSOT（正本）の確認漏れを伝える PR 作成時の確認。SSOT は、sdd で作成・維持する PRD・FDS・ADD 等の文書で、共有設定 `.hq/v2/settings.json` の `ssot.paths` に登録する（既定値なし、場所からは推測しない）。SSOT が登録されたプロジェクトで、変更に SSOT への影響ありの作業記録があり、実装が変わって SSOT が変わっていない PR に、SSOT の確認・更新が必要か確かめるよう伝える。整合性は判定せず、注意が出ないことは整合の確認を意味しない。状態ファイルの不正など判定できない理由は別に伝える。`scripts/wip.py check-pr` が判定し、設定と状態ファイルは判定するコミットから読む。pr・git・wip の手順で PR 作成前に確認し、Codex・Claude Code の `PostToolUse` の Plugin Hook が、エージェントの作成した PR の head・base のコミットに同じ判定を行う。PR とコミットを対応付けられない場合は、未確認であることを伝える。PR 作成は止めない。定義は `docs/references/ssot.md` にまとめた。

- sdd が文書を作成・維持する場所を、共有設定 `.hq/v2/settings.json` の `sdd.path`（未指定は `docs`）で変更できるようにした。

- 完了した作業記録を整理する `sweep` Skill。取り込み先に `done` の状態が入った記録だけを、知識の反映と参照の付け替えを確認して削除し、状態ファイルの欠落・不正、PR がすべて取り込まれたのに進行中の記録、Done When のない記録などを報告する。取り込み方法には依存しない。判断は remote と Git の履歴から分かる事実だけで行うため、GitHub Actions などのローカル以外の環境でも実行できる。PR はブランチ `chore/sweep`・タイトル `chore: sweep work records`・ラベル `hq:sweep`（なければ作成）の固定の形にし、開いている sweep の PR があれば更新する。

- 作業記録の状態ファイル `status.json`（状態 `active`・`paused`・`done`、SSOT への影響 `ssotImpact`、PR 番号）と、記録の一覧と削除できる記録を判定する `scripts/wip.py`。SSOT への影響（個別の実装判断を方向付ける事項への影響）がある作業は、SSOT の有無にかかわらず必ず記録を作り、ない作業は必要性から判断する。作業の規模では決めない。記録の形式・状態の変更・削除の条件は `docs/references/work-records.md` にまとめた。

- README に利用先のセットアップ手順と、利用先のセッションに貼り付ける導入プロンプトを追加。利用先で必要な設定を項目ごとに状態確認・選択・再確認しながら導入・変更・取りやめでき、Plugin Hook と Git Hook の役割・動作箇所・対象外の操作を一覧にした。

- コミット前チェックの採用を共有設定の `commitSecurity.required` で宣言する設定。

- 利用先ごとのオプトインで AI レビュアーの指摘を待機・分類・修正・返信・Resolve・再確認する `pr-feedback` Skill、最大3回のバッチ管理と Codex・Claude Code 向け Hook。

- ステージ済みのローカルパス・env ファイル・秘密情報らしい値を検出するコミット前チェック、Git Hook の導入・更新・状態確認、チェックの前に利用先の処理（整形など）を走らせる `<Hook 名>.d/` と、Codex・Claude Code 向けの SessionStart の Plugin Hook。

- プロジェクトの大枠を相談し、要求・設計の基準を残す `sdd` Skill。
- 具体的な作業を相談・実装・検証し、記録から再開する `wip` Skill。
- プロジェクト共通の落とし穴を参照・記録・整理する `gotchas` Skill。
- Git・GitHub の作業準備、コミット、PR・取り込みを支援する `git` Skill。
- PR のタイトル・本文を整理して作成・更新し、利用先の `.hq/v2/pr.md` の指示・書式を優先する `pr` Skill。
- CHANGELOG・バージョンの整理からリリース準備・公開を扱う `release` Skill。
- Codex・Claude Code 向けの共通 Plugin 構成と、利用先向けの規約・設定例。

### Changed

- コミット前チェックの `secret-assignment` で、値の読み方を拡張子で変えるようにした。Swift・Kotlin・JavaScript・TypeScript・Python・Java・C 系などのコードでは、引用符で囲んだ値だけを具体値とみなし、変数名・引数名・型名を検出しない。その言語の文字列補間を含む値は式とみなす。YAML・シェル・`.env` などの設定形式と、不明な拡張子は従来どおり。`.hq/v2/security.json` の `rules` で、拡張子の対応の追加・変更と、既知の画像・PDF・フォントのバイナリで `unscannable` を出さない設定（既定は従来どおり止める）を指定できる。止めない場合も読める部分は検査し、10 MiB 超のファイルは引き続き止める。`rules` を書いたポリシーは以前のコピーでは不正として止まるため、`setup_security.py update` で更新する。

- 作業記録の `done` は作業の最後の PR の中で取り込み前に設定する。Done When は取り込みまでに確認できる条件とし、取り込み後の運用確認は検証資料・チェックリストで別に管理する。最終記録の削除条件は維持する。

- 用語集を基準に、利用するツール・作業記録・Git Hook・Plugin Hook・AI レビュアー・コミット前チェック等の表記を、Skill・利用ガイド・開発規約・設定例で統一。

- Skill 共通資料を `docs/references/`、pr-feedback の運用資料を `skills/pr-feedback/references/operations.md` へ移動し、参照を更新。HQ 自身の PRD 草案と実プロジェクト検証チェックリストを `docs/ssot/` に配置し、既存の動作確認ケースをチェックリストへ集約。利用先の設定と sdd の標準文書構成は変更しない。

- `wip` の要求の書式を Goal・Context・Constraints・Done When に変更し、Done When を完了判断の根拠にした。

- コミット前チェックの `SessionStart` 通知で、未導入は採用を宣言したリポジトリでだけ通知するように変更。導入後の欠損・変更・外部管理経路の未確認・更新候補は従来どおり通知する。

- `setup_security.py` の `install`・`uninstall` を繰り返し実行できるように変更。導入済みでの `install` は成功し、HQ の以前の版の Hook、実行権限を失った HQ の Hook、欠けたコピーを現在の版に揃える。未導入での `uninstall` は変更せず成功する。HQ 以外の Hook や手編集した Hook があれば、従来どおり変更せず停止する。

- `gotchas` に対象領域・操作・症状から探せる分類・検索語・状態の整理と、手動・定期タスク共通の見直し手順・依頼例を追加。

- `pr-feedback` の macOS Hook 待機中のアイドルスリープ抑止・失敗通知と、取り残された待機の検出・報告・履歴を保った再開を追加。収束には期限到達時も静穏期間の成立を要求。

- README に `pr-feedback` の利用先セットアップ手順を追加し、共通設定と Codex・Claude Code ごとの読み込み・Hook・開始・停止の差異を明記。

- worktree の標準運用を、新規作業ごとの専用環境作成と再開時の再利用に統一。標準配置を基準 checkout の `.hq/v2/.ignore/worktrees/<作業名>/` とし、利用先の `AGENTS.md` または参照先の規約で項目ごとに上書き可能にした。転記できる規約と、長期開発系列・個別作業の使い分け、環境準備・整理の条件を整備し、README・設定説明・利用先例・検証手順を統一。Codex・Claude Code ごとの `.worktreeinclude` およびセットアップ方法は README に記載。

- README の前半を利用者向けの導入・使い方に整理し、コミット前チェックのチャット依頼例と手動導入・状態確認を追加。

- 作業記録の Skill 名を `steering` から `wip` に変更し、作業記録の標準保存先をプロジェクトのルートの `wip/YYYYMMDD-<作業名>/` に統一。active/archived の区別を廃止し、`wip/` には進行中と再開を見込む保留中の作業だけを置く。完了・取りやめた記録は必要な内容を関連文書へ反映して削除し、Git の履歴に残す。削除は完了にした変更の取り込み後に別の変更で行い、取り込み方法によって最終記録が履歴から欠けることを防ぐ。Gotchas の標準保存先もルートの `GOTCHAS.md` に変更。どちらも HQ がなくても読めるプロジェクトの記録として扱い、`.hq/v2/` には HQ が解釈する規約・設定だけを置く。旧配置との互換処理は持たない。

- 作業記録と Gotchas の保存先を、共有設定 `.hq/v2/settings.json` の `wip.path`・`gotchas.path` で変更できるようにした。未指定なら `wip/`・`GOTCHAS.md` を使い、不正な値は標準値に戻さず伝える。

- 第2世代の Plugin 名を `hq`、初回リリース予定バージョンを `2.0.0` に統一。

- `pr-feedback` にレビュアーごとの `waitAfterPush` を追加。初回だけレビューする相手を push 後の待機から外せるようにし、文字列設定との互換性、追加指摘の取得、レビュー到着後の静穏期間を維持。
