"""
State Layer - Manage stem metadata and node tracking.

Handles reading/writing nodes.json, generating sequential node IDs,
tracking node relationships and head pointer.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


class StateError(Exception):
    """Exception raised for state management failures."""
    pass


class StateCorruptionError(StateError):
    """Exception raised when state corruption is detected."""
    pass


class StateValidationError(StateError):
    """Exception raised when state validation fails."""
    pass


@dataclass
class Node:
    """Represents a single stem node with metadata."""
    id: str
    parent: Optional[str]
    prompt: str
    summary: str
    ref: str
    created_at: datetime


@dataclass
class StemState:
    """Represents the complete state of a stem repository."""
    counter: int
    head: Optional[str]
    nodes: Dict[str, Node]
    
    def next_id(self) -> str:
        """Generate next sequential node ID."""
        self.counter += 1
        return f"{self.counter:03d}"


def load_state() -> Dict:
    """Read nodes.json atomically with validation and corruption detection."""
    stem_dir = Path(".git/stem")
    nodes_file = stem_dir / "nodes.json"
    backup_file = stem_dir / "nodes.json.backup"
    
    # If nodes.json doesn't exist, return empty state
    if not nodes_file.exists():
        return {
            "counter": 0,
            "head": None,
            "nodes": {}
        }
    
    # Try to load the main file
    try:
        with open(nodes_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate the loaded state
        validation_result = _validate_state_detailed(data)
        if validation_result['valid']:
            return data
        else:
            raise StateValidationError(f"Invalid state structure: {validation_result['errors']}")
            
    except (json.JSONDecodeError, StateValidationError, KeyError) as e:
        print(f"Warning: nodes.json is corrupted ({e})")
        
        # Try to recover from backup
        recovery_attempted = False
        if backup_file.exists():
            try:
                print("Attempting recovery from backup...")
                with open(backup_file, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)
                
                backup_validation = _validate_state_detailed(backup_data)
                if backup_validation['valid']:
                    print("Successfully recovered from backup")
                    # Restore the main file from backup
                    shutil.copy2(backup_file, nodes_file)
                    recovery_attempted = True
                    return backup_data
                else:
                    print(f"Backup is also corrupted: {backup_validation['errors']}")
            except Exception as backup_error:
                print(f"Failed to recover from backup: {backup_error}")
        
        # Try to repair the corrupted state
        if not recovery_attempted:
            try:
                print("Attempting to repair corrupted state...")
                repaired_state = _attempt_state_repair(nodes_file)
                if repaired_state:
                    print("Successfully repaired state")
                    return repaired_state
            except Exception as repair_error:
                print(f"State repair failed: {repair_error}")
        
        # If all recovery attempts fail, return empty state and create backup of corrupted file
        corrupted_file = stem_dir / f"nodes.json.corrupted.{int(datetime.now().timestamp())}"
        if nodes_file.exists():
            shutil.copy2(nodes_file, corrupted_file)
            print(f"Corrupted file saved as: {corrupted_file}")
        
        print("Starting with empty state")
        return {
            "counter": 0,
            "head": None,
            "nodes": {}
        }


def save_state(state: Dict) -> None:
    """Write nodes.json atomically with backup mechanism and rollback on failure."""
    stem_dir = Path(".git/stem")
    nodes_file = stem_dir / "nodes.json"
    backup_file = stem_dir / "nodes.json.backup"
    
    # Ensure stem directory exists
    stem_dir.mkdir(parents=True, exist_ok=True)
    
    # Validate state before saving
    validation_result = _validate_state_detailed(state)
    if not validation_result['valid']:
        raise StateValidationError(f"Invalid state structure - refusing to save corrupted data: {validation_result['errors']}")
    
    # Store original file for rollback if needed
    original_backup = None
    if nodes_file.exists():
        try:
            # Create backup of existing file
            shutil.copy2(nodes_file, backup_file)
            # Also keep a temporary copy for rollback
            original_backup = stem_dir / f"nodes.json.original.{int(datetime.now().timestamp())}"
            shutil.copy2(nodes_file, original_backup)
        except Exception as e:
            print(f"Warning: Failed to create backup: {e}")
    
    # Write to temporary file first for atomic operation
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', 
            encoding='utf-8', 
            dir=stem_dir, 
            delete=False,
            suffix='.tmp'
        ) as tmp_file:
            json.dump(state, tmp_file, indent=2, ensure_ascii=False)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())  # Force write to disk
            temp_file = tmp_file.name
        
        # Validate the written file before committing
        try:
            with open(temp_file, 'r', encoding='utf-8') as f:
                written_data = json.load(f)
            
            written_validation = _validate_state_detailed(written_data)
            if not written_validation['valid']:
                raise StateValidationError(f"Written file validation failed: {written_validation['errors']}")
                
        except Exception as e:
            raise StateCorruptionError(f"Failed to validate written state file: {e}")
        
        # Atomic move to final location
        try:
            if os.name == 'nt':  # Windows
                if nodes_file.exists():
                    nodes_file.unlink()
            shutil.move(temp_file, nodes_file)
            temp_file = None  # Successfully moved
            
        except Exception as e:
            raise StateCorruptionError(f"Failed to save state atomically: {e}")
        
        # Clean up original backup on success
        if original_backup and original_backup.exists():
            try:
                original_backup.unlink()
            except:
                pass  # Ignore cleanup errors
                
    except Exception as e:
        # Rollback on any failure
        try:
            # Clean up temp file if it exists
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)
            
            # Restore original file if we have a backup
            if original_backup and original_backup.exists() and not nodes_file.exists():
                shutil.copy2(original_backup, nodes_file)
                print("Rolled back to original state after save failure")
                
        except Exception as rollback_error:
            print(f"Warning: Rollback failed: {rollback_error}")
        
        # Clean up rollback backup
        if original_backup and original_backup.exists():
            try:
                original_backup.unlink()
            except:
                pass
        
        # Re-raise the original error
        raise StateCorruptionError(f"Failed to save state: {e}")


def create_node(prompt: str, summary: str, ref: str, parent: str) -> str:
    """Create new node and return node ID."""
    # Load current state
    state = load_state()
    
    # Generate next sequential ID
    state["counter"] += 1
    node_id = f"{state['counter']:03d}"
    
    # Create the new node
    state["nodes"][node_id] = {
        "parent": parent,
        "prompt": prompt,
        "summary": summary,
        "ref": ref
    }
    
    # Update head to point to new node
    state["head"] = node_id
    
    # Save updated state
    save_state(state)
    
    return node_id


def get_next_id() -> str:
    """Generate sequential node ID without creating a node."""
    state = load_state()
    next_counter = state["counter"] + 1
    return f"{next_counter:03d}"


def update_head(node_id: str) -> None:
    """Update head pointer to specified node."""
    state = load_state()
    
    # Validate that the node exists
    if node_id not in state["nodes"]:
        raise ValueError(f"Node {node_id} does not exist")
    
    # Update head pointer
    state["head"] = node_id
    
    # Save updated state
    save_state(state)


def get_current_head() -> Optional[str]:
    """Get the current head node ID."""
    state = load_state()
    return state["head"]


def get_all_nodes() -> Dict[str, Dict]:
    """Get all nodes in the current repository."""
    state = load_state()
    return state["nodes"]


def _validate_state_detailed(state: Dict) -> dict:
    """Validate the structure and content of a state dictionary with detailed error reporting."""
    errors = []
    
    try:
        # Check required top-level keys
        required_keys = {"counter", "head", "nodes"}
        missing_keys = required_keys - set(state.keys())
        if missing_keys:
            errors.append(f"Missing required keys: {missing_keys}")
        
        # Validate counter
        if "counter" in state:
            if not isinstance(state["counter"], int):
                errors.append(f"Counter must be integer, got {type(state['counter'])}")
            elif state["counter"] < 0:
                errors.append(f"Counter must be non-negative, got {state['counter']}")
        
        # Validate head (can be None or string)
        if "head" in state:
            if state["head"] is not None and not isinstance(state["head"], str):
                errors.append(f"Head must be None or string, got {type(state['head'])}")
        
        # Validate nodes dictionary
        if "nodes" in state:
            if not isinstance(state["nodes"], dict):
                errors.append(f"Nodes must be dictionary, got {type(state['nodes'])}")
            else:
                # Validate each node
                for node_id, node_data in state["nodes"].items():
                    if not isinstance(node_id, str):
                        errors.append(f"Node ID must be string, got {type(node_id)} for {node_id}")
                        continue
                    
                    if not isinstance(node_data, dict):
                        errors.append(f"Node data must be dictionary for node {node_id}")
                        continue
                    
                    # Check required node fields
                    required_node_keys = {"parent", "prompt", "summary", "ref"}
                    missing_node_keys = required_node_keys - set(node_data.keys())
                    if missing_node_keys:
                        errors.append(f"Node {node_id} missing keys: {missing_node_keys}")
                    
                    # Validate node field types
                    if "parent" in node_data:
                        if node_data["parent"] is not None and not isinstance(node_data["parent"], str):
                            errors.append(f"Node {node_id} parent must be None or string")
                    
                    if "prompt" in node_data and not isinstance(node_data["prompt"], str):
                        errors.append(f"Node {node_id} prompt must be string")
                    
                    if "summary" in node_data and not isinstance(node_data["summary"], str):
                        errors.append(f"Node {node_id} summary must be string")
                    
                    if "ref" in node_data and not isinstance(node_data["ref"], str):
                        errors.append(f"Node {node_id} ref must be string")
        
        # Cross-reference validation
        if "head" in state and "nodes" in state:
            # Validate head points to existing node (if not None)
            if state["head"] is not None and state["head"] not in state["nodes"]:
                errors.append(f"Head points to non-existent node: {state['head']}")
        
        if "nodes" in state and isinstance(state["nodes"], dict):
            # Validate parent references point to existing nodes
            for node_id, node_data in state["nodes"].items():
                if isinstance(node_data, dict) and "parent" in node_data:
                    if node_data["parent"] is not None and node_data["parent"] not in state["nodes"]:
                        errors.append(f"Node {node_id} parent points to non-existent node: {node_data['parent']}")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
        
    except Exception as e:
        return {
            'valid': False,
            'errors': [f"Validation exception: {e}"]
        }


def _attempt_state_repair(nodes_file: Path) -> Optional[Dict]:
    """Attempt to repair a corrupted state file by fixing common issues."""
    try:
        # Try to load the raw JSON first
        with open(nodes_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # Start with a clean state template
        repaired_state = {
            "counter": 0,
            "head": None,
            "nodes": {}
        }
        
        # Try to recover counter
        if "counter" in raw_data and isinstance(raw_data["counter"], int) and raw_data["counter"] >= 0:
            repaired_state["counter"] = raw_data["counter"]
        
        # Try to recover nodes
        if "nodes" in raw_data and isinstance(raw_data["nodes"], dict):
            valid_nodes = {}
            
            for node_id, node_data in raw_data["nodes"].items():
                if not isinstance(node_id, str) or not isinstance(node_data, dict):
                    continue
                
                # Try to repair this node
                repaired_node = {}
                
                # Required fields with defaults
                repaired_node["parent"] = None
                repaired_node["prompt"] = "Recovered node"
                repaired_node["summary"] = "Summary lost during recovery"
                repaired_node["ref"] = f"refs/heads/stem/unknown/{node_id}"
                
                # Try to recover actual values
                if "parent" in node_data:
                    if node_data["parent"] is None or isinstance(node_data["parent"], str):
                        repaired_node["parent"] = node_data["parent"]
                
                if "prompt" in node_data and isinstance(node_data["prompt"], str):
                    repaired_node["prompt"] = node_data["prompt"]
                
                if "summary" in node_data and isinstance(node_data["summary"], str):
                    repaired_node["summary"] = node_data["summary"]
                
                if "ref" in node_data and isinstance(node_data["ref"], str):
                    repaired_node["ref"] = node_data["ref"]
                
                valid_nodes[node_id] = repaired_node
            
            repaired_state["nodes"] = valid_nodes
            
            # Update counter based on recovered nodes
            if valid_nodes:
                try:
                    max_id = max(int(node_id) for node_id in valid_nodes.keys() if node_id.isdigit())
                    repaired_state["counter"] = max(repaired_state["counter"], max_id)
                except (ValueError, TypeError):
                    pass
        
        # Try to recover head, but validate it points to existing node
        if "head" in raw_data and isinstance(raw_data["head"], str):
            if raw_data["head"] in repaired_state["nodes"]:
                repaired_state["head"] = raw_data["head"]
        
        # Fix parent references that point to non-existent nodes
        for node_id, node_data in repaired_state["nodes"].items():
            if node_data["parent"] is not None and node_data["parent"] not in repaired_state["nodes"]:
                node_data["parent"] = None
        
        # Validate the repaired state
        validation_result = _validate_state_detailed(repaired_state)
        if validation_result['valid']:
            # Save the repaired state
            save_state(repaired_state)
            return repaired_state
        else:
            print(f"Repair validation failed: {validation_result['errors']}")
            return None
            
    except Exception as e:
        print(f"State repair exception: {e}")
        return None


def detect_orphaned_nodes() -> dict:
    """Detect nodes that reference missing Git branches."""
    try:
        from . import git
        
        state = load_state()
        nodes = state.get("nodes", {})
        
        orphaned_nodes = []
        healthy_nodes = []
        
        for node_id, node_data in nodes.items():
            ref = node_data.get("ref", "")
            if ref.startswith("refs/heads/"):
                branch_name = ref[11:]  # Remove "refs/heads/"
                
                if git.branch_exists(branch_name):
                    healthy_nodes.append({
                        'node_id': node_id,
                        'branch_name': branch_name,
                        'prompt': node_data.get('prompt', ''),
                        'parent': node_data.get('parent')
                    })
                else:
                    orphaned_nodes.append({
                        'node_id': node_id,
                        'branch_name': branch_name,
                        'prompt': node_data.get('prompt', ''),
                        'parent': node_data.get('parent'),
                        'ref': ref
                    })
        
        return {
            'orphaned_nodes': orphaned_nodes,
            'healthy_nodes': healthy_nodes,
            'total_nodes': len(nodes),
            'orphan_count': len(orphaned_nodes)
        }
        
    except Exception as e:
        raise StateError(f"Cannot detect orphaned nodes: {e}")


def suggest_orphan_cleanup() -> str:
    """Provide suggestions for cleaning up orphaned nodes."""
    try:
        info = detect_orphaned_nodes()
        
        if not info['orphaned_nodes']:
            return "✓ No orphaned nodes detected. All nodes have valid Git branches."
        
        suggestions = []
        suggestions.append(f"⚠ Found {info['orphan_count']} orphaned nodes:")
        suggestions.append("")
        
        for node_info in info['orphaned_nodes']:
            suggestions.append(f"  Node {node_info['node_id']}: {node_info['prompt']}")
            suggestions.append(f"    Missing branch: {node_info['branch_name']}")
            if node_info['parent']:
                suggestions.append(f"    Parent: {node_info['parent']}")
        
        suggestions.append("")
        suggestions.append("Cleanup options:")
        suggestions.append("1. Remove orphaned nodes from metadata:")
        suggestions.append("   - This will permanently delete the node records")
        suggestions.append("   - The Git commits may still exist but won't be tracked")
        suggestions.append("")
        suggestions.append("2. Mark nodes as orphaned (keep for reference):")
        suggestions.append("   - Nodes will be marked as orphaned but kept in metadata")
        suggestions.append("   - You can still see them in 'stem list' with orphan indicator")
        suggestions.append("")
        suggestions.append(f"Healthy nodes: {len(info['healthy_nodes'])}/{info['total_nodes']}")
        
        return "\n".join(suggestions)
        
    except Exception as e:
        return f"Cannot provide orphan cleanup suggestions: {e}"
def _validate_state(state: Dict) -> bool:
    """Validate the structure and content of a state dictionary (legacy wrapper)."""
    return _validate_state_detailed(state)['valid']