# GitHub Actions 予約投稿キュー（無料・±5分）

このフォルダの `posts.json` が「予約の真実」です。GitHub Actions が **5分ごと**に起動し、
`scheduled_at` の時刻が **±QUEUE_TOLERANCE_MINUTES** の窓に入った `pending` を投稿します。

## セットアップ手順（最短）

1. このリポジトリを GitHub に push する
2. GitHub の **Repository secrets** に以下を登録する
   - `THREADS_USER_ID`
   - `THREADS_ACCESS_TOKEN`
3. `queue/posts.json` に予約を追加する（雛形は `queue/posts.example.json`）
4. `queue/posts.json` を commit / push する
5. GitHub の **Actions** タブで workflow が動いていることを確認する

## `posts.json` のルール

- `scheduled_at` は **タイムゾーン付きISO**推奨（例: `2026-04-12T21:30:00+09:00`）
- `status`
  - `pending`: 未投稿（Actionsが対象にする）
  - `posting`: 投稿処理中（二重投稿防止）
  - `posted`: 投稿完了（`threads_post_id` が入る）
  - `failed`: 失敗（`last_error` を見る）

## 遅延（GitHub Actionsのズレ）について

GitHub の scheduled workflow は数分ズレることがあります。
そのため runner は **「±許容」に加えて、少し過ぎた pending も拾う**設定になっています（`QUEUE_OVERDUE_EXTRA_MINUTES`）。

## 手動実行

GitHub Actions の `threads-queue` workflow を **Run workflow** できます。

## トラブルシュート（よくある事故）

### GitHub Actions がすぐ落ちる（Secrets）
workflow 冒頭で **`THREADS_USER_ID` / `THREADS_ACCESS_TOKEN` が空**なら失敗します（値はログに出しません）。

### ローカル（PowerShell）で `.env` を更新したのに反映されない
Windows のユーザー/システム環境変数に **`THREADS_ACCESS_TOKEN` などが既に入っている**と、状況によっては `.env` よりそちらが優先されます。

このリポジトリの `main.py` / `mei-threads` は **`load_dotenv(..., override=True)`** にして、基本的に `.env` が勝つようにしています。
それでもおかしい場合は、環境変数の残骸（短いダミー値）を疑ってください。

### `Invalid OAuth access token`（code 190）
トークン文字列の破損・期限切れ・コピペミスが多いです。Secrets を作り直してください。
