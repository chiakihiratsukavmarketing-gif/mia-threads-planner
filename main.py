#!/usr/bin/env python3
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
"""
AI SNS Team — みあ（証券ウーマン）Threads自動投稿パイプライン

使い方:
  python main.py run        # 今日のスケジュールを確認→生成→レビュー→投稿
  python main.py auto       # 今日の未投稿を自動生成→自動投稿（確認なし）
  python main.py auto --tomorrow          # 明日の分を自動実行
  python main.py auto --date YYYY-MM-DD   # 指定日の分を自動実行
  python main.py auto --dry-run           # 投稿せずに処理だけ確認
  python main.py generate   # 生成のみ（投稿しない）
  python main.py compose    # テーマ/型/メモ→生成→あなたがOKで投稿
  python main.py status     # 今日の投稿状況を確認
  python main.py post <file># 指定テキストファイルを投稿
 python main.py post <file> --yes        # 確認なしで投稿
 python main.py post-latest [--yes]      # 最新の下書きを投稿
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

load_dotenv(Path(__file__).parent / ".env", override=True)

from agents.generator import generate_from_schedule_row, generate_post
from agents.poster import ThreadsPoster
from agents.scheduler import get_pending_posts, mark_as_posted

console = Console()


def cmd_run():
    """今日のスケジュール確認 → 生成 → ヒューマンレビュー → 投稿"""
    poster = ThreadsPoster()
    dry_run_label = "[yellow][DRY RUN][/yellow] " if poster.dry_run else ""

    pending = get_pending_posts()
    if not pending:
        console.print("[green]今日の未投稿スケジュールはありません。[/green]")
        return

    console.print(f"\n[bold]今日の未投稿: {len(pending)}件[/bold]")

    for i, row in enumerate(pending, 1):
        console.rule(f"[{i}/{len(pending)}] {row.get('投稿予定時間', '時間未設定')}")

        # 既存の投稿本文 or 自動生成
        existing = row.get("投稿本文", "").strip()
        if existing:
            console.print(Panel(existing, title="スケジュール済み投稿文", border_style="blue"))
            text = existing
        else:
            console.print("[cyan]投稿文を生成中...[/cyan]")
            text = generate_from_schedule_row(row)
            console.print(Panel(text, title="生成された投稿文", border_style="cyan"))

        # 文字数チェック
        console.print(f"[dim]文字数: {len(text)}字[/dim]")

        # ヒューマンレビュー
        choice = Prompt.ask(
            "どうしますか？",
            choices=["post", "edit", "skip", "quit"],
            default="skip",
        )

        if choice == "quit":
            console.print("終了します。")
            break
        elif choice == "skip":
            console.print("[yellow]スキップしました。[/yellow]")
            continue
        elif choice == "edit":
            console.print("[dim]投稿文を入力してください（空行で終了）:[/dim]")
            lines = []
            while True:
                line = input()
                if line == "":
                    break
                lines.append(line)
            text = "\n".join(lines)
            console.print(Panel(text, title="編集後の投稿文", border_style="green"))
            if not Confirm.ask("この内容で投稿しますか？"):
                console.print("[yellow]スキップしました。[/yellow]")
                continue

        # 投稿
        console.print(f"{dry_run_label}投稿中...")
        result = poster.post(text)

        if result["success"]:
            post_id = result["post_id"]
            if post_id == "DRY_RUN":
                console.print("[yellow][DRY RUN] 投稿は実行されませんでした。[/yellow]")
            else:
                console.print(f"[green]投稿完了！ post_id: {post_id}[/green]")
            if post_id != "DRY_RUN":
                mark_as_posted(row, threads_post_id=post_id)
        else:
            console.print(f"[red]投稿失敗: {result['error']}[/red]")

        if i < len(pending):
            poster.wait_between_posts()


def cmd_generate():
    """投稿文の生成のみ（スケジュール外の即席生成）"""
    console.print("[bold]投稿文を生成します[/bold]")

    topic = Prompt.ask("テーマ", default="育児と仕事の両立")
    post_type = Prompt.ask(
        "投稿の型",
        choices=["暴露型", "数字型", "逆説型", "共感型", "実績型", "スレッド型"],
        default="逆説型",
    )
    theme = Prompt.ask("方向性メモ（任意）", default="")

    console.print("[cyan]生成中...[/cyan]")
    text = generate_post(topic=topic, post_type=post_type, theme=theme)
    console.print(Panel(text, title="生成された投稿文", border_style="cyan"))
    console.print(f"[dim]文字数: {len(text)}字[/dim]")

    if Confirm.ask("ファイルに保存しますか？"):
        drafts_dir = Path(__file__).parent / "data" / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        filename = drafts_dir / f"draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filename.write_text(text, encoding="utf-8")
        console.print(f"[green]保存しました: {filename}[/green]")


def cmd_compose():
    """テーマ/型/メモを入力→生成→あなたがOKで投稿"""
    console.print("[bold]投稿文を作って、OKなら投稿します[/bold]")

    topic = Prompt.ask("テーマ", default="育児と仕事の両立")
    post_type = Prompt.ask(
        "投稿の型",
        choices=["暴露型", "数字型", "逆説型", "共感型", "実績型", "スレッド型"],
        default="逆説型",
    )
    theme = Prompt.ask("方向性メモ（任意）", default="")

    poster = ThreadsPoster()
    dry_run_label = "[yellow][DRY RUN][/yellow] " if poster.dry_run else ""

    text = ""
    while True:
        if text == "":
            console.print("[cyan]生成中...[/cyan]")
            text = generate_post(topic=topic, post_type=post_type, theme=theme)

        console.print(Panel(text, title="投稿文（確認してください）", border_style="cyan"))
        console.print(f"[dim]文字数: {len(text)}字[/dim]")

        choice = Prompt.ask(
            "どうしますか？",
            choices=["post", "edit", "regen", "save", "quit"],
            default="post",
        )

        if choice == "quit":
            console.print("終了します。")
            return

        if choice == "save":
            drafts_dir = Path(__file__).parent / "data" / "drafts"
            drafts_dir.mkdir(parents=True, exist_ok=True)
            from datetime import datetime
            filename = drafts_dir / f"draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filename.write_text(text, encoding="utf-8")
            console.print(f"[green]保存しました: {filename}[/green]")
            continue

        if choice == "regen":
            console.print("[cyan]再生成します...[/cyan]")
            text = generate_post(topic=topic, post_type=post_type, theme=theme)
            continue

        if choice == "edit":
            console.print("[dim]投稿文を入力してください（空行で終了）:[/dim]")
            lines = []
            while True:
                line = input()
                if line == "":
                    break
                lines.append(line)
            text = "\n".join(lines).strip()
            continue

        if choice == "post":
            if not Confirm.ask("この内容で投稿しますか？"):
                continue

            console.print(f"{dry_run_label}投稿中...")
            result = poster.post(text)
            if result["success"]:
                if result["post_id"] == "DRY_RUN":
                    console.print("[yellow][DRY RUN] 投稿は実行されませんでした。[/yellow]")
                else:
                    console.print(f"[green]投稿完了！ post_id: {result['post_id']}[/green]")
            else:
                console.print(f"[red]投稿失敗: {result['error']}[/red]")
            return


def cmd_status():
    """今日の投稿状況を表示"""
    from agents.scheduler import get_posts_for_date, _load_posted_log
    from datetime import date

    target = date.today().isoformat()
    if "--date" in sys.argv:
        try:
            target = sys.argv[sys.argv.index("--date") + 1]
        except Exception:
            pass
    today_posts = get_posts_for_date(target)
    posted_log = [e for e in _load_posted_log() if e.get("date") == target]
    poster = ThreadsPoster()

    table = Table(title=f"({target}) の投稿状況")
    table.add_column("時間", style="cyan")
    table.add_column("内容（先頭30字）")
    table.add_column("ステータス", style="bold")

    posted_ids = {e["id"] for e in _load_posted_log()}

    for row in today_posts:
        # 旧ログとの互換のため、posted.json の "id" があるケースも見る
        legacy_id = f"{(row.get('日付','') or row.get('date',''))}_{(row.get('投稿予定時間','') or row.get('time',''))}".strip()
        status = "[green]投稿済み[/green]" if legacy_id in posted_ids else "[yellow]未投稿[/yellow]"
        text_preview = (row.get("content") or row.get("投稿本文") or "")[:30]
        table.add_row(row.get("time", "-") or "-", text_preview, status)

    console.print(table)
    console.print(f"\n本日の実投稿数: [bold]{poster._today_post_count()}[/bold] / {poster.max_per_day}件上限")
    if poster.dry_run:
        console.print("[yellow]DRY_RUN=true（実際の投稿は行われません）[/yellow]")


def cmd_post_file(filepath: str):
    """指定ファイルのテキストをそのまま投稿"""
    path = Path(filepath)
    if not path.exists():
        console.print(f"[red]ファイルが見つかりません: {filepath}[/red]")
        sys.exit(1)

    text = path.read_text(encoding="utf-8").strip()
    console.print(Panel(text, title=f"投稿文 ({path.name})", border_style="blue"))
    console.print(f"[dim]文字数: {len(text)}字[/dim]")

    assume_yes = "--yes" in sys.argv
    if not assume_yes and not Confirm.ask("この内容で投稿しますか？"):
        console.print("キャンセルしました。")
        return

    poster = ThreadsPoster()
    result = poster.post(text)
    if result["success"]:
        if result["post_id"] == "DRY_RUN":
            console.print("[yellow][DRY RUN] 投稿は実行されませんでした。[/yellow]")
        else:
            console.print(f"[green]投稿完了！ post_id: {result['post_id']}[/green]")
    else:
        console.print(f"[red]投稿失敗: {result['error']}[/red]")


def cmd_post_latest():
    """data/drafts/ の最新下書きを投稿"""
    drafts_dir = Path(__file__).parent / "data" / "drafts"
    if not drafts_dir.exists():
        console.print(f"[red]下書きフォルダが見つかりません: {drafts_dir}[/red]")
        sys.exit(1)

    candidates = sorted(drafts_dir.glob("draft_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        console.print(f"[red]下書きがありません: {drafts_dir}[/red]")
        sys.exit(1)

    cmd_post_file(str(candidates[0]))


def cmd_auto():
    """今日の未投稿スケジュールを自動で生成→投稿（確認なし）"""
    # CLIフラグで DRY_RUN を上書きできるようにする（安全に確認したい時用）
    if "--dry-run" in sys.argv:
        os.environ["DRY_RUN"] = "true"

    poster = ThreadsPoster()
    dry_run_label = "[yellow][DRY RUN][/yellow] " if poster.dry_run else ""

    target_date = None
    if "--date" in sys.argv:
        try:
            target_date = sys.argv[sys.argv.index("--date") + 1]
        except Exception:
            target_date = None
    if "--tomorrow" in sys.argv:
        from datetime import timedelta, date as _date
        target_date = (_date.today() + timedelta(days=1)).isoformat()

    pending = get_pending_posts(target_date=target_date)
    if not pending:
        label = target_date or "今日"
        console.print(f"[green]{label}の未投稿スケジュールはありません。[/green]")
        return

    label = target_date or "今日"
    console.print(f"\n[bold]AUTO: {label}の未投稿 {len(pending)}件[/bold]")
    for i, row in enumerate(pending, 1):
        time_label = row.get("time") or row.get("投稿予定時間") or "時間未設定"
        console.rule(f"[AUTO {i}/{len(pending)}] {time_label}")

        existing = (row.get("content") or row.get("投稿本文") or "").strip()
        if existing:
            text = existing
        else:
            console.print("[cyan]投稿文を生成中...[/cyan]")
            text = generate_from_schedule_row(row.get("_raw") or row)

        console.print(Panel(text, title="投稿文", border_style="cyan"))
        console.print(f"[dim]文字数: {len(text)}字[/dim]")

        console.print(f"{dry_run_label}投稿中...")
        result = poster.post(text)
        if result["success"]:
            post_id = result["post_id"]
            if post_id == "DRY_RUN":
                console.print("[yellow][DRY RUN] 投稿は実行されませんでした。[/yellow]")
            else:
                console.print(f"[green]投稿完了！ post_id: {post_id}[/green]")
            if post_id != "DRY_RUN":
                mark_as_posted(row, threads_post_id=post_id)
        else:
            console.print(f"[red]投稿失敗: {result['error']}[/red]")

        if i < len(pending):
            poster.wait_between_posts()


def main():
    if len(sys.argv) < 2:
        console.print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "run":
        cmd_run()
    elif cmd == "auto":
        cmd_auto()
    elif cmd == "generate":
        cmd_generate()
    elif cmd == "compose":
        cmd_compose()
    elif cmd == "status":
        cmd_status()
    elif cmd == "post" and len(sys.argv) >= 3:
        cmd_post_file(sys.argv[2])
    elif cmd == "post-latest":
        cmd_post_latest()
    else:
        console.print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
