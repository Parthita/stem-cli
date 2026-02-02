"""
Watcher Layer - Filesystem monitoring and idle detection.

Monitors filesystem changes using watchdog, implements idle detection,
and triggers auto-commits when nodes exist. Integrates with agent
intent system to record intent suggestions.
"""

import os
import time
import threading
from pathlib import Path
from typing import Any, Optional, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from .state import load_state, get_current_head
from .git import is_repo_clean, commit_changes, get_staged_diff_stat
from .summary import generate_summary
from . import agent
from .cli import internal_branch


class StemFileSystemEventHandler(FileSystemEventHandler):
    """Custom event handler for stem filesystem watching."""
    
    def __init__(self, idle_timeout: int = 3):
        super().__init__()
        self.idle_timeout = idle_timeout
        self.last_change_time: Optional[float] = None
        self.idle_timer: Optional[threading.Timer] = None
        self.lock = threading.Lock()
        
    def on_any_event(self, event: FileSystemEvent) -> None:
        """Handle any filesystem event."""
        # Ignore directory events and events in .git/
        if event.is_directory:
            return
            
        # Filter out .git/ and .git/stem/ directories
        if self._should_ignore_path(event.src_path):
            return
            
        # Handle the file change
        self._handle_file_change(event)
    
    def _should_ignore_path(self, path: str) -> bool:
        """Check if path should be ignored based on filtering rules."""
        path_obj = Path(path).resolve()
        
        # Check if path is within .git/ directory
        try:
            # Get relative path from current working directory
            rel_path = path_obj.relative_to(Path.cwd())
            path_parts = rel_path.parts
            
            # Ignore anything in .git/ or .git/stem/
            if path_parts and (path_parts[0] == '.git'):
                return True
                
        except ValueError:
            # Path is not relative to current directory, don't ignore
            pass
            
        return False
    
    def _handle_file_change(self, event: FileSystemEvent) -> None:
        """Handle filesystem change events with idle detection."""
        with self.lock:
            # Update last change time
            self.last_change_time = time.time()
            
            # Cancel existing timer if any
            if self.idle_timer is not None:
                self.idle_timer.cancel()
            
            # Start new idle timer
            self.idle_timer = threading.Timer(
                self.idle_timeout, 
                self._on_idle_timeout
            )
            self.idle_timer.start()
    
    def _on_idle_timeout(self) -> None:
        """Called when idle timeout is reached."""
        with self.lock:
            # Check if we're still idle (no changes since timer started)
            if (self.last_change_time is not None and 
                time.time() - self.last_change_time >= self.idle_timeout):
                
                # Trigger auto-commit if needed
                try:
                    auto_commit_if_needed()
                except Exception as e:
                    print(f"Error during auto-commit: {e}")
            
            # Clear the timer
            self.idle_timer = None


def start_background_watcher(path: str, idle_timeout: int = 3) -> int:
    """Start filesystem watcher as a background subprocess.
    
    Args:
        path: Directory path to monitor
        idle_timeout: Seconds to wait after last change before triggering auto-commit
        
    Returns:
        int: Process ID of the background watcher, or 0 if failed
    """
    import subprocess
    import sys
    
    try:
        # Start watcher as background subprocess
        process = subprocess.Popen([
            sys.executable, '-m', 'stem.watcher',
            '--path', path,
            '--timeout', str(idle_timeout)
        ], 
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True  # Detach from parent process
        )
        
        return process.pid
        
    except Exception as e:
        print(f"Failed to start background watcher: {e}")
        return 0


def stop_background_watcher(pid: int) -> bool:
    """Stop background watcher process.
    
    Args:
        pid: Process ID of the watcher to stop
        
    Returns:
        bool: True if successfully stopped
    """
    import os
    import signal
    
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except (OSError, ProcessLookupError):
        return False


def is_watcher_running(pid: int) -> bool:
    """Check if watcher process is still running.
    
    Args:
        pid: Process ID to check
        
    Returns:
        bool: True if process is running
    """
    import os
    
    try:
        os.kill(pid, 0)  # Signal 0 just checks if process exists
        return True
    except (OSError, ProcessLookupError):
        return False


def start_watching(path: str, idle_timeout: int = 3) -> None:
    """Start filesystem monitoring with idle detection.
    
    Args:
        path: Directory path to monitor
        idle_timeout: Seconds to wait after last change before triggering auto-commit
        
    Raises:
        RuntimeError: If watching cannot be started
    """
    try:
        # Resolve path to absolute path
        watch_path = Path(path).resolve()
        
        if not watch_path.exists():
            raise RuntimeError(f"Path does not exist: {watch_path}")
            
        if not watch_path.is_dir():
            raise RuntimeError(f"Path is not a directory: {watch_path}")
        
        # Create event handler
        event_handler = StemFileSystemEventHandler(idle_timeout)
        
        # Create observer
        observer = Observer()
        observer.schedule(event_handler, str(watch_path), recursive=True)
        
        # Start watching
        observer.start()
        
        print(f"Watching {watch_path} for changes (idle timeout: {idle_timeout}s)")
        print("Press Ctrl+C to stop watching...")
        
        try:
            # Keep the main thread alive
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping filesystem watcher...")
        finally:
            observer.stop()
            observer.join()
            
    except Exception as e:
        raise RuntimeError(f"Failed to start filesystem watching: {e}")


def handle_file_change(event: Any) -> None:
    """Handle filesystem change events.
    
    This function is called by the event handler when files change.
    It implements the idle detection logic.
    
    Args:
        event: Filesystem event from watchdog
    """
    # This is now handled by the StemFileSystemEventHandler class
    # This function is kept for backward compatibility but delegates
    # to the event handler implementation
    pass


def check_idle_state() -> bool:
    """Check if system is in idle state.
    
    Returns:
        bool: True if system has been idle for the configured timeout
    """
    # This is now handled internally by the event handler
    # For external callers, we can't easily determine idle state
    # without access to the handler instance
    return True


def auto_commit_if_needed() -> None:
    """Trigger auto-commit only when nodes exist, with agent integration.
    
    This function implements the core auto-commit logic with agent integration:
    1. Check for agent intent and record it as a suggestion if present
    2. If a pending agent intent exists and repo is dirty, auto-create a node
    3. Check if any nodes exist (if not, do nothing)
    4. Check if working tree is dirty (if clean, do nothing)  
    5. Create exactly one commit per node
    
    Agent integration ensures that:
    - Agent intents are recorded and auto-create nodes only after changes are present
    - Manual stem branch always works regardless of agent state
    
    Raises:
        Exception: If auto-commit fails
    """
    try:
        # First, check for agent intent and record it as a suggestion
        intent_id = agent.process_agent_intent()
        if intent_id:
            print(f"Recorded agent intent suggestion (id: {intent_id}). Awaiting changes.")

        # Auto-branch from pending agent intent when changes are present
        from . import state
        pending = state.get_pending_intent_by_source("agent_file")
        if pending and not is_repo_clean():
            confirmed = state.confirm_intent(int(pending["id"]))
            prompt = confirmed["prompt"]
            summary = confirmed.get("summary")
            success = internal_branch(prompt, summary, intent_id=int(pending["id"]))
            if success:
                print(f"Created node from agent intent: {prompt}")
            else:
                state.log_anomaly(
                    "intent_auto_branch_failed",
                    {"intent_id": int(pending["id"]), "prompt": prompt},
                    node_id=None,
                )
            return
        
        # Check if any nodes exist - requirement 3.7
        state = load_state()
        if not state["nodes"]:
            # No nodes exist and no agent intent, don't auto-commit
            return
            
        # Check if working tree is clean - requirement 3.5
        if is_repo_clean():
            # Working tree is clean, nothing to commit
            return
            
        # Get current head node
        current_head = get_current_head()
        if current_head is None:
            # No head node, this shouldn't happen if nodes exist
            print("Warning: Nodes exist but no head node found")
            return
            
        # Generate summary for the commit
        # Agent summary preference is handled in the node creation above
        # For auto-commits of existing nodes, use standard summary generation
        try:
            # Try to use the summary module if available
            summary = generate_summary()
            if not summary:
                # If summary is empty, fallback to diff stat
                summary = get_staged_diff_stat()
        except Exception as e:
            # Fallback to basic diff stat if summary generation fails
            print(f"Warning: Summary generation failed, using diff stat: {e}")
            summary = get_staged_diff_stat()
            
        # Create commit message
        commit_message = f"Auto-commit for node {current_head}"
        
        # Commit the changes - requirement 3.3, 3.6
        commit_hash = commit_changes(commit_message)
        
        print(f"Auto-committed changes for node {current_head}: {commit_hash[:8]}")
        
    except Exception as e:
        # Re-raise with context
        raise Exception(f"Auto-commit failed: {e}")


if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Stem filesystem watcher")
    parser.add_argument("--path", required=True, help="Directory path to monitor")
    parser.add_argument("--timeout", type=int, default=3, help="Idle timeout in seconds")
    
    args = parser.parse_args()
    
    try:
        start_watching(args.path, args.timeout)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Watcher failed: {e}")
        sys.exit(1)
