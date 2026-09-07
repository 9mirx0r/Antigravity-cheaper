# FastMCP Technical Patterns & Architecture for Antigravity

This reference manual complements `mcp-builder` with technical specifications, strict typing guidelines, transport trade-offs, and reference implementations of token-efficient FastMCP servers.

---

## 1. FastMCP Architecture & Core Decorators

FastMCP abstracts the JSON-RPC Model Context Protocol specification through an idiomatic Python API powered by decorators and Pydantic validation.

### 1.1 `@mcp.tool()`
Exposes executable functions to the agent. Antigravity translates function signatures, type annotations, and docstrings directly into the tool's JSON Schema within the System Prompt.

```python
@mcp.tool()
async def inspect_entity(
    name: str = Field(..., description="Canonical entity name."),
    verbose: bool = Field(False, description="Include extended metadata if True."),
    ctx: Context = None
) -> dict:
    """Retrieves operational summary for a system entity."""
    ...
```

*Design rules*:
- Arguments with default values are marked optional in the JSON Schema.
- Required arguments without defaults should use `Field(...)`.
- Include `ctx: Context = None` to receive the injected context object for logging and progress reporting.

### 1.2 `@mcp.resource()`
Exposes read-only static or dynamic data through URI schemes (e.g., `workspace://config/schema`). Unlike tools (which compute actions or produce side effects), resources represent structured read-only documents.

```python
@mcp.resource("workspace://status")
async def get_workspace_status() -> str:
    """Returns synthetic workspace operational status."""
    return '{"ready": true, "environment": "production"}'
```

*AGY Usage*: Prefer `@mcp.tool()` for parameterized searches or filters. Reserve `@mcp.resource()` for static configuration documents.

### 1.3 `@mcp.prompt()`
Exposes parameterized instruction templates invocable via slash commands or workflow triggers.

```python
@mcp.prompt()
def review_commit(hash_id: str) -> str:
    """Generates a structured review prompt for a specific commit."""
    return f"Review changes in commit {hash_id} focusing on security boundaries and token discipline."
```

---

## 2. Strict Typing & Schema Minimization

The System Prompt token footprint in Antigravity is directly proportional to tool schema complexity. Follow these guidelines:

### 2.1 Primitive Types vs Complex Models

| Python Type | Generated JSON Schema | Token Cost |
| :--- | :--- | :--- |
| `str`, `int`, `float`, `bool` | Simple `"type": "string"`, etc. | Minimal (~8 tokens) |
| `Optional[str] = None` | `"type": "string"`, not in `required` | Minimal (~10 tokens) |
| `list[str]` | `"type": "array"`, `"items": {"type": "string"}` | Low (~18 tokens) |
| Nested Pydantic Model | Deep nested `$defs` and property objects | High (~120–400 tokens) |
| Polymorphic Unions (`Union[A, B, C]`) | Multiple `anyOf`/`oneOf` schema blocks | Massive (~300–800 tokens) |

**Rule**: Keep tool parameters flat. Pass primitives and parse structured combinations internally within the server.

---

## 3. Cursor Pagination Implementation Pattern

```python
import base64
import json
from typing import Any, Dict, List, Optional
from pydantic import Field

def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()

def decode_cursor(cursor: Optional[str]) -> int:
    if not cursor:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        return 0

def paginate_records(
    records: List[Dict[str, Any]],
    limit: int = 20,
    cursor: Optional[str] = None,
    fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    safe_limit = max(1, min(limit, 50))
    offset = decode_cursor(cursor)
    
    sliced = records[offset : offset + safe_limit]
    has_more = (offset + safe_limit) < len(records)
    next_cursor = encode_cursor(offset + safe_limit) if has_more else None

    # Field projection
    if fields:
        field_set = set(fields)
        items = [{k: v for k, v in item.items() if k in field_set} for item in sliced]
    else:
        items = sliced

    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "total_count": len(records),
    }
```

---

## 4. Transport Protocols: Stdio vs SSE

| Dimension | Stdio (Standard I/O) | SSE (Server-Sent Events / HTTP) |
| :--- | :--- | :--- |
| **Communication** | Subprocess stdin / stdout | HTTP streaming via localhost |
| **Use Case in AGY** | Local workspace scripts (`.agents/`) | Shared microservices, Docker containers |
| **Overhead** | Instant startup (<50ms), 0 network ports | HTTP server listening on TCP port |
| **Debugging** | Logs via `ctx.info()` to stderr | Standard HTTP request logs |

**Recommendation for AGY**: Default to `stdio` transport for all workspace tools. It guarantees zero port collisions, requires no daemon management, and launches natively alongside agent sessions.
