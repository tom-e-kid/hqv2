# 作業と現在地

状態: PR (2) のレビュー待ち

概要: 作業記録に状態ファイルと SSOT への影響の判断を導入し、完了記録の削除を共通 Skill `sweep` に任せ、SSOT が登録されたプロジェクトで PR 作成時に SSOT の確認漏れを注意する。要求の書式も見直す。

## 関連文書

- [要求](requirements.md)
- [設計](design.md)

## 合意の記録

- 2026-10-23: 削除は「完了にした変更では消さず、取り込み後に別の変更で消す」とし、取り込み方法を制限しない（PR #20 で反映済み）。
- 2026-10-23: `sweep` を共通 Skill にし、work-maintenance は名前を変えずに `sweep` を参照する入口にする。README に設定手順を追加する。
- 2026-10-23: 状態は `status.json`、完了は `done`。記録を作るかは当初、重み 1〜3 で決めた（後に二択へ変更）。PR 作成前チェックはまず止めずに注意する。
- 2026-10-23: ユーザーが要求の観点として Goal・Context・Constraints・Done When を提案し、`requirements.md` に置くことに合意。
- 2026-10-23: 重みと工数をやめ、SOT への影響の二択にする。影響ありは必ず記録を作り、なしはモデルが判断する（ユーザー指示「SOTに影響があるものは必ずwip書く。ないものはLLM判断」）。
- 2026-10-24: SOT 確認の Hook を `PostToolUse` に移し、作成された PR の head・base のコミットを判定する（ユーザーが B 案を選択）。条件: コミット ID で対象を固定する、設定と状態ファイルも対象コミットから読む、worktree は Git オブジェクトへのアクセス手段として扱いリポジトリの対応とコミットの存在を確かめる、取得失敗を問題なしと扱わず未確認と伝える。
- 2026-10-24: 用語を SSOT に統一し、PR 作成時の確認を「SSOT を見直す機会の抜けの注意」に再定義する（設計 F、合意した判断 6〜11）。SSOT は `ssot.paths` で明示し既定値を持たない（多くは `sdd.path` が入る想定）、草案かどうかは判断しない、影響ありの作業は SSOT 未定義でも記録を作る、`impact-mismatch`・`sot-without-record` を外す、PR #22 を作り直す。
- 2026-10-24: `impact-mismatch` は変更全体で判定し、記録単位で断定しない（レビューの推奨を受けて対応。後に判定自体を外した）。
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
- [x] 検証して PR (2) を作成する（[PR #22](https://github.com/tom-e-kid/hqv2/pull/22)）。
- [x] PR #22 のレビュー指摘2件に対応する（2026-10-24）。`status.json` だけが欠けた記録を、記録の削除と区別して `invalid-status` にした。Hook は `cd` の移動先と `--head`・MCP の `head` から PR を作る checkout を判定し、作成元を特定できない場合や判定先に取り込み先より先のコミットがない場合は未確認と伝えるようにした（次の項目で置き換え）。
- [x] 再レビューで改行区切りの `cd` の見落としを指摘された（2026-10-24）。シェルの解析による推定をやめ、Hook を `PostToolUse` に移して作成された PR の head・base のコミットを判定する。`check-pr` に `--head` を加え、設定と状態ファイルを判定するコミットから読むようにした。
- [x] 再々レビューの指摘に対応する（2026-10-24）。PR のコミットを確認できない場合は、作業中の checkout に記録がなくても未確認と伝える。`impact-mismatch` を変更全体の判定にした。
- [x] SSOT の再定義に合わせて PR #22 を作り直す（2026-10-24）。`docs/ssot.md` に定義・登録・影響・PR 作成時の確認を置き、`docs/work-records.md` は記録の規則だけにした。`ssot.paths` の読み取りと検証、`check-pr` の注意（`ssot-review`）と判定できない理由（`invalid-status`・`ssot-missing`）、Hook の改名（`hooks/ssot_check.py`）、`ssotImpact` への改名（雛形と既存記録4件）、wip・sdd・pr・git の Skill、雛形、README、利用先の例、検証手順、CHANGELOG、Codex マニフェストを更新した。

## 検証・結果

| 対象の条件 | 確認方法 | 結果・根拠 |
| --- | --- | --- |
| Codex の PreToolUse で Bash・MCP ツールを検出し、additionalContext を返せる | 公式文書の確認 | 確認済み。`ask` は未対応 |
| Codex の PostToolUse に `tool_response` が渡り、additionalContext を返せる | 公式文書の確認（2026-10-24） | 確認済み。同じイベントの Hook は同時に起動する。Bash の `tool_response` の構造は文書に記載がない |
| `scripts/wip.py` の一覧と削除判定 | `tests/test_wip.py`（6件、一時リポジトリ） | 成功。squash で取り込んだ `done` の記録も `deletable`、取り込み後の編集・未追跡ファイル・再開・状態ファイルの欠落は削除不可 |
| このリポジトリの記録の状態ファイル | `scripts/validate.py` | 成功。不正・欠落を検出することも確認 |
| 構造・参照・Skill・配布設定 | `scripts/validate.py`、アンカー照合、`quick_validate.py`（Skill 10件）、`python3 -m unittest discover -s tests`（113件）、`claude plugin validate .`、Codex のカタログ確認 | 成功。`claude plugin validate` の警告は develop と同じ既知のもののみ |
| 管理外のファイルを含む記録 | 一時リポジトリで無視対象 `evidence.local` を置いて再現し、修正後にテストで確認 | 修正前は `deletable`、修正後は未追跡・無視対象・隠しファイルのいずれも `changed` |
| ステージ済みの変更を含む記録 | 一時リポジトリで、編集をステージしてから作業ファイルだけ元に戻した状態（`MM`）を再現し、修正後にテストで確認 | 修正前は `deletable`、修正後は `changed`。新しいテストは修正前のコードで失敗する |
| `check-pr` と `sdd.path` | `tests/test_wip.py`（追加4件） | 成功。実装だけの変更で `sot-not-updated`、SOT の更新で解消、SOT が先行する変更は指摘なし、記録なしの SOT 変更・判断のずれ・不正な状態を指摘、設定した `sdd.path`・`wip.path` を使う、記録を削除する変更と未コミットの変更は対象外 |
| PR 作成後の Hook の入出力 | `tests/test_ssot_check.py`（8件、偽の `gh`） | 成功。PR 作成以外は無出力で `gh` も呼ばない、Bash と MCP の実行結果から PR を特定する、PR の head・base のコミットで判定する（別ブランチの checkout・未コミットの設定変更・別の worktree の影響を受けない）、URL なし・複数・別リポジトリ・同じコミットを持つ別リポジトリ・`gh` の失敗・不正な出力・タイムアウト・コミットの欠落・リポジトリ外は未確認（作業中の checkout に記録がなくても伝える）、PR の head で SSOT が未登録なら無出力、判定できない理由と不正な設定を伝える |
| SSOT の再定義後の `check-pr` | `tests/test_wip.py`（check-pr 6件） | 成功。未登録なら適用しない（`docs/`・AGENTS.md があっても推測しない）、影響ありの記録・実装の変更・SSOT の変更なしがそろったときだけ注意を1件出し、影響なしの記録は挙げない、SSOT の更新で条件から外れても整合の確認とは扱わない、SSOT の先行・記録だけ・影響なし・記録なしの SSOT 変更では注意しない、状態ファイルの欠落・不正と登録パスの欠落は判定できない理由として別に伝える、SSOT ディレクトリ内の記録は SSOT の変更に数えない、設定は head から読み `.`・`..`・絶対パス・空・型違いを拒否する |
| テストが実装の誤りを検出できるか（SSOT の再定義後） | 実装を意図的に壊した変異版でテストを実行 | `docs` を SSOT と推測する、ルートを許す、影響なしの記録でも注意する、実装の変更や SSOT の変更を見ない、記録を SSOT の変更に数える、登録パスの欠落を伝えない、欠落時も判定する、設定を作業ディレクトリから読む、Hook が判定できない理由を黙る、の10通りすべてでテストが失敗する |
| テストが実装の誤りを検出できるか | 実装を意図的に壊した変異版でテストを実行 | 設定を作業ディレクトリから読む、状態ファイルや差分を HEAD から取る、リモートやコミットの確認を外す、タイムアウトを外す、複数の URL を許す、記録のないリポジトリでも判定する、`--head` を無視する、確認できない場合に作業中の checkout で黙る、リポジトリ外で黙る、`impact-mismatch` を記録単位にする、不正な記録があっても `impact-mismatch` を出す、の各変異でテストが失敗する |
| PR を作る checkout の判定（PR #22 の指摘、後に PostToolUse 方式へ置き換え） | 一時リポジトリで基準 checkout から `cd <worktree> && gh pr create` を再現し、修正後にテストで確認。このリポジトリでも主 checkout を cwd として実行 | 修正前は基準 checkout を判定して無通知、修正後は worktree を判定して `sot-not-updated`。`$変数` への移動・サブシェル・`--head` の不一致・`--repo`・解析できないコマンド・先行コミットのない checkout は未確認と伝える。新しいテストは修正前のコードで失敗する |
| 状態ファイルだけが欠けた記録（PR #22 の指摘） | `tests/test_wip.py`（追加1件） | 修正前は指摘なし、修正後は `invalid-status`（`status.json is missing`）。記録全体の削除と `.` で始まるディレクトリは従来どおり対象外 |
| 製品内での `sweep` の実行 | 新しいセッションでの依頼 | 未実施 |
| 製品内での PR 作成後の Hook | 両製品の新しいセッションでの PR 作成。`tool_response` の実際の形を含む | 未実施 |

## 中断・再開と完了

現在地: PR (1) は #21 で取り込み済み。PR (2) の #22 は、レビュー指摘への対応と SSOT の再定義に合わせて作り直した。再レビュー・取り込み待ち。取り込み後に、両製品での `sweep` と PR 作成後の Hook の確認が残る。`sweep` の確認は、削除できる `20261022-worktree-default-policy` を使い別 PR で行う。
