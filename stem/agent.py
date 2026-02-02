"""
Agent Integration Layer - Handle agent intent declaration and processing.

Provides functionality for agents to declare intent through JSON files,
generate AGENT.md documentation, and process agent intents to record
suggestions for user confirmation.
"""

import json
import os
from pathlib import Path
from typing import Optional
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
    If AGENT.md already exists, appends stem integration rules to it.
    
    Args:
        force: If True, overwrite existing AGENT.md file completely
        
    Returns:
        bool: True if file was created/updated, False if skipped
        
    Raises:
        OSError: If file cannot be created
    """
    agent_md_path = Path("AGENT.md")
    
    # Check if file already exists
    if agent_md_path.exists() and not force:
        # Append to existing file instead of overwriting
        try:
            existing_content = agent_md_path.read_text(encoding='utf-8')
            
            # Check if stem integration rules already exist
            if "# Stem Agent Integration Guide" in existing_content:
                print("AGENT.md already contains stem integration rules")
                return False
            
            # Append stem integration rules
            stem_integration_section = """

---

# AI Agent Integration

## Workflow
1. Write intent JSON to `.git/stem/intent/next.json` only if you will change code
2. Make code changes
3. System auto-creates node after changes complete (idle)

## Intent Format
```json
{
    "prompt": "user's request",
    "summary": "what you changed"
}
```

## Example
User: "Add login form"

Intent file:
```json
{
    "prompt": "add login form",
    "summary": "Added LoginForm.jsx with validation"
}
```

Then the system records the intent, waits for changes, and creates a node.

## Rules
- Only write intent if you will change code
- No intent → no node
- Agent suggestions are non-authoritative
 - After any `stem jump`, read `.git/stem/context/current.json`
"""
            
            # Append to existing file
            with open(agent_md_path, 'a', encoding='utf-8') as f:
                f.write(stem_integration_section)
            
            print("Appended stem integration rules to existing AGENT.md")
            return True
            
        except OSError as e:
            raise OSError(f"Failed to append to AGENT.md: {e}")
    
    # Create new file or overwrite if force=True
    agent_md_content = """# AI Agent Integration

## Workflow
1. Write intent JSON to `.git/stem/intent/next.json` only if you will change code
2. Make code changes
3. System auto-creates node after changes complete (idle)

## Intent Format
```json
{
    "prompt": "user's request",
    "summary": "what you changed"
}
```

## Example
User: "Add login form"

Intent file:
```json
{
    "prompt": "add login form",
    "summary": "Added LoginForm.jsx with validation"
}
```

Then the system records the intent, waits for changes, and creates a node.

## Rules
- Only write intent if you will change code
- No intent → no node
- Agent suggestions are non-authoritative
 - After any `stem jump`, read `.git/stem/context/current.json`
"""
    
    try:
        action = "Updated" if agent_md_path.exists() else "Created"
        with open(agent_md_path, 'w', encoding='utf-8') as f:
            f.write(agent_md_content)
        print(f"{action} AGENT.md with integration rules")
        return True
    except OSError as e:
        raise OSError(f"Failed to create AGENT.md: {e}")


def create_agents_md(force: bool = False) -> bool:
    """Generate AGENTS.md with short, strict instructions for agents."""
    agents_md_path = Path("AGENTS.md")
    if agents_md_path.exists() and not force:
        return False
    content = """# Stem Agent Instructions (Read Me First)

If you are an AI coding agent, follow this workflow exactly.

## Workflow
1. Write intent JSON to `.git/stem/intent/next.json` only if you will change code
2. Make the code changes
3. The system auto-creates a stem node after changes complete (idle)
4. After any `stem jump`, read `.git/stem/context/current.json` to restore context
5. If unsure, read `.git/stem/context/agent_prompt.txt` for strict system rules

## Intent JSON format
```json
{
  "prompt": "why you are changing code",
  "summary": "what you changed"
}
```

## Rules
- Do not write intent for discussion-only prompts
- Summary is WHAT, never WHY
- Git remains source of truth; do not run stem commands unless asked
"""
    try:
        action = "Updated" if agents_md_path.exists() else "Created"
        with open(agents_md_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"{action} AGENTS.md with integration rules")
        return True
    except OSError as e:
        raise OSError(f"Failed to create AGENTS.md: {e}")


def get_agent_prompt_text() -> str:
    """Return strict agent prompt instructions for system prompts."""
    return """You are an AI coding agent working inside a Git repo using stem.

Core rules:
1) Only write intent JSON if you will change code.
2) If the user request is discussion-only, do NOT write intent JSON.
3) Intent JSON goes to `.git/stem/intent/next.json` with:
   - prompt: WHY you are changing code
   - summary: WHAT you changed (never WHY)
4) After any `stem jump`, read `.git/stem/context/current.json` to restore context.
5) Do not run stem commands unless the user asks.

When you will change code:
- Write intent JSON first.
- Make code changes.
- The system auto-creates a stem node after changes complete.
"""


def write_agent_prompt_file() -> Path:
    """Write agent prompt instructions to .git/stem/context/agent_prompt.txt."""
    context_dir = Path(".git") / "stem" / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    path = context_dir / "agent_prompt.txt"
    path.write_text(get_agent_prompt_text(), encoding="utf-8")
    return path


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


def process_agent_intent() -> Optional[int]:
    """Process pending agent intent and record as a suggestion.
    
    Reads agent intent, validates it, and records a pending intent.
    Auto-branching is handled by the watcher when changes are present.
    
    Returns:
        Optional[int]: The recorded intent ID, or None if no valid intent exists
    """
    intent = read_agent_intent()
    if intent is None:
        return None
    
    from . import state
    return state.suggest_intent(intent.prompt, intent.summary, source="agent_file")


def create_agent_intent(prompt: str, summary: str) -> bool:
    """Create agent intent JSON file for suggestion-only processing.
    
    This is a helper function that agents can use to declare their intent
    before making changes. The intent must be explicitly confirmed by
    a user before any node is created.
    
    Args:
        prompt: The reason for making changes (WHY)
        summary: Brief description of what will be changed (WHAT)
        
    Returns:
        bool: True if intent was created successfully
        
    Raises:
        OSError: If intent file cannot be created
    """
    try:
        # Ensure intent directory exists
        ensure_intent_directory()
        
        # Create intent data
        intent_data = {
            "prompt": prompt.strip(),
            "summary": summary.strip() if summary else None
        }
        
        # Remove None values
        intent_data = {k: v for k, v in intent_data.items() if v is not None}
        
        # Write intent file
        intent_path = Path(".git/stem/intent/next.json")
        with open(intent_path, 'w', encoding='utf-8') as f:
            json.dump(intent_data, f, indent=2)
        
        print(f"Created agent intent: {prompt}")
        return True
        
    except Exception as e:
        print(f"Failed to create agent intent: {e}")
        return False


def has_pending_intent() -> bool:
    """Check if there's a pending agent intent file.
    
    Returns:
        bool: True if .git/stem/intent/next.json exists
    """
    intent_path = Path(".git/stem/intent/next.json")
    return intent_path.exists()
