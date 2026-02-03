from __future__ import annotations

import json
import os
from dataclasses import dataclass
import re

from .util import short_text


ALLOWED_COMMANDS = {"branch", "update", "update_branch", "jump"}
JSON_SCHEMA_VERSION = 4
ALLOWED_KEYS = {
    "command",
    "prompt",
    "summary",
    "prev_prompt",
    "prev_summary",
    "old_prompt",
    "old_summary",
    "branch_id",
    "target",
    "mode",
    "timestamp",
    "nonce",
    "schema_version",
}

BRANCH_ID_RE = re.compile("^b\\d{4}$")


@dataclass(frozen=True)
class Command:
    command: str
    prompt: str | None
    summary: str | None
    prev_prompt: str | None
    prev_summary: str | None
    branch_id: str | None
    target: str | None
    mode: str | None
    timestamp: str | None
    nonce: str
    source_file: str


def queue_dir(repo_root: str) -> str:
    return os.path.join(repo_root, ".stem", "agent", "queue")


def archive_dir(repo_root: str) -> str:
    return os.path.join(repo_root, ".stem", "agent", "archive")


def list_queue_files(repo_root: str) -> list[str]:
    qdir = queue_dir(repo_root)
    if not os.path.isdir(qdir):
        return []
    files = [os.path.join(qdir, f) for f in os.listdir(qdir) if f.endswith(".json")]
    return sorted(files, key=lambda p: os.path.getmtime(p))


def _load_json(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _norm(text: str | None) -> str | None:
    if text is None:
        return None
    return short_text(text, max_len=140)


def parse_command(path: str) -> Command | None:
    data = _load_json(path)
    if not isinstance(data, dict):
        return None
    if any(key not in ALLOWED_KEYS for key in data.keys()):
        return None
    if "commands" in data:
        return None

    command = data.get("command")
    nonce = data.get("nonce", "")
    schema_version = data.get("schema_version")
    if command is not None and (not isinstance(command, str) or command not in ALLOWED_COMMANDS):
        return None
    if nonce is None:
        nonce = ""
    if not isinstance(nonce, str):
        return None
    if schema_version is not None and schema_version not in {4}:
        return None

    prompt = _norm(data.get("prompt"))
    summary = _norm(data.get("summary"))
    prev_prompt = _norm(data.get("prev_prompt") or data.get("old_prompt"))
    prev_summary = _norm(data.get("prev_summary") or data.get("old_summary"))
    branch_id = _norm(data.get("branch_id"))
    target = data.get("target")
    mode = data.get("mode")
    timestamp = data.get("timestamp")

    if command == "branch" and (not prompt or not summary):
        return None
    if command == "update" and (not prev_prompt or not prev_summary):
        return None
    if command == "update_branch" and (
        not prompt or not summary or not prev_prompt or not prev_summary
    ):
        return None
    if command in {"update", "update_branch"} and branch_id:
        if not BRANCH_ID_RE.match(branch_id):
            return None
    if command == "jump" and not isinstance(target, str):
        return None

    return Command(
        command=command,
        prompt=prompt,
        summary=summary,
        prev_prompt=prev_prompt,
        prev_summary=prev_summary,
        branch_id=branch_id,
        target=target if isinstance(target, str) else None,
        mode=mode if isinstance(mode, str) else None,
        timestamp=timestamp if isinstance(timestamp, str) else None,
        nonce=nonce,
        source_file=path,
    )


def archive_file(repo_root: str, path: str, suffix: str = "done") -> None:
    os.makedirs(archive_dir(repo_root), exist_ok=True)
    base = os.path.basename(path)
    dst = os.path.join(archive_dir(repo_root), f"{base}.{suffix}")
    try:
        os.replace(path, dst)
    except Exception:
        try:
            os.remove(path)
        except Exception:
            return
