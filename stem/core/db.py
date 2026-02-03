from __future__ import annotations

import os
import sqlite3
from typing import Iterable

from .paths import stem_db_path
from .util import now_iso


SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


class StemDB:
    def __init__(self, repo_root: str):
        self.repo_root = repo_root
        self.db_path = stem_db_path(repo_root)
        self.schema_version = 1

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema = f.read()
        with self.connect() as conn:
            conn.executescript(schema)
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                    (str(self.schema_version),),
                )

    def get_meta(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?",
                (key,),
            ).fetchone()
            return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_current_branch(self) -> str | None:
        return self.get_meta("current_branch_id")

    def set_current_branch(self, branch_id: str) -> None:
        self.set_meta("current_branch_id", branch_id)

    def get_branch_count(self) -> int:
        value = self.get_meta("branch_count")
        return int(value) if value and value.isdigit() else 0

    def set_branch_count(self, count: int) -> None:
        self.set_meta("branch_count", str(count))

    def verify_schema(self) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                raise RuntimeError("stem db schema version missing")
            if row["value"] != str(self.schema_version):
                raise RuntimeError(
                    f"stem db schema version mismatch: {row['value']} != {self.schema_version}"
                )

    def next_branch_id(self) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'branch_seq'"
            ).fetchone()
            if row is None:
                seq = 1
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('branch_seq', ?)",
                    (str(seq + 1),),
                )
            else:
                seq = int(row["value"])
                conn.execute(
                    "UPDATE meta SET value = ? WHERE key = 'branch_seq'",
                    (str(seq + 1),),
                )
        return f"b{seq:04d}"

    def next_leaf_id(self, branch_id: str) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(1) as count FROM leaves WHERE repo_root = ? AND branch_id = ?",
                (self.repo_root, branch_id),
            ).fetchone()
            count = int(row["count"])
        major = (count // 26) + 1
        minor = count % 26
        leaf_id = f"{major:03d}{chr(ord('a') + minor)}"
        return leaf_id

    def insert_branch(
        self,
        branch_id: str,
        slug: str,
        user: str,
        prompt: str,
        summary: str,
        git_branch: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO branches(
                    branch_id, slug, user, prompt, summary, git_branch, created_at, repo_root
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (branch_id, slug, user, prompt, summary, git_branch, now_iso(), self.repo_root),
            )

    def insert_leaf(
        self,
        branch_id: str,
        leaf_id: str,
        prompt: str,
        summary: str,
        git_commit: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO leaves(
                    branch_id, leaf_id, prompt, summary, git_commit, created_at, repo_root
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (branch_id, leaf_id, prompt, summary, git_commit, now_iso(), self.repo_root),
            )

    def insert_jump(
        self,
        branch_id: str,
        leaf_id: str,
        prompt: str,
        summary: str,
        ancestry: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO jumps(
                    branch_id, leaf_id, prompt, summary, ancestry, created_at, repo_root
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (branch_id, leaf_id, prompt, summary, ancestry, now_iso(), self.repo_root),
            )

    def has_exec_nonce(self, nonce: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM command_exec WHERE repo_root = ? AND nonce = ?",
                (self.repo_root, nonce),
            ).fetchone()
            return row is not None

    def insert_exec_nonce(self, nonce: str, command: str, source_file: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO command_exec(nonce, command, source_file, created_at, repo_root)
                VALUES (?, ?, ?, ?, ?)
                """,
                (nonce, command, source_file, now_iso(), self.repo_root),
            )

    def list_branches(self, limit: int = 10) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT * FROM branches
                    WHERE repo_root = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (self.repo_root, limit),
                )
            )

    def list_leaves(self, branch_id: str, limit: int = 5) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT * FROM leaves
                    WHERE repo_root = ? AND branch_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (self.repo_root, branch_id, limit),
                )
            )

    def get_branch(self, branch_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM branches WHERE repo_root = ? AND branch_id = ?",
                (self.repo_root, branch_id),
            ).fetchone()

    def get_leaf(self, leaf_id: str) -> sqlite3.Row | None:
        rows = self.find_leaves_by_id(leaf_id)
        if len(rows) == 1:
            return rows[0]
        return None

    def get_leaf_on_branch(self, branch_id: str, leaf_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM leaves
                WHERE repo_root = ? AND branch_id = ? AND leaf_id = ?
                """,
                (self.repo_root, branch_id, leaf_id),
            ).fetchone()

    def find_leaves_by_id(self, leaf_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM leaves WHERE repo_root = ? AND leaf_id = ?",
                    (self.repo_root, leaf_id),
                )
            )

    def latest_leaf_for_branch(self, branch_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM leaves
                WHERE repo_root = ? AND branch_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (self.repo_root, branch_id),
            ).fetchone()

    def first_leaf_for_branch(self, branch_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM leaves
                WHERE repo_root = ? AND branch_id = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (self.repo_root, branch_id),
            ).fetchone()
