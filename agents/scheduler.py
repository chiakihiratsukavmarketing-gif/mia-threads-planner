"""
スケジューラーエージェント
posts_schedule.csv を読み込み、今日投稿すべき内容を管理する。
"""
import csv
import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path


SCHEDULE_PATH = Path(__file__).parent.parent / "posts_schedule.csv"
DRAFTS_DIR = Path(__file__).parent.parent / "data" / "drafts"
LOGS_DIR = Path(__file__).parent.parent / "data" / "logs"
POST_LOG = LOGS_DIR / "posted.json"


def load_schedule(schedule_path: Path = SCHEDULE_PATH) -> list[dict]:
    """CSVスケジュールを読み込む"""
    if not schedule_path.exists():
        return []

    posts = []
    last_err: Exception | None = None
    for encoding in ("utf-8-sig", "cp932"):
        try:
            with open(schedule_path, encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    posts.append(row)
            last_err = None
            break
        except UnicodeDecodeError as e:
            posts = []
            last_err = e

    if last_err is not None:
        raise last_err
    return posts


def get_posts_for_date(target_date: str, schedule_path: Path = SCHEDULE_PATH) -> list[dict]:
    """指定日付(YYYY-MM-DD)に一致する投稿スケジュールを返す"""
    all_posts = load_schedule(schedule_path)
    result: list[dict] = []
    for p in all_posts:
        p_norm = _normalize_row(p)
        if p_norm.get("date") == target_date:
            result.append(p_norm)
    return result


def get_today_posts(schedule_path: Path = SCHEDULE_PATH) -> list[dict]:
    """今日の日付に一致する投稿スケジュールを返す"""
    return get_posts_for_date(date.today().strftime("%Y-%m-%d"), schedule_path=schedule_path)


def get_pending_posts(schedule_path: Path = SCHEDULE_PATH, target_date: str | None = None) -> list[dict]:
    """ステータスが未投稿の指定日の投稿を返す（未指定なら今日）"""
    if target_date is None:
        target_date = date.today().strftime("%Y-%m-%d")
    posts = get_posts_for_date(target_date, schedule_path=schedule_path)
    posted_fps = _load_posted_fingerprints()
    pending = []
    for p in posts:
        status = (p.get("status") or "").strip().lower()
        fp = _fingerprint(p)
        if fp not in posted_fps and status not in ("posted", "投稿済み", "skip", "skipped"):
            pending.append(p)
    return pending


def mark_as_posted(post: dict, threads_post_id: str | None = None) -> None:
    """投稿済みとして記録する"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    posted = _load_posted_log()
    entry = {
        "fingerprint": _fingerprint(post),
        "date": post.get("date", ""),
        "time": post.get("time", ""),
        "posted_at": datetime.now().isoformat(),
        "threads_post_id": threads_post_id,
        "text_preview": (post.get("content") or "")[:50],
    }
    posted.append(entry)
    with open(POST_LOG, "w", encoding="utf-8") as f:
        json.dump(posted, f, ensure_ascii=False, indent=2)


def _normalize_row(row: dict) -> dict:
    def pick(*keys: str, default: str = "") -> str:
        for k in keys:
            v = row.get(k)
            if v is None:
                continue
            s = str(v).strip()
            if s != "":
                return s
        return default

    return {
        "date": pick("日付", "date"),
        "time": pick("投稿予定時間", "time", "scheduled_time", default=""),
        "topic": pick("テーマ", "topic", "カテゴリ", "category", default=""),
        "post_type": pick("投稿タイプ", "post_type", "型", "type", default=""),
        "memo": pick("メモ", "memo", "方向性", "note", default=""),
        "content": pick("投稿本文", "content", "本文", default=""),
        "status": pick("ステータス", "status", default=""),
        "_raw": row,
    }


def _fingerprint(post: dict) -> str:
    basis = "|".join([
        str(post.get("date", "")).strip(),
        str(post.get("time", "")).strip(),
        str(post.get("topic", "")).strip(),
        str(post.get("post_type", "")).strip(),
        str(post.get("memo", "")).strip(),
        str(post.get("content", "")).strip(),
    ])
    return hashlib.sha1(basis.encode("utf-8", errors="ignore")).hexdigest()


def _load_posted_log() -> list[dict]:
    if not POST_LOG.exists():
        return []
    with open(POST_LOG, encoding="utf-8") as f:
        return json.load(f)


def _load_posted_fingerprints() -> set[str]:
    fps = set()
    for e in _load_posted_log():
        fp = e.get("fingerprint")
        if fp:
            fps.add(fp)
    return fps
