# 作業記録のライフサイクル管理の設計

状態: 合意済み（2026-10-23）

## 要求との対応

[要求](requirements.md) の Goal を、状態ファイル、SOT への影響の判断、要求の書式、判定スクリプト、`sweep` Skill、PR 作成前チェックで実現する。

## 実現方法と判断理由

### A. 状態ファイル

各記録に `wip/<作業名>/status.json` を置く。

```json
{ "status": "active", "sotImpact": true, "prs": [123] }
```

- `status`: `active`（進行中）・`paused`（保留）・`done`（完了・取りやめ）。取りやめも `done` とし、理由は記録本文に残す。
- `sotImpact`: SOT への影響の判断（`true`・`false`）。
- `prs`: この作業の PR 番号。PR を作成した時点で wip または pr の手順で追記する。
- 状態ファイルがない、または不正な記録は、一覧で警告し、`sweep` は削除しない。

空ファイルを目印にする案より、PR が複数ある場合や SOT への影響を一つのファイルで表せ、差分で変化を追えるため JSON とした。一覧はスクリプトで表にする。

### B. SOT への影響

着手時に、作業が SOT の範囲（主要要求・基本設計・方針・制約）を変えるかを二択で判断し、`sotImpact` に残す。影響ありなら必ず記録を作り、影響なしなら残す判断・引き継ぎ・合意の必要性からモデルが判断する。規模・工数では決めない。規則の本文は `docs/work-records.md` に置く。

経緯: 当初は重み 1〜3 と工数の目安で決めていたが、2026-10-23 のレビューで重み 2 と 3 の条件の重なりを指摘された。いったん SOT への影響を優先する順位で整理した後、同日のユーザー指示「重みについては工数は忘れよう。SOTに影響があるか、ないかの二択から始めるか。SOTに影響があるものは必ずwip書く。ないものはLLM判断」により二択にした。

### C. 要求の書式

`requirements.md` の見出しを Goal・Context・Constraints・Done When にする（この記録で試行中）。`design.md` は実現方法・判断理由・大枠への影響・検証方針を持つ。1ファイルの `work.md` は同じ4項目の後に実現方法とタスクを置く。

Goal・Constraints・Done When は要求の側に属するため、`design.md` ではなく `requirements.md` に置く案を推奨する。`design.md` に置くと、wip が区別している「要求」と「設計判断」が混ざる。Done When は `sweep` と wip が完了を判断する根拠にも使う。

### D. 判定スクリプト `scripts/wip.py`

Python 標準ライブラリだけで動く。保存先は `.hq/v2/settings.json` の `wip.path` に従う。

- `list`: 記録ごとの状態・SOT への影響・PR と、状態ファイルの欠落・不正を表で出す。
- `sweepable --base <ref>`: `<ref>` の時点で `done` になっている記録を、削除できるものとして出す。`git show <ref>:<path>` で読むため、GitHub の API や取り込み方法に依存しない。
- `check-pr --base <ref>`: `<ref>...HEAD` で変更された記録の `sotImpact` と、SOT（`sdd.path`、未指定は `docs`）の変更有無を突き合わせる。判定結果を返すだけで、PR 作成を止めない。判定の向きは F を参照。

### E. `sweep` Skill

`skills/sweep/SKILL.md` を共通 Skill として追加する。wip の実行を前提にせず、記録の形式と `scripts/wip.py` を使う。

1. 取り込み先（ベースブランチ）を利用先の規約・設定から確定する。
2. `sweepable` の記録について、Done When と継続して必要な内容の反映先を確認し、記録への参照を反映先かコミットを固定した URL に付け替えて削除する。ブランチ・コミット・PR は利用先の規約と依頼の範囲で行う。
3. 削除しないが伝えるもの: 状態ファイルの欠落・不正、`done` だが未取り込み、PR がすべてマージ済みなのに `active`、Done When が未記載。経過日数だけで状態を推測しない。

開発専用の work-maintenance は、`sweep` を読む入口に作り直す。判断基準は `sweep` に一本化し、HQ 固有の処理（develop 向け PR、並行実行のロック、通知の条件、週次タスクの前提）だけを残す。名前は変えないため、週次タスクの指示文は変更不要。

### F. PR 作成前チェック

目的は SOT と実装の乖離を防ぐこと。`sotImpact` と SOT の変更有無の突き合わせは、乖離の可能性に気づくためのきっかけとして使う。SOT は詳細を網羅しない指針であり、開発は常に SOT を目指す。このため判定には向きがある。

- 実装が SOT の範囲（主要要求・基本設計・方針・制約）を変えたのに、SOT が更新されていない: 乖離として注意する。`sotImpact: true` の記録で SOT の変更がない場合を検出条件とする。注意では、実装を SOT に合わせるか、合意して SOT を更新するかを確認させる。
- SOT が先に更新され、実装が追いついていない: SOT を目指す途中として扱い、注意しない。
- SOT を変更したが、変更に含まれる記録がすべて `sotImpact: false`: 判断のずれであり乖離ではないため、注意ではなく判断の見直しを伝える。PR が記録を触ったことはその記録の作業が SOT を変えたことを意味しないため、変更全体で判定し、どの記録が誤りかは断定しない。影響ありの記録が一つでもあれば指摘しない（2026-10-24、PR #21 への試行で `status.json` を足しただけの記録が指摘されたため）。

注意の文面は「SOT が変更されていない」だけでなく、関係する SOT の箇所と実装の差を確かめるよう促す。

- pr Skill: PR 作成前に `scripts/wip.py check-pr` を実行し、注意があれば本文や利用者への報告で扱う。実行できなければ記録を読んで同じ観点で確認する。
- Plugin Hook: `PostToolUse` で `gh pr create` と PR 作成用 MCP ツールを検出し、作成された PR へ同じ判定を行って、結果を `additionalContext` でモデルに渡す。Claude Code は `hooks/hooks.json`、Codex は `hooks/codex.json` に追加する。当初は `PreToolUse` でコマンドを解析して PR を作る checkout を推定したが、改行区切りの `cd` などを見落とし、シェルの書き方を網羅できないため改めた（2026-10-24）。`PreToolUse` の注意も実行結果とともに届くため、時点の違いはない。
- 判定の根拠は作成された PR にする。実行結果から PR の URL を一つ特定し、`gh pr view` で head・base のコミット ID を取得して、そのコミットで判定する。設定と状態ファイルも head のコミットから読む。作業中のリポジトリは Git オブジェクトへのアクセス手段として使い、PR のリポジトリを指すリモートがあることと、両コミットが手元にあることを確かめる。PR の特定・リポジトリの対応・`gh` の取得（失敗・タイムアウト）・コミットのいずれかが欠ければ、判定せずに未確認と伝える。黙るのは、PR の base・head のどちらにも記録がないと確認できた場合だけとし、作業中の checkout の状態は根拠にしない。

Git には PR 作成のイベントがないため Git Hook は使わない。ブラウザ等で作成する PR は対象外とする。

### G. 文書と配布

- README: Skill 一覧と呼び出し例に `sweep`、作業記録の節に状態・SOT への影響・要求の書式、利用先のセットアップに `sweep` の定期実行の項目、Hook の全体像に SOT 確認の Hook を追加する。
- AGENTS.md の構成と責務、Codex マニフェストの説明、利用先の AGENTS.md の例、検証手順、CHANGELOG を更新する。
- `scripts/validate.py` の必須資源に `skills/sweep/SKILL.md` を加える。

## 大枠への影響

このリポジトリには PRD 等の docs/ がなく、AGENTS.md と README が構成・方針の正本を兼ねる。共通 Skill の追加と Hook の追加により、両方の構成・責務の記述を更新する。

## 検証方針

- `scripts/wip.py` の自動テスト: 一時リポジトリで状態ファイルの読み取り・欠落・不正、`sweepable` の取り込み先判定、`check-pr` の `sotImpact` と SOT の変更の突き合わせ、`wip.path` の設定。
- Hook の入出力テスト: 偽の `gh` を使い、入力の種類ごとに確認する。PR の URL の有無・複数、リポジトリの不一致（同じコミットを持つ別リポジトリを含む）、`gh` の失敗・不正な出力・タイムアウト、head・base のコミットの欠落、checkout の切り替えと未コミットの設定変更が判定に混ざらないこと、別の worktree から作った PR、記録のないリポジトリの無出力。実装を意図的に壊してテストが失敗することも確かめる。
- 既存の検証: `scripts/validate.py`、`quick_validate.py`、`python3 -m unittest discover -s tests`、`claude plugin validate .`、Codex のカタログ確認。
- 製品での確認: 両製品の新しいセッションで、PR 作成後の `PostToolUse` の注意が届くこと。実行結果（`tool_response`）の形は単体テストとは別の未検証項目として扱う。未実施なら PR に明記する。

## 合意した判断（2026-10-23）

1. 要求の書式（Goal・Context・Constraints・Done When）は `requirements.md` に置く。
2. SOT の場所は標準を `docs/` とし、`.hq/v2/settings.json` の `sdd.path` で変更できるようにする。sdd・wip・PR 作成前チェックが同じ設定に従う。
3. `prs` は wip・pr の手順で追記する。
4. 既存記録3件の状態はエージェントの判断に任された。
5. PR を2つに分ける。(1) 状態・SOT への影響・書式・スクリプト（`list`・`sweepable`）・`sweep`・work-maintenance、(2) `sdd.path` と PR 作成前チェック。
