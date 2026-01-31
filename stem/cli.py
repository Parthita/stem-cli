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
        click.echo("Your nodes.json file may be corrupted. Check for backup files in .git/stem/", err=True)
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
        
        # Check if stem is already initialized
        nodes_file = stem_dir / "nodes.json"
        if nodes_file.exists() and not force:
            click.echo("Stem already initialized")
            if not agent_mode:
                return
        
        # Create stem directory structure
        stem_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize empty state if needed or if forced
        if not nodes_file.exists() or force:
            initial_state = {
                "counter": 0,
                "head": None,
                "nodes": {}
            }
            state.save_state(initial_state)
        
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
                agent.ensure_intent_directory()
                
                if created:
                    click.echo("Agent integration enabled")
                else:
                    if not force:
                        click.echo("AGENT.md exists, use --force to overwrite")
                    
            except Exception as e:
                # Don't fail the entire operation if agent setup fails
                pass
        
        # Success message
        click.echo("Stem initialized")
        
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


def internal_branch(prompt: str, summary: Optional[str] = None) -> bool:
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
        
        # Check if we're in a stem repository
        stem_dir = Path(current_dir) / ".git" / "stem"
        if not stem_dir.exists():
            click.echo("Error: Not in a stem repository. Run 'stem create' first.", err=True)
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
        
        # Generate summary BEFORE committing - prefer agent summary over git diff (Requirement 4.5, 1.4)
        if summary:
            # Use agent-provided summary (Requirement 4.4)
            node_summary = summary
        else:
            # Fallback to git diff summary (Requirement 4.5, 5.1, 5.2)
            try:
                # Stage all changes first so we can get diff stat
                git.stage_all_changes()
                
                # Try to use summary module first
                if hasattr(summary_module, 'generate_summary') and callable(getattr(summary_module, 'generate_summary', None)):
                    node_summary = summary_module.generate_summary()
                    if not node_summary or not node_summary.strip():
                        # Fallback to git diff if summary module returns empty
                        node_summary = git.get_staged_diff_stat()
                else:
                    # Get diff stat of staged changes
                    node_summary = git.get_staged_diff_stat()
                
                if not node_summary or not node_summary.strip():
                    node_summary = "No changes detected"
                    
            except Exception as e:
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
        
        # Store metadata in nodes.json (Requirement 1.5)
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
        
        # Update global registry node count
        try:
            current_state = state.load_state()
            node_count = len(current_state["nodes"])
            util.update_repo_node_count(current_dir, node_count)
        except Exception as e:
            # Don't fail the operation if global registry update fails
            pass
        
        # Success message
        click.echo(f"Created node {node_id}")
        
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
            except:
                handle_error(f"Node {validated_node_id} does not exist. Use 'stem list' to see available nodes.")
            return
        
        # Check if we're already on this node
        if current_head == validated_node_id:
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
        
        click.echo(f"Jumping to node {validated_node_id}: {node_data['prompt']}")
        
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
        except Exception as e:
            # Don't fail the operation if head update fails, just warn
            pass
        
        # Show current node info
        summary = node_data.get('summary', 'No summary')
        summary_line = summary.split('\n')[0]  # First line only
        if len(summary_line) > 60:
            summary_line = summary_line[:57] + "..."
        
        click.echo(f"Now on node {validated_node_id}: {summary_line}")
        
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


@main.command()
@click.option('--verbose', '-v', is_flag=True, help='Show detailed node information')
def list(verbose: bool = False) -> None:
    """Display all nodes in current repository.
    
    Shows a list of all nodes with their IDs, prompts, and summaries.
    Use --verbose for additional details like parent relationships.
    
    Examples:
    
    \b
    stem list           # Basic node listing
    stem list --verbose # Detailed node information
    """
    try:
        from . import state
        
        current_dir = os.getcwd()
        
        # Check if we're in a stem repository
        stem_dir = Path(current_dir) / ".git" / "stem"
        if not stem_dir.exists():
            handle_error("Not in a stem repository. Run 'stem create' first.")
        
        # Load current state
        current_state = state.load_state()
        nodes = current_state["nodes"]
        current_head = current_state["head"]
        
        if not nodes:
            click.echo("No nodes found")
            return
        
        # Sort nodes by ID for consistent display
        sorted_nodes = sorted(nodes.items(), key=lambda x: x[0])
        
        for node_id, node_data in sorted_nodes:
            # Mark current head with indicator
            head_indicator = " <- HEAD" if node_id == current_head else ""
            
            # Basic display
            click.echo(f"{node_id}: {node_data['prompt']}{head_indicator}")
            
            if verbose:
                # Show parent relationship
                parent = node_data.get('parent')
                parent_info = f" (parent: {parent})" if parent else " (root)"
                click.echo(f"     Parent{parent_info}")
                
                # Show branch reference
                ref = node_data.get('ref', '')
                if ref.startswith('refs/heads/'):
                    branch_name = ref[11:]  # Remove 'refs/heads/'
                    click.echo(f"     Branch: {branch_name}")
                
                # Show summary (truncated if too long)
                summary = node_data.get('summary', 'No summary')
                if len(summary) > 80:
                    summary = summary[:77] + "..."
                # Replace newlines with spaces for compact display
                summary = summary.replace('\n', ' ')
                click.echo(f"     Summary: {summary}")
            else:
                # Show compact summary
                summary = node_data.get('summary', 'No summary')
                # Take first line only for compact view
                summary_line = summary.split('\n')[0]
                if len(summary_line) > 60:
                    summary_line = summary_line[:57] + "..."
                click.echo(f"     {summary_line}")
        
        # Show total count
        click.echo(f"Total: {len(nodes)} node{'s' if len(nodes) != 1 else ''}")
        
    except Exception as e:
        handle_error(f"Failed to list nodes: {e}")


@main.command()
@click.option('--timeout', '-t', default=3, type=int, 
              help='Idle timeout in seconds before auto-commit (default: 3)')
def watch(timeout: int = 3) -> None:
    """Start foreground filesystem watcher.
    
    Monitors filesystem changes and automatically commits them after the
    specified idle timeout. Only works when nodes exist - will not create
    nodes automatically.
    
    Examples:
    
    \b
    stem watch           # Watch with 3-second timeout
    stem watch -t 5      # Watch with 5-second timeout
    
    Press Ctrl+C to stop watching.
    """
    try:
        if timeout < 1:
            raise click.BadParameter("Timeout must be at least 1 second")
        
        from . import watcher, state
        
        current_dir = os.getcwd()
        
        # Check if we're in a stem repository
        stem_dir = Path(current_dir) / ".git" / "stem"
        if not stem_dir.exists():
            handle_error("Not in a stem repository. Run 'stem create' first.")
        
        # Check if any nodes exist (optional warning)
        current_state = state.load_state()
        if not current_state["nodes"]:
            click.echo("No nodes exist yet")
        
        # Start the filesystem watcher
        click.echo(f"Starting filesystem watcher (timeout: {timeout}s)")
        
        try:
            watcher.start_watching(current_dir, timeout)
        except KeyboardInterrupt:
            click.echo("Filesystem watcher stopped")
        except Exception as e:
            handle_error(f"Filesystem watcher failed: {e}")
            
    except Exception as e:
        handle_error(f"Failed to start filesystem watcher: {e}")


@main.command('global')
@click.option('--repo', '-r', help='Show details for specific repository path')
def global_view(repo: Optional[str] = None) -> None:
    """Show global repository view.
    
    Displays all stem repositories and their nodes from the global registry.
    This is a read-only view - use 'cd' to navigate to a repository for mutations.
    
    Examples:
    
    \b
    stem global                    # Show all repositories
    stem global --repo /path/to/repo  # Show specific repository
    """
    try:
        from . import util, state
        
        # Load global registry
        try:
            registry = util.get_global_registry()
        except Exception as e:
            handle_error(f"Failed to load global registry: {e}")
        
        if not registry.repos:
            click.echo("No stem repositories found.")
            click.echo("Initialize a repository with: stem create")
            return
        
        if repo:
            # Show specific repository details
            repo_path = os.path.abspath(repo)
            if repo_path not in registry.repos:
                handle_error(f"Repository not found in global registry: {repo_path}")
            
            repo_info = registry.repos[repo_path]
            click.echo(f"Repository: {repo_info.name}")
            click.echo(f"Path: {repo_info.path}")
            click.echo(f"Last accessed: {repo_info.last_accessed.strftime('%Y-%m-%d %H:%M:%S')}")
            click.echo(f"Node count: {repo_info.node_count}")
            click.echo()
            
            # Try to load and display nodes from this repository
            try:
                # Temporarily change to the repo directory to load its state
                original_cwd = os.getcwd()
                os.chdir(repo_path)
                
                try:
                    repo_state = state.load_state()
                    nodes = repo_state["nodes"]
                    current_head = repo_state["head"]
                    
                    if nodes:
                        click.echo("Nodes:")
                        sorted_nodes = sorted(nodes.items(), key=lambda x: x[0])
                        for node_id, node_data in sorted_nodes:
                            head_indicator = " ← HEAD" if node_id == current_head else ""
                            click.echo(f"  {node_id}: {node_data['prompt']}{head_indicator}")
                            
                            # Show compact summary
                            summary = node_data.get('summary', 'No summary')
                            summary_line = summary.split('\n')[0]
                            if len(summary_line) > 60:
                                summary_line = summary_line[:57] + "..."
                            click.echo(f"       {summary_line}")
                    else:
                        click.echo("No nodes in this repository.")
                        
                finally:
                    os.chdir(original_cwd)
                    
            except Exception as e:
                click.echo(f"Warning: Could not load repository details: {e}")
        
        else:
            # Show all repositories
            click.echo("Global stem repositories:")
            
            # Sort repositories by last accessed (most recent first)
            sorted_repos = sorted(
                registry.repos.items(), 
                key=lambda x: x[1].last_accessed, 
                reverse=True
            )
            
            for repo_path, repo_info in sorted_repos:
                click.echo(f"{repo_info.name} ({repo_info.node_count} nodes)")
                click.echo(f"  {repo_path}")
            
            click.echo(f"Total: {len(registry.repos)} repositor{'ies' if len(registry.repos) != 1 else 'y'}")
            
    except Exception as e:
        handle_error(f"Failed to show global view: {e}")


@main.command()
@click.option('--fix', is_flag=True, help='Attempt to fix detected issues automatically')
def doctor() -> None:
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
            current_state = state.load_state()
            validation_result = state._validate_state_detailed(current_state)
            
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
                        nodes_file = stem_dir / "nodes.json"
                        repaired_state = state._attempt_state_repair(nodes_file)
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