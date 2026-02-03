from __future__ import annotations

import os
from typing import Optional

from .util import run


def git_root(cwd: str) -> Optional[str]:
    res = run(["git", "rev-parse", "--show-toplevel"], cwd=cwd)
    if res.code != 0:
        return None
    return res.stdout.strip()


def stem_dir(repo_root: str) -> str:
    return os.path.join(repo_root, ".stem")


def stem_db_path(repo_root: str) -> str:
    return os.path.join(stem_dir(repo_root), "stem.db")


def stem_agent_dir(repo_root: str) -> str:
    return os.path.join(stem_dir(repo_root), "agent")


def stem_md_path(repo_root: str) -> str:
    return os.path.join(repo_root, "stem.md")


def registry_dir() -> str:
    override = os.getenv("STEM_HOME")
    if override:
        return os.path.abspath(override)
    return os.path.join(os.path.expanduser("~"), ".stem")


def registry_db_path() -> str:
    return os.path.join(registry_dir(), "registry.db")
