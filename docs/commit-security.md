# コミット前のセキュリティチェック

HQ は、ステージ済みファイルのローカルパス・環境変数ファイル・秘密情報らしい値を検出するスクリプトと、Git Hook の導入・更新手順を提供します。Python 3.10 以上と Git 2.31 以上を使用し、追加の Python パッケージや通常実行時のネットワーク接続は不要です。

## 利用者の導入手順

1. HQ Plugin をインストールします。この操作だけでは Git 設定や既存 Hook を変更しません。
2. 対象プロジェクトで「HQ のコミット前チェックを有効にして」と依頼するか、以下のコマンドを実行します。
3. 通常どおりコミットします。検出・検証失敗時は Git Hook がコミットを中止します。

`<HQ_ROOT>` はインストールした HQ Plugin のルートへ置き換えます。利用先プロジェクトのルートで実行します。

```bash
python3 "<HQ_ROOT>/scripts/setup_security.py" install --repo .
python3 "<HQ_ROOT>/scripts/setup_security.py" status --repo .
```

状態が `ready` なら、HQ のコピー済みスクリプトと実行可能な Git Hook が揃っています。検出規則自体の完全性を保証する状態ではありません。

スクリプトは Git の共通管理ディレクトリ内の `hq-commit-security/check.py` へコピーし、標準の `hooks/pre-commit`・`hooks/pre-merge-commit`・`hooks/pre-applypatch` に同じ呼び出しを設置します。通常のコミット、ローカルの自動マージコミット、`git am` のパッチ適用後のコミットを対象にします。グローバル設定と `core.hooksPath` は変更しません。コピーは Git 管理対象にならず、Plugin の移動・アンインストール後も残ります。clone 先では再導入が必要です。同じ Git 共通管理ディレクトリを使う worktree には Hook とコピーを共有し、チェック時は各 worktree の index を読みます。worktree 固有の `core.hooksPath` がある場合は、そちらへの組み込みが必要です。

対象の既存 Git Hook や `core.hooksPath` がある場合、`install` はそれらを上書きせず停止します。既存の Hook を HQ と併用する場合は、その Hook を [`<Hook 名>.d/`](#チェックの前に処理を走らせる) へ移してから `install` すると、チェックの前に実行されます。移した Hook が自身の配置場所を前提にしていないかは確認します。Husky・pre-commit 等、`core.hooksPath` や独自の Hook で管理している場合は、次の操作でスクリプトだけをコピーし、その呼び出しを既存 Hook へ組み込みます。

```bash
python3 "<HQ_ROOT>/scripts/setup_security.py" prepare --repo .
```

既存 Hook 内で実行する処理の例です。既存処理と HQ のどちらの失敗も、Hook 全体の非ゼロ終了へ反映してください。既存管理ツールが別の作業ディレクトリや環境を使う場合は、それに合わせて調整します。

```sh
python3 "$(git rev-parse --git-common-dir)/hq-commit-security/check.py" || exit $?
```

既存管理方法への手動組み込みは `status` で実行経路を保証できません。`external-hook-unverified` または `hook-missing-or-modified` と表示します。既存管理方法のテスト手順と、隔離したリポジトリで拒否されるコミットの試験で確認します。

## チェックの前に処理を走らせる

HQ の Hook は、同じ場所にある `<Hook 名>.d/` の実行ファイルを名前の順に実行してから、最後にチェックを実行します。整形のようにステージ内容を変える処理や、プロジェクト固有の確認は、Hook を書き換えずにここへ置きます。HQ の Hook の内容は変わらないため、`status` は `ready` のままです。

```bash
hooks_dir="$(git rev-parse --git-common-dir)/hooks"
mkdir -p "$hooks_dir/pre-commit.d"
cp <処理のスクリプト> "$hooks_dir/pre-commit.d/10-format"
chmod +x "$hooks_dir/pre-commit.d/10-format"
```

- Hook ごとに `pre-commit.d/`・`pre-merge-commit.d/`・`pre-applypatch.d/` を使います。worktree には共有され、Git 管理対象にはなりません。clone 先では置き直します。
- 名前の順に実行します。順序は `10-`・`20-` のような番号の接頭辞で決めます。`.` で始まる名前は無視します。
- 各処理は Hook と同じ作業ディレクトリ・引数・環境変数で実行します。`GIT_INDEX_FILE` も引き継ぐため、`git commit -a`・`git commit --only` でも、コミットに使う index を `git add` 等で更新できます。
- チェックは最後に実行し、処理が更新した後の index を検査します。処理がステージした内容も検出の対象です。
- 処理が非ゼロで終了した場合や、実行できないもの（実行権限のないファイル・ディレクトリ・リンク切れ）がある場合は、チェックの前にコミットを止めます。黙って飛ばしません。
- 処理の内容は利用先の管理物です。処理はチェックと同じ権限で動くため、信頼できるものだけを置きます。`status` は HQ の Hook とコピーしたチェックだけを確認し、`<Hook 名>.d/` の内容は保証しません。`uninstall` は `<Hook 名>.d/` を残し、以後は実行されなくなります。

Git 2.54 以降は設定で Hook を追加でき（`hook.<名前>.command`）、HQ の Hook より先に実行されます。それより前の Git は設定の Hook を表示なしで無視するため、使う Git の版や、GUI クライアントが同梱する Git によって処理が抜けます。版によらず実行するには `<Hook 名>.d/` を使います。

## 普段の使い方

導入後は通常の `git commit`・マージコミット・`git am` により自動実行します。部分ステージ、`git commit -a`、`git commit --only` では Git がコミットに使用する index を読み、未ステージの作業ツリーを検証済みと取り違えません。手動で同じチェックを実行することもできます。

```bash
python3 "$(git rev-parse --git-common-dir)/hq-commit-security/check.py"
```

HQ 開発リポジトリでコピー前のソースを確認する場合は、次を使用します。

```bash
python3 scripts/commit_security.py
```

出力はルール名・リポジトリ相対のファイル名・行番号です。該当行・秘密値は出力しません。終了コードは、問題なしが 0、検出が 1、Git・ポリシー等の検証不能が 2 です。修正後は再ステージしてから再実行します。

## 検出範囲

| ルール | 検出する内容 |
| --- | --- |
| `env-file` | `.env`・`.env.*`・`*.env`・`*.env.*`・`.envrc` 系。`.example`・`.sample`・`.template` で終わる雛形は名前の規則から除外し、内容は検査 |
| `local-path` | macOS・Linux・Windows の具体的なユーザーディレクトリと macOS の `/var/folders/` 系一時パス。`$HOME`・`/Users/<user>/project` 等の変数参照や雛形とは区別 |
| `private-key` | PEM・OpenSSH 等の秘密鍵開始ヘッダー |
| `service-token` | GitHub・OpenAI・AWS・Google API・Slack・Stripe の代表的なキー／トークンの形式 |
| `secret-assignment` | API キー・トークン・秘密値・パスワード等への8文字以上の具体値の代入。明示的なプレースホルダーや変数参照を区別 |
| `unscannable` | UTF-8・BOM 付き UTF-16 で読めないファイル、NUL を含むファイル、10 MiB 超のファイル、submodule の参照。黙って検証済みとしない |

対象は追加・変更・コピー・名前変更されたファイルのステージ済み内容全体です。削除したファイルの内容、変更のない既存ファイル、過去の履歴、submodule 内部、展開前の圧縮データ、Git LFS のポインターが指す実体は監査しません。シンボリックリンクはリンク先を辿らず、Git に保存されるリンク先文字列を確認します。バイナリと判定した小さなファイルも、読める部分の既知トークン等は検査します。

規則による最低限の検出です。未知形式・短い秘密値・難読化／分割された値・未対応のパス形式等は見逃す可能性があります。検出だけで実際の認証情報だと断定せず、誤検出の可能性も確認します。漏えいした実値と判明した場合は、コミットからの除去だけでなく、そのサービスで失効・再発行します。

## 必要な例外を限定する

検出時に規則を一律無効化せず、実値を除去するか、文書のパスを変数・プレースホルダーに置き換えることを優先します。テスト用の合成値やレビュー済みバイナリ等で必要な場合だけ、利用先の `.hq/v2/security.json` に例外を記録します。

```bash
python3 "$(git rev-parse --git-common-dir)/hq-commit-security/check.py" --fingerprints
```

このオプションは秘密値の代わりに内容の fingerprint を追加表示します。テキスト検出は該当行の SHA-256、ファイル名・検証不能の検出は Git の blob ID（submodule は commit ID）です。

```json
{
  "version": 1,
  "allow": [
    {
      "path": "tests/fixtures/example.txt",
      "rule": "local-path",
      "fingerprint": "sha256:<表示されたハッシュへ置換>",
      "reason": "ローカルパス検出用の合成データであることをレビューした"
    }
  ]
}
```

パスは完全一致で指定し、ワイルドカードによる除外は行いません。対象・規則・内容の fingerprint がすべて一致した検出だけを除外します。他の規則は引き続き適用し、内容が変われば例外は一致しなくなります。ハッシュを作るために秘密値をコマンド引数や例外設定へ転記しないでください。

ポリシー自体も Git にステージします。未ステージの例外設定は読みません。ポリシーが不正・競合中・読み取り不能ならチェックを止めます。例外を変更するコミットでは、理由と対象をレビューします。

## 更新・解除と状態表示

HQ Plugin の更新だけではコピー済みコードと Hook は変更しません。更新内容を確認し、各リポジトリで明示的に更新します。`update` はコピーしたチェックと、以前の版の HQ の Hook を現在の版に置き換えます。コピーを手編集している場合は上書きせず停止します。手編集した Hook や HQ 以外の Hook は置き換えません。

```bash
python3 "<HQ_ROOT>/scripts/setup_security.py" update --repo .
python3 "<HQ_ROOT>/scripts/setup_security.py" status --repo .
```

`not-installed` は未導入、`damaged` はコピー／管理情報の欠損や変更、`hook-missing-or-modified` は Hook の欠損・変更・実行権限不足、`external-hook-unverified` は外部管理経路の未確認、`update-available` は稼働するコピーまたは Hook が HQ の現在の版より古いことを示します。問題があれば通常のコミットを進める前に確認します。

HQ が設置した標準 Hook（以前の版を含む）とコピーを解除する場合は次を使います。同じ Git 共通管理ディレクトリの worktree にも影響します。既存 Hook や外部管理経路がある場合は自動削除せず、先にその管理方法で HQ の呼び出しを除去します。`<Hook 名>.d/` は残します。

```bash
python3 "<HQ_ROOT>/scripts/setup_security.py" uninstall --repo .
```

## Plugin Hooks と保証の境界

Codex 向けの `hooks/codex.json`、Claude Code 向けの `hooks/hooks.json` で `SessionStart` を提供します。Git リポジトリで導入状態を読み取り、未導入・設定切れ・更新候補をエージェントへ通知します。利用先への書き込み・自動インストールはしません。正常時は何も通知しません。

Codex では Plugin の有効化に加え Hook 定義への信頼が必要です。対応するバージョン・実行環境で確認してください。共通設定は両製品が提供する `CLAUDE_PLUGIN_ROOT` を利用します。

Plugin Hooks は Git のコミットイベントではなく、他のターミナルや一つのコマンド内でのステージ更新を完全には追跡できません。そのため、停止処理は Git の `pre-commit` 等の Hook が担当します。Python やコピーしたスクリプトがなくなった場合もコミットは失敗します。

GitHub 上で作成するコミットにはローカル Hook は適用されません。Git Hooks は `--no-verify`・設定変更・低レベル Git 操作等で回避でき、clone だけでは有効になりません。通常作業で回避せず、失敗を成功扱いしません。悪意ある改変への強制や全経路での保証が必要な場合は、サーバー側の必須 CI 等を別途設計します。

## 開発時の検証

```bash
python3 -m unittest discover -s tests -v
```

隔離した Git リポジトリで、検出と正常系、部分ステージ、初回コミット、名前変更・削除・特殊なファイル名、worktree、Git の一時 index、例外、読み取り失敗、既存 Hook の保全、`<Hook 名>.d/` の処理の順序・失敗・index の更新、以前の版の Hook の更新、実際のコミット停止を確認します。モデル呼び出しは不要です。配布設定・対象製品での確認は [README の検証手順](../README.md#検証) に従います。
