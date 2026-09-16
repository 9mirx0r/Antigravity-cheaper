#!/usr/bin/env python3
"""Token-Efficient FastMCP Symbol Server for Antigravity (agy_mcp_server.py).

Implements the Model Context Protocol (MCP) JSON-RPC 2.0 stdio transport.
Exposes surgical AST and symbol navigation tools with minimal schema tax:
  - get_repo_map: Budget-fitted Personalized PageRank symbol tree.
  - get_symbol_subgraph: Definition locations and referencing callers for a symbol.
  - get_file_skeleton: AST elided signatures preserving types and docstrings.
  - get_bounded_slice: Focused log and source slices without whole-file dumping.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Enforce UTF-8 stdio encoding to prevent Windows cp1252 corruption
if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Support both package-relative and standalone imports
try:
    from .agy_ast import generate_skeleton
    from .agy_pack import pack_file
    from .agy_repomap import RepoMapGraph
except ImportError:
    SCRIPT_DIR = Path(__file__).resolve().parent
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from agy_ast import generate_skeleton
    from agy_pack import pack_file
    from agy_repomap import RepoMapGraph

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "agy-symbol-server"
SERVER_VERSION = "1.0.0"

# Strict Token Efficiency Contract: 1-2 sentence docstrings, flat parameters
TOOLS_SCHEMA = [
    {
        "name": "get_repo_map",
        "description": "Returns a budget-fitted Personalized PageRank symbol map of the workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory path to map (defaults to current directory).",
                },
                "budget_tokens": {
                    "type": "integer",
                    "description": "Maximum token budget for the map (default: 1200).",
                },
                "focus_file": {
                    "type": "string",
                    "description": "Optional focus file to bias PageRank traversal.",
                },
            },
        },
    },
    {
        "name": "get_symbol_subgraph",
        "description": "Finds where a symbol is defined and lists all files that reference it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol_name": {
                    "type": "string",
                    "description": "Identifier name (class, function, or method).",
                },
                "root_dir": {
                    "type": "string",
                    "description": "Root directory path to search (defaults to current directory).",
                },
            },
            "required": ["symbol_name"],
        },
    },
    {
        "name": "get_file_skeleton",
        "description": "Returns the AST skeleton of a file with function/method bodies elided.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the source file to skeletonize.",
                },
                "root_dir": {
                    "type": "string",
                    "description": "Optional root directory to resolve relative file paths.",
                },
                "style": {
                    "type": "string",
                    "enum": ["ellipsis", "pass"],
                    "description": "Placeholder style for elided bodies (default: ellipsis).",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "get_bounded_slice",
        "description": "Extracts matching lines and context from a log or file within a character budget.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the log or source file.",
                },
                "root_dir": {
                    "type": "string",
                    "description": "Optional root directory security boundary.",
                },
                "contains": {
                    "type": "string",
                    "description": "Substring to search for and isolate.",
                },
                "context": {
                    "type": "integer",
                    "description": "Number of context lines before and after match (default: 2).",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum character budget (default: 2000).",
                },
            },
            "required": ["file_path", "contains"],
        },
    },
]


def execute_tool(name: str, arguments: Dict[str, Any]) -> str:
    """Execute tool and return clean text result."""
    if name == "get_repo_map":
        root = arguments.get("root_dir", ".")
        budget = arguments.get("budget_tokens", 1200)
        focus = [arguments["focus_file"]] if arguments.get("focus_file") else None
        graph = RepoMapGraph(root)
        graph.scan()
        return graph.render_map(focus_files=focus, budget_tokens=budget)

    elif name == "get_symbol_subgraph":
        root = arguments.get("root_dir", ".")
        sym = arguments["symbol_name"]
        graph = RepoMapGraph(root)
        graph.scan()
        res = graph.get_symbol_subgraph(sym)
        return json.dumps(res, indent=2)

    elif name == "get_file_skeleton":
        root = Path(arguments.get("root_dir", ".")).resolve()
        file_path = Path(arguments["file_path"])
        if not file_path.is_absolute():
            file_path = root / file_path
        style = arguments.get("style", "ellipsis")
        if not file_path.exists():
            return f"Error: File '{file_path}' does not exist."
        return generate_skeleton(str(file_path), style=style)

    elif name == "get_bounded_slice":
        root = arguments.get("root_dir", ".")
        file_path = arguments["file_path"]
        contains = arguments["contains"]
        context = arguments.get("context", 2)
        max_chars = arguments.get("max_chars", 2000)
        try:
            packed = pack_file(
                file_path,
                root_dir=root,
                max_chars=max_chars,
                contains=contains,
                context=context,
            )
            return packed.get("formatted_text", "")
        except Exception as e:
            return f"Error packing file: {e}"

    raise ValueError(f"Unknown tool: {name}")


class MCPServer:
    """Stdio JSON-RPC 2.0 MCP Server."""

    def __init__(self):
        self.running = True

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    },
                },
            }

        elif method == "notifications/initialized":
            return None

        # Ignore unhandled notifications (JSON-RPC 2.0: notifications must not receive a response)
        if req_id is None:
            return None

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS_SCHEMA},
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            try:
                text_out = execute_tool(tool_name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": text_out}],
                        "isError": False,
                    },
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Tool error: {str(e)}"}],
                        "isError": True,
                    },
                }

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        # Method not found
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def run_stdio(self):
        """Main stdio JSON-RPC loop."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                resp = self.handle_request(req)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()


def run_self_test():
    """Run internal sanity verification on all tools."""
    server = MCPServer()

    # 1. Test initialize
    init_res = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_res["result"]["serverInfo"]["name"] == SERVER_NAME

    # 2. Test tools/list
    tools_res = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert len(tools_res["result"]["tools"]) == 4

    # 3. Test tools/call: get_repo_map
    map_res = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_repo_map", "arguments": {"root_dir": str(SCRIPT_DIR)}},
        }
    )
    assert not map_res["result"]["isError"]
    assert "Repository Map" in map_res["result"]["content"][0]["text"]

    # 4. Test tools/call: get_symbol_subgraph
    sub_res = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "get_symbol_subgraph",
                "arguments": {"symbol_name": "execute_tool", "root_dir": str(SCRIPT_DIR)},
            },
        }
    )
    assert not sub_res["result"]["isError"]
    assert "execute_tool" in sub_res["result"]["content"][0]["text"]

    # 5. Test tools/call: get_file_skeleton
    skel_res = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "get_file_skeleton",
                "arguments": {"file_path": str(Path(__file__).resolve())},
            },
        }
    )
    assert not skel_res["result"]["isError"]
    assert "class MCPServer:" in skel_res["result"]["content"][0]["text"]

    print("All FastMCP server tools verified successfully!")


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_self_test()
    else:
        server = MCPServer()
        server.run_stdio()
