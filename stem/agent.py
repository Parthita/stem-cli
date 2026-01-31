"""
Agent Integration Layer - Handle agent intent declaration and processing.

Provides functionality for agents to declare intent through JSON files,
generate AGENT.md documentation, and process agent intents to trigger
stem branch operations.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class AgentIntent:
    """Represents an agent's declared intent."""
    prompt: str
    summary: Optional[str] = None


def create_agent_md(force: bool = False) -> bool:
    """Generate AGENT.md with rules explanation for agent integration.
    
    Creates comprehensive documentation explaining how agents should
    interact with the stem system through intent declaration.
    
    Args:
        force: If True, overwrite existing AGENT.md file
        
    Returns:
        bool: True if file was created/updated, False if skipped
        
    Raises:
        OSError: If file cannot be created
    """
    agent_md_path = Path("AGENT.md")
    
    # Check if file already exists
    if agent_md_path.exists() and not force:
        print("AGENT.md already exists. Use --force to overwrite or remove it manually.")
        return False
    
    agent_md_content = """# Stem Agent Integration Rules

## Core Principles

The stem system is designed to work seamlessly with AI agents while maintaining human control over all meaningful decisions. Agents can declare their intent to make changes, but the system will only create nodes when intent is explicitly declared.

### Key Rules

1. **Declare intent BEFORE making changes** - Always write your intent JSON before modifying any files
2. **Use descriptive prompts** - Explain WHY you're making changes, not just what you're changing
3. **Provide summaries when possible** - Help users understand what you accomplished
4. **Respect the timing** - The system will auto-commit after detecting file changes and an idle period

## Intent Declaration Format

To declare your intent to make changes, write a JSON file to `.git/stem/intent/next.json`:

```json
{
    "prompt": "add user authentication system",
    "summary": "Created Login.jsx component and useAuth hook for handling user sessions"
}
```

### Required Fields

- `prompt` (string): A clear explanation of WHY you're making these changes. This becomes the node's prompt and should be meaningful to humans reviewing the code history.

### Optional Fields

- `summary` (string): A description of WHAT you changed. If provided, this will be used instead of the automatic git diff summary. Should be factual and specific.

## Workflow

1. **Plan your changes** - Decide what you want to accomplish
2. **Write intent JSON** - Create `.git/stem/intent/next.json` with your prompt and optional summary
3. **Make your changes** - Modify files as needed
4. **Wait for auto-commit** - The system will detect changes and automatically create a stem node

## Important Notes

- The intent JSON file will be consumed and removed after processing
- If no intent is declared, file changes will NOT create nodes automatically
- Manual `stem branch` commands always work regardless of agent state
- Agent assistance is optional - the system works fine without it
- Multiple intents should be declared separately for different logical changes

## Example Workflow

```bash
# Agent writes intent
echo '{"prompt": "implement user login form", "summary": "Added LoginForm.jsx with validation"}' > .git/stem/intent/next.json

# Agent makes changes
# ... modify files ...

# System detects changes after idle period and automatically:
# 1. Reads the intent JSON
# 2. Creates a new stem node with the prompt
# 3. Uses agent summary or falls back to git diff
# 4. Removes the intent JSON file
```

## Error Handling

- Invalid JSON will be logged and ignored
- Missing prompt field will cause the intent to be ignored
- File system errors will be handled gracefully
- The system will never fail silently - all errors are reported

## Integration with Manual Commands

- `stem branch "manual prompt"` always works, even with pending agent intents
- Manual commands take precedence over agent intents
- Agent intents are processed only during filesystem watching
- No conflicts arise between manual and agent operations

This system ensures that agents can work efficiently while maintaining the core stem principle: nodes are created only when intent is explicitly declared.
"""
    
    try:
        action = "Updated" if agent_md_path.exists() else "Created"
        with open(agent_md_path, 'w', encoding='utf-8') as f:
            f.write(agent_md_content)
        print(f"{action} AGENT.md with integration rules")
        return True
    except OSError as e:
        raise OSError(f"Failed to create AGENT.md: {e}")


def read_agent_intent() -> Optional[AgentIntent]:
    """Read agent intent from .git/stem/intent/next.json.
    
    Reads and validates the agent intent JSON file. The file is consumed
    (deleted) after successful reading to prevent duplicate processing.
    
    Returns:
        Optional[AgentIntent]: The parsed intent, or None if no valid intent exists
        
    Raises:
        OSError: If file operations fail (other than file not existing)
    """
    intent_path = Path(".git/stem/intent/next.json")
    
    # Return None if intent file doesn't exist
    if not intent_path.exists():
        return None
    
    try:
        # Read the intent file
        with open(intent_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate required fields
        if not isinstance(data, dict):
            print("Warning: Agent intent must be a JSON object")
            _cleanup_intent_file(intent_path)
            return None
        
        if 'prompt' not in data:
            print("Warning: Agent intent missing required 'prompt' field")
            _cleanup_intent_file(intent_path)
            return None
        
        if not isinstance(data['prompt'], str) or not data['prompt'].strip():
            print("Warning: Agent intent 'prompt' must be a non-empty string")
            _cleanup_intent_file(intent_path)
            return None
        
        # Extract fields
        prompt = data['prompt'].strip()
        summary = data.get('summary')
        
        # Validate optional summary field
        if summary is not None:
            if not isinstance(summary, str):
                print("Warning: Agent intent 'summary' must be a string, ignoring")
                summary = None
            else:
                summary = summary.strip() if summary.strip() else None
        
        # Clean up the intent file after successful reading
        _cleanup_intent_file(intent_path)
        
        return AgentIntent(prompt=prompt, summary=summary)
        
    except json.JSONDecodeError as e:
        print(f"Warning: Invalid JSON in agent intent file: {e}")
        _cleanup_intent_file(intent_path)
        return None
    except Exception as e:
        # Don't cleanup on unexpected errors to preserve debugging info
        print(f"Error reading agent intent: {e}")
        return None


def _cleanup_intent_file(intent_path: Path) -> None:
    """Remove the intent file after processing.
    
    Args:
        intent_path: Path to the intent file to remove
    """
    try:
        intent_path.unlink()
    except OSError as e:
        print(f"Warning: Failed to remove intent file: {e}")


def ensure_intent_directory() -> None:
    """Ensure the .git/stem/intent directory exists.
    
    Creates the intent directory structure needed for agent integration.
    
    Raises:
        OSError: If directories cannot be created
    """
    intent_dir = Path(".git/stem/intent")
    intent_dir.mkdir(parents=True, exist_ok=True)


def process_agent_intent() -> Optional[Dict[str, str]]:
    """Process pending agent intent and return branch parameters.
    
    Reads agent intent, validates it, and returns the parameters needed
    to create a stem branch. This function is called by the filesystem
    watcher when changes are detected.
    
    Returns:
        Optional[Dict[str, str]]: Dict with 'prompt' and optional 'summary' keys,
                                 or None if no valid intent exists
    """
    intent = read_agent_intent()
    if intent is None:
        return None
    
    result = {'prompt': intent.prompt}
    if intent.summary:
        result['summary'] = intent.summary
    
    return result


def has_pending_intent() -> bool:
    """Check if there's a pending agent intent file.
    
    Returns:
        bool: True if .git/stem/intent/next.json exists
    """
    intent_path = Path(".git/stem/intent/next.json")
    return intent_path.exists()