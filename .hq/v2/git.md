# HQ の Git・GitHub 運用

通常の作業とリリース準備は `develop` から作業ブランチを作り、PR で `develop` へ取り込む。リリースは別の PR で `develop` から `main` へ取り込む。値は [settings.json](settings.json)、リリース固有の条件は [release.md](release.md) に置く。

新規の作業ブランチは `<type>/<short-description>`。type は Conventional Commits と揃え、タイトルも同規約の簡潔な一行とする。作成ツール名の接頭辞は付けない。関連する既存ブランチは再利用する。

## 必須検証

以下はすべてリポジトリルートで実行する。アプリケーションではないため、別途の型チェック・ビルド・単体テストを一律には要求しない。実行スクリプトを変更する場合は、その変更に応じた正常系・失敗系も検証する。

| 段階 | 必須の確認 |
| --- | --- |
| コミット前 | `python3 scripts/validate.py` と `git diff --cached --check`。ステージ内容と CHANGELOG 更新の要否も確認 |
| PR 作成前・取り込み前 | [検証手順](../../docs/validation.md) にある構造・参照・両製品の配布設定の検証と `git diff --check` |
| リリース PR 作成前・取り込み前 | 上記に加え `python3 scripts/validate.py --release`。公開対象・バージョン・CHANGELOG の内容を確認 |

既知のルート `CLAUDE.md` 警告は検証手順の説明に従う。それ以外の警告・エラーを放置しない。同じ変更に対する有効な検証結果は再利用できるが、追加変更・競合解消で影響を受けた検証は再実施する。配布前のモデルによる確認は検証手順のケースから変更に応じて選び、未実施なら明記する。

## PR と接続先

PR の作成・更新は pr の手順を使う。このリポジトリでは独自の `.hq/v2/pr.md` を設けず、標準の書式を使う。後から同ファイルを追加した場合は、その指示・書式を優先する。

PR の省略を恒常的に許可する変更区分は設けない。例外はその作業に対する明示的な指示に従い、作業ブランチと必須検証を維持する。配布・テスト用ツールという分類だけで省略しない。

remote は `origin`、接続先は `git@github.com:tom-e-kid/hqv2.git`。導入時に空のリポジトリへ既存の `main` と `develop` を初期登録し、その後は上記の PR 運用を適用する。既存の main の履歴やマニフェストにバージョンがあっても、公開済みの証拠とは扱わない。

導入時点では自動実行する CI を収録していないため、上記の検証を手動で実施し PR に結果を記載する。GitHub 側のブランチ保護・必須 CI・承認条件を追加した場合は、その条件も取り込み前に確認する。

## コミット前のセキュリティチェック

コミット前は上記の必須検証に加え、`python3 scripts/commit_security.py` を必須とする。[導入手順](../../docs/commit-security.md) に従い、Git の Hook でも実行する。新しい clone では再導入する。`--no-verify` 等で回避せず、検出・検証失敗時はコミットを止める。例外は `.hq/v2/security.json` に対象・規則・内容の fingerprint と理由を記録し、ステージしてレビューする。

スクリプトや Hook を変更した場合は `python3 -m unittest discover -s tests -v` を実施する。コピー済みコードへの反映は `scripts/setup_security.py update` で明示的に行う。
