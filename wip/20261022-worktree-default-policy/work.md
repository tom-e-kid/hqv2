# worktree 標準運用の統一

概要: Plugin 全体の worktree 指示を確認し、新規作業の標準運用と利用先での項目別上書きを揃える。
状態: 更新・静的検証完了。develop 向け PR の提出対象。取り込みは未実施。

## 要求と合意

- 新規作業は専用 worktree と作業ブランチを作り、再開は再利用する。
- 標準運用をそのまま利用先 AGENTS.md に転記・編集でき、未指定項目に標準を適用する。
- 長期開発系列と個別作業の用途を整理し、配置を CLI 任せにしない。
- HQ 自体の AGENTS.md にも、新規作業ごとの作業ブランチ・専用 worktree 作成、再開時の再利用、標準配置を明記する。追加合意: 2026-10-22 のユーザー指示「このプロジェクト自体のポリシー」「作業ごとに作業ブランチを切ってworktreeを切りたい」。
- 合意の根拠: 2026-10-22 のユーザー指示「Plugin全体のworktreeに関連する指示を一通り確認して一貫性のあるように更新」。直前に提示した標準運用と上書き方式を対象とする。

## 設計と範囲

git Skill から参照する `references/worktree.md` に標準運用・上書き例・必要な確認をまとめる。README、利用先 AGENTS.md 例、設定説明、検証ケース、CHANGELOG を揃える。Hook・監視の共有状態や開発用 Plugin 反映元の保全は、運用方針と両立するため変更しない。製品固有のコピー仕様も変更しない。

## タスクと検証

- [x] Plugin 全体と開発専用 Skill の関連記述を確認
- [x] 標準運用・項目別上書き・長期系列と個別作業の区別を整備
- [x] 関連文書・記載例・CHANGELOG を更新
- [x] HQ 自体の AGENTS.md に同じ運用を明記
- [x] 構造・参照、両製品の配布設定、差分の整合性を検証

作業ブランチ: `docs/worktree-default-policy`。取り込み先: `origin/develop`。新規作業用 worktree は基準 checkout の `.hq/v2/.ignore/worktrees/worktree-default-policy/` に作成した。

## 検証結果と未実施範囲

- `python3 scripts/validate.py`: 成功。7 shared skills、両 Marketplace、129 ローカル参照を確認。
- `git diff --check` と `git diff --cached --check`: 成功。
- `python3 scripts/commit_security.py`: 成功。ステージ済み9ファイル、明示的例外0件。
- PR 作成前の確認: 最新の `origin/develop` は分岐元と一致し、同じ作業ブランチの既存 open PR はなかった。
- `claude plugin validate .` と `claude plugin validate .claude-plugin/plugin.json`: 通常プロファイルは終了コード 0。既知のルート CLAUDE.md 警告あり。追加表示された公開ディレクトリ向けの LICENSE 未設定・アイコン不足は、変更前の develop でも同一であることを確認。ライセンス選択や公開素材の追加は今回の範囲外。公開ディレクトリへの提出条件が満たされたとは扱わない。
- Codex の一時的な設定上書きによる `plugin list --marketplace hq-marketplace --available --json`: 成功。対象 worktree のカタログで `hq@hq-marketplace` を確認。恒久的な Marketplace 登録は変更していない。
- Skill 専用の `quick_validate.py skills/git`: 一時仮想環境に PyYAML 6.0.3 を導入して成功。
- 文書レビュー: 未指定時の新設、項目別上書き、作成済み環境の再利用、基準 checkout 起点の配置、長期系列との併用、整理条件を照合。参照文書と利用先例の標準運用6項目が一致することを確認。
- 文書のみの変更のため、モデル呼び出しによる製品内の実行テストは未実施。Plugin の再インストールと利用先での動作確認も未実施。

2026-10-22 のユーザー指示「PR出してくれる？」に基づき、コミット・push と develop 向け PR 作成を行う。未取り込みのため作業用 worktree と作業記録は保持する。取り込みと Plugin 反映は未実施。
