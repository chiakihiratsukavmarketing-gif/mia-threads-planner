# AI SNS Team — めいのThreads自動投稿パイプライン

## セットアップ

### 1. 依存ライブラリのインストール
```bash
cd ai-sns-team
pip install -r requirements.txt
```

### 2. .env ファイルの作成
```bash
cp .env.example .env
```
`.env` を編集して以下を設定：

| 変数 | 内容 |
|---|---|
| `THREADS_USER_ID` | ThreadsのユーザーID（数字） |
| `THREADS_ACCESS_TOKEN` | 長期アクセストークン（60日有効） |
| `ANTHROPIC_API_KEY` | Claude APIキー |
| `DRY_RUN` | `true`にすると投稿せずテストのみ |
| `MAX_POSTS_PER_DAY` | 1日の最大投稿数（デフォルト: 3） |

### 3. Threads APIトークンの取得方法
1. [Meta for Developers](https://developers.facebook.com/) でアプリ作成
2. Threads APIを追加
3. ユーザートークン（短期）を発行 → 長期トークンに交換
4. `THREADS_USER_ID` は `GET /me?fields=id` で取得

---

## 使い方

### 今日のスケジュールを実行（推奨フロー）
```bash
python main.py run
```
1. `posts_schedule.csv` から今日の未投稿を取得
2. 投稿文を生成（またはCSVの既存文を使用）
3. **あなたがレビュー・編集・承認**
4. 承認したものだけ投稿

### 今日のスケジュールを自動実行（確認なし）
```bash
python main.py auto
```
`posts_schedule.csv` の「今日の未投稿」を対象に、本文が空なら自動生成してそのまま投稿します。

### 即席で投稿文を生成（スケジュール外）
```bash
python main.py generate
```

### 今日の投稿状況を確認
```bash
python main.py status
```

### ファイルを直接投稿
```bash
python main.py post data/drafts/draft_xxx.txt
```

### 最新の下書きを確認なしで投稿
```bash
python main.py post-latest --yes
```

---

## 安全設計

| 機能 | 内容 |
|---|---|
| **ヒューマンレビュー必須** | 全投稿を自分で確認・承認してから投稿 |
| **DRY RUNモード** | `.env`で`DRY_RUN=true`にすると実投稿しない |
| **1日上限制限** | `MAX_POSTS_PER_DAY`で上限を設定（デフォルト3件） |
| **投稿間隔** | 連続投稿時は`POST_DELAY_SECONDS`秒待機 |
| **投稿ログ** | `data/logs/posted.json`に全履歴を記録 |
| **APIエラーログ** | `data/logs/api_errors.json`にエラーを記録 |

---

## ファイル構成

```
ai-sns-team/
├── main.py               # CLIエントリーポイント
├── agents/
│   ├── generator.py      # Claude APIで投稿文生成
│   ├── scheduler.py      # posts_schedule.csv管理
│   └── poster.py         # Threads API投稿
├── data/
│   ├── drafts/           # 生成した下書き保存
│   └── logs/
│       ├── posted.json   # 投稿済み記録
│       ├── rate_limit.json  # レート制限ログ
│       └── api_errors.json  # APIエラーログ
├── .env                  # 環境変数（gitに含めない）
├── .env.example          # テンプレート
└── requirements.txt
```

---

## posts_schedule.csv の列について

スケジュールCSVに以下の列を追加すると生成精度が上がります：

| 列名 | 内容 |
|---|---|
| `テーマ` | 投稿のテーマ（例：育児と仕事の両立失敗談） |
| `投稿タイプ` | 共感型 / 保存型 / 会話型 |
| `メモ` | 具体的なエピソードや方向性ヒント |
| `投稿本文` | 既存の文章があればリライト、なければ新規生成 |
