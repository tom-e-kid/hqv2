# 作業と現在地

状態: PR (2) の実装中

概要: 作業記録に状態ファイルと SOT への影響の判断を導入し、完了記録の削除を共通 Skill `sweep` に任せ、PR 作成前に SOT への影響の判断と SOT の変更を突き合わせる。要求の書式も見直す。

## 関連文書

- [要求](requirements.md)
- [設計](design.md)

## 合意の記録

- 2026-10-23: 削除は「完了にした変更では消さず、取り込み後に別の変更で消す」とし、取り込み方法を制限しない（PR #20 で反映済み）。
- 2026-10-23: `sweep` を共通 Skill にし、work-maintenance は名前を変えずに `sweep` を参照する入口にする。README に設定手順を追加する。
- 2026-10-23: 状態は `status.json`、完了は `done`。記録を作るかは当初、重み 1〜3 で決めた（後に二択へ変更）。PR 作成前チェックはまず止めずに注意する。
- 2026-10-23: ユーザーが要求の観点として Goal・Context・Constraints・Done When を提案し、`requirements.md` に置くことに合意。
- 2026-10-23: 重みと工数をやめ、SOT への影響の二択にする。影響ありは必ず記録を作り、なしはモデルが判断する（ユーザー指示「SOTに影響があるものは必ずwip書く。ないものはLLM判断」）。
- 2026-10-23: SOT の場所は `sdd.path`（標準 `docs`）で変更可能にする。PR 作成前チェックの目的は SOT と実装の乖離を防ぐこと（ユーザー指示「PR作成前チェックの大きな目的は SOTと実装の乖離を防ぎたいということ」）。`prs` は手順で追記。既存記録の状態はエージェントの判断に任された。PR を2つに分ける。

## タスクと進捗

PR を2つに分ける（2026-10-23 合意）。

PR (1): 状態・SOT への影響・書式・スクリプト・`sweep`・work-maintenance

- [x] 作業ブランチ `feat/wip-lifecycle` と記録を作成し、設計案をまとめる。
- [x] 設計の未決事項を合意する。
- [x] 状態・SOT への影響・要求の書式を wip Skill と雛形に反映し、既存記録に状態ファイルを付ける。既存記録の状態は記録と PR の状態から判断した（pr-feedback: 実機検証待ちのため `paused`、work-maintenance: 定期実行の確認待ちで `active`、worktree-default-policy: PR #16 取り込み済み・タスク完了のため `done`）。
- [x] `scripts/wip.py`（`list`・`sweepable`）とテストを追加する。
- [x] `sweep` Skill を追加し、work-maintenance を `sweep` を参照する入口に作り直す。判断の観点は `sweep` に移した。
- [x] README・AGENTS.md・利用先の例・検証手順・CHANGELOG・Codex マニフェスト・`scripts/validate.py` を更新する。
- [x] 検証して PR (1) を作成する（[PR #21](https://github.com/tom-e-kid/hqv2/pull/21)）。
- [x] PR #21 のレビュー指摘5件に対応する（2026-10-23）。無視対象を含む管理外のファイルがある記録を削除不可にした。既存記録3件に Done When を追加した。取りやめと判断できない状態の扱いを揃えた。pr・git に既存記録への PR 番号の追記を加えた。重みを SOT への影響の優先順位で決める形にした。
- [x] ユーザー指示により重みを廃止し、SOT への影響の二択（`sotImpact`）に変更する（2026-10-23）。影響ありは必ず記録を作り、なしはモデルが判断する。あわせて、記録の規則を `docs/work-records.md` に一本化し、wip・sweep は参照する形にした。

PR (2): `sdd.path` と PR 作成前チェック

- [x] `sdd.path` を追加し、sdd・wip・検証スクリプトを対応させる。
- [x] `scripts/wip.py check-pr` とテストを追加する。判定は SOT と実装の乖離の検出を目的とし、向きを持たせる（設計 F）。判定は `sot-not-updated`・`impact-mismatch`・`sot-without-record`・`invalid-status`。
- [x] pr Skill（git・wip からも参照）と PreToolUse Hook（両製品）を追加し、Hook の入出力テストを書く。PR 作成の検出は `hooks/pr_event.py` に共通化し、pr-feedback の Hook も使う。Claude Code の公式文書で、PreToolUse の `additionalContext` は実行結果とともに届き、決定を返さなければ通常の権限の流れが続くことを確認した。
- [x] README の Hook の全体像・保存先の設定・構成、共通の規則（`docs/work-records.md` の PR 作成前の確認）、検証手順、CHANGELOG、Codex マニフェストを更新する。
- [ ] 検証して PR (2) を作成する。

## 検証・結果

| 対象の条件 | 確認方法 | 結果・根拠 |
| --- | --- | --- |
| Codex の PreToolUse で Bash・MCP ツールを検出し、additionalContext を返せる | 公式文書の確認 | 確認済み。`ask` は未対応 |
| `scripts/wip.py` の一覧と削除判定 | `tests/test_wip.py`（6件、一時リポジトリ） | 成功。squash で取り込んだ `done` の記録も `deletable`、取り込み後の編集・未追跡ファイル・再開・状態ファイルの欠落は削除不可 |
| このリポジトリの記録の状態ファイル | `scripts/validate.py` | 成功。不正・欠落を検出することも確認 |
| 構造・参照・Skill・配布設定 | `scripts/validate.py`、アンカー照合、`quick_validate.py`（Skill 10件）、`python3 -m unittest discover -s tests`（113件）、`claude plugin validate .`、Codex のカタログ確認 | 成功。`claude plugin validate` の警告は develop と同じ既知のもののみ |
| 管理外のファイルを含む記録 | 一時リポジトリで無視対象 `evidence.local` を置いて再現し、修正後にテストで確認 | 修正前は `deletable`、修正後は未追跡・無視対象・隠しファイルのいずれも `changed` |
| ステージ済みの変更を含む記録 | 一時リポジトリで、編集をステージしてから作業ファイルだけ元に戻した状態（`MM`）を再現し、修正後にテストで確認 | 修正前は `deletable`、修正後は `changed`。新しいテストは修正前のコードで失敗する |
| `check-pr` と `sdd.path` | `tests/test_wip.py`（追加4件） | 成功。実装だけの変更で `sot-not-updated`、SOT の更新で解消、SOT が先行する変更は指摘なし、記録なしの SOT 変更・判断のずれ・不正な状態を指摘、設定した `sdd.path`・`wip.path` を使う、記録を削除する変更と未コミットの変更は対象外 |
| PreToolUse Hook の入出力 | `tests/test_sot_check.py`（5件） | 成功。PR 作成以外は無出力、拒否を返さず `additionalContext` だけ、`--base`・MCP の `base`・作業ブランチの記録・共有設定から取り込み先を決める、取り込み先不明は記録がある場合だけ伝える、不正な設定を伝える |
| 製品内での `sweep` の実行 | 新しいセッションでの依頼 | 未実施 |
| 製品内での PreToolUse Hook | 両製品の新しいセッションでの PR 作成 | 未実施 |

## 中断・再開と完了

現在地: PR (1) は #21 で取り込み済み。PR (2) を実装・検証中。
