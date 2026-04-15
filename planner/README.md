# Threads Planner UI（Cloudflare Pages + Access）

このフォルダは **Cloudflare Pages** 向けの最小UIです。

## 何ができるか

- `queue/posts.json` を **GitHub Contents API** 経由で読み書き
- Cloudflare Access で **サイト全体をあなた専用にロック**（A案）

> 予約投稿の実行自体は、既存の **GitHub Actions (`threads-queue`)** が担当します。  
> UIは「キュー編集」＋「即投稿（ワークフロー起動）」を担当します。

## Cloudflare側の設定（必須）

### 1) Pages プロジェクトを作成
- GitHubリポジトリ連携でOK
- **Root directory（プロジェクトのルート）** を `planner` に設定

### 2) Environment variables（Production / Preview 両方に）
以下を設定（値はここに書かない）:

- `GITHUB_TOKEN`  
  - 推奨: **Fine-grained PAT**
  - 必須権限:
    - `Contents: Read and write`（キュー編集）
    - `Actions: Read and write`（即投稿ボタンで workflow_dispatch を叩く）
- `GITHUB_OWNER`（例: `chiaki`）
- `GITHUB_REPO`（例: `ai-sns-team`）
- `GITHUB_BRANCH`（例: `main`）
- `GITHUB_WORKFLOW`（任意。未設定なら `threads-queue.yml`）
- `QUEUE_PATH`（デフォルト運用なら `queue/posts.json`）
- `ANTHROPIC_API_KEY`（生成機能を使う場合）
- `ANTHROPIC_MODEL`（任意。未設定なら `claude-opus-4-6`）

### 3) Cloudflare Access（A案）
PagesのURL（またはカスタムドメイン）に対して **Accessポリシー**を設定し、  
**あなたのアカウント（メール/Google/GitHub）だけ**許可してください。

## ローカル確認（任意）

Cloudflareのローカル実行は環境により手順が変わるため、基本は **Pagesへデプロイして確認**が最短です。
