# 作業記録のライフサイクル管理の要求

状態: 合意済み（2026-10-23。2026-10-24 に用語を SSOT に改め、PR 作成時の確認を再定義）。各項目の根拠は下記「合意済みの判断」と設計の「合意した判断」。

この記録は、提案中の要求の書式（Goal・Context・Constraints・Done When）を試験的に使う。

## Goal

作業記録（`wip/`）の状態と規模を機械的に読める形で残し、次の3点を実現する。

- 完了した記録の削除を、取り込み方法に依存せず安全に行う。判断は共通 Skill `sweep` が担う。（合意済み）
- 開発が SSOT（正本）を目指す形を保つため、SSOT を見直す機会の抜けを注意する。SSOT への影響を着手時に判断して記録に残し、SSOT が定義されたプロジェクトで、影響しうる作業の PR が実装だけを変えて SSOT を変えていない場合に、SSOT の確認・更新が必要かを確かめるよう伝える。意味の整合性は判定しない。（2026-10-23 のユーザー指示「PR作成前チェックの大きな目的は SOTと実装の乖離を防ぎたいということ」を、2026-10-24 にユーザーと機械的に判断できる範囲へ再定義）
- 作業の要求を Goal・Context・Constraints・Done When で明らかにし、着手・完了の判断材料を揃える。（ユーザー提案、書式の配置は相談中）

対象外: 取り込み方法の制限、PR 作成の強制的な停止、GitHub Actions など利用先リポジトリ側の仕組みの導入。

## Context

- 作業記録: `skills/wip/SKILL.md`、雛形 `skills/wip/assets/wip/`、保存先の設定 `wip.path`。このリポジトリの既存記録 `wip/20261018-pr-feedback/`、`wip/20261022-work-maintenance/`、`wip/20261022-worktree-default-policy/`。
- 整理: 開発専用の `.agents/skills/work-maintenance/SKILL.md` と週次の定期タスク。
- SSOT: sdd が作成・維持する文書（`skills/sdd/`）。共有の定義は新設する `docs/ssot.md`、登録は共有設定の `ssot.paths`。
- PR 作成: `skills/pr/SKILL.md`、Plugin Hook `hooks/hooks.json`（Claude Code）・`hooks/codex.json`（Codex）、PR 作成を検出する既存の `hooks/pr_feedback.py`。
- 文書・検証: README（利用先のセットアップ、Hook の全体像、作業記録の節）、`docs/validation.md`、`examples/project/`、`scripts/validate.py`、`tests/`、CHANGELOG、Codex マニフェストの説明。
- 関連する経緯: 削除は「完了にした変更では消さず、取り込み後に別の変更で消す」に決定済み（PR #20）。squash merge では同じ PR で作成・削除した記録が履歴に残らないことを確認済み。

## Constraints

- 各 Skill は単独で使える。`sweep` は `wip` の実行を前提にせず、記録の形式だけに依存する。
- 共通 Skill は製品固有の Hook に依存しない。Hook は任意の補助とし、Codex では信頼確認が必要。
- 利用先の運用（取り込み方法など）を制限しない。
- 未公開のため旧形式との互換処理は持たない。ただし状態ファイルのない記録を `sweep` が削除しないなど、判断できないものは安全側に倒す。
- スクリプトは Python 標準ライブラリだけで動く。
- 要求・設計をまとめて合意してから実装する。

## Done When

| 条件 | 確認方法 |
| --- | --- |
| 記録の状態を `wip/<作業名>/status.json`（`status`・`ssotImpact`・`prs`）で表し、wip が作成・更新する | Skill と雛形の記述、このリポジトリの既存記録への適用 |
| SSOT が扱う事項に影響する作業は、SSOT の定義の有無にかかわらず必ず記録を作り、影響しない作業はモデルが判断する | wip の記述と検証ケース |
| SSOT の定義（用語・対象・`ssot.paths` による登録・影響の範囲）が共有の規則にあり、sdd・wip・pr・git と判定スクリプトが同じ定義を参照する | 文書の記述と自動テスト |
| `done` の記録が取り込み先に入った後に、`sweep` が削除を判断・実施する。状態ファイルがない・不正な記録は削除しない | 一時リポジトリでのスクリプトの自動テスト |
| work-maintenance が `sweep` を読み、HQ 固有の処理だけを持つ | Skill の記述と週次タスクの指示文が変更不要であること |
| SSOT が定義され、変更に影響ありの記録があり、実装が変わって SSOT が変わっていない PR に、SSOT の確認・更新が必要かを確かめるよう止めずに伝える。判定できない理由は別に伝える。pr Skill と、作成した PR を確認する PostToolUse Hook の両方から同じ判定を使う | スクリプトと Hook 入出力の自動テスト、両製品での実機確認 |
| README に `sweep` の定期実行の設定手順、SSOT 確認の Hook を含む Hook の全体像、状態・SSOT への影響・`ssot.paths` の説明がある | README の確認とアンカー照合 |
| 要求の書式の扱いが決まり、雛形・Skill・検証ケースに反映されている | 雛形と Skill の記述 |
| 構造・参照・配布設定の検証、Skill の専用検証、自動テストが通る | `scripts/validate.py`、`quick_validate.py`、`python3 -m unittest discover -s tests`、`claude plugin validate .` |

## 合意済みの判断（2026-10-23）

- `sweep` を共通 Skill にし、開発専用の work-maintenance はそのまま `sweep` を参照する入口にする。README に設定手順を追加する。
- 状態は `status.json` で表す。完了は `done` で明示する。PR がマージ済みであることだけでは完了としない。
- SSOT に影響する作業は必ず記録を作り、影響しない作業はモデルが判断する。規模・工数では決めない（重み 1〜3 は廃止）。
- PR 作成前のチェックは、まず止めずに注意を伝える形にする。
