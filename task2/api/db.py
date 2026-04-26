from __future__ import annotations

import os


def get_db_path() -> str:
    return os.environ.get("DB_PATH", "./agent_tasks.db")
