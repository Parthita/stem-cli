from __future__ import annotations

import os
from dataclasses import dataclass

from .paths import stem_agent_dir
from .util import read_json, short_text


@dataclass(frozen=True)
class AgentNote:
    prompt: str
    summary: str


def _normalize(text: str) -> str:
    return short_text(text, max_len=140)


def _load_note(path: str) -> AgentNote | None:
    data = read_json(path)
    if not data:
        return None
    prompt = data.get("prompt")
    summary = data.get("summary")
    if not isinstance(prompt, str) or not isinstance(summary, str):
        return None
    prompt = _normalize(prompt)
    summary = _normalize(summary)
    if not prompt or not summary:
        return None
    return AgentNote(prompt=prompt, summary=summary)


def load_branch_note(repo_root: str) -> AgentNote | None:
    return _load_note(os.path.join(stem_agent_dir(repo_root), "branch.json"))


def load_leaf_note(repo_root: str) -> AgentNote | None:
    return _load_note(os.path.join(stem_agent_dir(repo_root), "leaf.json"))
