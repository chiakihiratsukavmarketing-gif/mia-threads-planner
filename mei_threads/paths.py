from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_path, user_data_path


def config_dir() -> Path:
    # Windows: C:\Users\<you>\AppData\Roaming\mei-threads
    return Path(user_config_path(appname="mei-threads", appauthor=False))


def data_dir() -> Path:
    # Windows: C:\Users\<you>\AppData\Local\mei-threads
    return Path(user_data_path(appname="mei-threads", appauthor=False))


def env_path() -> Path:
    return config_dir() / ".env"


def logs_dir() -> Path:
    return data_dir() / "logs"


def drafts_dir() -> Path:
    return data_dir() / "drafts"


def schedule_path() -> Path:
    return data_dir() / "posts_schedule.csv"
