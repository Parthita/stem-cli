# stem

stem is a post-hoc, feature-led exploratory history system layered on top of Git. It is designed for long, iterative, AI-assisted coding sessions where intermediate states are easy to lose and unsafe exploration can derail work. Git remains the source of truth for code and history; stem adds explicit, append-only metadata and a strict workflow for features and revisions.

stem is not intent-led. It never infers intent from code changes and never auto-branches on file changes. All actions are triggered only by explicit commands.

---

## Table of Contents

- Overview
- Core Concepts
- Non-Negotiable Invariants
- Quick Start
- CLI Commands
- Agent Workflow (JSON Transport)
- Storage and Data Model
- Git Orchestration
- Output Style
- TUI (Planned)
- Known Bugs
- Non-goals

---

## Overview

stem solves:
- Losing track of useful intermediate states
- Unsafe exploration during refactors or AI coding
- Poor visibility of feature evolution
- Navigating large exploratory histories

stem does not solve:
- Decision causality
- Merge/rebase abstraction
- Automatic intent detection
- Version control replacement

---

## Core Concepts

- **Branch (Feature)**
  - A post-hoc labeled exploration direction
  - Maps to a Git branch: `stem/<user>/<branch_id>-<slug>`

- **Leaf (Revision)**
  - A saved revision on a branch
  - Linear and immutable
  - Maps to a Git commit on the feature branch

Branches fork. Leaves do not.

---

## Non-Negotiable Invariants

1. Git is the source of truth for code and history
2. stem never infers intent from code changes
3. stem never auto-branches on file changes
4. All branching and saving is triggered only by explicit user commands
5. Agents are helpers, never authoritative
6. Agent misbehavior must not corrupt Git or stem state
7. History is append-only, inspectable, replayable
8. Must scale to 10,000+ branches and 50,000+ leaves
9. CLI must remain usable without the TUI
10. stem is not a Git replacement

---

## Quick Start

### 1) Initialize in a repo

```
stem create
```

### 2) Initialize for agent usage

```
stem create --agent
```

This creates:
- `stem.md` (agent protocol)
- `.stem/agent/branch.json`
- `.stem/agent/leaf.json`

---

## CLI Commands

### `stem create`
- Initializes stem in the current directory
- Initializes Git if missing
- Creates `.stem/` metadata storage
- Registers repo in the global registry

### `stem create --agent`
- Runs `stem create`
- Writes `stem.md`
- Writes `.stem/agent/branch.json` and `.stem/agent/leaf.json`
- Prints bootstrap prompt for agent

### `stem branch : <prompt>`
- Creates a new feature branch
- Creates the first leaf

### `stem update : <prompt>`
- Saves a new leaf on the current branch

### `stem update branch : <prompt>`
- Saves a final leaf on the current branch
- Starts a new branch + first leaf

### `stem jump`
- `stem jump <branch_id>` -> jump to latest leaf on branch
- `stem jump head <branch_id>` -> jump to first leaf
- `stem jump <branch_id> <leaf_id>` -> jump to specific leaf

### `stem list`
- Compact summary of branches and leaves

### `stem status`
- Queue length
- Watcher status
- Last executed command

### `stem watch`
- `stem watch --daemon` run background watcher
- `stem watch --stop` stop watcher

---

## Agent Workflow (JSON Transport)

When the user types a stem command inside an agent, the agent does the coding work, then edits one of these existing files:
- `.stem/agent/branch.json` for `stem branch`
- `.stem/agent/leaf.json` for `stem update` and `stem update branch`

The system auto-fills internal fields; the agent must not add hidden fields.

### stem branch
1. Do the work first.
2. Fill `prompt` and `summary` in `branch.json`.
3. Save the file.

### stem update
1. Finish OLD work.
2. Fill `old_prompt` and `old_summary` in `leaf.json`.
3. Save the file.
4. Only then start NEW work.

### stem update branch
1. Finish OLD work.
2. Fill `old_prompt` and `old_summary` in `leaf.json`.
3. Save the file.
4. Do NEW work.
5. Fill `prompt` and `summary` in `branch.json`.
6. Save the file.

---

## Storage and Data Model

- `.stem/stem.db` — repo-local SQLite metadata
- `.stem/agent/` — JSON files edited by agents
- `~/.stem/registry.db` — global repo registry

SQLite supports:
- O(1) lookup
- pagination
- search
- lazy traversal for TUI

Internal metadata:
- `current_branch_id`
- `branch_count`

---

## Git Orchestration

### Branch
- `git checkout -b stem/<user>/<branch_id>-<slug>`
- `git add -A`
- `git commit --allow-empty -m "stem leaf <leaf_id>: <prompt>"`

### Update
- `git add -A`
- `git commit --allow-empty -m "stem leaf <leaf_id>: <prompt>"`

### Jump
- `git checkout <branch>` or `git checkout <commit>`
- auto-stash when non-.stem changes exist

---

## Output Style

- Short, skimmable, one screen
- No verbose dumps

---

## TUI (Planned)

- Read-only navigation for large histories
- Keyboard-first, calm layout
- Lazy loading
- Clear visual tree

---

## Known Bugs (Current)

- `update` does not always change node after jump
- leaf can be duplicated if branching again after jump
- jump edge cases still need handling

---

## Non-goals

- Replace Git
- Infer intent from code or diffs
- Auto-branch from file changes
- Hide or reinterpret Git semantics
- Treat agent output as authoritative

---

## Notes

- `.stem/` is automatically added to `.gitignore`.
- The CLI is usable without the TUI.
