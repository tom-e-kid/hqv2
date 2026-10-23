# 作業記録のライフサイクル管理の設計

状態: 合意済み（2026-10-23）

## 要求との対応

[要求](requirements.md) の Goal を、状態ファイル、重み、要求の書式、判定スクリプト、`sweep` Skill、PR 作成前チェックで実現する。

## 実現方法と判断理由

### A. 状態ファイル

各記録に `wip/<作業名>/status.json` を置く。

```json
{ "status": "active", "weight": 2, "prs": [123] }
```

- `status`: `active`（進行中）・`paused`（保留）・`done`（完了・取りやめ）。取りやめも `done` とし、理由は記録本文に残す。
- `weight`: 1〜3。重み 1 は通常記録を作らないが、依頼などで作った場合も表せるようにする。
- `prs`: この作業の PR 番号。PR を作成した時点で wip または pr の手順で追記する。
- 状態ファイルがない、または不正な記録は、一覧で警告し、`sweep` は削除しない。

空ファイルを目印にする案より、PR が複数ある場合や重みを一つのファイルで表せ、差分で変化を追えるため JSON とした。一覧はスクリプトで表にする。

### B. 重み

2026-10-23 のレビューで、下表の 2（影響があれば更新）と 3（docs/ を変更）の条件が重なり、同じ作業をどちらにも分類できると指摘された。sdd は小さな修正でも大枠を変えるなら docs/ の更新を求めるため、規模と SOT への影響を同じ軸で扱うと矛盾する。そこで次の優先順位で決める形に改めた。規則の本文は `docs/work-records.md` に置く。

1. SOT の範囲を変える作業は、規模にかかわらず 3。
2. SOT を変えない、目的・範囲が明確な小さな作業は 1。
3. それ以外は 2。重み 2 の作業で SOT を変えると分かったら 3 に変える。

当初の表（参考。工数は目安として残す）:

| 重み | 定義（docs/ への影響） | 目安の工数 | 作業記録 |
| --- | --- | --- | --- |
| 1 | docs/ を変更しない。バグ修正・小改修 | ～1日 | 作らない |
| 2 | 影響があれば docs/ を更新する | ～3日 | モデルが判断する |
| 3 | docs/ を変更する。機能追加・大きめの仕様変更 | 5日以上 | 作る |

定義は docs/ への影響を主とし、工数は目安にとどめる。重みは作業中に変えてよく、変えた理由を記録に残す。

### C. 要求の書式

`requirements.md` の見出しを Goal・Context・Constraints・Done When にする（この記録で試行中）。`design.md` は実現方法・判断理由・大枠への影響・検証方針を持つ。1ファイルの `work.md` は同じ4項目の後に実現方法とタスクを置く。

Goal・Constraints・Done When は要求の側に属するため、`design.md` ではなく `requirements.md` に置く案を推奨する。`design.md` に置くと、wip が区別している「要求」と「設計判断」が混ざる。Done When は `sweep` と wip が完了を判断する根拠にも使う。

### D. 判定スクリプト `scripts/wip.py`

Python 標準ライブラリだけで動く。保存先は `.hq/v2/settings.json` の `wip.path` に従う。

- `list`: 記録ごとの状態・重み・PR と、状態ファイルの欠落・不正を表で出す。
- `sweepable --base <ref>`: `<ref>` の時点で `done` になっている記録を、削除できるものとして出す。`git show <ref>:<path>` で読むため、GitHub の API や取り込み方法に依存しない。
- `check-pr --base <ref>`: `<ref>...HEAD` で変更された記録の重みと、SOT（`sdd.path`、未指定は `docs`）の変更有無を突き合わせる。判定結果を返すだけで、PR 作成を止めない。判定の向きは F を参照。

### E. `sweep` Skill

`skills/sweep/SKILL.md` を共通 Skill として追加する。wip の実行を前提にせず、記録の形式と `scripts/wip.py` を使う。

1. 取り込み先（ベースブランチ）を利用先の規約・設定から確定する。
2. `sweepable` の記録について、Done When と継続して必要な内容の反映先を確認し、記録への参照を反映先かコミットを固定した URL に付け替えて削除する。ブランチ・コミット・PR は利用先の規約と依頼の範囲で行う。
3. 削除しないが伝えるもの: 状態ファイルの欠落・不正、`done` だが未取り込み、PR がすべてマージ済みなのに `active`、Done When が未記載。経過日数だけで状態を推測しない。

開発専用の work-maintenance は、`sweep` を読む入口に作り直す。判断基準は `sweep` に一本化し、HQ 固有の処理（develop 向け PR、並行実行のロック、通知の条件、週次タスクの前提）だけを残す。名前は変えないため、週次タスクの指示文は変更不要。

### F. PR 作成前チェック

目的は SOT と実装の乖離を防ぐこと。重みと SOT の変更有無の突き合わせは、乖離の可能性に気づくためのきっかけとして使う。SOT は詳細を網羅しない指針であり、開発は常に SOT を目指す。このため判定には向きがある。

- 実装が SOT の範囲（主要要求・基本設計・方針・制約）を変えたのに、SOT が更新されていない: 乖離として注意する。重み 3 で SOT の変更がない場合を主な検出条件とし、重み 2 で記録の Context に SOT への影響が書かれている場合も対象にする。注意では、実装を SOT に合わせるか、合意して SOT を更新するかを確認させる。
- SOT が先に更新され、実装が追いついていない: SOT を目指す途中として扱い、注意しない。
- 重み 1 で SOT を変更した: 見積もりのずれであり乖離ではないため、注意の対象にしない。

注意の文面は「SOT が変更されていない」だけでなく、関係する SOT の箇所と実装の差を確かめるよう促す。

- pr Skill: PR 作成前に `scripts/wip.py check-pr` を実行し、注意があれば本文や利用者への報告で扱う。実行できなければ記録を読んで同じ観点で確認する。
- Plugin Hook: `PreToolUse` で `gh pr create` と PR 作成用 MCP ツールを検出し、同じ判定の結果を `additionalContext` でモデルに渡す。拒否はしない。Claude Code は `hooks/hooks.json`、Codex は `hooks/codex.json` に追加する。Codex は公式文書で `PreToolUse` による Bash・MCP ツールの検出と `additionalContext` を確認済み。`ask` は Codex で未対応のため使わない。
- 取り込み先は、`gh pr create --base` の指定、作業ブランチの記録、`git.baseBranch` の順で決める。決まらなければ判定しなかったことを伝える。

Git には PR 作成のイベントがないため Git Hook は使わない。ブラウザ等で作成する PR は対象外とする。

### G. 文書と配布

- README: Skill 一覧と呼び出し例に `sweep`、作業記録の節に状態・重み・要求の書式、利用先のセットアップに `sweep` の定期実行の項目、Hook の全体像に `PreToolUse` を追加する。
- AGENTS.md の構成と責務、Codex マニフェストの説明、利用先の AGENTS.md の例、検証手順、CHANGELOG を更新する。
- `scripts/validate.py` の必須資源に `skills/sweep/SKILL.md` を加える。

## 大枠への影響

このリポジトリには PRD 等の docs/ がなく、AGENTS.md と README が構成・方針の正本を兼ねる。共通 Skill の追加と Hook の追加により、両方の構成・責務の記述を更新する。

## 検証方針

- `scripts/wip.py` の自動テスト: 一時リポジトリで状態ファイルの読み取り・欠落・不正、`sweepable` の取り込み先判定、`check-pr` の重みと docs/ の突き合わせ、`wip.path` の設定。
- Hook の入出力テスト: PR 作成コマンドの検出、注意の出力、取り込み先不明時の扱い、PR 作成以外の無出力。
- 既存の検証: `scripts/validate.py`、`quick_validate.py`、`python3 -m unittest discover -s tests`、`claude plugin validate .`、Codex のカタログ確認。
- 製品での確認: 両製品の新しいセッションで `PreToolUse` の注意が届くこと。未実施なら PR に明記する。

## 合意した判断（2026-10-23）

1. 要求の書式（Goal・Context・Constraints・Done When）は `requirements.md` に置く。
2. SOT の場所は標準を `docs/` とし、`.hq/v2/settings.json` の `sdd.path` で変更できるようにする。sdd・wip・PR 作成前チェックが同じ設定に従う。
3. `prs` は wip・pr の手順で追記する。
4. 既存記録3件の状態はエージェントの判断に任された。
5. PR を2つに分ける。(1) 状態・重み・書式・スクリプト（`list`・`sweepable`）・`sweep`・work-maintenance、(2) `sdd.path` と PR 作成前チェック。
