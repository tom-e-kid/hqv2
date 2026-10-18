# PR #6 Claude レビューへの対応

対象: `79def40` に対するローカルの `pr6-review.md`（2026-10-18）。全9件を確認した。以下の fix は既存の要求を満たすための補強であり、監視期間・最大3回・対象製品・外部操作の許可範囲は変更しない。

| 指摘 | 判断と根拠 | 対応 |
| --- | --- | --- |
| High 1: バッチ内変更後に復旧不能 | fix。respond の内容照合と finish の返信必須条件は妥当だが、stop/register は内容を更新せず閉塞する | refresh で同一バッチを更新し、履歴と回数を保持。変更項目は最新 fingerprint による再評価を要求。削除・他者による Resolve は superseded として記録し、返信なしで完了可能。再出現時は再評価 |
| High 2: Copilot の login 不一致 | fix。実際の GraphQL API で copilot-pull-request-reviewer を確認し、設定例の Copilot では一致しない | 大小文字・末尾の [bot] を正規化し、README・運用手順・設定例を修正。完了検出と Resolve の投稿者判定も統一 |
| Medium 3: 総評が毎回バッチになる | fix。実際の Copilot の総評は指摘なしでも本文を持つ。本文を無条件に対象にすると回数消費が発生する | ignoreReviewBodies を追加し、省略時は Copilot の総評を除外。通常コメント・個別スレッド・head ごとの完了検出は維持。本文に指摘を載せるレビュアーは除外しないよう文書化 |
| Medium 4: 許可外の返信で再処理される | fix。ただし本文が渡る事実だけで任意の push が可能とは断定できない。既存 Skill も本文を指示・権限として扱わない。新バッチを発生させる入力の制限は必要 | authorAssociation を取得し、設定レビュアーと OWNER/MEMBER/COLLABORATOR の追記だけを契機とする。全本文を信頼されていない文脈と明示し、許可外の追記も投稿前の変更検出・Resolve 阻止に使用 |
| Low: SSH URL・末尾スラッシュ | fix。対象範囲内の github.com の有効な origin を拒否する | ssh://git@github.com/ と末尾 / を許可し、対象 repository の一致条件は維持 |
| Low: Git 失敗が認証エラー扱い | fix。ローカル Git の失敗を通信・認証の問題と案内するのは不正確 | Git と gh の案内を分離し、detached HEAD は専用メッセージで拒否。生の stderr は表示しない |
| Low: Hook 登録失敗が見えない | fix。branch 不一致などがモデルの文脈に返らない | 登録失敗を additionalContext に返し、監視未確認と明示。入力や認証情報は含めない |
| Low: 同一セッションの2本目で監視が残る | fix。session の紐付け上書きにより最初の監視が取り残される | session ごとのロック下で2本目を拒否し、明示 stop 後に登録。旧担当からの停止・引き継ぎ手順も記載 |
| Low: respond の report 不足メッセージ | fix。要求する操作名が誤っている | 実行コマンド名に応じたエラーへ変更 |

## 検証

- `python3 -m unittest discover -s tests -v`: 全65件成功（従来49件、新規16件）。編集後の復旧、削除・他者による Resolve・再オープン、push 後の追記、途中投稿からの再開、API/head 競合、Copilot の総評と完了検出、許可外の追記、登録失敗・セッション引き継ぎを確認。
- `python3 scripts/validate.py`、`git diff --check`: 成功。
- Claude Code の root/manifest 検証: 成功。既知のルート CLAUDE.md 警告のみ。
- Codex の一時設定付きカタログ検証: hq@hq-marketplace を認識。制限環境で PATH alias を作れない警告が出たが、カタログ取得自体は成功。
- Skill 専用検証: 通常の Python には PyYAML がなく起動できなかったため、既存の一時仮想環境で実行し成功。システムの依存・設定は変更していない。
- 修正した GitHub.snapshot を microsoft/vscode#342304 に対して読み取り専用で実行: Copilot の login、本文のある総評、総評を除外した対応対象0件を確認。authorAssociation を含むクエリも API が受理。最初の制限環境での接続失敗後、承認されたネットワークアクセスで確認した。

実際の AI レビューへの返信・Resolve を伴う試験、両製品内での Hook 起動・継続は従来どおり後続の導入検証とし、今回も実施しない。

このレビューはローカルファイルとして提供されたため、GitHub のレビューコメントへの返信・Resolve の対象はない。自動監視のバッチとしては登録せず、レビュー対応は今回1回。Issue 化する候補や判断保留はない。


## 反映と競合解消

レビュー修正は `135829d`。PR #5 の取り込みで更新された develop (`136014a`) を作業ブランチへ取り込み、CHANGELOG の競合は両方の項目を保持して解消した。自動統合された README・検証手順・Git Skill・利用先の指示例も確認し、PR #5 の変更を保持した。構造・参照とステージ済み内容のセキュリティチェックを再実施し成功した。実行コードとテストには統合による変更がないため、65件成功の結果を再利用する。
