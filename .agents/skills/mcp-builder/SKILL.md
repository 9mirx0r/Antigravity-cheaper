---
name: mcp-builder
description: >-
  Designs, builds, and configures token-efficient FastMCP servers in Antigravity.
  Use when exposing custom tools, local utilities, or APIs via MCP
  to guarantee minimal context consumption and mitigate Tool Schema Tax.
---

# MCP Builder: Token-Efficient FastMCP Servers

This skill provides architectural guidelines, design patterns, and configuration conventions for building **FastMCP** (Model Context Protocol in Python) servers optimized for **Google Antigravity (AGY)**.

Core Objective: Equip agents with high-leverage tools without saturating the context window or degrading reasoning performance.

---

## 1. Token Efficiency Contract

Every registered MCP tool translates to a JSON Schema specification injected into the **System Prompt** on **every conversation turn**. This incurs the **Tool Schema Tax**: tools with bloated schemas, verbose docstrings, or redundant parameters permanently consume input tokens.

### Contract Rules

1. **1-2 Sentence Docstrings (Mitigating Tool Schema Tax)**:
   - The Python function docstring directly populates the tool's `description` in the JSON Schema exposed to the LLM.
   - **Strict limit**: 1 to 2 concise, unambiguous sentences.
   - Must answer: *What does the tool do, and what key data does it return?*
   - **Prohibited**: Background history, markdown usage examples, or extensive caveats inside tool docstrings.

2. **Flat, Primitive Schemas**:
   - Favor primitive types (`str`, `int`, `float`, `bool`) or flat string lists (`list[str]`).
   - Avoid deeply nested Pydantic models or polymorphic unions as arguments; they inflate JSON Schema definitions exponentially.

3. **Mandatory Pagination**:
   - Tools must never return unbounded collections.
   - Any tool querying or listing entities must implement:
     - `limit: int = 20` (with a defensive upper cap of 50 in implementation).
     - `cursor: Optional[str] = None` (or `offset: int = 0`).
   - Responses must include `items`, `next_cursor` (or `next_offset`), and a boolean `has_more`.

4. **Field Projection**:
   - For entities with extensive attributes (file metadata, database rows, AST records), provide:
     - `fields: Optional[list[str]] = None`
   - If omitted, return only essential identifying fields (e.g. `id`, `name`, `line`), never raw dumps.

5. **Defensive Truncation & Summaries**:
   - Tools returning multi-line text (diffs, logs, file snippets) must cap lines (`max_lines: int = 50`) and indicate truncation explicitly: `"... [Output truncated at 50 lines. Use cursor/offset for more]"`.

---

## 2. Python FastMCP Blueprint

FastMCP is the high-level reference framework for Python MCP servers (`pip install "mcp[cli]"`).

### Standard Server Structure

```python
from mcp.server.fastmcp import FastMCP, Context
from pydantic import Field

mcp = FastMCP("WorkspaceTools")

@mcp.tool()
async def search_records(
    query: str = Field(..., description="Search query string."),
    limit: int = Field(20, description="Max results (cap 50)."),
    offset: int = Field(0, description="Pagination start offset."),
    ctx: Context = None
) -> dict:
    """Searches records by query with bounded pagination."""
    safe_limit = max(1, min(limit, 50))
    if ctx:
        await ctx.info(f"Query: {query}, limit: {safe_limit}")
    return {"items": [{"id": "rec_1", "name": query}], "has_more": False}

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### Key Implementation Guidelines:
- **`Context` for Observability**: Inject `ctx: Context` for logging. FastMCP uses `stdout` for JSON-RPC messages; raw `print()` calls corrupt the channel.
- **Clean Error Handling**: Return structured dictionaries with `"error"` and `"message"` keys rather than uncaught 40-line stack traces.

---

## 3. Configuration in `mcp_config.json`

Antigravity resolves MCP server configs from:
1. **Workspace Configuration**: `.agents/mcp_config.json`.
2. **Global Configuration**: `~/.gemini/config/mcp_config.json`.

### Stdio Configuration Example (Local)

```json
{
  "mcpServers": {
    "workspace-tools": {
      "command": "python",
      "args": [
        "-u",
        ".agents/scripts/mcp_server.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "WORKSPACE_ROOT": "."
      }
    }
  }
}
```

---

## 4. Technical Reference

For advanced FastMCP patterns, cursor pagination implementations, and reference servers (AST Symbol Searcher & Git Diff Chunker):

👉 [FastMCP Patterns Reference](./references/fastmcp_patterns.md)
