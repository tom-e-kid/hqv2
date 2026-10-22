# 作業メモの週次整理を試行する

概要: HQ 開発専用 Skill に作業メモの評価・分類・整理・PR 提出手順を定義し、週次実行で試す。
状態: Skill の実装・静的検証済み。週次タスクを登録済み。[PR #17](https://github.com/tom-e-kid/hqv2/pull/17) を develop 向けに提出し、取り込み待ち。定期実行での実動作は未検証。

## 要求と合意

2026-10-22、ユーザーは作業メモの定期チェック観点を Skill に記載し、それを実行するタスクで、変更があれば PR 提出まで行う構成に対して「対応進めてくれる？」と依頼した。週1回深夜の希望に対し、毎週日曜 3:00（日本時間）を提示した内容で試行を進める。

- 対象は HQ 自体。汎用化・Plugin 配布は試行結果を見て判断する。
- 状態更新、active 維持、archived への移動、削除を根拠に基づいて判断する。
- 変更があれば検証して develop 向け PR 作成・更新まで行い、自動マージしない。
- マージ済みだけで作業全体を完了にしない。不明なものは保持する。
- 今回は作業メモを対象とし、既存 worktree・ブランチの削除は対象外。

## 設計とタスク

`.agents/skills/work-maintenance/SKILL.md` に手順を集約し、Claude Code 用の相対シンボリックリンクを置く。定期タスクには対象 checkout と Skill の実行指示を置く。Skill が develop に取り込まれる前は整理を実行しない。

- [x] Skill・README・Claude Code 用リンクを作成する。
- [x] 静的検証と、現行記録に対する読み取り評価で分類条件を確認する。
- [x] 開発専用 Skill の追加を develop 向け PR にする。
- [x] 毎週日曜 3:00（Asia/Tokyo）のタスクを登録する。
- [ ] 最初の数回の PR で誤分類・整理漏れ・通知頻度を評価する。

作業ブランチ: `feat/work-maintenance`。取り込み先: `origin/develop`。worktree は主 checkout 配下の `.hq/v2/.ignore/worktrees/work-maintenance/`。

開発専用のため、Plugin のマニフェスト・共通 Skill・CHANGELOG は変更しない。配布する利用者向け動作の変更は含まない。

## 検証と初期評価

- `python3 scripts/validate.py`: 成功。7 shared skills・両 Marketplace・136 ローカル参照を確認。
- Skill Creator の `quick_validate.py`: 一時仮想環境に PyYAML 6.0.3 を入れて成功。通常の Python 環境は変更していない。
- Claude Code 用リンクの実体が `.agents/skills/work-maintenance/` と一致することを確認。
- `git diff --check`、`git diff --cached --check`、`python3 scripts/commit_security.py` とコミット時の Git Hook: 成功。ステージ済み4ファイル、明示的例外0件。
- `claude plugin validate .` とマニフェスト指定の通常検証: 終了コード0。既知のルート CLAUDE.md 警告と、変更前から存在する任意の Directory 提出用 LICENSE・icon 不足の表示あり。
- Codex の一時設定による対象 worktree のカタログ読み込み: `hq@hq-marketplace` を確認。個人の Marketplace 設定や Plugin キャッシュは変更していない。制限環境で PATH alias 作成警告あり。
- 読み取り評価: GitHub の merged PR 検索で PR #16 の取り込みと develop の merge commit を照合。worktree 方針の記録は「未取り込み」のままであり、状態更新と保存先の判断の候補になる。今回その記録自体は編集していない。
- 読み取り評価: pr-feedback の PR #6・#11・#12 は merged だが、記録と PR 本文に実機確認の残件がある。自動的な完了・削除には分類せず、残件の扱いを確認する。今回その記録自体は編集していない。
- 手順の机上確認: 未コミットの最終記録は先にコミット、squash で履歴保存を確保できない場合は archived、判断不明・競合中は保持、既存整理 PR は再利用、無変更は通知しない条件を確認。モデルによる独立した実行テストや実際の記録移動・削除は未実施。

定期タスク ID: `hq`。このチャットに紐づく heartbeat として ACTIVE で登録し、登録ファイルの週次・日曜・03:00 の設定と対象チャットを読み取り確認した。origin/develop に Skill が存在しない間は整理を保留する。定期実行中の GitHub 認証・push・PR 作成、ロックと通知抑制の実挙動は最初の実行で確認する。
