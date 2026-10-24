# HQ Plugin の検証

この文書は Plugin 自体を開発・保守するための検証手順です。実行する段階と必須条件は [Git 規約](../.hq/v2/git.md) に従います。すべてのコマンドはリポジトリのルートで実行します。

## 構造・参照と配布設定

Python 3.10 以上と、配布設定を確認する利用するツールの CLI を用意します。`scripts/validate.py` は Python 標準ライブラリだけで実行でき、PyYAML は不要です。

通常の構造・参照のチェックは以下です。

```bash
python3 scripts/validate.py
claude plugin validate .
claude plugin validate .claude-plugin/plugin.json
```

Claude Code はルートの `CLAUDE.md` がインストール先のプロジェクトコンテキストとして読み込まれない旨を警告します。このファイルは Plugin 自体の開発用なので、この警告は想定内です。それ以外の警告・エラーは内容を確認して解消してください。`--strict` を付けると、この想定内の警告もエラーになり検証に失敗します。

個人の設定を変更せず、Codex でカタログが読み込めることを確認できます。

```bash
codex -c "marketplaces.hq-marketplace.source=\"$(pwd)\"" \
  -c 'marketplaces.hq-marketplace.source_type="local"' \
  plugin list --marketplace hq-marketplace --available --json
```

JSON に `hq@hq-marketplace` が出ることを確認します。

## リリース準備の検証

リリース準備を確定する場合は、追加で次を実行します。

```bash
python3 scripts/validate.py --release
```

両マニフェストと設定の整合、対象バージョンの日付付き CHANGELOG を確認します。まだ `Unreleased` のみの開発中は、このチェックが失敗するのが意図した動作です。この検証だけで公開済みとは判断しません。

## Skill の専用検証と PyYAML

`scripts/validate.py` は、マニフェスト・カタログ・必須リソース・設定・Markdown のローカル参照と、各 Skill の frontmatter の名前・説明の基本形式を確認します。frontmatter 全体を YAML として解析するものではありません。成功しても YAML 全体の構文や他のフィールドの妥当性まで確認済みとは扱いません。

Skill を追加・変更する際、Codex の skill-creator が利用できる環境では、付属の `scripts/quick_validate.py` で追加確認できます。この外部ツールは HQ には同梱していません。配置を確認し、`skill_validator` に実際のパスを指定します。以下は標準的な配置の例です。

```bash
skill_validator="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
test -f "$skill_validator"
```

専用検証ツールは PyYAML に依存します。`ModuleNotFoundError: No module named 'yaml'` が出た場合は検証が起動しておらず、Skill の検証成功を意味しません。システムの Python を変更せず、一時仮想環境に依存を導入し、その環境の Python で実行します。以下は過去の検証で使用した PyYAML 6.0.3 を指定した例です。パッケージ取得にはネットワーク接続が必要です。

```bash
validation_env="$(mktemp -d "${TMPDIR:-/tmp}/hq-validation.XXXXXX")"
python3 -m venv "$validation_env"
"$validation_env/bin/python" -m pip install 'PyYAML==6.0.3'
for skill in skills/*/; do
  "$validation_env/bin/python" "$skill_validator" "$skill" || exit 1
done
```

各コマンドの成功を確認してから次へ進み、全 Skill が `Skill is valid!`・終了コード 0 となることを確認します。ツールや依存がなく実行できなかった場合は、その理由と未実施の範囲を記録します。PyYAML はこの専用検証ツールの依存であり、HQ Plugin の実行時依存ではありません。Plugin の利用者に導入を要求しません。

## 検証スクリプトの構成と実行時間

現時点では `scripts/validate.py` を共通検証の入口として維持します。検証項目の増加により実行時間が開発や CI の支障になった場合は、まず検証単位の所要時間を計測し、時間のかかる処理を特定します。そのうえで、処理間の依存関係と共有ファイルへの書き込みの有無を確認し、独立した検証の並列実行を検討します。

ファイル分割だけでは並列実行にはなりません。保守性のための関数・モジュール分割と、実行時間を短縮するための並列化を分けて判断します。並列化する場合も、全検証の結果を集約し、一つでも失敗したら全体が失敗する挙動を維持します。プロセス起動などの負荷も含めて効果を計測してから採用します。

## モデルによる動作確認

カタログの読み込みと構造検証は、モデルが手順に従って作業することの保証ではありません。実プロジェクトでの確認項目と期待結果は [実プロジェクト検証チェックリスト](ssot/validation-checklist.md) で管理します。配布前に変更に応じたケースを選び、利用するツールの新しいセッションで確認し、対象・結果・根拠と未実施範囲を記録してください。

## PR フィードバック対応

待機中断の変更では、実行中の待機との競合、プロセス強制終了後の検出、旧状態の読み込み、回数・処理履歴の保持、二重通知防止を自動テストで確認します。macOS では利用するツール内でアイドルスリープ抑止と解除、手動スリープ後の復帰、Hook 打ち切り後の次回検出も確認します。子プロセスや時刻を差し替えたテストだけで、OS・ホストの挙動を確認済みとしません。

`python3 -m unittest discover -s tests -v` で、待機・ページ分割・複数レビュアー・失敗・排他・再開・上限・Hook 入出力を確認します。[運用手順](../skills/pr-feedback/references/operations.md) に沿って利用するツールの新しいセッションで PR 作成後の登録、Stop による待機・継続、返信・Resolve、修正後の再確認、対応回数の上限と終了報告を検証します。API を差し替えたテストやマニフェスト検証だけでツール内の動作を確認済みとしません。Codex の Interrupt と Codex・Claude Code の SessionEnd も対象です。

レビュアーの設定変更では、文字列との互換性、`waitAfterPush` が true/false の混在、初回未到着、現 head の再レビュー未到着、下書き・取り消し、追加指摘、Resolve の対象者判定、旧状態・対応回数の上限の保持を確認します。総評を除外したレビューの到着でも静穏期間を取り直し、期限到達だけで収束しない境界条件を含めます。

## PR 作成前の作業記録確認

`python3 -m unittest discover -s tests -p 'test_pr_preflight.py' -v` で、停止・中間 PR の再実行・base/head の変更による再確認・不正状態・取得失敗・設定した保存先を確認します。作成後の SSOT Hook は別の確認として維持します。利用するツール内での停止・理由の配送・再実行は [S52](ssot/validation-checklist.md#s52-pr-作成前の作業記録確認) で確認し、自動テストの成功と区別します。
