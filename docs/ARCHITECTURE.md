# Technical Architecture

This document outlines the technical design, data structures, and algorithms implemented in **Antigravity-Cheaper**.

---

## 1. System Overview

Antigravity-Cheaper sits between local workspace files and the LLM agent's context window. Its objective is to eliminate quadratic context growth ($O(N^2)$) in long-horizon agentic tasks by enforcing progressive disclosure:

```text
Local Workspace (2,500+ LOC / Large Logs)
                     │
                     ▼
  [ AST Parser & Slicer (ast.py, pack.py) ]
                     │  (Strips bodies, bounds error frames)
                     ▼
  [ Symbol Graph & PageRank (repomap.py) ]
                     │  (Ranks symbols, fits token budget)
                     ▼
  [ FastMCP stdio Server (mcp_server.py) ]
                     │  (Serves bounded queries to Agent)
                     ▼
  [ Frozen Prompt Invariants (prefix_lock.py) ]
                     │  (Guarantees Gemini context cache hits)
                     ▼
      LLM Agent Context Window (< 85% Cache Hits, -17% Reasoning Tokens)
```

---

## 2. Symbol Graph & PageRank Ranking (`agy_repomap.py`)

When an agent needs to understand a repository, dumping full directory listings or whole files consumes thousands of unbudgeted tokens.

### Graph Construction
1. **AST Extraction**: Each Python source file is parsed using Python's `ast` module into a directed reference graph $G = (V, E)$.
   - **Nodes ($V$)**: Defined classes, methods, and top-level functions.
   - **Edges ($E$)**: Function calls, class instantiations, inheritance, and module imports.
2. **Personalized PageRank**: To prioritize entrypoints and public interfaces over internal utility functions, the graph is ranked using power iteration with a damping factor of $d = 0.85$.
   - The personalization vector biases weight toward top-level module exports and central service interfaces.
3. **Binary Search Token Budget Fitter**:
   - Symbols are sorted by centrality score.
   - The renderer formats symbols into an indented outline.
   - If the outline exceeds the configured token budget (default: 1,200 tokens), low-centrality leaf symbols are iteratively pruned until the output strictly satisfies the budget constraint.

---

## 3. Gemini Context Caching Mechanics (`agy_prefix_lock.py`)

Google Gemini 2.5 and 3.x models offer automated prompt caching discounts (up to 90% cost reduction) for input tokens matching an identical prefix $\ge 2,048$ tokens.

### The Invalidation Problem
In naive multi-turn agent runs, prompt caches are frequently invalidated by:
- Volatile nonces or dynamic timestamps inserted into early prompt layers.
- Operating system line ending discrepancies (`\r\n` on Windows vs `\n` on Linux).
- Reordering of tool definitions or system rules.

### Solution: Deterministic Merkle Prefix Locking
1. **Layer 1 (System Prompt)** and **Layer 2 (Project Invariants)** are canonicalized to standard Unix line endings (`\n`) and UTF-8 bytes.
2. A SHA-256 Merkle root is computed over the static invariant blocks.
3. The prefix lock script verifies that the invariant prefix remains bit-identical across turns, ensuring that the model's server-side context cache is preserved throughout the session (>85% cache hit rate).

---

## 4. FastMCP Symbol Server (`agy_mcp_server.py`)

The toolkit provides a lightweight Model Context Protocol (MCP) server communicating over `stdio` using JSON-RPC 2.0.

### Exposed Tools
- **`get_repo_map(budget: int = 1200)`**: Returns the PageRank-ranked repository symbol outline within the specified token limit.
- **`get_file_skeleton(file_path: str)`**: Returns an AST skeleton of the target file where all function and method implementations are replaced with `...`.
- **`get_bounded_slice(file_path: str, needle: str, context_lines: int = 5)`**: Locates the specific string/symbol and returns only the surrounding line slice, preventing full-file dumps.
- **`get_symbol_subgraph(symbol_name: str, hops: int = 2)`**: Returns immediate callers and callees of a specific symbol.

---

## 5. Bounded Error Slicing (`agy_pack.py`)

In large test suites (e.g., distributed systems with thousands of log lines), test failures often produce 10,000+ line terminal dumps. When an agent blindly ingests the entire dump, context is flooded with repetitive stack traces.

`agy_pack.py` processes raw output streams:
1. Detects traceback frames and assertion error blocks using pattern matchers.
2. Extracts the initial failure frame and the concluding exception message.
3. Slices 5 lines of contextual code around the failure site.
4. Truncates intermediate repetitive polling logs, reducing ingested error characters by up to 90%.

---

## 6. Telemetry & Accounting (`agy_ledger.py`)

To prevent gaming metrics by generating short, incomplete answers, all evaluations are audited in a local JSONL ledger (`benchmarks/data/benchmark_usage.jsonl`).

### Recorded Fields
- `task_id`: Unique identifier for the benchmark workload.
- `variant`: Strategy variant (`baseline` vs `token_guard`).
- `input_tokens` / `cached_input_tokens`: Raw token counts from API telemetry.
- `reasoning_output_tokens`: Internal thinking tokens generated during reasoning turns.
- `retries`: Number of test runs or repair cycles.
- `elapsed_seconds`: Wall-clock execution time.
- `accepted`: Boolean flag indicating whether 100% of validation tests passed.
