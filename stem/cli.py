from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable

from stem.core import agent as agent_notes
from stem.core import db as db_mod
from stem.core import git as git_mod
from stem.core import paths
from stem.core import queue as queue_mod
from stem.core import registry
from stem.core.util import join_tokens, short_text, slugify


def _load_template(name: str) -> str:
    base = os.path.join(os.path.dirname(__file__), "templates")
    path = os.path.join(base, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read().rstrip()


def _repo_root_or_cwd() -> str:
    cwd = os.getcwd()
    root = paths.git_root(cwd)
    return root if root else cwd


def _require_stem(repo_root: str) -> db_mod.StemDB:
    db = db_mod.StemDB(repo_root)
    if not os.path.exists(db.db_path):
        _die("stem is not initialized in this repo. Run `stem create` first.")
    try:
        db.verify_schema()
    except RuntimeError as exc:
        _die(str(exc))
    return db


def _die(msg: str) -> None:
    print(msg)
    sys.exit(1)


def _normalize_prompt(tokens: Iterable[str]) -> str:
    raw = join_tokens(tokens)
    if raw.startswith(":"):
        raw = raw[1:].strip()
    return raw


def _branch_id_from_git_branch(git_branch: str) -> str | None:
    if not git_branch.startswith("stem/"):
        return None
    # stem/<user>/<branch_id>-<slug>
    parts = git_branch.split("/")
    if len(parts) < 3:
        return None
    tail = parts[2]
    if "-" not in tail:
        return None
    return tail.split("-")[0]


def _print_kv(title: str, value: str) -> None:
    print(f"{title}: {value}")


def cmd_create(args: argparse.Namespace) -> None:
    repo_root = os.getcwd()
    git_mod.ensure_git(repo_root)
    _ensure_gitignore(repo_root)

    db = db_mod.StemDB(repo_root)
    db.init()

    os.makedirs(paths.stem_agent_dir(repo_root), exist_ok=True)
    os.makedirs(queue_mod.queue_dir(repo_root), exist_ok=True)
    _ensure_agent_templates(repo_root)
    registry.register_repo(repo_root)

    if args.agent:
        stem_md_path = paths.stem_md_path(repo_root)
        if not os.path.exists(stem_md_path):
            template = _load_template("stem.md")
            with open(stem_md_path, "w", encoding="utf-8") as f:
                f.write(template + "\n")
        _ensure_agent_templates(repo_root)
        print(_load_template("bootstrap_prompt.txt"))
        return

    _print_kv("stem", "initialized")
    _print_kv("repo", repo_root)


def _run_branch(repo_root: str, prompt: str, summary: str) -> None:
    db = _require_stem(repo_root)
    user = git_mod.get_user(repo_root)
    safe_user = git_mod.safe_user(repo_root)
    branch_id = db.next_branch_id()
    slug = slugify(prompt)
    git_branch = f"stem/{safe_user}/{branch_id}-{slug}"

    git_mod.create_branch(repo_root, git_branch)
    git_mod.add_all(repo_root)

    leaf_id = db.next_leaf_id(branch_id)
    commit = git_mod.commit(repo_root, f"stem leaf {leaf_id}: {prompt}")

    db.insert_branch(branch_id, slug, user, prompt, summary, git_branch)
    db.insert_leaf(branch_id, leaf_id, prompt, summary, commit)
    db.set_current_branch(branch_id)
    db.set_branch_count(db.get_branch_count() + 1)

    _print_kv("branch", branch_id)
    _print_kv("leaf", leaf_id)
    _print_kv("git", git_branch)


def cmd_branch(args: argparse.Namespace) -> None:
    repo_root = _repo_root_or_cwd()
    prompt = _normalize_prompt(args.prompt)
    note = agent_notes.load_branch_note(repo_root)
    if not prompt and note:
        prompt = note.prompt
    if not prompt:
        _die("branch prompt required")

    summary = note.summary if note else prompt
    _run_branch(repo_root, short_text(prompt), short_text(summary))


def _run_update(repo_root: str, prompt: str, summary: str) -> None:
    db = _require_stem(repo_root)
    branch_id = db.get_current_branch()
    if not branch_id:
        _die("no current branch set (use `stem jump <branch_id>`)")
    _checkout_branch_id(repo_root, db, branch_id)

    leaf_id = db.next_leaf_id(branch_id)

    git_mod.add_all(repo_root)
    commit = git_mod.commit(repo_root, f"stem leaf {leaf_id}: {prompt}")

    db.insert_leaf(branch_id, leaf_id, prompt, summary, commit)

    _print_kv("leaf", leaf_id)
    _print_kv("git", commit)


def cmd_update(args: argparse.Namespace) -> None:
    if args.prompt and args.prompt[0] == "branch":
        tokens = list(args.prompt[1:])
        final = args.final
        if "--final" in tokens:
            idx = tokens.index("--final")
            if idx + 1 >= len(tokens):
                _die("missing value for --final")
            final = tokens[idx + 1]
            del tokens[idx : idx + 2]
        branch_args = argparse.Namespace(prompt=tokens, final=final)
        cmd_update_branch(branch_args)
        return

    repo_root = _repo_root_or_cwd()

    prompt = _normalize_prompt(args.prompt)
    note = agent_notes.load_leaf_note(repo_root)
    if not prompt and note:
        prompt = note.prompt
    if not prompt:
        _die("update prompt required")

    summary = note.summary if note else prompt
    prompt = short_text(prompt)
    summary = short_text(summary)

    _run_update(repo_root, short_text(prompt), short_text(summary))


def _run_update_branch(
    repo_root: str,
    final_prompt: str,
    final_summary: str,
    new_prompt: str,
    new_summary: str,
) -> None:
    repo_root = _repo_root_or_cwd()
    db = _require_stem(repo_root)

    branch_id = db.get_current_branch()
    if not branch_id:
        _die("no current branch set (use `stem jump <branch_id>`)")
    _checkout_branch_id(repo_root, db, branch_id)

    # Final leaf for current branch
    if not final_prompt:
        _die("final leaf prompt required (use leaf.json or --final)")

    final_leaf_id = db.next_leaf_id(branch_id)
    git_mod.add_all(repo_root)
    final_commit = git_mod.commit(
        repo_root, f"stem leaf {final_leaf_id}: {short_text(final_prompt)}"
    )
    db.insert_leaf(
        branch_id,
        final_leaf_id,
        short_text(final_prompt),
        short_text(final_summary),
        final_commit,
    )

    # New branch
    user = git_mod.get_user(repo_root)
    new_branch_id = db.next_branch_id()
    slug = slugify(new_prompt)
    new_git_branch = f"stem/{user}/{new_branch_id}-{slug}"

    git_mod.create_branch(repo_root, new_git_branch)
    git_mod.add_all(repo_root)
    new_leaf_id = db.next_leaf_id(new_branch_id)
    new_commit = git_mod.commit(repo_root, f"stem leaf {new_leaf_id}: {new_prompt}")

    db.insert_branch(
        new_branch_id, slug, user, new_prompt, new_summary, new_git_branch
    )
    db.insert_leaf(new_branch_id, new_leaf_id, new_prompt, new_summary, new_commit)
    db.set_current_branch(new_branch_id)
    db.set_branch_count(db.get_branch_count() + 1)

    _print_kv("final leaf", final_leaf_id)
    _print_kv("new branch", new_branch_id)
    _print_kv("new leaf", new_leaf_id)


def cmd_update_branch(args: argparse.Namespace) -> None:
    repo_root = _repo_root_or_cwd()
    note = agent_notes.load_leaf_note(repo_root)
    final_prompt = args.final or (note.prompt if note else "")
    if not final_prompt:
        _die("final leaf prompt required (use leaf.json or --final)")
    final_summary = note.summary if note else final_prompt

    new_prompt = _normalize_prompt(args.prompt)
    if not new_prompt:
        _die("new branch prompt required")
    new_summary = new_prompt

    _run_update_branch(
        repo_root,
        short_text(final_prompt),
        short_text(final_summary),
        short_text(new_prompt),
        short_text(new_summary),
    )


def _run_jump(repo_root: str, target: str, mode: str | None) -> None:
    db = _require_stem(repo_root)
    branch_id = None
    leaf = None

    if mode == "head":
        branch_id = target
        leaf = db.first_leaf_for_branch(branch_id)
    elif mode == "leaf":
        matches = db.find_leaves_by_id(target)
        if len(matches) == 1:
            leaf = matches[0]
            branch_id = leaf["branch_id"]
        elif len(matches) > 1:
            _die("leaf id is ambiguous; use a branch id")
    else:
        matches = db.find_leaves_by_id(target)
        if len(matches) == 1:
            leaf = matches[0]
            branch_id = leaf["branch_id"]
        elif len(matches) > 1:
            _die("leaf id is ambiguous; use a branch id")
        else:
            branch_id = target
            leaf = db.latest_leaf_for_branch(branch_id)

    if not leaf or not branch_id:
        _die("unknown branch or leaf")

    if mode in {"head", "leaf"}:
        _safe_checkout(repo_root, leaf["git_commit"])
    else:
        branch = db.get_branch(branch_id)
        if not branch:
            _die("unknown branch")
        _safe_checkout(repo_root, branch["git_branch"])

    ancestry = _build_ancestry(db, branch_id)

    db.insert_jump(
        branch_id,
        leaf["leaf_id"],
        leaf["prompt"],
        leaf["summary"],
        ancestry,
    )

    _write_jump_json(repo_root, branch_id, leaf, ancestry)
    print(_load_template("jump_prompt.txt"))


def cmd_jump(args: argparse.Namespace) -> None:
    repo_root = _repo_root_or_cwd()
    if args.leaf_id:
        db = _require_stem(repo_root)
        leaf = db.get_leaf_on_branch(args.target, args.leaf_id)
        if not leaf:
            _die("unknown branch/leaf")
        _jump_to_leaf_row(repo_root, db, leaf)
        return
    mode = "head" if args.head else ("leaf" if args.leaf else None)
    _run_jump(repo_root, args.target, mode)


def cmd_exec(args: argparse.Namespace) -> None:
    repo_root = _repo_root_or_cwd()
    db = _require_stem(repo_root)
    files = queue_mod.list_queue_files(repo_root)
    files += _agent_command_files(repo_root)
    if not files:
        print("no queued commands")
        return

    parsed = []
    seen_nonces: set[str] = set()
    branch_path = os.path.join(paths.stem_agent_dir(repo_root), "branch.json")
    leaf_path = os.path.join(paths.stem_agent_dir(repo_root), "leaf.json")

    # Handle agent files with inferred commands
    branch_ready = _command_file_ready(branch_path) if os.path.exists(branch_path) else False
    leaf_ready = _command_file_ready(leaf_path) if os.path.exists(leaf_path) else False

    if branch_ready and leaf_ready:
        # If branch.json was edited after leaf.json, treat as update_branch
        if os.path.getmtime(branch_path) >= os.path.getmtime(leaf_path):
            cmd = _parse_update_branch(repo_root, branch_path, leaf_path)
            parsed.append(cmd)
        else:
            cmd = _parse_update(repo_root, leaf_path)
            parsed.append(cmd)
            cmd = _parse_branch(repo_root, branch_path)
            parsed.append(cmd)
    else:
        if branch_ready:
            parsed.append(_parse_branch(repo_root, branch_path))
        if leaf_ready:
            parsed.append(_parse_update(repo_root, leaf_path))

    # Add any queued json files
    for path in files:
        if path.endswith("branch.json") or path.endswith("leaf.json"):
            continue
        cmd = queue_mod.parse_command(path)
        if not cmd:
            _die(f"invalid command file: {path}")
        parsed.append(cmd)

    processed = 0
    for cmd in parsed:
        if not cmd.nonce:
            cmd = _assign_nonce(cmd)
        if db.has_exec_nonce(cmd.nonce):
            queue_mod.archive_file(repo_root, cmd.source_file, suffix="dup")
            continue

        if cmd.command == "branch":
            _run_branch(repo_root, cmd.prompt or "", cmd.summary or (cmd.prompt or ""))
        elif cmd.command == "update":
            _run_update(
                repo_root,
                cmd.prev_prompt or "",
                cmd.prev_summary or (cmd.prev_prompt or ""),
            )
        elif cmd.command == "update_branch":
            _run_update_branch(
                repo_root,
                cmd.prev_prompt or "",
                cmd.prev_summary or (cmd.prev_prompt or ""),
                cmd.prompt or "",
                cmd.summary or (cmd.prompt or ""),
            )
        elif cmd.command == "jump":
            _run_jump(repo_root, cmd.target or "", cmd.mode)
        else:
            _die(f"unsupported command: {cmd.command}")

        db.insert_exec_nonce(cmd.nonce, cmd.command, cmd.source_file)
        if cmd.source_file.endswith("branch.json") or cmd.source_file.endswith("leaf.json"):
            _clear_command_file(cmd.source_file)
        else:
            queue_mod.archive_file(repo_root, cmd.source_file, suffix="done")
        processed += 1

    print(f"processed {processed} command(s)")


def cmd_watch(args: argparse.Namespace) -> None:
    import json
    import time
    import subprocess
    import traceback

    repo_root = _repo_root_or_cwd()
    heartbeat_path = os.path.join(repo_root, ".stem", "agent", "watch.json")
    pid_path = os.path.join(repo_root, ".stem", "agent", "watch.pid")
    log_path = os.path.join(repo_root, ".stem", "agent", "watch.log")

    if args.stop:
        stopped = False
        pid = None
        if os.path.exists(pid_path):
            try:
                with open(pid_path, "r", encoding="utf-8") as f:
                    pid = int(f.read().strip())
            except Exception:
                pid = None
        if pid is None:
            try:
                import json

                with open(heartbeat_path, "r", encoding="utf-8") as f:
                    hb = json.load(f)
                pid = int(hb.get("pid", 0)) or None
            except Exception:
                pid = None
        if pid is not None:
            try:
                os.kill(pid, 15)
                stopped = True
            except Exception:
                pass
        try:
            if os.path.exists(pid_path):
                os.remove(pid_path)
            if os.path.exists(heartbeat_path):
                os.remove(heartbeat_path)
        except Exception:
            pass
        if stopped:
            print(f"watch stopped (pid {pid})")
            return
        _die("watch not running")

    if args.daemon:
        if os.path.exists(pid_path):
            _die("watch already running (use `stem watch --stop`)")
        cmd = [
            sys.executable,
            "-m",
            "stem.cli",
            "watch",
            "--interval",
            str(args.interval),
            "--daemon-child",
        ]
        proc = subprocess.Popen(
            cmd, cwd=repo_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )
        os.makedirs(os.path.dirname(pid_path), exist_ok=True)
        with open(pid_path, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
        print(f"watch started (pid {proc.pid})")
        print(f"heartbeat: {heartbeat_path}")
        return

    quiet = bool(args.daemon_child)
    last_nonce = "-"
    while True:
        try:
            files = queue_mod.list_queue_files(repo_root) + _agent_command_files(repo_root)
            queue_len = len(files)
            if queue_len:
                cmd_exec(args)
                db = _require_stem(repo_root)
                with db.connect() as conn:
                    row = conn.execute(
                        "SELECT nonce FROM command_exec WHERE repo_root = ? ORDER BY id DESC LIMIT 1",
                        (repo_root,),
                    ).fetchone()
                if row:
                    last_nonce = row["nonce"]
        except SystemExit:
            pass
        except Exception:
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(traceback.format_exc() + "\n")
            except Exception:
                pass
        payload = {
            "heartbeat": "ok",
            "queue": queue_len,
            "last_nonce": last_nonce,
            "timestamp": time.time(),
            "pid": os.getpid(),
            "interval": args.interval,
        }
        try:
            os.makedirs(os.path.dirname(heartbeat_path), exist_ok=True)
            with open(heartbeat_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
        except Exception:
            pass
        if not quiet:
            line = f"heartbeat ok | queue {queue_len} | last {last_nonce}"
            print(line.ljust(80), end="\r", flush=True)
        time.sleep(max(0.2, args.interval))


def cmd_status(args: argparse.Namespace) -> None:
    repo_root = _repo_root_or_cwd()
    db = _require_stem(repo_root)
    queue_files = queue_mod.list_queue_files(repo_root) + _agent_command_files(repo_root)
    queue_len = 0
    for path in queue_files:
        if path.endswith("branch.json") or path.endswith("leaf.json"):
            if _command_file_ready(path):
                queue_len += 1
        else:
            queue_len += 1
    heartbeat_path = os.path.join(repo_root, ".stem", "agent", "watch.json")
    watch_state = "stopped"
    if os.path.exists(heartbeat_path):
        try:
            import json
            import time

            with open(heartbeat_path, "r", encoding="utf-8") as f:
                hb = json.load(f)
            age = time.time() - float(hb.get("timestamp", 0))
            interval = float(hb.get("interval", 1.0))
            threshold = max(5.0, interval * 3)
            watch_state = "running" if age <= threshold else "stale"
        except Exception:
            watch_state = "unknown"
    with db.connect() as conn:
        row = conn.execute(
            "SELECT nonce, command, created_at FROM command_exec WHERE repo_root = ? ORDER BY id DESC LIMIT 1",
            (repo_root,),
        ).fetchone()
    last = row["nonce"] if row else "-"
    last_cmd = row["command"] if row else "-"
    last_time = row["created_at"] if row else "-"
    print(f"queue: {queue_len}")
    print(f"watch: {watch_state}")
    print(f"last nonce: {last}")
    print(f"last command: {last_cmd}")
    print(f"last time: {last_time}")


def _write_jump_json(repo_root: str, branch_id: str, leaf, ancestry: str) -> None:
    from stem.core.util import write_json

    data = {
        "branch_id": branch_id,
        "leaf_id": leaf["leaf_id"],
        "prompt": leaf["prompt"],
        "summary": leaf["summary"],
        "ancestry": ancestry,
    }
    path = os.path.join(paths.stem_agent_dir(repo_root), "jump.json")
    write_json(path, data)


def _build_ancestry(db: db_mod.StemDB, branch_id: str) -> str:
    leaves = db.list_leaves(branch_id, limit=3)
    parts = [f"{l['leaf_id']}: {short_text(l['prompt'], 60)}" for l in leaves]
    return " | ".join(reversed(parts))


def _jump_to_leaf_row(repo_root: str, db: db_mod.StemDB, leaf) -> None:
    _safe_checkout(repo_root, leaf["git_commit"])
    ancestry = _build_ancestry(db, leaf["branch_id"])
    db.insert_jump(
        leaf["branch_id"],
        leaf["leaf_id"],
        leaf["prompt"],
        leaf["summary"],
        ancestry,
    )
    _write_jump_json(repo_root, leaf["branch_id"], leaf, ancestry)
    print(_load_template("jump_prompt.txt"))


def cmd_list(args: argparse.Namespace) -> None:
    repo_root = _repo_root_or_cwd()
    db = _require_stem(repo_root)

    branches = db.list_branches(limit=args.limit)
    if not branches:
        print("no branches")
        return

    for b in branches:
        print(f"{b['branch_id']}  {short_text(b['prompt'], 60)}")
        leaves = db.list_leaves(b["branch_id"], limit=args.leaves)
        for l in leaves:
            print(f"  {l['leaf_id']}  {short_text(l['summary'], 70)}")


def cmd_global(args: argparse.Namespace) -> None:
    if args.repo:
        repo_root = args.repo
        row = registry.get_repo(repo_root)
        if not row:
            _die("repo not found in registry")
        db = db_mod.StemDB(repo_root)
        if not os.path.exists(db.db_path):
            _die("repo has no stem metadata")
        branches = db.list_branches(limit=10)
        print(repo_root)
        for b in branches:
            print(f"{b['branch_id']}  {short_text(b['prompt'], 60)}")
        return

    rows = registry.list_repos(limit=args.limit)
    if not rows:
        print("no stem repos")
        return
    for r in rows:
        print(r["repo_root"])


def cmd_tui(args: argparse.Namespace) -> None:
    print("tui not implemented yet")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stem")
    parser.add_argument(
        "--version", action="version", version="stem 0.1.0"
    )
    sub = parser.add_subparsers(dest="cmd")

    create = sub.add_parser("create")
    create.add_argument("--agent", action="store_true")
    create.set_defaults(func=cmd_create)

    branch = sub.add_parser("branch")
    branch.add_argument("prompt", nargs=argparse.REMAINDER)
    branch.set_defaults(func=cmd_branch)

    update = sub.add_parser("update")
    update.add_argument("--final", default="")
    update.add_argument("prompt", nargs=argparse.REMAINDER)
    update.set_defaults(func=cmd_update)

    jump = sub.add_parser("jump")
    jump.add_argument("target")
    jump.add_argument("leaf_id", nargs="?")
    jump.add_argument("--head", action="store_true")
    jump.add_argument("--leaf", action="store_true")
    jump.set_defaults(func=cmd_jump)

    exec_cmd = sub.add_parser("exec")
    exec_cmd.set_defaults(func=cmd_exec)

    watch_cmd = sub.add_parser("watch")
    watch_cmd.add_argument("--interval", type=float, default=1.0)
    watch_cmd.add_argument("--daemon", action="store_true")
    watch_cmd.add_argument("--stop", action="store_true")
    watch_cmd.add_argument("--daemon-child", action="store_true", help=argparse.SUPPRESS)
    watch_cmd.set_defaults(func=cmd_watch)

    status_cmd = sub.add_parser("status")
    status_cmd.set_defaults(func=cmd_status)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--limit", type=int, default=10)
    list_cmd.add_argument("--leaves", type=int, default=3)
    list_cmd.set_defaults(func=cmd_list)

    global_cmd = sub.add_parser("global")
    global_cmd.add_argument("repo", nargs="?")
    global_cmd.add_argument("--limit", type=int, default=50)
    global_cmd.set_defaults(func=cmd_global)

    tui = sub.add_parser("tui")
    tui.set_defaults(func=cmd_tui)

    return parser


def _agent_command_files(repo_root: str) -> list[str]:
    base = paths.stem_agent_dir(repo_root)
    files = []
    for name in ("branch.json", "leaf.json"):
        path = os.path.join(base, name)
        if os.path.exists(path):
            files.append(path)
    return files


def _assign_nonce(cmd: queue_mod.Command) -> queue_mod.Command:
    import dataclasses
    import time

    nonce = f"{cmd.command}-{int(time.time())}"
    return dataclasses.replace(cmd, nonce=nonce)


def _command_file_ready(path: str) -> bool:
    try:
        import json

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # branch.json: prompt + summary
        if path.endswith("branch.json"):
            return bool(data.get("prompt")) and bool(data.get("summary"))
        # leaf.json: old_prompt + old_summary
        if path.endswith("leaf.json"):
            return bool(data.get("prev_prompt") or data.get("old_prompt")) and bool(
                data.get("prev_summary") or data.get("old_summary")
            )
        return False
    except Exception:
        return False


def _clear_command_file(path: str) -> None:
    try:
        import json

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in ("prompt", "summary", "prev_prompt", "prev_summary", "old_prompt", "old_summary", "nonce"):
            if key in data:
                data[key] = ""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
    except Exception:
        return


def _parse_branch(repo_root: str, path: str) -> queue_mod.Command:
    cmd = queue_mod.parse_command(path)
    if cmd and cmd.command:
        return cmd
    # infer
    import json
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return queue_mod.Command(
        command="branch",
        prompt=data.get("prompt", ""),
        summary=data.get("summary", ""),
        prev_prompt=None,
        prev_summary=None,
        branch_id=None,
        target=None,
        mode=None,
        timestamp=None,
        nonce=data.get("nonce", ""),
        source_file=path,
    )


def _parse_update(repo_root: str, path: str) -> queue_mod.Command:
    cmd = queue_mod.parse_command(path)
    if cmd and cmd.command:
        return cmd
    import json
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return queue_mod.Command(
        command="update",
        prompt=data.get("prompt", ""),
        summary=data.get("summary", ""),
        prev_prompt=data.get("prev_prompt") or data.get("old_prompt", ""),
        prev_summary=data.get("prev_summary") or data.get("old_summary", ""),
        branch_id=data.get("branch_id", ""),
        target=None,
        mode=None,
        timestamp=None,
        nonce=data.get("nonce", ""),
        source_file=path,
    )


def _parse_update_branch(repo_root: str, branch_path: str, leaf_path: str) -> queue_mod.Command:
    import json
    with open(branch_path, "r", encoding="utf-8") as f:
        b = json.load(f)
    with open(leaf_path, "r", encoding="utf-8") as f:
        l = json.load(f)
    return queue_mod.Command(
        command="update_branch",
        prompt=b.get("prompt", ""),
        summary=b.get("summary", ""),
        prev_prompt=l.get("prev_prompt") or l.get("old_prompt", ""),
        prev_summary=l.get("prev_summary") or l.get("old_summary", ""),
        branch_id=b.get("branch_id") or l.get("branch_id", ""),
        target=None,
        mode=None,
        timestamp=None,
        nonce=b.get("nonce") or l.get("nonce", ""),
        source_file=leaf_path,
    )


def _ensure_agent_templates(repo_root: str) -> None:
    base = paths.stem_agent_dir(repo_root)
    os.makedirs(base, exist_ok=True)
    for name in ("branch.json", "leaf.json"):
        dst = os.path.join(base, name)
        if not os.path.exists(dst):
            with open(dst, "w", encoding="utf-8") as f:
                f.write(_load_template(name) + "\n")


def _set_branch_id(repo_root: str, branch_id: str) -> None:
    if not branch_id:
        return
    for name in ("branch.json", "leaf.json"):
        path = os.path.join(paths.stem_agent_dir(repo_root), name)
        if not os.path.exists(path):
            continue
        try:
            import json

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["branch_id"] = branch_id
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
        except Exception:
            continue


def _last_branch_id(repo_root: str, db: db_mod.StemDB) -> str:
    row = db.list_branches(limit=1)
    if not row:
        return ""
    return row[0]["branch_id"]


def _ensure_gitignore(repo_root: str) -> None:
    path = os.path.join(repo_root, ".gitignore")
    line = ".stem/\n"
    try:
        contents = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                contents = f.read()
            if ".stem/" in contents:
                return
        with open(path, "a", encoding="utf-8") as f:
            if contents and not contents.endswith("\n"):
                f.write("\n")
            f.write(line)
    except Exception:
        return


def _checkout_branch_id(repo_root: str, db: db_mod.StemDB, branch_id: str) -> None:
    branch = db.get_branch(branch_id)
    if not branch:
        _die(f"unknown branch: {branch_id}")
    try:
        _safe_checkout(repo_root, branch["git_branch"])
    except RuntimeError as exc:
        _die(str(exc))


def _safe_checkout(repo_root: str, ref: str) -> None:
    try:
        git_mod.checkout(repo_root, ref)
        return
    except RuntimeError:
        pass

    dirty = git_mod.status_porcelain(repo_root)
    if not dirty:
        git_mod.checkout_force(repo_root, ref)
        return

    only_stem = True
    for line in dirty.splitlines():
        path = line[3:].strip()
        if not path.startswith(".stem/"):
            only_stem = False
            break
    if only_stem:
        git_mod.checkout_force(repo_root, ref)
        return
    # Explicit jump: auto-stash non-.stem changes to proceed
    try:
        git_mod.stash_push(repo_root, "stem jump auto-stash")
    except RuntimeError as exc:
        _die(str(exc))
    git_mod.checkout_force(repo_root, ref)
    print("stashed working changes to complete jump")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
