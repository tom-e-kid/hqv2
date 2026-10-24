# 最後の PR での完了状態と作成前チェックの設計

[要求](requirements.md) に基づく。作成後の既存 Hook への統合案は撤回し、独立した `PreToolUse` Hook を追加する。

## 共通規則と手順

`docs/references/work-records.md` を共通規則として更新する。Done When は取り込みまでに確認できる条件とし、取り込み自体で満たされる条件だけを例外とする。必須検証の未実施を成功にしない。作業の最後の PR に `done` と最終記録を含め、同じ変更で削除しない。同じ目的に必要な残作業が見つかったら active へ戻す。

wip・pr・git は作成前に最後の PR かを判断し、sweep は PR がすべて取り込まれても active の記録を設定漏れの可能性として報告する。要求の雛形と実プロジェクト検証チェックリストも更新する。

## Pre チェック

`hooks/pr_preflight.py` を両ツールの `PreToolUse` に登録する。既存の作成後 SSOT チェック・AI レビュー監視は維持する。

- 単独の gh pr create の明示した repository・base・head、または既知の MCP 入力形式から対象を取得する。複雑なシェル・省略・未知の形式を推測しない。未対応形式は未確認として止め、対応する明示形式を案内する。
- ホストを含めて remote と照合し、gh api の remote の branch ref から base/head のコミットを取得する。コミットがローカルに存在することを確認する。未取得は fetch を案内し、勝手に fetch しない。
- head の設定・状態ファイルを読む。merge base からの変更に含まれる記録を対象とする。SSOT 未定義でも同じ確認を行い、削除された記録は対象外とする。
- 記録なし・すべて done は通す。active・paused は最終 PR かの判断を促す理由を付けて deny する。不正・欠落・取得失敗も未確認として deny する。
- 最後の PR なら、エージェントが条件を確かめて done と最終記録を commit・push し、再実行する。
- 中間 PR なら、残作業を作業記録に残して commit・push した後、同スクリプトの `--reviewed --reason` で判断理由を保存する。対象・コミット・記録に一致する判断結果がある場合だけ再実行を通す。
- 保存先は worktree ごとの Git 管理領域 hq/pr-preflight。原子的な置換で保存し、別の対象・コミット・worktree の結果を流用しない。状態は自動変更しない。

現在の対象は同一リポジトリ内のブランチ。fork/head_repo、未知の MCP schema・シェル形式は未対応として停止する。全作成経路の強制境界ではなく、対象外経路や Hook の無効化・信頼・ホスト側のエラー継続は別の制約として文書化する。

## 仕様確認と検証

Claude Code の PreToolUse の additionalContext はツール結果とともに届くため、作成前に判断させるには deny が必要。[公式仕様](https://code.claude.com/docs/en/hooks#pretooluse-decision-control) を確認した。[Codex の公式仕様](https://learn.chatgpt.com/docs/hooks) も deny と permissionDecisionReason をサポートする（2026-10-24）。公式仕様確認とツール内での実動作確認は区別する。

自動テストは一時リポジトリと偽 gh で正常系・停止・再実行・コミット変更・別 worktree・不正状態・取得失敗を確認する。通過判定を壊した変異版でも停止のテストが失敗することを確認する。構造・参照・変更 Skill の専用検証・両ツールの配布設定を確認し、実プロジェクト検証は S52 に未実施として残す。

## SSOT への影響

作業記録の完了条件と PR 作成前の確認方法を変えるため ssotImpact は true。PRD の R3・R4 と合意の記録、検証チェックリストを更新する。詳細は共通資料へ置き、PRD へ全実装を複製しない。
