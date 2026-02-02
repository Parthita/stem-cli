"""
Enhanced output formatting for stem CLI.
Provides tree visualization and improved display formatting.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime


def build_node_tree(nodes: Dict[str, dict]) -> Tuple[Dict[str, List[str]], List[str]]:
    """Build a tree structure from nodes showing parent-child relationships."""
    children = {}
    roots = []
    
    # Initialize children dict and find roots
    for node_id, node_data in nodes.items():
        children[node_id] = []
        parent = node_data.get('parent')
        if not parent:
            roots.append(node_id)
    
    # Build parent-child relationships
    for node_id, node_data in nodes.items():
        parent = node_data.get('parent')
        if parent and parent in children:
            children[parent].append(node_id)
    
    return children, roots


def _collect_subtree(children: Dict[str, List[str]], root_id: str) -> List[str]:
    """Collect nodes in subtree rooted at root_id (preorder)."""
    order: List[str] = []

    def walk(node_id: str) -> None:
        order.append(node_id)
        for child_id in sorted(children.get(node_id, [])):
            walk(child_id)

    walk(root_id)
    return order


def format_tree_node(node_id: str, node_data: dict, current_head: str,
                    forked: bool, prefix: str = "", is_last: bool = True) -> List[str]:
    """Format a single node for tree display."""
    # Tree symbols
    connector = "└── " if is_last else "├── "
    markers: List[str] = []
    if node_id == current_head:
        markers.append("HEAD")
    status = node_data.get("status", "active")
    if status == "invalid":
        markers.append("INVALID")
    if forked:
        markers.append("FORK")
    marker_text = f" [{', '.join(markers)}]" if markers else ""
    
    # Format the main line
    main_line = f"{prefix}{connector}{node_id}: {node_data['prompt']}{marker_text}"
    
    # Format summary (compact)
    summary = node_data.get('summary', 'No summary')
    summary_line = summary.split('\n')[0]
    if len(summary_line) > 70:
        summary_line = summary_line[:67] + "..."
    
    # Prepare prefix for summary line
    summary_prefix = prefix + ("    " if is_last else "│   ")
    summary_formatted = f"{summary_prefix}    {summary_line}"

    return [main_line, summary_formatted]


def render_tree_blocks(nodes: Dict[str, dict], current_head: str, root_id: Optional[str] = None,
                      include_all_roots: bool = False) -> Tuple[List[List[str]], List[str]]:
    """Render the node tree into blocks. Returns (blocks, node_order)."""
    if not nodes:
        return [], []
    
    children, roots = build_node_tree(nodes)
    node_order: List[str] = []
    blocks: List[List[str]] = []

    def render_subtree(node_id: str, prefix: str = "", is_last: bool = True) -> None:
        node_data = nodes[node_id]
        forked = len(children.get(node_id, [])) > 1
        blocks.append(format_tree_node(node_id, node_data, current_head, forked, prefix, is_last))
        node_order.append(node_id)

        child_nodes = sorted(children.get(node_id, []))
        for i, child_id in enumerate(child_nodes):
            is_last_child = (i == len(child_nodes) - 1)
            child_prefix = prefix + ("    " if is_last else "│   ")
            render_subtree(child_id, child_prefix, is_last_child)

    if include_all_roots or not root_id:
        sorted_roots = sorted(roots)
        for i, root in enumerate(sorted_roots):
            is_last_root = (i == len(sorted_roots) - 1)
            render_subtree(root, "", is_last_root)
            if not is_last_root and len(sorted_roots) > 1:
                blocks.append([""])
    else:
        if root_id in nodes:
            render_subtree(root_id, "", True)

    return blocks, node_order


def _flatten_blocks(blocks: List[List[str]]) -> List[str]:
    lines: List[str] = []
    for block in blocks:
        lines.extend(block)
    return lines


def _paginate_blocks(blocks: List[List[str]], page: int, page_size: int) -> Tuple[List[List[str]], int]:
    if page_size <= 0:
        return blocks, 1
    total_blocks = len([b for b in blocks if b != [""]])
    total_pages = max(1, (total_blocks + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))

    # Flatten blocks into display blocks but count only node blocks
    paged_blocks: List[List[str]] = []
    count = 0
    start = (page - 1) * page_size
    end = start + page_size

    for block in blocks:
        if block == [""]:
            # Only include separators if we already have content on page
            if paged_blocks:
                paged_blocks.append(block)
            continue
        if count >= start and count < end:
            paged_blocks.append(block)
        count += 1

    return paged_blocks, total_pages


def format_global_view(registry) -> str:
    """Format the global repository view with enhanced styling."""
    if not registry.repos:
        return "No stem repositories found.\nInitialize a repository with: stem create"
    
    lines = ["🌳 Global Stem Repositories", ""]
    
    # Sort repositories by last accessed (most recent first)
    sorted_repos = sorted(
        registry.repos.items(), 
        key=lambda x: x[1].last_accessed, 
        reverse=True
    )
    
    # Group by activity (today, this week, older)
    now = datetime.now()
    today_repos = []
    week_repos = []
    older_repos = []
    
    for repo_path, repo_info in sorted_repos:
        days_ago = (now - repo_info.last_accessed).days
        if days_ago == 0:
            today_repos.append((repo_path, repo_info))
        elif days_ago <= 7:
            week_repos.append((repo_path, repo_info))
        else:
            older_repos.append((repo_path, repo_info))
    
    # Format each group
    if today_repos:
        lines.append("📅 Active Today:")
        for repo_path, repo_info in today_repos:
            node_count = f"{repo_info.node_count} nodes" if repo_info.node_count > 0 else "empty"
            lines.append(f"  ├── {repo_info.name} ({node_count})")
            lines.append(f"  │   {repo_path}")
        lines.append("")
    
    if week_repos:
        lines.append("📊 This Week:")
        for repo_path, repo_info in week_repos:
            node_count = f"{repo_info.node_count} nodes" if repo_info.node_count > 0 else "empty"
            lines.append(f"  ├── {repo_info.name} ({node_count})")
            lines.append(f"  │   {repo_path}")
        lines.append("")
    
    if older_repos:
        lines.append("📦 Older:")
        for repo_path, repo_info in older_repos:
            node_count = f"{repo_info.node_count} nodes" if repo_info.node_count > 0 else "empty"
            lines.append(f"  ├── {repo_info.name} ({node_count})")
            lines.append(f"  │   {repo_path}")
        lines.append("")
    
    # Summary
    total = len(registry.repos)
    active_count = len([r for r in sorted_repos if (now - r[1].last_accessed).days <= 7])
    lines.append(f"📈 Summary: {total} repositories ({active_count} active this week)")
    
    return "\n".join(lines)


def format_repository_details(repo_info, nodes: Dict[str, dict], current_head: str) -> str:
    """Format detailed view of a specific repository."""
    lines = [
        f"🏠 Repository: {repo_info.name}",
        f"📁 Path: {repo_info.path}",
        f"🕒 Last accessed: {repo_info.last_accessed.strftime('%Y-%m-%d %H:%M:%S')}",
        f"📊 Node count: {repo_info.node_count}",
        ""
    ]
    
    if nodes:
        lines.append("🌲 Node Tree:")
        lines.append("")
        blocks, _ = render_tree_blocks(nodes, current_head, include_all_roots=True)
        for line in _flatten_blocks(blocks):
            lines.append(f"  {line}" if line.strip() else "")
    else:
        lines.append("📭 No nodes in this repository")
    
    return "\n".join(lines)


def format_jump_success(node_id: str, node_data: dict, previous_head: Optional[str]) -> str:
    """Format success message for node jump."""
    lines = [
        f"✅ Successfully jumped to node {node_id}",
        ""
    ]
    
    # Show what we jumped from
    if previous_head:
        lines.append(f"📍 Previous: {previous_head} → Current: {node_id}")
    else:
        lines.append(f"📍 Now on: {node_id}")
    
    # Show node details
    lines.append(f"🎯 Prompt: {node_data['prompt']}")
    
    # Show summary
    summary = node_data.get('summary', 'No summary')
    summary_line = summary.split('\n')[0]
    if len(summary_line) > 70:
        summary_line = summary_line[:67] + "..."
    lines.append(f"📝 Changes: {summary_line}")
    
    # Show parent relationship
    parent = node_data.get('parent')
    if parent:
        lines.append(f"🔗 Parent: {parent}")
    else:
        lines.append("🌱 Root node")
    
    return "\n".join(lines)


def format_node_creation_success(node_id: str, prompt: str, summary: str, 
                                parent: Optional[str], total_nodes: int) -> str:
    """Format success message for node creation."""
    lines = [
        f"✅ Created node {node_id}: {prompt}",
        ""
    ]
    
    # Show parent relationship
    if parent:
        lines.append(f"🔗 Branched from: {parent}")
    else:
        lines.append("🌱 Root node created")
    
    # Show summary (truncated if too long)
    summary_line = summary.split('\n')[0] if summary else "No changes"
    if len(summary_line) > 80:
        summary_line = summary_line[:77] + "..."
    lines.append(f"📝 Changes: {summary_line}")
    
    # Show repository status
    lines.append(f"📊 Repository now has {total_nodes} nodes")
    
    return "\n".join(lines)


def format_node_list(
    nodes: Dict[str, dict],
    current_head: Optional[str],
    verbose: bool = False,
    root_id: Optional[str] = None,
    include_all_roots: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> str:
    """Format node list with tree structure and pagination."""
    if not nodes:
        return "📭 No nodes found"
    
    if include_all_roots:
        scope = "all roots"
    else:
        scope = root_id or current_head or "root"
    lines = [f"🌲 Node Tree ({len(nodes)} nodes, scope: {scope}):", ""]
    
    if not include_all_roots and not root_id:
        root_id = current_head
    blocks, node_order = render_tree_blocks(
        nodes,
        current_head or "",
        root_id=root_id,
        include_all_roots=include_all_roots,
    )
    paged_blocks, total_pages = _paginate_blocks(blocks, page, page_size)
    for block in paged_blocks:
        lines.extend(block)

    lines.append("")
    lines.append(f"Page {min(page, total_pages)}/{total_pages} (page size: {page_size})")

    if verbose:
        lines.extend(["", "📋 Detailed Information (paged):", ""])
        # Show details for nodes that appear in this page
        page_nodes = []
        count = 0
        start = (page - 1) * page_size
        end = start + page_size
        for node_id in node_order:
            if count >= start and count < end:
                page_nodes.append(node_id)
            count += 1

        for node_id in page_nodes:
            node_data = nodes[node_id]
            head_indicator = " ← HEAD" if node_id == current_head else ""
            status = node_data.get("status", "active")
            status_info = f" ({status})" if status != "active" else ""
            lines.append(f"🔹 {node_id}: {node_data['prompt']}{head_indicator}{status_info}")

            parent = node_data.get("parent")
            parent_info = f"Parent: {parent}" if parent else "Root node"
            lines.append(f"   └─ {parent_info}")

            ref = node_data.get("ref", "")
            if ref.startswith("refs/heads/"):
                branch_name = ref[11:]
                lines.append(f"   └─ Branch: {branch_name}")

            summary = node_data.get("summary", "No summary")
            lines.append(f"   └─ Summary: {summary}")
            lines.append("")
    
    return "\n".join(lines)
