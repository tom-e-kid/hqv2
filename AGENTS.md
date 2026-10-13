# HQv2 のメンテナンス

このリポジトリはアプリケーションではなく、Codex と Claude Code で使える開発ノウハウの Skill 集を Plugin として配布する。
利用先プロジェクトの開発ルールは `examples/project/` にある。Plugin 自体の編集にその例を適用しない。

- Skill はそれぞれ `skills/<skill-name>/` に置く。大枠の策定・見直しは `skills/sdd/`、具体的な作業の相談・実装・検証・再開は `skills/steering/` に置く。
- 各 Skill は単独で使えるようにし、別 Skill の実行を前提にしない。
- Codex は `.codex-plugin/plugin.json`、Claude Code は `.claude-plugin/plugin.json` を使う。
- 名前とバージョンは両マニフェストで揃える。配布時は両方のバージョンを更新する。
- 製品固有のツール名、Next.js、特定のモデル、Hooks、専用サブエージェントを共通 Skill の前提にしない。
- 要求・設計をまとめて合意してから実装へ進む標準を維持する。大枠と作業の詳細を混同しない。
- 手順の変更時は参照文書、テンプレート、プロジェクト側の記載例との整合性を確認する。
- 検証は README の手順を使い、文書だけの変更でモデルを呼ぶ実行テストを必須にしない。
