"""
Threads投稿エージェント（ツール版）
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path

import requests

from mei_threads.paths import logs_dir


THREADS_API_BASE = "https://graph.threads.net/v1.0"
MAX_TEXT_LENGTH = 500


class ThreadsPoster:
    def __init__(self):
        self.user_id = os.environ["THREADS_USER_ID"]
        self.access_token = os.environ["THREADS_ACCESS_TOKEN"]
        self.dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"
        self.max_per_day = int(os.environ.get("MAX_POSTS_PER_DAY", "3"))
        self.post_delay = int(os.environ.get("POST_DELAY_SECONDS", "60"))

        self._logs_dir = logs_dir()
        self._rate_log = self._logs_dir / "rate_limit.json"

    def post(self, text: str) -> dict:
        if len(text) > MAX_TEXT_LENGTH:
            return {"success": False, "post_id": None, "error": f"文字数超過: {len(text)}字（上限{MAX_TEXT_LENGTH}字）"}

        today_count = self._today_post_count()
        if today_count >= self.max_per_day:
            return {
                "success": False,
                "post_id": None,
                "error": f"1日の投稿上限({self.max_per_day}件)に達しました。今日の投稿数: {today_count}",
            }

        if self.dry_run:
            self._log_rate(dry_run=True)
            return {"success": True, "post_id": "DRY_RUN", "error": None}

        container_id = self._create_container(text)
        if not container_id:
            return {"success": False, "post_id": None, "error": "コンテナ作成失敗"}

        time.sleep(5)

        post_id = self._publish_container(container_id)
        if not post_id:
            return {"success": False, "post_id": None, "error": "投稿公開失敗"}

        self._log_rate(dry_run=False)
        return {"success": True, "post_id": post_id, "error": None}

    def _create_container(self, text: str) -> str | None:
        url = f"{THREADS_API_BASE}/{self.user_id}/threads"
        params = {"media_type": "TEXT", "text": text, "access_token": self.access_token}
        resp = requests.post(url, params=params, timeout=30)
        if resp.ok:
            payload = _safe_json(resp)
            container_id = (payload or {}).get("id")
            if container_id:
                return container_id
            _log_api_error("create_container_missing_id", resp, extra={"json": payload})
            return None
        _log_api_error("create_container", resp)
        return None

    def _publish_container(self, container_id: str) -> str | None:
        url = f"{THREADS_API_BASE}/{self.user_id}/threads_publish"
        params = {"creation_id": container_id, "access_token": self.access_token}
        resp = requests.post(url, params=params, timeout=30)
        if resp.ok:
            payload = _safe_json(resp)
            post_id = (payload or {}).get("id")
            if post_id:
                return post_id
            _log_api_error("publish_container_missing_id", resp, extra={"json": payload})
            return None
        _log_api_error("publish_container", resp)
        return None

    def _today_post_count(self) -> int:
        log = self._load_rate_log()
        today = date.today().isoformat()
        return sum(1 for e in log if e.get("date") == today and not e.get("dry_run"))

    def _log_rate(self, dry_run: bool) -> None:
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        log = self._load_rate_log()
        log.append({"date": date.today().isoformat(), "dry_run": dry_run})
        with open(self._rate_log, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

    def _load_rate_log(self) -> list[dict]:
        if not self._rate_log.exists():
            return []
        with open(self._rate_log, encoding="utf-8") as f:
            return json.load(f)

    def wait_between_posts(self) -> None:
        if not self.dry_run:
            time.sleep(self.post_delay)


def _safe_json(resp: requests.Response) -> dict | None:
    try:
        data = resp.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _log_api_error(step: str, resp: requests.Response, extra: dict | None = None) -> None:
    error_dir = logs_dir()
    error_dir.mkdir(parents=True, exist_ok=True)
    error_log = error_dir / "api_errors.json"

    errors = []
    if error_log.exists():
        with open(error_log, encoding="utf-8") as f:
            errors = json.load(f)

    entry = {"step": step, "status_code": resp.status_code, "body": resp.text[:2000]}
    if extra:
        entry["extra"] = extra
    errors.append(entry)

    with open(error_log, "w", encoding="utf-8") as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)
