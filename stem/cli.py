"""
CLI Layer - Command orchestration and user interface.

Handles command line argument parsing, user input validation,
and coordinates operations across other components.
"""

import sys
import os
from pathlib import Path
from typing import Any, Optional
import click
from . import agent


def handle_error(message: str, exit_code: int = 1) -> None:
    """Handle errors with consistent formatting and exit codes."""
    click.echo(f"Error: {message}", err=True)
    sys.exit(exit_code)


def handle_git_error(e: Exception) -> None:
    """Handle Git-specific errors with appropriate recovery suggestions."""
    from .git import (GitError, GitBranchError, GitCommitError, GitCheckoutError, 
                      GitRepositoryError, suggest_detached_head_recovery, 
                      suggest_missing_branch_recovery)
    
    if isinstance(e, GitRepositoryError):
        if "detached HEAD" in str(e):
            click.echo("Error: Repository is in detached HEAD state", err=True)
            click.echo(suggest_detached_head_recovery(), err=True)
        else:
            click.echo(f"Error: {e}", err=True)
    elif isinstance(e, GitBranchError):
        if "does not exist" in str(e):
            click.echo(f"Error: {e}", err=True)
        else:
            click.echo(f"Error: {e}", err=True)
    elif isinstance(e, GitCheckoutError):
        click.echo(f"Error: {e}", err=True)
        click.echo("Tip: Commit or stash your changes before switching branches", err=True)
    elif isinstance(e, GitCommitError):
        click.echo(f"Error: {e}", err=True)
    else:
        click.echo(f"Error: {e}", err=True)
    
    sys.exit(1)


def handle_state_error(e: Exception) -> None:
    """Handle state-specific errors with appropriate recovery suggestions."""
    from .state import StateError, StateCorruptionError, StateValidationError, suggest_orphan_cleanup
    
    if isinstance(e, StateCorruptionError):
        click.echo(f"Error: State corruption detected - {e}", err=True)
        click.echo("Your stem.db file may be corrupted. Check .git/stem/ for backups.", err=True)
    elif isinstance(e, StateValidationError):
        click.echo(f"Error: State validation failed - {e}", err=True)
        click.echo("The stem metadata is invalid. Try running 'stem create --force' to reset", err=True)
    else:
        click.echo(f"Error: {e}", err=True)
    
    sys.exit(1)


def validate_node_id(node_id: str) -> str:
    """Validate node ID format (001, 002, etc.)."""
    if not node_id.isdigit() or len(node_id) != 3:
        raise click.BadParameter(
            "Node ID must be a 3-digit number (e.g., 001, 002, 003)"
        )
    return node_id


def validate_prompt(prompt: str) -> str:
    """Validate prompt is not empty and reasonable length."""
    if not prompt or not prompt.strip():
        raise click.BadParameter("Prompt cannot be empty")
    
    if len(prompt.strip()) > 200:
        raise click.BadParameter("Prompt must be 200 characters or less")
    
    return prompt.strip()


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="stem")
@click.option('--help', '-h', is_flag=True, help='Show this message and exit.')
@click.pass_context
def main(ctx: click.Context, help: bool) -> None:
    """Stem CLI - Intent-driven checkpoint system for code exploration.
    
    Stem provides a Git-based node system for tracking intentional checkpoints
    during code exploration. Each node represents an explicit decision point
    with a clear prompt (WHY) and mechanical summary (WHAT).
    
    Common workflow:
    
    \b
    1. stem create          # Initialize stem in current directory
    2. stem branch "reason" # Create checkpoint with intent
    3. stem list            # View all nodes
    4. stem jump 002        # Navigate to specific node
    
    For more information on any command, use: stem COMMAND --help
    """
    if ctx.invoked_subcommand is None:
        if help:
            click.echo(ctx.get_help())
        else:
            # Show help by default when no command is provided
            click.echo(ctx.get_help())
            ctx.exit(0)


@main.command()
@click.option('--agent', 'agent_mode', is_flag=True, 
              help='Enable agent integration mode with AGENT.md creation')
@click.option('--force', is_flag=True, 
              help='Force overwrite existing stem metadata and AGENT.md')
def create(agent_mode: bool = False, force: bool = False) -> None:
    """Initialize stem in current directory.
    
    Creates stem metadata structure and optionally sets up agent integration.
    Will initialize Git repository if one doesn't exist.
    
    Examples:
    
    \b
    stem create              # Basic initialization
    stem create --agent      # Initialize with agent integration
    stem create --force      # Overwrite existing setup
    """
    try:
        from . import git, state, util
        
        current_dir = os.getcwd()
        
        # Step 1: Initialize Git repository if missing (Requirement 2.1)
        try:
            git.init_repo(current_dir)
        except Exception as e:
            handle_error(f"Failed to initialize Git repository: {e}")
        
        # Step 2: Initialize stem metadata in .git/stem/ (Requirement 2.2)
        stem_dir = Path(current_dir) / ".git" / "stem"
        db_file = stem_dir / "stem.db"
        
        # Check if stem is already initialized
        if db_file.exists() and not force:
            click.echo("Stem already initialized")
            if not agent_mode:
                return
        
        # Create stem directory structure
        stem_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        state.ensure_db()
        
        # Step 3: Register repository globally (Requirement 2.3, 6.1)
        try:
            util.register_repo_globally(current_dir)
        except Exception as e:
            # Don't fail the entire operation if global registration fails
            pass
        
        # Step 4: Handle agent mode setup if requested
        if agent_mode:
            try:
                created = agent.create_agent_md(force=force)
                agent.create_agents_md(force=force)
                agent.ensure_intent_directory()
                agent.write_agent_prompt_file()
                
                if created:
                    click.echo("Agent integration enabled")
                else:
                    if not force:
                        click.echo("AGENT.md exists, use --force to overwrite")

                click.echo("Agent prompt written to .git/stem/context/agent_prompt.txt")
                    
            except Exception as e:
                # Don't fail the entire operation if agent setup fails
                pass
        
        # Success message
        click.echo("Stem initialized")
        
        # Provide instructions for agent mode
        if agent_mode:
            click.echo("")
            click.echo("Agent mode ready. Starting background watcher...")
            
            # Auto-start background watcher for agent mode
            try:
                from . import watcher
                pid = watcher.start_background_watcher(current_dir, 3)
                if pid > 0:
                    click.echo(f"Filesystem watcher started in background (PID: {pid})")
                    click.echo(f"Use 'stem watch-stop {pid}' to stop")
                    click.echo("")
                    click.echo("Agent integration ready:")
                    click.echo("  - Agents can write intent JSON")
                    click.echo("  - Nodes auto-create after code changes complete")
                    click.echo("  - Manual 'stem branch' always available")
                else:
                    click.echo("Warning: Could not start background watcher")
                    click.echo("Use 'stem watch --background' to start manually")
            except Exception as e:
                click.echo(f"Warning: Could not start background watcher: {e}")
                click.echo("Use 'stem watch --background' to start manually")
        
    except Exception as e:
        handle_error(f"Failed to initialize stem: {e}")


@main.command()
@click.argument('prompt')
def branch(prompt: str) -> None:
    """Create new node with given prompt.
    
    Creates a new checkpoint node with the specified prompt explaining WHY
    this checkpoint is being created. The system will snapshot the current
    working tree and generate a mechanical summary of changes.
    
    Examples:
    
    \b
    stem branch "add user authentication"
    stem branch "fix memory leak in parser"
    stem branch "refactor database layer"
    
    The prompt should be descriptive and explain the intent behind the changes.
    """
    try:
        # Validate prompt manually since callback isn't working as expected
        validated_prompt = validate_prompt(prompt)
        
        # Call internal implementation
        success = internal_branch(validated_prompt)
        if not success:
            handle_error("Failed to create branch")
        
    except click.BadParameter as e:
        handle_error(str(e))
    except Exception as e:
        # Use specific error handlers
        from .git import GitError
        from .state import StateError
        
        if isinstance(e, GitError):
            handle_git_error(e)
        elif isinstance(e, StateError):
            handle_state_error(e)
        else:
            handle_error(f"Failed to create branch: {e}")


@main.command('intent-suggest')
@click.argument('prompt', required=False)
@click.option('--summary', '-s', help='Optional summary of intended changes')
@click.option('--from-file', is_flag=True, help='Read intent from .git/stem/intent/next.json')
def intent_suggest(prompt: Optional[str] = None, summary: Optional[str] = None, from_file: bool = False) -> None:
    """Record an agent intent suggestion (requires confirmation)."""
    try:
        from . import state, agent as agent_module

        if from_file:
            if prompt:
                handle_error("Do not pass prompt when using --from-file")
            intent = agent_module.read_agent_intent()
            if intent is None:
                handle_error("No pending intent file found")
            if summary:
                handle_error("Do not pass --summary when using --from-file")
            prompt = intent.prompt
            summary = intent.summary
            source = "agent_file"
        else:
            if not prompt:
                handle_error("Prompt is required unless --from-file is used")
            source = "cli"

        intent_id = state.suggest_intent(prompt, summary, source=source)
        click.echo(f"Recorded intent suggestion {intent_id}: {prompt}")
    except Exception as e:
        handle_error(f"Failed to suggest intent: {e}")


@main.command('intent-confirm')
@click.argument('intent_id', required=False, type=int)
def intent_confirm(intent_id: Optional[int] = None) -> None:
    """Confirm a pending agent intent and create a node."""
    try:
        from . import state

        pending = state.get_pending_intent(intent_id)
        if not pending or pending.get("status") != "pending":
            handle_error("No pending intent found" if intent_id is None else f"Intent {intent_id} is not pending")

        confirmed = state.confirm_intent(int(pending["id"]))
        prompt = confirmed["prompt"]
        summary = confirmed.get("summary")

        success = internal_branch(prompt, summary, intent_id=int(pending["id"]))
        if not success:
            state.log_anomaly(
                "intent_confirm_failed",
                {"intent_id": int(pending["id"]), "prompt": prompt},
                node_id=None,
            )
            handle_error("Failed to create node from confirmed intent")
    except Exception as e:
        handle_error(f"Failed to confirm intent: {e}")


@main.command('intent-reject')
@click.argument('intent_id', required=False, type=int)
@click.option('--reason', default="rejected_by_user", help='Reason for rejection')
def intent_reject(intent_id: Optional[int] = None, reason: str = "rejected_by_user") -> None:
    """Reject a pending agent intent."""
    try:
        from . import state

        pending = state.get_pending_intent(intent_id)
        if not pending or pending.get("status") != "pending":
            handle_error("No pending intent found" if intent_id is None else f"Intent {intent_id} is not pending")

        state.reject_intent(int(pending["id"]), reason=reason)
        click.echo(f"Rejected intent {pending['id']}: {pending['prompt']}")
    except Exception as e:
        handle_error(f"Failed to reject intent: {e}")


@main.command('intent-list')
@click.option('--all', 'include_all', is_flag=True, help='Show all intents (not just pending)')
def intent_list(include_all: bool = False) -> None:
    """List agent intents."""
    try:
        from . import state

        state.ensure_db()
        conn = state._connect()  # Internal use for listing
        try:
            if include_all:
                rows = conn.execute(
                    "SELECT id, prompt, status, source, created_at FROM agent_intents "
                    "ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, prompt, status, source, created_at FROM agent_intents "
                    "WHERE status = 'pending' ORDER BY created_at DESC"
                ).fetchall()
        finally:
            conn.close()

        if not rows:
            click.echo("No intents found.")
            return

        for row in rows:
            click.echo(f"{row['id']}: {row['prompt']} [{row['status']}] ({row['source']}) {row['created_at']}")
    except Exception as e:
        handle_error(f"Failed to list intents: {e}")


@main.command('intent-show')
@click.argument('intent_id', type=int)
def intent_show(intent_id: int) -> None:
    """Show details for a specific intent."""
    try:
        from . import state

        state.ensure_db()
        conn = state._connect()
        try:
            row = conn.execute(
                "SELECT id, prompt, summary, status, source, created_at, updated_at, node_id "
                "FROM agent_intents WHERE id = ?",
                (intent_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            handle_error(f"Intent {intent_id} not found")

        click.echo(f"ID: {row['id']}")
        click.echo(f"Status: {row['status']}")
        click.echo(f"Source: {row['source']}")
        click.echo(f"Created: {row['created_at']}")
        click.echo(f"Updated: {row['updated_at']}")
        click.echo(f"Node: {row['node_id'] or 'None'}")
        click.echo(f"Prompt: {row['prompt']}")
        click.echo(f"Summary: {row['summary'] or ''}")
    except Exception as e:
        handle_error(f"Failed to show intent: {e}")


@main.command('agent-prompt')
@click.option('--write', is_flag=True, help='Write prompt to .git/stem/context/agent_prompt.txt')
def agent_prompt(write: bool = False) -> None:
    """Print agent system prompt instructions."""
    try:
        from . import agent as agent_module

        if write:
            path = agent_module.write_agent_prompt_file()
            click.echo(f"Wrote agent prompt to {path}")
        click.echo(agent_module.get_agent_prompt_text())
    except Exception as e:
        handle_error(f"Failed to print agent prompt: {e}")


def internal_branch(prompt: str, summary: Optional[str] = None, intent_id: Optional[int] = None) -> bool:
    """Internal function to create a branch, used by agent integration.
    
    This function performs the same operations as the branch command
    but can be called programmatically by the agent integration system.
    It handles agent-provided summaries with preference over git diff.
    
    Args:
        prompt: The prompt for the new node
        summary: Optional agent-provided summary to use instead of git diff
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Import here to avoid circular imports
        from . import git, state, summary as summary_module, util
        
        current_dir = os.getcwd()
        
        # Check if we're in a Git repository, initialize if not
        try:
            # First check if git is available and if we're in a git repo
            if not git._is_git_repo(current_dir):
                click.echo("Initializing Git repository...")
                git.init_repo(current_dir)
                # Verify initialization worked
                if not git._is_git_repo(current_dir):
                    click.echo("Error: Git repository initialization failed", err=True)
                    return False
        except git.GitError as e:
            if "Git is not installed" in str(e):
                click.echo("Error: Git is not installed or not found in PATH", err=True)
                click.echo("Please install Git and try again", err=True)
                return False
            else:
                click.echo(f"Error: Failed to initialize Git repository: {e}", err=True)
                return False
        except Exception as e:
            click.echo(f"Error: Failed to initialize Git repository: {e}", err=True)
            return False
        
        # Check if we're in a stem repository, initialize if not
        stem_dir = Path(current_dir) / ".git" / "stem"
        if not stem_dir.exists():
            click.echo("Initializing stem metadata...")
            try:
                stem_dir.mkdir(parents=True, exist_ok=True)
                state.ensure_db()
                
                # Register repository globally (non-fatal)
                try:
                    util.register_repo_globally(current_dir)
                except Exception as e:
                    click.echo(f"Warning: Failed to register repo globally: {e}", err=True)
                
                click.echo("Stem initialized")
            except Exception as e:
                click.echo(f"Error: Failed to initialize stem: {e}", err=True)
                return False
        
        # Get current head to determine parent (Requirement 1.6)
        current_head = state.get_current_head()
        
        # Generate next node ID (Requirement 1.1)
        node_id = state.get_next_id()
        
        # Create branch name following convention (Requirement 1.2)
        branch_name = git.create_stem_branch_name(node_id, prompt)
        
        click.echo(f"Creating node {node_id}: {prompt}")
        
        # Create and checkout the new branch (Requirement 1.2)
        try:
            git.create_branch(branch_name)
        except Exception as e:
            click.echo(f"Error: Failed to create branch: {e}", err=True)
            return False
        
        # Stage all changes so we can derive diff stat and ensure commits are correct
        diff_stat = ""
        try:
            git.stage_all_changes()
            diff_stat = git.get_staged_diff_stat()
        except Exception:
            diff_stat = ""

        # Generate summary BEFORE committing - prefer agent summary over git diff
        if summary:
            node_summary = summary
        else:
            try:
                if hasattr(summary_module, 'generate_summary') and callable(getattr(summary_module, 'generate_summary', None)):
                    node_summary = summary_module.generate_summary()
                    if not node_summary or not node_summary.strip():
                        node_summary = diff_stat
                else:
                    node_summary = diff_stat

                if not node_summary or not node_summary.strip():
                    node_summary = "No changes detected"
            except Exception:
                node_summary = "Summary generation failed"
        
        # Snapshot working tree into exactly ONE commit (Requirement 1.3)
        try:
            commit_message = f"stem: {prompt}"
            # Use the new function that commits staged changes
            commit_hash = git.commit_staged_changes(commit_message)
        except Exception as e:
            click.echo(f"Error: Failed to commit changes: {e}", err=True)
            # Try to cleanup by going back to previous branch
            try:
                if current_head:
                    # Try to get the branch for current head
                    current_state = state.load_state()
                    if current_head in current_state["nodes"]:
                        current_ref = current_state["nodes"][current_head]["ref"]
                        # Extract branch name from ref (assuming it's a branch)
                        if current_ref.startswith("refs/heads/"):
                            prev_branch = current_ref[11:]  # Remove "refs/heads/"
                            git.checkout_branch(prev_branch)
                else:
                    git.checkout_branch("main")
            except:
                pass  # Ignore cleanup errors
            return False
        
        # Get the commit reference for storage
        commit_ref = f"refs/heads/{branch_name}"
        
        # Store metadata in stem.db (Requirement 1.5)
        try:
            created_node_id = state.create_node(
                prompt=prompt,
                summary=node_summary,
                ref=commit_ref,
                parent=current_head
            )
        except Exception as e:
            click.echo(f"Error: Failed to save node metadata: {e}", err=True)
            return False

        # If this was an agent-confirmed intent, attach and enforce no-change invalidation
        if intent_id is not None:
            try:
                state.attach_intent_to_node(intent_id, created_node_id)
            except Exception:
                pass

            changes_detected = bool(diff_stat.strip())
            if not changes_detected:
                try:
                    state.invalidate_node(created_node_id, "agent_intent_no_changes")
                    state.log_anomaly(
                        "anomaly_no_changes",
                        {"intent_id": intent_id, "node_id": created_node_id},
                        node_id=created_node_id,
                    )
                    click.echo(f"Warning: No changes detected for intent {intent_id}; node {created_node_id} invalidated.")
                except Exception:
                    pass
        
        # Update global registry node count
        try:
            current_state = state.load_state()
            node_count = len(current_state["nodes"])
            util.update_repo_node_count(current_dir, node_count)
        except Exception as e:
            # Don't fail the operation if global registry update fails
            pass
        
        # Success message with context
        from .display import format_node_creation_success
        success_msg = format_node_creation_success(
            node_id, prompt, node_summary, current_head, len(current_state["nodes"])
        )
        click.echo(success_msg)
        
        return True
        
    except Exception as e:
        click.echo(f"Error in internal_branch: {e}", err=True)
        return False


@main.command()
@click.argument('node_id')
def jump(node_id: str) -> None:
    """Switch to specified node.
    
    Safely navigate to the specified node by checking out its Git branch.
    The node ID should be a 3-digit number (001, 002, 003, etc.).
    
    Examples:
    
    \b
    stem jump 001    # Jump to first node
    stem jump 005    # Jump to fifth node
    
    This operation will fail if the working tree is dirty to prevent data loss.
    """
    try:
        # Validate node_id manually since callback isn't working as expected
        validated_node_id = validate_node_id(node_id)
        _perform_jump(validated_node_id)
        
    except click.BadParameter as e:
        handle_error(str(e))
    except Exception as e:
        # Use specific error handlers
        from .git import GitError
        from .state import StateError
        
        if isinstance(e, GitError):
            handle_git_error(e)
        elif isinstance(e, StateError):
            handle_state_error(e)
        else:
            handle_error(f"Failed to jump to node {node_id}: {e}")


def _perform_jump(validated_node_id: str, quiet: bool = False) -> None:
    from . import state, git

    current_dir = os.getcwd()

    # Check if we're in a stem repository
    stem_dir = Path(current_dir) / ".git" / "stem"
    if not stem_dir.exists():
        handle_error("Not in a stem repository. Run 'stem create' first.")

    # Load current state
    current_state = state.load_state()
    nodes = current_state["nodes"]
    current_head = current_state["head"]

    # Check if node exists
    if validated_node_id not in nodes:
        # Check for orphaned nodes and provide helpful suggestions
        try:
            orphan_info = state.detect_orphaned_nodes()
            orphaned_ids = [n['node_id'] for n in orphan_info['orphaned_nodes']]

            if validated_node_id in orphaned_ids:
                click.echo(f"Error: Node {validated_node_id} is orphaned (missing Git branch)", err=True)
                click.echo(state.suggest_orphan_cleanup(), err=True)
            else:
                handle_error(f"Node {validated_node_id} does not exist. Use 'stem list' to see available nodes.")
        except Exception:
            handle_error(f"Node {validated_node_id} does not exist. Use 'stem list' to see available nodes.")
        return

    # Check if we're already on this node
    if current_head == validated_node_id:
        if not quiet:
            click.echo(f"Already on node {validated_node_id}")
        return

    # Check if working tree is clean (Requirement 6.6 - safe navigation)
    if not git.is_repo_clean():
        handle_error("Cannot jump to node: working tree has uncommitted changes. Commit or stash your changes first.")

    # Get the branch reference for the target node
    node_data = nodes[validated_node_id]
    ref = node_data['ref']

    # Extract branch name from reference
    if ref.startswith('refs/heads/'):
        branch_name = ref[11:]  # Remove 'refs/heads/'
    else:
        handle_error(f"Invalid branch reference for node {validated_node_id}: {ref}")

    if not quiet:
        click.echo(f"🚀 Jumping to node {validated_node_id}: {node_data['prompt']}")

    # Perform the checkout
    try:
        git.checkout_branch(branch_name)
    except Exception as e:
        if isinstance(e, git.GitError):
            handle_git_error(e)
        else:
            handle_error(f"Failed to checkout branch {branch_name}: {e}")

    # Update head pointer in state
    try:
        state.update_head(validated_node_id)
    except Exception:
        pass

    # Build read-only context snapshot for agents
    try:
        state.write_context_snapshot(validated_node_id)
    except Exception:
        pass

    if not quiet:
        from .display import format_jump_success
        success_msg = format_jump_success(validated_node_id, node_data, current_head)
        click.echo(success_msg)


@main.command()
@click.option('--verbose', '-v', is_flag=True, help='Show detailed node information')
@click.option('--root', help='Root node ID for subtree view (default: HEAD)')
@click.option('--all', 'include_all_roots', is_flag=True, help='Show all roots (full tree)')
@click.option('--page', type=int, default=1, help='Page number')
@click.option('--page-size', type=int, default=50, help='Nodes per page')
def list(verbose: bool = False, root: Optional[str] = None, include_all_roots: bool = False,
         page: int = 1, page_size: int = 50) -> None:
    """Display all nodes in current repository.
    
    Shows a tree view of all nodes with their relationships and summaries.
    Use --verbose for additional details like parent relationships and branches.
    
    Examples:
    
    \b
    stem list           # Tree view of nodes
    stem list --verbose # Detailed node information with tree
    """
    try:
        from . import state
        from .display import format_node_list
        
        current_dir = os.getcwd()
        
        # Check if we're in a stem repository
        stem_dir = Path(current_dir) / ".git" / "stem"
        if not stem_dir.exists():
            handle_error("Not in a stem repository. Run 'stem create' first.")
        
        # Load current state
        current_state = state.load_state()
        nodes = current_state["nodes"]
        current_head = current_state["head"]

        if root:
            root = validate_node_id(root)
            if root not in nodes:
                handle_error(f"Node {root} does not exist. Use 'stem list --all' to see available nodes.")
        elif not include_all_roots and not current_head:
            include_all_roots = True

        # Use enhanced formatting
        output = format_node_list(
            nodes,
            current_head,
            verbose=verbose,
            root_id=root,
            include_all_roots=include_all_roots,
            page=page,
            page_size=page_size,
        )
        click.echo(output)
        
    except Exception as e:
        handle_error(f"Failed to list nodes: {e}")


@main.command('tui')
def tui() -> None:
    """Launch read-only TUI for browsing and jumping."""
    try:
        from . import state
        try:
            from .tui import run_tui
        except Exception as import_e:
            handle_error(f"TUI unavailable: {import_e}")

        current_state = state.load_state()
        nodes = current_state["nodes"]
        current_head = current_state["head"]

        if not nodes:
            handle_error("No nodes found. Create a node first.")

        selected = run_tui(nodes, current_head)
        if selected:
            _perform_jump(selected, quiet=True)
    except Exception as e:
        handle_error(f"Failed to start TUI: {e}")


@main.command()
@click.option('--timeout', '-t', default=3, type=int, 
              help='Idle timeout in seconds before auto-commit (default: 3)')
@click.option('--background', '-b', is_flag=True,
              help='Run watcher in background (non-blocking)')
def watch(timeout: int = 3, background: bool = False) -> None:
    """Start filesystem watcher.
    
    Monitors filesystem changes and automatically commits to current node
    when changes are detected after an idle period.
    
    Examples:
    
    \b
    stem watch              # Foreground watcher
    stem watch --background # Background watcher
    stem watch -t 5 -b      # Background with 5s timeout
    """
    try:
        from . import state, watcher
        
        current_dir = os.getcwd()
        
        # Validate timeout
        if timeout < 1:
            handle_error("Timeout must be at least 1 second")
        
        # Check if we're in a stem repository
        stem_dir = Path(current_dir) / ".git" / "stem"
        if not stem_dir.exists():
            handle_error("Not in a stem repository. Run 'stem create' first.")
        
        # Check if any nodes exist (optional warning)
        current_state = state.load_state()
        if not current_state["nodes"]:
            click.echo("No nodes exist yet")
        
        if background:
            # Start background watcher
            pid = watcher.start_background_watcher(current_dir, timeout)
            if pid > 0:
                click.echo(f"Filesystem watcher started in background (PID: {pid})")
                click.echo(f"Use 'stem watch-stop {pid}' to stop")
            else:
                handle_error("Failed to start background watcher")
        else:
            # Start foreground watcher
            click.echo(f"Starting filesystem watcher (timeout: {timeout}s)")
            
            try:
                watcher.start_watching(current_dir, timeout)
            except KeyboardInterrupt:
                click.echo("Filesystem watcher stopped")
            except Exception as e:
                handle_error(f"Filesystem watcher failed: {e}")
            
    except Exception as e:
        handle_error(f"Failed to start filesystem watcher: {e}")


@main.command('watch-stop')
@click.argument('pid', type=int)
def watch_stop(pid: int) -> None:
    """Stop background filesystem watcher.
    
    Args:
        pid: Process ID of the watcher to stop
        
    Examples:
    
    \b
    stem watch-stop 12345   # Stop watcher with PID 12345
    """
    try:
        from . import watcher
        
        if watcher.stop_background_watcher(pid):
            click.echo(f"Stopped background watcher (PID: {pid})")
        else:
            click.echo(f"Could not stop watcher (PID: {pid}) - process may not exist")
            
    except Exception as e:
        handle_error(f"Failed to stop watcher: {e}")


@main.command('watch-status')
def watch_status() -> None:
    """Check status of background watchers.
    
    Shows information about running background watcher processes.
    """
    try:
        import psutil
        
        # Find stem watcher processes
        watchers = []
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and len(cmdline) >= 3:
                    if 'python' in cmdline[0] and 'stem.watcher' in ' '.join(cmdline):
                        watchers.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if watchers:
            click.echo("Running background watchers:")
            for pid in watchers:
                click.echo(f"  PID: {pid}")
        else:
            click.echo("No background watchers running")
            
    except ImportError:
        click.echo("Install psutil to check watcher status: pip install psutil")
    except Exception as e:
        handle_error(f"Failed to check watcher status: {e}")


@main.command('global')
@click.option('--repo', '-r', help='Show details for specific repository path')
def global_view(repo: Optional[str] = None) -> None:
    """Show global repository view.
    
    Displays all stem repositories organized by activity with enhanced formatting.
    This is a read-only view - use 'cd' to navigate to a repository for mutations.
    
    Examples:
    
    \b
    stem global                    # Show all repositories with activity grouping
    stem global --repo /path/to/repo  # Show specific repository with tree view
    """
    try:
        from . import util, state
        from .display import format_global_view, format_repository_details
        
        # Load global registry
        try:
            registry = util.get_global_registry()
        except Exception as e:
            handle_error(f"Failed to load global registry: {e}")
        
        if not registry.repos:
            click.echo("📭 No stem repositories found.")
            click.echo("Initialize a repository with: stem create")
            return
        
        if repo:
            # Show specific repository details with tree view
            repo_path = os.path.abspath(repo)
            if repo_path not in registry.repos:
                handle_error(f"Repository not found in global registry: {repo_path}")
            
            repo_info = registry.repos[repo_path]
            
            # Try to load and display nodes from this repository
            try:
                # Temporarily change to the repo directory to load its state
                original_cwd = os.getcwd()
                os.chdir(repo_path)
                
                try:
                    repo_state = state.load_state()
                    nodes = repo_state["nodes"]
                    current_head = repo_state["head"]
                    
                    output = format_repository_details(repo_info, nodes, current_head)
                    click.echo(output)
                        
                finally:
                    os.chdir(original_cwd)
                    
            except Exception as e:
                click.echo(f"⚠️  Warning: Could not load repository details: {e}")
        
        else:
            # Show all repositories with enhanced formatting
            output = format_global_view(registry)
            click.echo(output)
            
    except Exception as e:
        handle_error(f"Failed to show global view: {e}")


@main.command()
@click.option('--fix', is_flag=True, help='Attempt to fix detected issues automatically')
def doctor(fix: bool = False) -> None:
    """Diagnose and optionally fix stem repository issues.
    
    Checks for common problems like corrupted state, missing branches,
    orphaned nodes, and Git repository issues. Use --fix to attempt
    automatic repairs where possible.
    
    Examples:
    
    \b
    stem doctor         # Check for issues
    stem doctor --fix   # Check and attempt to fix issues
    """
    try:
        from . import state, git
        
        current_dir = os.getcwd()
        
        # Check if we're in a stem repository
        stem_dir = Path(current_dir) / ".git" / "stem"
        if not stem_dir.exists():
            handle_error("Not in a stem repository. Run 'stem create' first.")
        
        click.echo("Diagnosing stem repository...")
        
        issues_found = 0
        
        # Check 1: Git repository state
        try:
            if git.is_detached_head():
                click.echo("Warning: Repository is in detached HEAD state")
                issues_found += 1
            else:
                click.echo("Git repository state: OK")
        except Exception as e:
            click.echo(f"Git check failed: {e}")
            issues_found += 1
        
        # Check 2: State file integrity
        click.echo("2. Checking state file integrity...")
        try:
            validation_result = state.validate_state()
            
            if validation_result['valid']:
                click.echo("   ✓ State file is valid")
            else:
                click.echo("   ⚠ State file has validation issues:")
                for error in validation_result['errors']:
                    click.echo(f"     - {error}")
                issues_found += 1
                
                if fix:
                    click.echo("   🔧 Attempting to repair state file...")
                    try:
                        # Legacy nodes.json repair removed; SQLite is authoritative
                        repaired_state = None
                        if repaired_state:
                            click.echo("   ✓ State file repaired successfully")
                        else:
                            click.echo("   ❌ Could not repair state file")
                    except Exception as repair_e:
                        click.echo(f"   ❌ Repair failed: {repair_e}")
                        
        except Exception as e:
            click.echo(f"   ❌ State check failed: {e}")
            issues_found += 1
        
        click.echo()
        
        # Check 3: Missing branches and orphaned nodes
        click.echo("3. Checking for missing branches and orphaned nodes...")
        try:
            orphan_info = state.detect_orphaned_nodes()
            
            if orphan_info['orphan_count'] == 0:
                click.echo("   ✓ All nodes have valid Git branches")
            else:
                click.echo(f"   ⚠ Found {orphan_info['orphan_count']} orphaned nodes")
                for orphan in orphan_info['orphaned_nodes']:
                    click.echo(f"     - Node {orphan['node_id']}: {orphan['prompt']}")
                    click.echo(f"       Missing branch: {orphan['branch_name']}")
                
                click.echo()
                click.echo(state.suggest_orphan_cleanup())
                issues_found += 1
                
        except Exception as e:
            click.echo(f"   ❌ Orphan check failed: {e}")
            issues_found += 1
        
        click.echo()
        
        # Check 4: Working tree cleanliness
        click.echo("4. Checking working tree state...")
        try:
            if git.is_repo_clean():
                click.echo("   ✓ Working tree is clean")
            else:
                click.echo("   ⚠ Working tree has uncommitted changes")
                click.echo("     This may prevent some stem operations")
                click.echo("     Consider committing or stashing changes")
                issues_found += 1
        except Exception as e:
            click.echo(f"   ❌ Working tree check failed: {e}")
            issues_found += 1
        
        click.echo()
        
        # Summary
        if issues_found == 0:
            click.echo("🎉 No issues found! Your stem repository is healthy.")
        else:
            click.echo(f"⚠ Found {issues_found} issue{'s' if issues_found != 1 else ''}")
            if not fix:
                click.echo("Run 'stem doctor --fix' to attempt automatic repairs")
        
    except Exception as e:
        handle_error(f"Doctor check failed: {e}")


if __name__ == '__main__':
    main()
