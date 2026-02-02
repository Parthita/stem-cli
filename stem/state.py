"""
State Layer - Manage stem metadata and node tracking.

SQLite-backed store for nodes, events, prompts, and head tracking.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Iterable, Any, List


class StateError(Exception):
    """Exception raised for state management failures."""
    pass


class StateCorruptionError(StateError):
    """Exception raised when state corruption is detected."""
    pass


class StateValidationError(StateError):
    """Exception raised when state validation fails."""
    pass


@dataclass
class Node:
    """Represents a single stem node with metadata."""
    id: str
    parent: Optional[str]
    prompt: str
    summary: str
    ref: str
    created_at: str
    status: str


def _stem_dir() -> Path:
    return Path(".git") / "stem"


def _db_path() -> Path:
    return _stem_dir() / "stem.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn
    except sqlite3.Error as e:
        raise StateError(f"Failed to connect to state database: {e}")


def ensure_db() -> None:
    """Ensure the stem database exists and is initialized."""
    stem_dir = _stem_dir()
    stem_dir.mkdir(parents=True, exist_ok=True)

    needs_create = not _db_path().exists()
    conn = _connect()
    try:
        _create_tables(conn)
        _ensure_meta_defaults(conn)
        if needs_create:
            _migrate_nodes_json_if_present(conn)
    finally:
        conn.close()


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            parent_id TEXT NULL,
            prompt TEXT NOT NULL,
            summary TEXT NOT NULL,
            ref TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active', 'invalid')),
            FOREIGN KEY(parent_id) REFERENCES nodes(id)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(node_id) REFERENCES nodes(id)
        );

        CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(node_id) REFERENCES nodes(id)
        );

        CREATE TABLE IF NOT EXISTS agent_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt TEXT NOT NULL,
            summary TEXT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending', 'confirmed', 'rejected')),
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            node_id TEXT NULL,
            FOREIGN KEY(node_id) REFERENCES nodes(id)
        );

        CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(status);
        CREATE INDEX IF NOT EXISTS idx_events_node ON events(node_id);
        CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
        CREATE INDEX IF NOT EXISTS idx_prompts_node ON prompts(node_id);
        CREATE INDEX IF NOT EXISTS idx_prompts_created ON prompts(created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_intents_status ON agent_intents(status);
        CREATE INDEX IF NOT EXISTS idx_agent_intents_created ON agent_intents(created_at);
        """
    )
    conn.commit()


def _ensure_meta_defaults(conn: sqlite3.Connection) -> None:
    existing = {row["key"] for row in conn.execute("SELECT key FROM meta")}
    if "counter" not in existing:
        conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("counter", "0"))
    if "head" not in existing:
        conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("head", ""))
    conn.commit()


def _get_meta(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _record_event(conn: sqlite3.Connection, event_type: str, payload: Dict[str, Any], node_id: Optional[str] = None) -> None:
    conn.execute(
        "INSERT INTO events (node_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
        (node_id, event_type, json.dumps(payload, ensure_ascii=False), _now_iso()),
    )


def _migrate_nodes_json_if_present(conn: sqlite3.Connection) -> None:
    nodes_file = _stem_dir() / "nodes.json"
    if not nodes_file.exists():
        return

    try:
        with open(nodes_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return

    nodes = data.get("nodes") if isinstance(data, dict) else None
    if not isinstance(nodes, dict):
        return

    # Avoid duplicate migration if db already has nodes
    existing_count = conn.execute("SELECT COUNT(*) AS c FROM nodes").fetchone()["c"]
    if existing_count > 0:
        return

    now = _now_iso()
    # Insert nodes in id order for stable parent resolution
    for node_id in sorted(nodes.keys()):
        node = nodes[node_id]
        if not isinstance(node, dict):
            continue
        parent = node.get("parent")
        if parent is not None and parent not in nodes:
            parent = None
        prompt = node.get("prompt") if isinstance(node.get("prompt"), str) else "Recovered node"
        summary = node.get("summary") if isinstance(node.get("summary"), str) else "Summary lost during migration"
        ref = node.get("ref") if isinstance(node.get("ref"), str) else f"refs/heads/stem/unknown/{node_id}"

        conn.execute(
            "INSERT INTO nodes (id, parent_id, prompt, summary, ref, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (node_id, parent, prompt, summary, ref, now, "active"),
        )
        _record_event(conn, "node_migrated", {"source": "nodes.json"}, node_id=node_id)

    # Restore meta
    counter = data.get("counter") if isinstance(data.get("counter"), int) else 0
    if counter < 0:
        counter = 0
    _set_meta(conn, "counter", str(counter))
    head = data.get("head") if isinstance(data.get("head"), str) else ""
    if head and head not in nodes:
        head = ""
    _set_meta(conn, "head", head)
    conn.commit()


def load_state() -> Dict:
    """Return a compatibility state dict from SQLite."""
    ensure_db()
    conn = _connect()
    try:
        counter = int(_get_meta(conn, "counter") or "0")
        head = _get_meta(conn, "head") or None
        nodes: Dict[str, Dict[str, Any]] = {}
        rows = conn.execute(
            "SELECT id, parent_id, prompt, summary, ref, created_at, status FROM nodes ORDER BY id"
        ).fetchall()
        for row in rows:
            nodes[row["id"]] = {
                "parent": row["parent_id"],
                "prompt": row["prompt"],
                "summary": row["summary"],
                "ref": row["ref"],
                "created_at": row["created_at"],
                "status": row["status"],
            }
        return {"counter": counter, "head": head, "nodes": nodes}
    finally:
        conn.close()


def get_all_nodes() -> Dict[str, Dict[str, Any]]:
    """Get all nodes in the current repository."""
    return load_state()["nodes"]


def get_next_id() -> str:
    """Generate sequential node ID without creating a node."""
    ensure_db()
    conn = _connect()
    try:
        counter = int(_get_meta(conn, "counter") or "0") + 1
        return f"{counter:03d}"
    finally:
        conn.close()


def create_node(prompt: str, summary: str, ref: str, parent: Optional[str]) -> str:
    """Create new node and return node ID."""
    ensure_db()
    conn = _connect()
    try:
        conn.execute("BEGIN")
        counter = int(_get_meta(conn, "counter") or "0") + 1
        node_id = f"{counter:03d}"

        if parent is not None:
            exists = conn.execute("SELECT 1 FROM nodes WHERE id = ?", (parent,)).fetchone()
            if not exists:
                raise StateValidationError(f"Parent node does not exist: {parent}")

        conn.execute(
            "INSERT INTO nodes (id, parent_id, prompt, summary, ref, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (node_id, parent, prompt, summary, ref, _now_iso(), "active"),
        )
        _set_meta(conn, "counter", str(counter))
        _set_meta(conn, "head", node_id)

        _record_event(conn, "node_created", {"prompt": prompt, "ref": ref, "parent": parent}, node_id=node_id)
        _record_event(conn, "head_updated", {"head": node_id}, node_id=node_id)

        conn.commit()
        return node_id
    except sqlite3.Error as e:
        conn.rollback()
        raise StateError(f"Failed to create node: {e}")
    finally:
        conn.close()


def update_head(node_id: str) -> None:
    """Update head pointer to specified node."""
    ensure_db()
    conn = _connect()
    try:
        exists = conn.execute("SELECT 1 FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not exists:
            raise StateValidationError(f"Node {node_id} does not exist")
        _set_meta(conn, "head", node_id)
        _record_event(conn, "head_updated", {"head": node_id}, node_id=node_id)
        conn.commit()
    finally:
        conn.close()


def get_current_head() -> Optional[str]:
    """Get the current head node ID."""
    ensure_db()
    conn = _connect()
    try:
        head = _get_meta(conn, "head")
        return head or None
    finally:
        conn.close()


def invalidate_node(node_id: str, reason: str) -> None:
    """Mark a node invalid via event (no deletion)."""
    ensure_db()
    conn = _connect()
    try:
        exists = conn.execute("SELECT status FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not exists:
            raise StateValidationError(f"Node {node_id} does not exist")
        if exists["status"] == "invalid":
            return
        conn.execute("UPDATE nodes SET status = 'invalid' WHERE id = ?", (node_id,))
        _record_event(conn, "node_invalidated", {"reason": reason}, node_id=node_id)
        conn.commit()
    finally:
        conn.close()


def record_prompt(node_id: str, role: str, content: str) -> None:
    """Record a prompt for context restoration."""
    ensure_db()
    conn = _connect()
    try:
        exists = conn.execute("SELECT 1 FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not exists:
            raise StateValidationError(f"Node {node_id} does not exist")
        conn.execute(
            "INSERT INTO prompts (node_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (node_id, role, content, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_prompts(node_id: str, limit: int = 10) -> Iterable[Dict[str, str]]:
    """Fetch recent prompts for a node."""
    ensure_db()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT role, content, created_at FROM prompts WHERE node_id = ? ORDER BY created_at DESC LIMIT ?",
            (node_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_node(node_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single node by id."""
    ensure_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, parent_id, prompt, summary, ref, created_at, status FROM nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "parent": row["parent_id"],
            "prompt": row["prompt"],
            "summary": row["summary"],
            "ref": row["ref"],
            "created_at": row["created_at"],
            "status": row["status"],
        }
    finally:
        conn.close()


def get_ancestor_chain(node_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Fetch ancestor chain up to limit (excluding the node itself)."""
    ensure_db()
    conn = _connect()
    chain: List[Dict[str, Any]] = []
    try:
        current = conn.execute(
            "SELECT parent_id FROM nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        parent_id = current["parent_id"] if current else None
        while parent_id and len(chain) < limit:
            row = conn.execute(
                "SELECT id, parent_id, prompt, summary, ref, created_at, status FROM nodes WHERE id = ?",
                (parent_id,),
            ).fetchone()
            if not row:
                break
            chain.append(
                {
                    "id": row["id"],
                    "parent": row["parent_id"],
                    "prompt": row["prompt"],
                    "summary": row["summary"],
                    "ref": row["ref"],
                    "created_at": row["created_at"],
                    "status": row["status"],
                }
            )
            parent_id = row["parent_id"]
        return chain
    finally:
        conn.close()


def build_context_snapshot(node_id: str, ancestor_limit: int = 5, prompt_limit: int = 10) -> Dict[str, Any]:
    """Build a read-only context bundle for agents on jump."""
    ensure_db()
    node = get_node(node_id)
    if not node:
        raise StateValidationError(f"Node {node_id} does not exist")
    head = get_current_head()
    bundle = {
        "generated_at": _now_iso(),
        "head": head,
        "node": node,
        "ancestors": get_ancestor_chain(node_id, limit=ancestor_limit),
        "recent_prompts": list(get_recent_prompts(node_id, limit=prompt_limit)),
    }
    return bundle


def write_context_snapshot(node_id: str, ancestor_limit: int = 5, prompt_limit: int = 10) -> Path:
    """Write a context snapshot to .git/stem/context/current.json."""
    bundle = build_context_snapshot(node_id, ancestor_limit=ancestor_limit, prompt_limit=prompt_limit)
    context_dir = _stem_dir() / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    path = context_dir / "current.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, ensure_ascii=False)
    # Log event
    conn = _connect()
    try:
        _record_event(conn, "context_snapshot_written", {"path": str(path)}, node_id=node_id)
        conn.commit()
    finally:
        conn.close()
    return path


def suggest_intent(prompt: str, summary: Optional[str], source: str) -> int:
    """Record a suggested agent intent and return intent ID."""
    ensure_db()
    conn = _connect()
    try:
        now = _now_iso()
        cur = conn.execute(
            "INSERT INTO agent_intents (prompt, summary, status, source, created_at, updated_at) "
            "VALUES (?, ?, 'pending', ?, ?, ?)",
            (prompt, summary, source, now, now),
        )
        intent_id = int(cur.lastrowid)
        _record_event(
            conn,
            "agent_intent_suggested",
            {"intent_id": intent_id, "prompt": prompt, "source": source},
            node_id=None,
        )
        conn.commit()
        return intent_id
    finally:
        conn.close()


def get_pending_intent(intent_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Fetch a pending intent by id or latest pending intent."""
    ensure_db()
    conn = _connect()
    try:
        if intent_id is not None:
            row = conn.execute(
                "SELECT id, prompt, summary, status, source, created_at, updated_at, node_id "
                "FROM agent_intents WHERE id = ?",
                (intent_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, prompt, summary, status, source, created_at, updated_at, node_id "
                "FROM agent_intents WHERE status = 'pending' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_pending_intent_by_source(source: str) -> Optional[Dict[str, Any]]:
    """Fetch latest pending intent by source."""
    ensure_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, prompt, summary, status, source, created_at, updated_at, node_id "
            "FROM agent_intents WHERE status = 'pending' AND source = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (source,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def confirm_intent(intent_id: int) -> Dict[str, Any]:
    """Confirm a pending agent intent and return its data."""
    ensure_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, prompt, summary, status, source FROM agent_intents WHERE id = ?",
            (intent_id,),
        ).fetchone()
        if not row:
            raise StateValidationError(f"Intent {intent_id} does not exist")
        if row["status"] != "pending":
            raise StateValidationError(f"Intent {intent_id} is not pending")
        now = _now_iso()
        conn.execute(
            "UPDATE agent_intents SET status = 'confirmed', updated_at = ? WHERE id = ?",
            (now, intent_id),
        )
        _record_event(
            conn,
            "agent_intent_confirmed",
            {"intent_id": intent_id, "prompt": row["prompt"]},
            node_id=None,
        )
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def reject_intent(intent_id: int, reason: str) -> None:
    """Reject a pending agent intent."""
    ensure_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, status FROM agent_intents WHERE id = ?",
            (intent_id,),
        ).fetchone()
        if not row:
            raise StateValidationError(f"Intent {intent_id} does not exist")
        if row["status"] != "pending":
            raise StateValidationError(f"Intent {intent_id} is not pending")
        now = _now_iso()
        conn.execute(
            "UPDATE agent_intents SET status = 'rejected', updated_at = ? WHERE id = ?",
            (now, intent_id),
        )
        _record_event(
            conn,
            "agent_intent_rejected",
            {"intent_id": intent_id, "reason": reason},
            node_id=None,
        )
        conn.commit()
    finally:
        conn.close()


def attach_intent_to_node(intent_id: int, node_id: str) -> None:
    """Attach a confirmed intent to a node."""
    ensure_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id FROM agent_intents WHERE id = ?",
            (intent_id,),
        ).fetchone()
        if not row:
            raise StateValidationError(f"Intent {intent_id} does not exist")
        now = _now_iso()
        conn.execute(
            "UPDATE agent_intents SET node_id = ?, updated_at = ? WHERE id = ?",
            (node_id, now, intent_id),
        )
        _record_event(
            conn,
            "agent_intent_attached",
            {"intent_id": intent_id, "node_id": node_id},
            node_id=node_id,
        )
        conn.commit()
    finally:
        conn.close()


def log_anomaly(event_type: str, payload: Dict[str, Any], node_id: Optional[str] = None) -> None:
    """Record an anomaly event for auditability."""
    ensure_db()
    conn = _connect()
    try:
        _record_event(conn, event_type, payload, node_id=node_id)
        conn.commit()
    finally:
        conn.close()


def validate_state() -> Dict[str, Any]:
    """Basic state validation for doctor checks."""
    ensure_db()
    conn = _connect()
    errors = []
    try:
        # Head must exist if set
        head = _get_meta(conn, "head")
        if head:
            exists = conn.execute("SELECT 1 FROM nodes WHERE id = ?", (head,)).fetchone()
            if not exists:
                errors.append(f"Head points to non-existent node: {head}")

        # Parent linkage must exist
        rows = conn.execute("SELECT id, parent_id FROM nodes WHERE parent_id IS NOT NULL").fetchall()
        for row in rows:
            exists = conn.execute("SELECT 1 FROM nodes WHERE id = ?", (row["parent_id"],)).fetchone()
            if not exists:
                errors.append(f"Node {row['id']} parent points to non-existent node: {row['parent_id']}")

        return {"valid": len(errors) == 0, "errors": errors}
    finally:
        conn.close()


def detect_orphaned_nodes() -> dict:
    """Detect nodes that reference missing Git branches."""
    try:
        from . import git

        state = load_state()
        nodes = state.get("nodes", {})

        orphaned_nodes = []
        healthy_nodes = []

        for node_id, node_data in nodes.items():
            ref = node_data.get("ref", "")
            if ref.startswith("refs/heads/"):
                branch_name = ref[11:]
                if git.branch_exists(branch_name):
                    healthy_nodes.append(
                        {
                            "node_id": node_id,
                            "branch_name": branch_name,
                            "prompt": node_data.get("prompt", ""),
                            "parent": node_data.get("parent"),
                        }
                    )
                else:
                    orphaned_nodes.append(
                        {
                            "node_id": node_id,
                            "branch_name": branch_name,
                            "prompt": node_data.get("prompt", ""),
                            "parent": node_data.get("parent"),
                            "ref": ref,
                        }
                    )

        return {
            "orphaned_nodes": orphaned_nodes,
            "healthy_nodes": healthy_nodes,
            "total_nodes": len(nodes),
            "orphan_count": len(orphaned_nodes),
        }
    except Exception as e:
        raise StateError(f"Cannot detect orphaned nodes: {e}")


def suggest_orphan_cleanup() -> str:
    """Provide suggestions for cleaning up orphaned nodes."""
    try:
        info = detect_orphaned_nodes()

        if not info["orphaned_nodes"]:
            return "✓ No orphaned nodes detected. All nodes have valid Git branches."

        suggestions = []
        suggestions.append(f"⚠ Found {info['orphan_count']} orphaned nodes:")
        suggestions.append("")

        for node_info in info["orphaned_nodes"]:
            suggestions.append(f"  Node {node_info['node_id']}: {node_info['prompt']}")
            suggestions.append(f"    Missing branch: {node_info['branch_name']}")
            if node_info["parent"]:
                suggestions.append(f"    Parent: {node_info['parent']}")

        suggestions.append("")
        suggestions.append("Cleanup options:")
        suggestions.append("1. Remove orphaned nodes from metadata:")
        suggestions.append("   - This will permanently delete the node records")
        suggestions.append("   - The Git commits may still exist but won't be tracked")
        suggestions.append("")
        suggestions.append("2. Mark nodes as orphaned (keep for reference):")
        suggestions.append("   - Nodes will be marked as orphaned but kept in metadata")
        suggestions.append("   - You can still see them in 'stem list' with orphan indicator")
        suggestions.append("")
        suggestions.append(f"Healthy nodes: {len(info['healthy_nodes'])}/{info['total_nodes']}")

        return "\n".join(suggestions)
    except Exception as e:
        return f"Cannot provide orphan cleanup suggestions: {e}"
