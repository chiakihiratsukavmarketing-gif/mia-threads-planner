from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from mei_threads.paths import config_dir, data_dir, env_path
from mei_threads.agents.generator import generate_post
from mei_threads.agents.poster import ThreadsPoster


console = Console()

def _ask_choice(prompt: str, options: list[str], default: str) -> str:
    opts = [o.lower() for o in options]
    default = default.lower()
    hint = "/".join(options)
    while True:
        raw = input(f"{prompt} [{hint}] ({default}): ").strip().lower()
        if raw == "":
            return default
        if raw.isdigit():
            i = int(raw) - 1
            if 0 <= i < len(opts):
                return opts[i]
        if raw in opts:
            return raw
        matches = [o for o in opts if o.startswith(raw)]
        if len(matches) == 1:
            return matches[0]
        console.print(f"[yellow]入力が不正です。{hint}（または 1..{len(opts)}）で入力してください。[/yellow]")


def _confirm(prompt: str, default: bool = False) -> bool:
    d = "y" if default else "n"
    while True:
        raw = input(f"{prompt} [y/n] ({d}): ").strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        console.print("[yellow]y か n を入力してください。[/yellow]")


ENV_TEMPLATE = """# Threads API
THREADS_USER_ID=
THREADS_ACCESS_TOKEN=

# Anthropic API
ANTHROPIC_API_KEY=
# ANTHROPIC_MODEL=claude-opus-4-6

# Settings
DRY_RUN=true
MAX_POSTS_PER_DAY=3
POST_DELAY_SECONDS=60
"""


def _ensure_env_loaded() -> None:
    cfg = config_dir()
    cfg.mkdir(parents=True, exist_ok=True)

    p = env_path()
    if not p.exists():
        p.write_text(ENV_TEMPLATE, encoding="utf-8")
        console.print(Panel(str(p), title="設定ファイルを作りました", border_style="yellow"))
        console.print("中身を埋めたら、もう一度同じコマンドを実行してください。")
        raise SystemExit(2)

    load_dotenv(p, override=True)

    missing = [k for k in ("THREADS_USER_ID", "THREADS_ACCESS_TOKEN", "ANTHROPIC_API_KEY") if not os.environ.get(k)]
    if missing:
        console.print(Panel("\n".join(missing), title="未設定の環境変数", border_style="red"))
        console.print(f"`{p}` を編集して埋めてください。")
        raise SystemExit(2)


def cmd_compose(args: argparse.Namespace) -> None:
    _ensure_env_loaded()
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    console.print("[bold]テーマ/型/メモ → 生成 → OKで投稿[/bold]")
    topic = args.topic or Prompt.ask("テーマ", default="育児と仕事の両立")
    post_type = args.post_type or Prompt.ask(
        "投稿の型",
        choices=["暴露型", "数字型", "逆説型", "共感型", "実績型", "スレッド型"],
        default="逆説型",
    )
    memo = args.memo or Prompt.ask("方向性メモ（任意）", default="")

    poster = ThreadsPoster()
    dry_run_label = "[yellow][DRY RUN][/yellow] " if poster.dry_run else ""

    text = ""
    while True:
        if text == "":
            console.print("[cyan]生成中...[/cyan]")
            text = generate_post(topic=topic, post_type=post_type, memo=memo)

        console.print(Panel(text, title="投稿文（確認してください）", border_style="cyan"))
        console.print(f"[dim]文字数: {len(text)}字[/dim]")

        choice = _ask_choice("どうしますか？", ["post", "edit", "regen", "quit"], default="post")
        if choice == "quit":
            return
        if choice == "regen":
            text = ""
            continue
        if choice == "edit":
            console.print("[dim]投稿文を入力してください（空行で終了）:[/dim]")
            lines: list[str] = []
            while True:
                line = input()
                if line == "":
                    break
                lines.append(line)
            text = "\n".join(lines).strip()
            continue

        # post
        if not args.yes and not _confirm("この内容で投稿しますか？", default=False):
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


def cmd_where(_: argparse.Namespace) -> None:
    console.print(Panel(str(config_dir()), title="config dir", border_style="cyan"))
    console.print(Panel(str(data_dir()), title="data dir", border_style="cyan"))
    console.print(Panel(str(env_path()), title="env path", border_style="cyan"))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mei-threads")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compose", help="テーマ/型/メモ → 生成 → OKで投稿")
    c.add_argument("--topic", default="")
    c.add_argument("--post-type", dest="post_type", default="")
    c.add_argument("--memo", default="")
    c.add_argument("--dry-run", action="store_true", help="投稿せずに動作確認")
    c.add_argument("--yes", action="store_true", help="最終確認をスキップ")
    c.set_defaults(func=cmd_compose)

    w = sub.add_parser("where", help="設定/データ保存先を表示")
    w.set_defaults(func=cmd_where)

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
