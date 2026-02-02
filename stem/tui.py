"""
TUI Layer - Read-only browser and jump confirmation.

Provides a curses-based interface for navigating large node histories.
"""

from __future__ import annotations

import curses
from typing import Dict, List, Optional, Tuple

from .display import render_tree_blocks


class TuiExit(Exception):
    """Used to signal a controlled exit from the TUI."""


def _flatten_blocks(blocks: List[List[str]]) -> Tuple[List[str], List[Optional[str]]]:
    lines: List[str] = []
    line_to_node: List[Optional[str]] = []
    for block in blocks:
        if block == [""]:
            lines.append("")
            line_to_node.append(None)
            continue
        for i, line in enumerate(block):
            lines.append(line)
            # Only the first line is used for selection
            line_to_node.append(None if i > 0 else "NODE")
    return lines, line_to_node


def _build_filtered_nodes(nodes: Dict[str, dict], query: str) -> Dict[str, dict]:
    if not query:
        return nodes
    query_lower = query.lower()
    included = set()

    def include_ancestors(node_id: str) -> None:
        current = node_id
        while current:
            if current in included:
                break
            included.add(current)
            parent = nodes[current].get("parent")
            current = parent if parent in nodes else None

    for node_id, node_data in nodes.items():
        prompt = node_data.get("prompt", "")
        if query_lower in node_id.lower() or query_lower in prompt.lower():
            include_ancestors(node_id)

    return {node_id: nodes[node_id] for node_id in nodes if node_id in included}


def _build_tree_lines(nodes: Dict[str, dict], current_head: Optional[str]) -> Tuple[List[str], List[Optional[str]], List[str]]:
    blocks, node_order = render_tree_blocks(
        nodes,
        current_head or "",
        include_all_roots=True,
    )
    lines, line_to_node = _flatten_blocks(blocks)
    # Map line_to_node: mark first line of each block with node id using node_order
    node_iter = iter(node_order)
    current_node = next(node_iter, None)
    for i, marker in enumerate(line_to_node):
        if marker == "NODE":
            line_to_node[i] = current_node
            current_node = next(node_iter, None)
    return lines, line_to_node, node_order


def _draw_details(stdscr, nodes: Dict[str, dict], node_id: Optional[str], max_height: int, max_width: int) -> None:
    if not node_id or node_id not in nodes:
        return
    node = nodes[node_id]
    lines = [
        f"Node: {node_id}",
        f"Status: {node.get('status', 'active')}",
        f"Parent: {node.get('parent') or 'None'}",
        f"Ref: {node.get('ref', '')}",
        "Prompt:",
        f"  {node.get('prompt', '')}",
        "Summary:",
        f"  {node.get('summary', '')}",
    ]
    for i, line in enumerate(lines[:max_height]):
        stdscr.addnstr(i, 0, line, max_width - 1)


def _draw_tree(stdscr, lines: List[str], top: int, selected_line: int, start_col: int, height: int, width: int) -> None:
    for i in range(height):
        line_idx = top + i
        if line_idx >= len(lines):
            break
        line = lines[line_idx]
        if line_idx == selected_line:
            stdscr.attron(curses.A_REVERSE)
            stdscr.addnstr(i, start_col, line, width - 1)
            stdscr.attroff(curses.A_REVERSE)
        else:
            stdscr.addnstr(i, start_col, line, width - 1)


def run_tui(nodes: Dict[str, dict], current_head: Optional[str]) -> Optional[str]:
    """Run the TUI. Returns selected node id to jump, or None."""

    def _main(stdscr) -> Optional[str]:
        curses.curs_set(0)
        stdscr.nodelay(False)
        stdscr.keypad(True)

        query = ""
        filtered = nodes
        lines, line_to_node, node_order = _build_tree_lines(filtered, current_head)

        selected_line = 0
        top = 0
        status = "q: quit  /: search  Enter: jump"
        pending_jump = False

        def _current_node() -> Optional[str]:
            if 0 <= selected_line < len(line_to_node):
                return line_to_node[selected_line]
            return None

        while True:
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            left_width = max(30, width // 2)
            right_width = width - left_width - 1

            _draw_details(stdscr, filtered, _current_node(), height - 2, left_width)
            _draw_tree(stdscr, lines, top, selected_line, left_width + 1, height - 2, right_width)

            stdscr.addnstr(height - 2, 0, status, width - 1)
            stdscr.addnstr(height - 1, 0, f"Filter: {query}", width - 1)
            stdscr.refresh()

            ch = stdscr.getch()
            if ch in (ord("q"), 27):
                return None
            if ch in (curses.KEY_UP, ord("k")):
                if selected_line > 0:
                    selected_line -= 1
                if selected_line < top:
                    top = selected_line
            elif ch in (curses.KEY_DOWN, ord("j")):
                if selected_line < len(lines) - 1:
                    selected_line += 1
                if selected_line >= top + (height - 2):
                    top = selected_line - (height - 3)
            elif ch in (curses.KEY_NPAGE, ):
                selected_line = min(len(lines) - 1, selected_line + (height - 2))
                top = min(selected_line, max(0, len(lines) - (height - 2)))
            elif ch in (curses.KEY_PPAGE, ):
                selected_line = max(0, selected_line - (height - 2))
                top = max(0, selected_line)
            elif ch in (curses.KEY_HOME, ):
                selected_line = 0
                top = 0
            elif ch in (curses.KEY_END, ):
                selected_line = max(0, len(lines) - 1)
                top = max(0, selected_line - (height - 3))
            elif ch == ord("/"):
                status = "Enter search query: "
                stdscr.addnstr(height - 2, 0, status, width - 1)
                stdscr.refresh()
                curses.echo()
                query = stdscr.getstr(height - 1, 8, width - 9).decode("utf-8")
                curses.noecho()
                filtered = _build_filtered_nodes(nodes, query)
                lines, line_to_node, node_order = _build_tree_lines(filtered, current_head)
                selected_line = 0
                top = 0
                status = "q: quit  /: search  Enter: jump"
            elif ch in (curses.KEY_ENTER, 10, 13):
                node_id = _current_node()
                if not node_id:
                    continue
                status = f"Jump to node {node_id}? (y/n)"
                pending_jump = True
            elif pending_jump and ch in (ord("y"), ord("Y")):
                node_id = _current_node()
                return node_id
            elif pending_jump and ch in (ord("n"), ord("N")):
                status = "q: quit  /: search  Enter: jump"
                pending_jump = False

        return None

    return curses.wrapper(_main)
