# stem

## What problem this solves

During exploratory coding, refactoring, and AI-assisted development, developers frequently lose track of *why* they made changes. Git tracks what changed and when, but the reasoning behind decisions often gets lost in commit messages that are written after the fact.

This becomes particularly problematic when:
- Experimenting with different approaches and needing to backtrack
- Working with AI agents that make rapid changes
- Exploring unfamiliar codebases where context switching is expensive
- Conducting research or learning where the journey matters as much as the destination

stem addresses this by requiring explicit intent declaration before making changes, creating a parallel layer of intentional checkpoints alongside your Git history.

stem is not a Git replacement. It works with Git to add a layer of intentional decision tracking.

## Core idea

stem introduces **intent-driven checkpoints** called **nodes**. Each node represents a deliberate decision point in your development process.

A **node** contains:
- An explicit prompt explaining WHY you're making changes
- A snapshot of your working tree at that moment
- A mechanical summary of WHAT actually changed
- A unique identifier for navigation

Intent must be explicit because inference is unsafe. stem never guesses why you made changes - you must declare your reasoning before creating each checkpoint. This forces clarity of thought and preserves decision context.

## Non-goals (important)

stem does NOT:
- Replace Git or abstract away Git concepts
- Guess or infer your intent from code changes
- Automatically create branches when files change without explicit intent
- Allow AI agents to rewrite or modify your development history
- Provide merge conflict resolution or advanced Git workflows
- Work without Git (Git is a hard requirement)

stem is a complementary tool that adds intentional structure to your existing Git workflow.

## How stem works (mental model)

1. **Initialize**: `stem create` sets up stem metadata in your existing Git repository
2. **Declare intent**: `stem branch "reason for changes"` creates a new node with your explicit reasoning
3. **Make changes**: Edit your code as normal
4. **Snapshot**: stem commits your changes with the declared intent
5. **Navigate**: `stem jump 001` switches between different decision points
6. **Fork**: Create new nodes from any previous state to explore alternatives

Each node is backed by a Git branch following the naming convention `stem/<user>/<id>-<slug>`.
Metadata is stored in `.git/stem/stem.db` (SQLite) for fast lookups at scale.

## Installation

Requires Git and Python 3.8+.

### From source (current method)

```bash
git clone https://github.com/Parthita/stem-cli.git
cd stem-cli
pipx install .
```

Or with pip:
```bash
pip install .
```

### From PyPI (coming soon)

```bash
pipx install stem-cli
```

Verify installation:
```bash
stem --help
```

## Basic usage

```bash
# Initialize stem in your Git repository
stem create

# Declare intent and create a checkpoint
stem branch "add user authentication"
# Creates node 001, stages all changes, commits with intent

# List nodes (subtree by default, paginated)
stem list

# List full tree
stem list --all

# List a specific subtree
stem list --root 005

# Open read-only TUI for large histories
stem tui

# Navigate to a previous node
stem jump 001
# Checks out the Git branch for node 001

# Continue from any node
stem branch "try different approach"
# Creates node 002 from current state

# Start filesystem watcher for auto-commits
stem watch
# Monitors changes and auto-commits to current node
```

Each `stem branch` command creates exactly one Git commit with your declared intent. The working tree is snapshotted as-is when you declare intent.

## Working with AI agents (optional)

stem integrates with AI agents through explicit intent files and auto-branching only after changes occur:

### Setup (One Command)
```bash
stem create --agent  # Sets up agent mode and starts background watcher
```

This single command:
- Creates or appends to `AGENT.md` and `AGENTS.md` with integration rules (preserves existing content)
- Writes strict prompt instructions to `.git/stem/context/agent_prompt.txt`
- Sets up intent directory structure
- Starts filesystem watcher in background automatically

### Agent Workflow

When a user gives an agent a prompt like "add a login form", the agent should:

1. **Write intent JSON** to `.git/stem/intent/next.json`:
   ```json
   {
     "prompt": "add login form to homepage",
     "summary": "Added LoginForm component with email/password fields"
   }
   ```

2. **Make code changes** as requested

3. **System automatically creates node** after changes are detected and idle
4. **After any `stem jump`**, agent reads `.git/stem/context/current.json` to restore context

### Background Watcher Management

```bash
# Check watcher status
stem watch-status

# Stop background watcher
stem watch-stop <PID>

# Start additional background watcher
stem watch --background
```

### Usage Options

**Automatic mode** (default with `--agent`):
- Background watcher runs automatically
- Agent writes intent JSON and makes changes
- System automatically creates nodes
- Terminal stays free for manual commands

**Manual mode**:
- Use `stem branch "prompt"` manually when ready
- Full control over when nodes are created
- Works alongside automatic mode

### Key Benefits

- **Non-blocking**: Background watcher doesn't block terminal
- **Automatic startup**: `stem create --agent` starts watcher automatically
- **Preserves existing content**: Won't overwrite your existing agent instructions
- **Dual workflow**: Both automatic and manual branching available
- **Process management**: Easy start/stop/status commands for background watcher

The agent only writes the intent file and makes code changes. The background watcher handles branching automatically while keeping your terminal available for manual commands.

If you need a copy-paste system prompt for agents:
```bash
stem agent-prompt
```

### Intent Utilities
```bash
stem intent-list          # Show pending intents
stem intent-list --all    # Show all intents
stem intent-show 12       # Show intent details
```

## Safety and guarantees

stem maintains these invariants:
- One declared intent creates exactly one snapshot (Git commit)
- Git remains the source of truth for all code and history
- No automatic history rewriting or modification
- State corruption fails loudly rather than silently
- All operations are reversible through standard Git commands

If an agent writes intent but no code changes follow, the node is invalidated and recorded for inspection.

Your Git repository remains fully functional with or without stem. Removing stem leaves behind only additional Git branches and metadata files.

## Who this tool is for

stem is designed for developers who:
- Engage in exploratory coding or research
- Work on complex refactoring projects
- Collaborate with AI agents on code changes
- Need to maintain context during frequent context switching
- Value explicit decision tracking over implicit commit messages
- Want to experiment with different approaches while preserving decision history

## Who this tool is not for

stem may not be useful if you:
- Prefer linear, single-branch development workflows
- Want automation without explicit intent declaration
- Are looking for Git abstraction or simplification
- Need advanced Git workflow features (merging, rebasing, etc.)
- Work primarily on small, straightforward changes
- Prefer implicit documentation over explicit intent tracking

## Status

This is a v1 tool under active development. It has been tested across platforms and includes comprehensive error handling, but you should use it cautiously on important projects.

The core functionality is stable, but the interface and features may evolve based on user feedback. We recommend trying stem on a small repository first to understand its workflow and determine if it fits your development style.

Contributions, bug reports, and feedback are welcome. The tool is designed to be a thoughtful addition to your development toolkit rather than a replacement for existing workflows.
