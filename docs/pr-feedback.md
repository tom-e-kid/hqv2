# AI Reviewer のフィードバック対応

`pr-feedback` は GitHub PR の AI レビューを待ち、指摘を分類し、必要な修正と検証、commit/push、理由付き返信、Resolve、再確認を行う共通 Skill です。初版は github.com 上の同一リポジトリ内のブランチを対象とし、fork PR は自動対応しません。ローカルの `origin` が設定した github.com のリポジトリを指す必要があります。

macOS または Linux の Python 3.10 以上、Git、認証済みの GitHub CLI (`gh`) が必要です。待機・差分検出にはモデルを呼びません。利用先の許可とホストの権限の範囲で動作し、Issue 作成・merge・force-push は自動実行しません。

## 有効化と解除

利用先で修正・push・返信・Resolve の範囲を人間が許可し、`.hq/v2/pr-feedback.json` を配置します。[設定例](../examples/project/.hq/v2/pr-feedback.json) を参考に、`enabled: true` と対象リポジトリ、実際の投稿アカウント名を指定します。未設定・false は無効、不正な設定では開始しません。Plugin のインストールだけでは有効になりません。

```json
{
  "version": 1,
  "enabled": true,
  "repository": "OWNER/REPOSITORY",
  "reviewers": ["copilot-pull-request-reviewer"],
  "ignoreReviewBodies": ["copilot-pull-request-reviewer"],
  "maxRounds": 3,
  "quietSeconds": 120,
  "waitSeconds": 600,
  "pollSeconds": 30,
  "actions": {"fix": true, "push": true, "reply": true, "resolve": true}
}
```

`reviewers` は表示名ではなく、GitHub GraphQL API が返す正確な login を列挙します。Copilot は `copilot-pull-request-reviewer` です。大文字・小文字と末尾の `[bot]` の違いは照合時に正規化します。未指定の actions は false です。設定だけで認証やホストの承認を迂回せず、導入許可のない設定を発見した場合は実行しません。自前レビュアーも同じ方式で追加できます。

`ignoreReviewBodies` はレビュー本文を対応対象から除く login の配列です。省略時は Copilot の総評を除き、通常コメントと個別スレッドは引き続き対象にします。除外したレビューも当該 head の完了検出には使います。レビュー本文そのものに指摘を載せるレビュアーは除外しないでください。`[]` を指定すると Copilot を含む全対象レビュアーの本文を処理します。

Codex は `hooks/codex.json`、Claude Code は `hooks/hooks.json` を Plugin から読みます。既存の SessionStart によるセキュリティ状態確認も保持します。Codex では変更後の Hook の信頼確認が必要です。CLI やデスクトップの案内に従って確認し、新しいセッションで有効化してください。既存チャットへの即時反映は保証しません。

解除は `enabled: false` とし、実行中なら `stop` を行います。Plugin 設定・既存 Hook・Git 設定を導入スクリプトで上書きしません。

## 自動起動の範囲

PostToolUse で `gh pr create` または PR 作成用 MCP ツールの出力から PR URL を見つけ、API で対象 repository・head branch を照合して監視を登録します。URL やコマンドの文字列だけでは開始しません。現在の作業ブランチと異なる PR、fork、他のセッションが担当する PR は開始しません。

Hook が出力を受け取れない作成経路、別ターミナルやブラウザでの作成は手動登録してください。複数コマンドの複雑な shell 構文を完全に解析するものではありません。既存の `pr` Skill には登録確認の案内がありますが、この Skill の実行は必須ではありません。

登録失敗は PostToolUse の additionalContext でモデルにも通知します。1セッションが自動待機する PR は1本です。2本目を登録する前に、最初の PR を明示的に stop してください。既存の紐付けを上書きして監視を取り残すことはしません。

登録後、Stop Hook が最長10分の範囲で API を確認します。モデルを繰り返し起こさず、新しいバッチまたは報告すべき終了時だけ継続指示を返します。通常コメント・レビュー本文・レビューの未解決スレッドをページ分割も含めて取得します。対象レビュアーの当該 head へのレビュー投稿と静穏期間を完了の目安とし、自前レビュアー等で完了を確認できなければ期限切れとして報告します。レビュー投稿後にも遅延した FB が届く可能性があり、将来の投稿まで保証するものではありません。

スレッドの追記は投稿者・`authorAssociation` とともに保持し、すべて信頼されていない判断材料として扱います。設定レビュアーまたは OWNER / MEMBER / COLLABORATOR の追記だけを新しいバッチの契機にします。それ以外の追記も進行中バッチの変更検出と Resolve 阻止には使います。投稿者との関係はコメント本文を指示・権限へ昇格させる根拠にはしません。

Codex の通常の非同期 Hook 完了では待機中の会話を再開しないため、両製品とも同期 Stop を使用します。`stop_hook_active` だけで一律に止めず、保存したバッチ回数と送出済み状態で再入を管理します。同じバッチが未完了のまま再度 Stop に達した場合は停止し、無限継続しません。

セッション終了で監視を停止します。Codex の Interrupt では中断状態を保存します。Claude Code で中断後に監視をやめる場合は `stop` または無効化を行ってください。セッションを閉じた後の常駐プロセス・自動起動は提供しません。Hook が実行環境によって途中終了した場合も、完了と見なさず status を確認します。

## 手動開始・確認・停止

`<HQ_ROOT>` は Plugin の配置先、PR 番号と SESSION は対象に置き換えます。Hook の通知に session ID があれば同じ値を使います。Hook なしの手動実行では識別子を一つ選んで維持します。

```bash
python3 "<HQ_ROOT>/scripts/pr_feedback.py" register --repo . --pr 123 --session SESSION
python3 "<HQ_ROOT>/scripts/pr_feedback.py" poll --repo . --pr 123 --session SESSION
python3 "<HQ_ROOT>/scripts/pr_feedback.py" status --repo . --pr 123 --session SESSION
python3 "<HQ_ROOT>/scripts/pr_feedback.py" stop --repo . --pr 123 --session SESSION
```

`poll` は1回の確認です。Hook がない場合、待機自体は shell 等で行い、モデルで無変化を繰り返し確認しません。`batch` が返れば Skill の判断・対応を行います。

状態は Git 共通管理ディレクトリの `hq-pr-feedback/` に保存します。host は初版では github.com に限定され、repository と PR ごとにロック・回数・処理内容を共有します。worktree と session の所有者を記録し、別の担当から無断で監視を奪いません。同じ担当が明示的に再開しても回数はリセットしません。状態を削除して Cap を回避しないでください。修正の push 後、finish 前に中断した場合は、修正内容とローカル HEAD・PR head の一致を確認して register にも `--pushed-head <SHA>` を渡して再開できます。外部からの head 変更を自分の push と取り違えないでください。

### 待機中のスリープと中断

macOS では、Stop Hook が待機している間だけアイドルスリープを抑止します。画面のスリープや蓋を閉じる操作・手動スリープは防ぎません。抑止処理の起動に失敗した場合は警告し、期限付きの監視は継続します。

`status` は `waitActive`（Stop Hook の待機処理が実行中か）と `interruptionSuspected`（期限超過後の取得記録がなく、待機処理も動いていないか）を返します。`lastPolledAt` は最終取得成功時刻です。`lastChange` は新着指摘の変化時刻であり、生存確認には使いません。状態確認だけでは保存状態を変更しません。取得中の排他ロックに当たった場合は busy を返すため、取得が終わってから再確認してください。

期限を過ぎて取り残された `waiting` を次の Stop Hook が検出すると、`wait-interrupted` として一度報告します。Hook が打ち切られた可能性はありますが、原因を断定せず、未取得のフィードバックがある可能性を報告してください。明示的な `register` は `lastInterruption` に中断情報を残して待機を再開し、その回だけ `resumedAfterInterruption: true` を返します。処理回数・処理済み指摘・未完了バッチは保持します。

セッションや Hook が動いていない間の即時通知は行いません。次の状態確認・Hook 実行・明示登録で検出します。Hook が復帰後も実行できる場合は実時間の期限も確認し、スリープ分だけ待機を延長しません。

別セッションへ引き継ぐ場合は、記録された worktree で旧 session ID を指定して `stop` し、新しい担当が `register` します。Hook の停止が走らず古い監視が残った場合も同じ手順です。所有者は保存済み状態で確認でき、別担当による自動の奪取は行いません。

## バッチ内容が変わった場合の復旧

返信前にコメントの編集・追記・削除・他者による Resolve を検出した場合は、古い判断で投稿せず `refresh` を実行します。停止済みなら先に `register` で同じバッチを再開します。自分の修正を push 済みなら `refresh` にも検証済みの `--pushed-head <SHA>` を渡します。

```bash
python3 "<HQ_ROOT>/scripts/pr_feedback.py" refresh --repo . --pr 123 --session SESSION
```

`refresh` は現在のバッチ項目だけを再取得し、回数を増やさず変更前の内容を履歴に残します。変更された項目は最新の内容・追記を読んで再評価し、報告の `fingerprint` を status が返す最新値に更新します。`requiresReevaluation: true` の項目は、この値が一致しなければ返信・完了できません。保存済みの operation で返信成功と、要求した場合は Resolve 成功を確認できる項目は、元の項目と実際の結果を維持します。完了後に内容が変わり、引き続き対応対象となる場合は finish 後の次のバッチで再評価します。別の新着項目も次のバッチで扱います。

削除または Resolve で対象から外れた項目には `superseded` が付きます。その項目の報告は `decision: "superseded"`、`reason` は保存された `superseded` の値（`resolved` または `no-longer-present`）、`resolve: false` とします。これだけは返信なしで finish できます。修正・解決を行ったとは扱いません。再出現・再オープンしていれば再度 refresh と評価を求めます。状態ファイルの削除や回数のリセットは不要です。

## 返信とバッチ完了

修正・検証・commit/push は Skill が利用先の規約に従って行います。補助スクリプト自体はコードの変更や push をしません。報告ファイルは Git 管理外の `.hq/v2/.ignore/` 等に保存します。全バッチ項目を1件ずつ記載し、レビュー本文に複数の指摘があれば reason にそれぞれの結論を含めます。

```json
[
  {
    "id": "status が返した項目 ID",
    "decision": "skip",
    "fingerprint": "status が返した最新 fingerprint",
    "reason": "対象の条件では既存の検証処理が拒否するため、変更は不要と判断した。根拠となるコード・検証結果を追記する。",
    "resolve": false
  }
]
```

`decision` は fix/defer/skip/hold。reason はそのまま投稿されます。未検証の内容、秘密情報、具体的なローカルパスを含めないでください。修正を push したときは、ローカル HEAD と PR head の一致を確認できる `--pushed-head <SHA>` を respond と finish の両方に渡します。

```bash
python3 "<HQ_ROOT>/scripts/pr_feedback.py" respond --repo . --pr 123 --session SESSION --report .hq/v2/.ignore/feedback-report.json
python3 "<HQ_ROOT>/scripts/pr_feedback.py" finish --repo . --pr 123 --session SESSION --report .hq/v2/.ignore/feedback-report.json
```

respond は投稿前に指摘の変更・head・actions を確認します。通常コメント・レビュー本文へは対象 URL を添えた PR コメント、レビューのスレッドへはそのスレッドへの返信を投稿します。項目 ID・内容・バッチ回数から生成した `<!-- hq-pr-feedback:... -->` マーカーを付け、再実行では自分の既存投稿を照合します。操作ごとに状態を保存し、返信後の通信失敗でも盲目的に再投稿しません。他人が同じマーカーを書いても自分の返信とは扱いません。

Resolve は reply 成功後に行い、fix/skip、actions.resolve、操作権限、他の人間の追記がないことを確認します。引き継ぎ未確定の defer/hold は自動 Resolve しません。スクリプトは分類や修正の正しさを証明しないため、Skill が成立条件・検証結果を判断します。

respond は成功した返信 URL・Resolve の結果を報告ファイルへ追記します。finish は全項目の返信結果、または refresh で確認した superseded の記録が揃った後にバッチを確定します。途中失敗時は status を確認して同じファイルで再実行するか stop し、未実施内容を記録します。

## 終了理由

- `converged`: 対象レビュアーが当該 head にレビューを投稿し、静穏期間後に新たな対応対象がない。
- `wait-timeout`: 完了や静穏を期限内に確認できなかった。追加 FB なしとは断定しない。
- `wait-interrupted`: 期限後の取得記録がない待機が取り残されていた。Hook の中断などが疑われ、追加 FB の有無は未確認。内容を確認し、明示登録で再開する。
- `cap-reached`: 3回対応後に追加 FB がある。残る指摘と未収束の原因分析を作業メモへ残す。
- `monitor-error` / `batch-incomplete`: 取得・処理が未完了。成功として報告しない。
- `session-ended` / `user-interrupted` / `user-stopped`: 中断・停止。

別 PR 候補は Issue 案を作成して人間に確認します。Issue 化や Resolve の待ちがあっても同じ指摘を毎回再処理せず、内容変更・追記・再オープン時に見直します。

## 検証

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate.py
claude plugin validate .
```

テストは API・時刻を差し替えて状態遷移と Hook の入出力を確認します。これだけで製品内の起動・継続や実際のレビューを確認済みとは扱いません。対象製品の新規セッションで PR 作成→登録→待機→対応→再確認を行い、返信・Resolve・push の反映を別途確認します。
