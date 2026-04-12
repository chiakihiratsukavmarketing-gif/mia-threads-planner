#!/usr/bin/env python3
"""
GitHub Actions向け: queue/posts.json から予約投稿を実行する。

設計前提:
- scheduled workflow のズレがあるので「±tolerance」＋「少し過ぎた分も拾う」
- 二重投稿防止のため pending -> posting -> posted/failed の遷移を使う
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

THREADS_API_BASE = "https://graph.threads.net/v1.0"
MAX_TEXT_LENGTH = 500


def _parse_dt(value: str) -> datetime:
    # Python 3.11+: fromisoformat supports offsets like +09:00
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError(f"timezoneなしの日時は不可: {value}")
    return dt.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _git(*args: str) -> None:
    subprocess.check_call(["git", *args])


def _git_commit_if_needed(message: str) -> bool:
    # returns True if a commit was created
    diff = subprocess.check_output(["git", "status", "--porcelain"]).decode("utf-8", errors="ignore").strip()
    if not diff:
        return False
    _git("add", "-A")
    _git("commit", "-m", message)
    _git("push")
    return True


def _safe_json(resp: requests.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


@dataclass(frozen=True)
class ThreadsConfig:
    user_id: str
    access_token: str


class ThreadsTextPoster:
    def __init__(self, cfg: ThreadsConfig):
        self.cfg = cfg

    def post(self, text: str) -> tuple[bool, str | None, str | None]:
        if len(text) > MAX_TEXT_LENGTH:
            return False, None, f"文字数超過: {len(text)}字（上限{MAX_TEXT_LENGTH}字）"

        container_id = self._create_container(text)
        if not container_id:
            return False, None, "コンテナ作成失敗"

        time.sleep(5)

        post_id = self._publish_container(container_id)
        if not post_id:
            return False, None, "投稿公開失敗"

        return True, post_id, None

    def _create_container(self, text: str) -> str | None:
        url = f"{THREADS_API_BASE}/{self.cfg.user_id}/threads"
        params = {"media_type": "TEXT", "text": text, "access_token": self.cfg.access_token}
        resp = requests.post(url, params=params, timeout=30)
        if resp.ok:
            payload = _safe_json(resp)
            return (payload or {}).get("id")
        return None

    def _publish_container(self, container_id: str) -> str | None:
        url = f"{THREADS_API_BASE}/{self.cfg.user_id}/threads_publish"
        params = {"creation_id": container_id, "access_token": self.cfg.access_token}
        resp = requests.post(url, params=params, timeout=30)
        if resp.ok:
            payload = _safe_json(resp)
            return (payload or {}).get("id")
        return None


def _today_posted_count(posts: list[dict[str, Any]]) -> int:
    today = _utc_now().date().isoformat()
    n = 0
    for p in posts:
        if p.get("status") != "posted":
            continue
        posted_at = p.get("posted_at")
        if not posted_at:
            continue
        try:
            dt = _parse_dt(str(posted_at))
        except Exception:
            continue
        if dt.date().isoformat() == today:
            n += 1
    return n


def _pick_due_posts(
    posts: list[dict[str, Any]],
    *,
    now: datetime,
    tolerance: timedelta,
    overdue_extra: timedelta,
) -> list[dict[str, Any]]:
    due: list[dict[str, Any]] = []
    for p in posts:
        if p.get("status") != "pending":
            continue
        sa = p.get("scheduled_at")
        if not sa:
            continue
        try:
            sched = _parse_dt(str(sa))
        except Exception:
            continue

        start = sched - tolerance - overdue_extra
        end = sched + tolerance
        if start <= now <= end:
            due.append(p)

    due.sort(key=lambda x: str(x.get("scheduled_at", "")))
    return due


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", default="queue/posts.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-push", action="store_true", help="commitは作るがpushしない（ローカル検証用）")
    args = parser.parse_args()

    queue_path = Path(args.queue)
    if not queue_path.exists():
        print(f"queue file not found: {queue_path}", file=sys.stderr)
        return 2

    tolerance_min = int(os.environ.get("QUEUE_TOLERANCE_MINUTES", "5"))
    overdue_extra_min = int(os.environ.get("QUEUE_OVERDUE_EXTRA_MINUTES", "10"))
    max_per_day = int(os.environ.get("QUEUE_MAX_POSTS_PER_DAY", os.environ.get("MAX_POSTS_PER_DAY", "3")))
    max_attempts = int(os.environ.get("QUEUE_MAX_ATTEMPTS", "8"))

    tolerance = timedelta(minutes=tolerance_min)
    overdue_extra = timedelta(minutes=overdue_extra_min)
    now = _utc_now()

    raw = json.loads(queue_path.read_text(encoding="utf-8"))
    posts: list[dict[str, Any]] = list(raw.get("posts", []))

    posted_today = _today_posted_count(posts)
    if posted_today >= max_per_day:
        print(f"skip: daily cap reached ({posted_today}/{max_per_day})")
        return 0

    due = _pick_due_posts(posts, now=now, tolerance=tolerance, overdue_extra=overdue_extra)
    if not due:
        print("no due posts")
        return 0

    poster: ThreadsTextPoster | None = None
    if not args.dry_run:
        user_id = (os.environ.get("THREADS_USER_ID") or "").strip()
        token = (os.environ.get("THREADS_ACCESS_TOKEN") or "").strip()
        if not user_id or not token:
            print("THREADS_USER_ID / THREADS_ACCESS_TOKEN が空です（GitHub Secrets を確認）", file=sys.stderr)
            return 2
        # 典型事故: OS環境変数に短いダミー値が残り、.env更新が反映されない/CIでも誤設定に気づきにくい
        if len(token) < 30 or len(user_id) < 5:
            print(
                "THREADS_ACCESS_TOKEN / THREADS_USER_ID が短すぎます。"
                " OSに古い環境変数が残っていないか、GitHub Secrets の typo を疑ってください。",
                file=sys.stderr,
            )
            return 2

        cfg = ThreadsConfig(user_id=user_id, access_token=token)
        poster = ThreadsTextPoster(cfg)

    changed = False
    for p in due:
        if posted_today >= max_per_day:
            break

        pid = str(p.get("id", "")).strip()
        text = str(p.get("text", "")).strip()
        if not pid or not text:
            p["status"] = "failed"
            p["last_error"] = "id/text が空です"
            p["updated_at"] = now.isoformat()
            changed = True
            continue

        attempts = int(p.get("attempts") or 0)
        if attempts >= max_attempts:
            p["status"] = "failed"
            p["last_error"] = f"最大試行回数超過 ({max_attempts})"
            p["updated_at"] = now.isoformat()
            changed = True
            continue

        # lock
        if p.get("status") != "pending":
            continue
        p["status"] = "posting"
        p["attempts"] = attempts + 1
        p["updated_at"] = now.isoformat()
        changed = True

        if args.dry_run:
            p["status"] = "posted"
            p["threads_post_id"] = "DRY_RUN"
            p["posted_at"] = now.isoformat()
            p["last_error"] = None
            posted_today += 1
            continue

        assert poster is not None
        ok, threads_post_id, err = poster.post(text)
        if ok and threads_post_id:
            p["status"] = "posted"
            p["threads_post_id"] = threads_post_id
            p["posted_at"] = now.isoformat()
            p["last_error"] = None
            posted_today += 1
        else:
            # 次の周期で再試行できるように pending に戻す（ただし attempts で上限）
            p["status"] = "pending"
            p["last_error"] = err or "unknown_error"

        p["updated_at"] = _utc_now().isoformat()
        changed = True

    if not changed:
        print("no changes")
        return 0

    raw["posts"] = posts
    queue_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # CIではGITHUB_ACTIONSがセットされる想定
    if os.environ.get("GITHUB_ACTIONS") == "true" and not args.no_push:
        msg = f"chore(queue): update posts ({now.isoformat()})"
        committed = _git_commit_if_needed(msg)
        print("committed+push" if committed else "no git changes (unexpected)")
    else:
        print("wrote queue file (local mode)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
