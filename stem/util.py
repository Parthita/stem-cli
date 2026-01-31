"""
Utility Layer - Common utilities and helpers.

Provides username detection, slug generation, path manipulation,
and global repository registration functions.
"""

import os
import re
import json
import getpass
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class GlobalRegistry:
    """Represents the global registry of all stem repositories."""
    repos: Dict[str, 'RepoInfo']


@dataclass
class RepoInfo:
    """Information about a registered stem repository."""
    path: str
    name: str
    last_accessed: datetime
    node_count: int


def get_username() -> str:
    """Get current username with fallbacks.
    
    Uses os.getlogin() with fallbacks to getpass.getuser() and environment variables.
    
    Returns:
        str: The current username
        
    Raises:
        RuntimeError: If no username can be determined
    """
    # Try os.getlogin() first (most reliable for actual login user)
    try:
        return os.getlogin()
    except (OSError, AttributeError):
        pass
    
    # Fallback to getpass.getuser() (checks various env vars)
    try:
        return getpass.getuser()
    except Exception:
        pass
    
    # Final fallback to environment variables
    for env_var in ['USER', 'USERNAME', 'LOGNAME']:
        username = os.environ.get(env_var)
        if username:
            return username
    
    # If all else fails
    raise RuntimeError("Unable to determine username")


def create_slug(prompt: str) -> str:
    """Generate URL-safe slug from prompt.
    
    Converts a prompt string to a URL-safe branch name component by:
    - Converting to lowercase
    - Replacing spaces and special chars with hyphens
    - Removing consecutive hyphens
    - Trimming hyphens from start/end
    - Limiting length to 50 characters
    
    Args:
        prompt: The input prompt string
        
    Returns:
        str: URL-safe slug suitable for Git branch names
    """
    if not prompt or not prompt.strip():
        return "untitled"
    
    # Convert to lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r'[^a-z0-9]+', '-', prompt.lower().strip())
    
    # Remove consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    
    # Limit length to 50 characters
    if len(slug) > 50:
        slug = slug[:50].rstrip('-')
    
    # Ensure we have something
    return slug if slug else "untitled"


def ensure_stem_dirs() -> None:
    """Create necessary stem directories.
    
    Creates the ~/.stem directory and any required subdirectories
    for global repository registration and configuration.
    
    Raises:
        OSError: If directories cannot be created due to permissions
    """
    stem_dir = Path.home() / '.stem'
    stem_dir.mkdir(exist_ok=True)
    
    # Create subdirectories if needed in the future
    # For now, just ensure the main directory exists


def register_repo_globally(repo_path: str) -> None:
    """Register repository in global registry.
    
    Adds or updates repository information in ~/.stem/repos.json
    with atomic file operations to prevent corruption.
    
    Args:
        repo_path: Absolute path to the repository
        
    Raises:
        OSError: If file operations fail
        ValueError: If repo_path is invalid
    """
    if not repo_path or not os.path.isabs(repo_path):
        raise ValueError("Repository path must be absolute")
    
    # Ensure stem directories exist
    ensure_stem_dirs()
    
    # Normalize the path
    repo_path = os.path.normpath(repo_path)
    repo_name = os.path.basename(repo_path)
    
    # Load existing registry
    registry = load_global_registry()
    
    # Update or add repository info
    registry.repos[repo_path] = RepoInfo(
        path=repo_path,
        name=repo_name,
        last_accessed=datetime.now(),
        node_count=0  # Will be updated when nodes are created
    )
    
    # Save registry atomically
    save_global_registry(registry)


def load_global_registry() -> GlobalRegistry:
    """Load global repository registry from ~/.stem/repos.json.
    
    Returns:
        GlobalRegistry: The loaded registry, or empty registry if file doesn't exist
        
    Raises:
        json.JSONDecodeError: If the registry file is corrupted
    """
    registry_path = Path.home() / '.stem' / 'repos.json'
    
    if not registry_path.exists():
        return GlobalRegistry(repos={})
    
    try:
        with open(registry_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Convert dict data back to RepoInfo objects
        repos = {}
        for path, repo_data in data.get('repos', {}).items():
            repos[path] = RepoInfo(
                path=repo_data['path'],
                name=repo_data['name'],
                last_accessed=datetime.fromisoformat(repo_data['last_accessed']),
                node_count=repo_data['node_count']
            )
        
        return GlobalRegistry(repos=repos)
    
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise json.JSONDecodeError(f"Corrupted registry file: {e}", "", 0)


def save_global_registry(registry: GlobalRegistry) -> None:
    """Save global repository registry to ~/.stem/repos.json atomically.
    
    Uses atomic file operations to prevent corruption during writes.
    
    Args:
        registry: The registry to save
        
    Raises:
        OSError: If file operations fail
    """
    registry_path = Path.home() / '.stem' / 'repos.json'
    temp_path = registry_path.with_suffix('.json.tmp')
    
    # Convert RepoInfo objects to serializable dict
    data = {
        'repos': {}
    }
    
    for path, repo_info in registry.repos.items():
        data['repos'][path] = {
            'path': repo_info.path,
            'name': repo_info.name,
            'last_accessed': repo_info.last_accessed.isoformat(),
            'node_count': repo_info.node_count
        }
    
    try:
        # Write to temporary file first
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Atomic move to final location
        temp_path.replace(registry_path)
        
    except Exception:
        # Clean up temp file if it exists
        if temp_path.exists():
            temp_path.unlink()
        raise


def update_repo_node_count(repo_path: str, node_count: int) -> None:
    """Update the node count for a repository in the global registry.
    
    Args:
        repo_path: Absolute path to the repository
        node_count: New node count
        
    Raises:
        ValueError: If repository is not registered
    """
    registry = load_global_registry()
    
    if repo_path not in registry.repos:
        raise ValueError(f"Repository not registered: {repo_path}")
    
    registry.repos[repo_path].node_count = node_count
    registry.repos[repo_path].last_accessed = datetime.now()
    
    save_global_registry(registry)


def get_global_registry() -> GlobalRegistry:
    """Get the current global registry.
    
    Returns:
        GlobalRegistry: The current registry
    """
    return load_global_registry()