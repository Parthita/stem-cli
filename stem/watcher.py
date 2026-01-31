"""
Watcher Layer - Filesystem monitoring and idle detection.

Monitors filesystem changes using watchdog, implements idle detection,
and triggers auto-commits when nodes exist. Integrates with agent
intent system to automatically create nodes when agents declare intent.
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
    1. Check for agent intent and process it if present
    2. Check if any nodes exist (if not, do nothing unless agent intent exists)
    3. Check if working tree is dirty (if clean, do nothing)  
    4. Create exactly one commit per node
    
    Agent integration ensures that:
    - Agent intents are processed to create nodes automatically
    - Agent-provided summaries are preferred over git diff
    - Manual stem branch always works regardless of agent state
    
    Raises:
        Exception: If auto-commit fails
    """
    try:
        # First, check for agent intent and process it - requirements 4.4, 4.5
        agent_intent_data = agent.process_agent_intent()
        
        if agent_intent_data:
            # Agent has declared intent, create a new node
            prompt = agent_intent_data['prompt']
            agent_summary = agent_intent_data.get('summary')
            
            print(f"Processing agent intent: {prompt}")
            
            # Use internal branch function to create the node
            success = internal_branch(prompt, agent_summary)
            
            if success:
                print(f"Created node from agent intent: {prompt}")
                # After creating node, continue with normal auto-commit logic
                # to handle any additional changes
            else:
                print(f"Failed to create node from agent intent: {prompt}")
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