from __future__ import annotations

import os
import sqlite3

from .paths import registry_db_path, registry_dir
from .util import now_iso


REGISTRY_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS repos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo_root TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
"""


def init_registry() -> None:
    os.makedirs(registry_dir(), exist_ok=True)
    with sqlite3.connect(registry_db_path()) as conn:
        conn.executescript(REGISTRY_SCHEMA)


def register_repo(repo_root: str) -> None:
    init_registry()
    with sqlite3.connect(registry_db_path()) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO repos(repo_root, created_at) VALUES(?, ?)",
            (repo_root, now_iso()),
        )


def list_repos(limit: int = 50) -> list[sqlite3.Row]:
    with sqlite3.connect(registry_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        return list(
            conn.execute(
                "SELECT * FROM repos ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        )


def get_repo(repo_root: str) -> sqlite3.Row | None:
    with sqlite3.connect(registry_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM repos WHERE repo_root = ?",
            (repo_root,),
        ).fetchone()
