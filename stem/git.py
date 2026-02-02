"""
Git Layer - All Git repository interactions.

Handles Git repository initialization, branch management, commits,
checkouts, and diff statistics generation.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional
from .util import get_username, create_slug


class GitError(Exception):
    """Exception raised for Git operation failures."""
    pass


class GitBranchError(GitError):
    """Exception raised for Git branch operation failures."""
    pass


class GitCommitError(GitError):
    """Exception raised for Git commit operation failures."""
    pass


class GitCheckoutError(GitError):
    """Exception raised for Git checkout operation failures."""
    pass


class GitRepositoryError(GitError):
    """Exception raised for Git repository state issues."""
    pass


def _run_git_command(args: list[str], cwd: Optional[str] = None, check_output: bool = False) -> str:
    """Run git command and handle errors with detailed error reporting."""
    try:
        if check_output:
            result = subprocess.run(
                ["git"] + args,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        else:
            subprocess.run(
                ["git"] + args,
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True
            )
            return ""
    except subprocess.CalledProcessError as e:
        # Parse stderr for specific error types, also check stdout
        error_msg = e.stderr.strip() if e.stderr else ""
        if not error_msg and e.stdout:
            error_msg = e.stdout.strip()
        if not error_msg:
            error_msg = str(e)
        
        # Handle specific Git error scenarios
        if "not a git repository" in error_msg.lower():
            raise GitRepositoryError(f"Not a Git repository: {cwd or os.getcwd()}")
        
        if "pathspec" in error_msg.lower() and "did not match" in error_msg.lower():
            raise GitBranchError(f"Branch does not exist: {error_msg}")
        
        if "already exists" in error_msg.lower() and "branch" in error_msg.lower():
            raise GitBranchError(f"Branch already exists: {error_msg}")
        
        if "your local changes" in error_msg.lower() and "overwritten" in error_msg.lower():
            raise GitCheckoutError(f"Cannot checkout: working tree has uncommitted changes")
        
        if "nothing to commit" in error_msg.lower() or "working tree clean" in error_msg.lower():
            raise GitCommitError("No changes to commit")
        
        if "detached head" in error_msg.lower():
            raise GitRepositoryError("Repository is in detached HEAD state")
        
        # Generic error with command context
        raise GitError(f"Git command failed: {' '.join(args)}\nError: {error_msg}")
    except FileNotFoundError:
        raise GitError("Git is not installed or not found in PATH")
    except Exception as e:
        raise GitError(f"Unexpected error running git command: {e}")


def init_repo(path: str) -> None:
    """Initialize Git repository when missing."""
    repo_path = Path(path).resolve()
    git_dir = repo_path / ".git"
    
    if git_dir.exists():
        return  # Repository already exists
    
    try:
        _run_git_command(["init"], cwd=str(repo_path))
        
        # Create an initial commit so we can create branches
        # Check if there are any files to commit
        try:
            # Add all files in the directory
            _run_git_command(["add", "."], cwd=str(repo_path))
            
            # Try to create initial commit
            try:
                _run_git_command(["commit", "-m", "Initial commit"], cwd=str(repo_path))
            except GitError:
                # If commit fails (no files), create an empty commit
                _run_git_command(["commit", "--allow-empty", "-m", "Initial commit"], cwd=str(repo_path))
                
        except GitError:
            # If adding files fails, just create an empty commit
            try:
                _run_git_command(["commit", "--allow-empty", "-m", "Initial commit"], cwd=str(repo_path))
            except GitError:
                # If even empty commit fails, that's okay - we'll handle it later
                pass
                
    except GitError as e:
        raise GitError(f"Failed to initialize Git repository at {repo_path}: {e}")


def _is_git_repo(path: str) -> bool:
    """Check if directory is a Git repository."""
    try:
        _run_git_command(["rev-parse", "--git-dir"], cwd=path)
        return True
    except GitError:
        return False


def _validate_repo(path: str) -> None:
    """Validate that path is a Git repository."""
    if not _is_git_repo(path):
        raise GitError(f"Not a Git repository: {path}")


def is_repo_clean() -> bool:
    """Check if working tree is clean."""
    try:
        # First check if we're in a git repository
        if not _is_git_repo(os.getcwd()):
            return True  # Not in a git repo, consider it "clean"
        
        # Check for staged changes
        try:
            _run_git_command(["diff-index", "--quiet", "--cached", "HEAD"])
        except GitError:
            # If this fails, there might be staged changes
            return False
        
        # Check for unstaged changes
        try:
            _run_git_command(["diff-files", "--quiet"])
        except GitError:
            # If this fails, there are unstaged changes
            return False
        
        # Check for untracked files
        try:
            output = _run_git_command(["ls-files", "--others", "--exclude-standard"], check_output=True)
            if len(output.strip()) > 0:
                return False
        except GitError:
            # If this fails, assume there might be untracked files
            return False
        
        return True
        
    except Exception:
        # If any unexpected error occurs, assume dirty to be safe
        return False


def is_detached_head() -> bool:
    """Check if repository is in detached HEAD state."""
    try:
        # First check if we're in a git repository
        if not _is_git_repo(os.getcwd()):
            return False  # Not in a git repo, so not detached HEAD
        
        # Try to get current branch name
        branch = _run_git_command(["branch", "--show-current"], check_output=True)
        return not branch.strip()  # Empty string means detached HEAD
    except GitError:
        # If command fails, assume detached HEAD for safety
        return True


def get_detached_head_info() -> dict:
    """Get information about detached HEAD state for recovery guidance."""
    try:
        # First validate we're in a git repository
        _validate_repo(os.getcwd())
        
        # Get current commit hash
        commit_hash = _run_git_command(["rev-parse", "HEAD"], check_output=True)
        
        # Get commit message
        commit_msg = _run_git_command(["log", "-1", "--pretty=format:%s"], check_output=True)
        
        # Check if this commit is on any stem branches
        try:
            branches_output = _run_git_command(["branch", "--contains", commit_hash], check_output=True)
            branches = [line.strip().lstrip('* ') for line in branches_output.split('\n') if line.strip()]
            stem_branches = [b for b in branches if b.startswith('stem/')]
        except GitError:
            stem_branches = []
            branches = []
        
        return {
            'commit_hash': commit_hash,
            'commit_message': commit_msg,
            'stem_branches': stem_branches,
            'all_branches': branches
        }
    except GitRepositoryError as e:
        raise GitRepositoryError(f"Cannot get detached HEAD information: {e}")
    except GitError as e:
        raise GitRepositoryError(f"Cannot get detached HEAD information: {e}")


def suggest_detached_head_recovery() -> str:
    """Provide recovery suggestions for detached HEAD state."""
    try:
        info = get_detached_head_info()
        
        suggestions = []
        suggestions.append("You are in a detached HEAD state. Here are your options:")
        suggestions.append("")
        
        if info['stem_branches']:
            suggestions.append("✓ This commit is on stem branches:")
            for branch in info['stem_branches']:
                suggestions.append(f"  - {branch}")
            suggestions.append("")
            suggestions.append("To return to a stem branch, run:")
            suggestions.append(f"  git checkout {info['stem_branches'][0]}")
        else:
            suggestions.append("⚠ This commit is not on any stem branches.")
            suggestions.append("")
            suggestions.append("To create a new stem branch from this commit:")
            suggestions.append("  stem branch \"describe your changes\"")
            suggestions.append("")
            suggestions.append("To return to the main branch:")
            suggestions.append("  git checkout main")
        
        suggestions.append("")
        suggestions.append(f"Current commit: {info['commit_hash'][:8]}")
        suggestions.append(f"Message: {info['commit_message']}")
        
        return "\n".join(suggestions)
        
    except Exception as e:
        return f"Cannot provide recovery suggestions: {e}"


def get_current_branch() -> str:
    """Get current Git branch name."""
    try:
        # Try to get current branch name
        branch = _run_git_command(["branch", "--show-current"], check_output=True)
        if branch:
            return branch
        
        # If no branch name (detached HEAD), get commit hash
        commit = _run_git_command(["rev-parse", "HEAD"], check_output=True)
        return f"detached-{commit[:8]}"
    except GitError:
        # If no commits exist yet
        return "main"


def branch_exists(branch_name: str) -> bool:
    """Check if a Git branch exists."""
    try:
        _run_git_command(["show-ref", "--verify", f"refs/heads/{branch_name}"])
        return True
    except GitError:
        return False


def get_missing_branches_info() -> dict:
    """Get information about missing stem branches referenced in stem metadata."""
    try:
        from . import state
        
        # Load current state to get all node references
        current_state = state.load_state()
        nodes = current_state.get("nodes", {})
        
        missing_branches = []
        existing_branches = []
        
        for node_id, node_data in nodes.items():
            ref = node_data.get("ref", "")
            if ref.startswith("refs/heads/"):
                branch_name = ref[11:]  # Remove "refs/heads/"
                
                if branch_exists(branch_name):
                    existing_branches.append({
                        'node_id': node_id,
                        'branch_name': branch_name,
                        'prompt': node_data.get('prompt', '')
                    })
                else:
                    missing_branches.append({
                        'node_id': node_id,
                        'branch_name': branch_name,
                        'prompt': node_data.get('prompt', ''),
                        'ref': ref
                    })
        
        return {
            'missing_branches': missing_branches,
            'existing_branches': existing_branches,
            'total_nodes': len(nodes)
        }
        
    except Exception as e:
        raise GitRepositoryError(f"Cannot analyze missing branches: {e}")


def suggest_missing_branch_recovery() -> str:
    """Provide recovery suggestions for missing branches."""
    try:
        info = get_missing_branches_info()
        
        if not info['missing_branches']:
            return "✓ All stem branches are present and accounted for."
        
        suggestions = []
        suggestions.append(f"⚠ Found {len(info['missing_branches'])} missing stem branches:")
        suggestions.append("")
        
        for branch_info in info['missing_branches']:
            suggestions.append(f"  Node {branch_info['node_id']}: {branch_info['branch_name']}")
            suggestions.append(f"    Prompt: {branch_info['prompt']}")
        
        suggestions.append("")
        suggestions.append("Recovery options:")
        suggestions.append("1. Clean up orphaned nodes:")
        suggestions.append("   - These nodes will be marked as orphaned in the metadata")
        suggestions.append("   - You can still see them in 'stem list' but cannot jump to them")
        suggestions.append("")
        suggestions.append("2. Recreate missing branches (advanced):")
        suggestions.append("   - If you have the commit hashes, you can recreate branches manually")
        suggestions.append("   - This requires Git expertise and is not recommended")
        suggestions.append("")
        suggestions.append(f"Healthy branches: {len(info['existing_branches'])}/{info['total_nodes']}")
        
        return "\n".join(suggestions)
        
    except Exception as e:
        return f"Cannot provide missing branch recovery suggestions: {e}"
    """Get current Git branch name."""
    try:
        # Try to get current branch name
        branch = _run_git_command(["branch", "--show-current"], check_output=True)
        if branch:
            return branch
        
        # If no branch name (detached HEAD), get commit hash
        commit = _run_git_command(["rev-parse", "HEAD"], check_output=True)
        return f"detached-{commit[:8]}"
    except GitError:
        # If no commits exist yet
        return "main"


def create_stem_branch_name(node_id: str, prompt: str) -> str:
    """Create stem branch name following convention: stem/<user>/<id>-<slug>.
    
    Args:
        node_id: The node ID (e.g., "001", "002")
        prompt: The user prompt to convert to slug
        
    Returns:
        str: Full branch name following stem convention
        
    Raises:
        RuntimeError: If username cannot be determined
    """
    username = get_username()
    slug = create_slug(prompt)
    return f"stem/{username}/{node_id}-{slug}"


def create_branch(branch_name: str) -> None:
    """Create stem branch with naming convention.
    
    Creates a new Git branch with the given name. The branch name should
    follow the stem/<user>/<id>-<slug> convention.
    
    Args:
        branch_name: Full branch name to create
        
    Raises:
        GitBranchError: If branch creation fails
        GitRepositoryError: If repository is in invalid state
    """
    # First validate we're in a git repository
    if not _is_git_repo(os.getcwd()):
        raise GitRepositoryError(f"Not in a Git repository. Initialize with 'git init' or 'stem create' first.")
    
    # Check for detached HEAD state
    if is_detached_head():
        try:
            recovery_msg = suggest_detached_head_recovery()
            raise GitRepositoryError(f"Cannot create branch in detached HEAD state.\n\n{recovery_msg}")
        except GitRepositoryError as detached_error:
            # If we can't get recovery suggestions, provide basic guidance
            raise GitRepositoryError("Cannot create branch in detached HEAD state. Use 'git checkout main' or 'git checkout -b <branch-name>' to create a new branch first.")
    
    # Check if branch already exists
    if branch_exists(branch_name):
        raise GitBranchError(f"Branch '{branch_name}' already exists")
    
    # Auto-stage any uncommitted changes before creating branch
    if not is_repo_clean():
        try:
            stage_all_changes()
        except GitError as e:
            raise GitCheckoutError(f"Cannot stage changes before creating branch: {e}")
    
    try:
        # Create and checkout the new branch
        _run_git_command(["checkout", "-b", branch_name])
    except GitBranchError:
        raise  # Re-raise specific branch errors
    except GitError as e:
        raise GitBranchError(f"Failed to create branch '{branch_name}': {e}")


def commit_changes(message: str) -> str:
    """Perform commits and return commit hash.
    
    Stages all changes and creates exactly one commit with the given message.
    
    Args:
        message: Commit message
        
    Returns:
        str: The commit hash of the created commit
        
    Raises:
        GitCommitError: If commit fails
        GitRepositoryError: If repository is in invalid state
    """
    # Check for detached HEAD state
    if is_detached_head():
        recovery_msg = suggest_detached_head_recovery()
        raise GitRepositoryError(f"Cannot commit in detached HEAD state.\n\n{recovery_msg}")
    
    try:
        # Stage all changes (including new files)
        _run_git_command(["add", "."])
        
        # Check if there are actually changes to commit
        try:
            _run_git_command(["diff-index", "--quiet", "--cached", "HEAD"])
            # If we get here, there are no staged changes
            raise GitCommitError("No changes to commit")
        except GitError:
            # This is expected - means there are staged changes
            pass
        
        # Create the commit
        _run_git_command(["commit", "-m", message])
        
        # Get the commit hash
        commit_hash = _run_git_command(["rev-parse", "HEAD"], check_output=True)
        return commit_hash
        
    except GitCommitError:
        raise  # Re-raise specific commit errors
    except GitError as e:
        raise GitCommitError(f"Failed to commit changes: {e}")


def checkout_branch(branch_name: str) -> None:
    """Perform safe checkout to specified branch.
    
    Safely switches to the specified branch, ensuring working tree is clean first.
    
    Args:
        branch_name: Name of branch to checkout
        
    Raises:
        GitCheckoutError: If checkout fails or working tree is dirty
        GitBranchError: If branch doesn't exist
        GitRepositoryError: If repository is in invalid state
    """
    # Check if branch exists
    if not branch_exists(branch_name):
        # Provide helpful suggestions for missing branches
        if branch_name.startswith('stem/'):
            recovery_msg = suggest_missing_branch_recovery()
            raise GitBranchError(f"Branch '{branch_name}' does not exist.\n\n{recovery_msg}")
        else:
            raise GitBranchError(f"Branch '{branch_name}' does not exist")
    
    # Check if working tree is clean before checkout
    if not is_repo_clean():
        raise GitCheckoutError("Cannot checkout branch: working tree has uncommitted changes")
    
    try:
        _run_git_command(["checkout", branch_name])
    except GitCheckoutError:
        raise  # Re-raise specific checkout errors
    except GitError as e:
        raise GitCheckoutError(f"Failed to checkout branch '{branch_name}': {e}")


def get_staged_diff_stat() -> str:
    """Generate diff statistics for staged changes.
    
    Gets the diff stat of currently staged changes, which is useful
    for generating summaries before committing.
    
    Returns:
        str: Git diff stat output for staged changes
        
    Raises:
        GitError: If diff command fails
    """
    try:
        # Get diff of staged changes
        diff_output = _run_git_command(["diff", "--stat", "--cached"], check_output=True)
        return diff_output.strip()
        
    except GitError as e:
        raise GitError(f"Failed to generate staged diff statistics: {e}")


def stage_all_changes() -> None:
    """Stage all changes in the working directory.
    
    Stages all modified, new, and deleted files for commit.
    
    Raises:
        GitError: If staging fails
    """
    try:
        _run_git_command(["add", "."])
    except GitError as e:
        raise GitError(f"Failed to stage changes: {e}")


def commit_staged_changes(message: str) -> str:
    """Create commit from staged changes and return commit hash.
    
    Creates a commit from currently staged changes with the given message.
    If there are no staged changes, creates an empty commit.
    
    Args:
        message: Commit message
        
    Returns:
        str: The commit hash of the created commit
        
    Raises:
        GitError: If commit fails
    """
    try:
        # Try to create the commit
        try:
            _run_git_command(["commit", "-m", message])
        except GitCommitError as e:
            # If commit fails due to no changes, create an empty commit
            if "no changes to commit" in str(e).lower():
                _run_git_command(["commit", "--allow-empty", "-m", message])
            else:
                raise e
        except GitError as e:
            # Handle other git errors that might indicate no changes
            if "nothing to commit" in str(e).lower() or "no changes added to commit" in str(e).lower():
                _run_git_command(["commit", "--allow-empty", "-m", message])
            else:
                raise e
        
        # Get the commit hash
        commit_hash = _run_git_command(["rev-parse", "HEAD"], check_output=True)
        return commit_hash
        
    except GitError as e:
        raise GitError(f"Failed to commit staged changes: {e}")
    """Generate diff statistics for summaries.
    
    Uses git diff --stat to get mechanical summary of changes.
    Handles both staged and unstaged changes.
    
    Returns:
        str: Git diff stat output
        
    Raises:
        GitError: If diff command fails
    """
    try:
        # First try to get diff against HEAD (for repos with commits)
        try:
            diff_output = _run_git_command(["diff", "--stat", "HEAD"], check_output=True)
            if diff_output.strip():
                return diff_output
        except GitError:
            # If HEAD doesn't exist, this might be the first commit
            pass
        
        # Try to get diff of staged changes (for initial commit)
        try:
            diff_output = _run_git_command(["diff", "--stat", "--cached"], check_output=True)
            if diff_output.strip():
                return diff_output
        except GitError:
            pass
        
        # If no staged changes, get diff of all changes
        try:
            diff_output = _run_git_command(["diff", "--stat"], check_output=True)
            if diff_output.strip():
                return diff_output
        except GitError:
            pass
        
        # If no diff available, return empty
        return ""
        
    except GitError as e:
        raise GitError(f"Failed to generate diff statistics: {e}")


def get_file_changes() -> dict:
    """Get detailed file change information for summary generation.
    
    Returns a dictionary with file change details that can be used
    by the summary layer to generate mechanical summaries.
    
    Returns:
        dict: File change information with keys:
            - added_files: list of newly added files
            - modified_files: list of modified files  
            - deleted_files: list of deleted files
            - renamed_files: list of (old_name, new_name) tuples
            
    Raises:
        GitError: If status command fails
    """
    try:
        # Get status in porcelain format for easy parsing
        status_output = _run_git_command(["status", "--porcelain"], check_output=True)
        
        added_files = []
        modified_files = []
        deleted_files = []
        renamed_files = []
        
        for line in status_output.split('\n'):
            if not line.strip():
                continue
                
            # Parse porcelain format: XY filename
            status_code = line[:2]
            filename = line[3:]
            
            # Handle different status codes
            if status_code[0] == 'A' or status_code[1] == 'A':
                added_files.append(filename)
            elif status_code[0] == 'M' or status_code[1] == 'M':
                modified_files.append(filename)
            elif status_code[0] == 'D' or status_code[1] == 'D':
                deleted_files.append(filename)
            elif status_code[0] == 'R':
                # Renamed files show as "R  old_name -> new_name"
                if ' -> ' in filename:
                    old_name, new_name = filename.split(' -> ', 1)
                    renamed_files.append((old_name, new_name))
                else:
                    # Fallback: treat as modified
                    modified_files.append(filename)
        
        return {
            'added_files': added_files,
            'modified_files': modified_files,
            'deleted_files': deleted_files,
            'renamed_files': renamed_files
        }
        
    except GitError as e:
        raise GitError(f"Failed to get file changes: {e}")
