from __future__ import annotations

import os

from .util import run, slugify


def ensure_git(repo_root: str) -> None:
    res = run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo_root)
    if res.code != 0:
        run(["git", "init"], cwd=repo_root)


def current_branch(repo_root: str) -> str:
    res = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    return res.stdout.strip()


def status_porcelain(repo_root: str) -> str:
    res = run(["git", "status", "--porcelain"], cwd=repo_root)
    return res.stdout


def create_branch(repo_root: str, branch_name: str) -> None:
    res = run(["git", "checkout", "-b", branch_name], cwd=repo_root)
    if res.code != 0:
        raise RuntimeError(res.stderr or "git checkout -b failed")


def checkout(repo_root: str, ref: str) -> None:
    res = run(["git", "checkout", ref], cwd=repo_root)
    if res.code != 0:
        raise RuntimeError(res.stderr or "git checkout failed")


def checkout_force(repo_root: str, ref: str) -> None:
    res = run(["git", "checkout", "-f", ref], cwd=repo_root)
    if res.code != 0:
        raise RuntimeError(res.stderr or "git checkout -f failed")


def stash_push(repo_root: str, message: str) -> None:
    res = run(["git", "stash", "push", "-u", "-m", message], cwd=repo_root)
    if res.code != 0:
        raise RuntimeError(res.stderr or "git stash failed")


def add_all(repo_root: str) -> None:
    run(["git", "add", "-A"], cwd=repo_root)


def commit(repo_root: str, message: str, allow_empty: bool = True) -> str:
    args = ["git", "commit", "-m", message]
    if allow_empty:
        args.append("--allow-empty")
    run(args, cwd=repo_root)
    res = run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    return res.stdout.strip()


def get_user(repo_root: str) -> str:
    res = run(["git", "config", "user.name"], cwd=repo_root)
    if res.code == 0 and res.stdout.strip():
        return res.stdout.strip()
    return os.getenv("USER", "user")


def safe_user(repo_root: str) -> str:
    raw = get_user(repo_root)
    safe = slugify(raw, max_len=32)
    return safe or "user"


def show_stat(repo_root: str, commit: str) -> str:
    res = run(["git", "show", "--stat", "--oneline", "-1", commit], cwd=repo_root)
    return res.stdout.strip()
