---
name: token-guard
description: >-
  Optimizes token consumption and quota management in complex engineering tasks, massive log debugging, deep codebase exploration, and long-horizon agentic workflows. Activates on context saturation, voluminous traces, multi-file inspection, or extended runs to enforce Progressive Disclosure, Gemini Context Caching preservation (>85% hit rate), and compact handoffs.
---

# Token Guard: Quota Control & Context Engineering

Token Guard is a specialized skill designed to eradicate quadratic context growth ($O(N^2)$), safeguard tokens-per-minute (TPM) limits, and maximize **Gemini Context Caching** efficiency (>85% cache hit rate).

Core Axiom: **Spend attention only where it changes a technical decision**.

---

## 1. Attention Budgeting Rules

1. **Critical Attention vs. Noise**:
   - Every injected token must inform an imminent branching decision or technical action.
   - If an artifact contains 90%+ irrelevant data, whole-file dumping is prohibited.
2. **No Blind Dumps**:
   - Never use unbounded `view_file` on files >100 lines without inspecting symbols or locating regions via `grep_search`.
   - Never run unbounded commands that dump arbitrary output into the context window.

---

## 2. Progressive Disclosure & Tool Suite

Information must be acquired in layers of increasing depth:

```
[Level 0: Project Map] -> [Level 1: AST Skeletons] -> [Level 2: Bounded Views] -> [Level 3: Exact Slices]
```

### 2.0 Global Workspace Map & Causal Pathfinding (`scripts/agy_repomap.py`)
- **When to invoke**: At session start or when investigating cross-module dependencies and error root causes in <1,200 tokens.
- **Usage**:
  - `python scripts/agy_repomap.py map --root <dir> [--budget 1200] [--focus <file>]`: Computes Personalized PageRank over symbol references and renders a budget-fitted symbol tree.
  - `python scripts/agy_repomap.py subgraph --root <dir> --symbol <name>`: Queries all definitions and referencing files for a symbol.
  - `python scripts/agy_repomap.py path --root <dir> --from-symbol <A> --to-symbol <B>`: Computes shortest directed causal dependency chain between two symbols, emitting sub-60 token slices.
  - `python scripts/agy_repomap.py causal --root <dir> --query "<error or stack trace>"`: Identifies symbols in an error trace and traces upstream caller lineages.

### 2.1 AST Structural Inspection (`scripts/agy_ast.py`)
- **When to invoke**: Initial exploration of modules or APIs to learn classes, functions, type hints, and docstrings without reading implementation bodies.
- **Usage**: Run `python scripts/agy_ast.py skeleton --source <file>` to extract a ~45-token skeleton with elided bodies (`...`).

### 2.2 Bounded Views & Literal Focus (`scripts/agy_pack.py`)
- **When to invoke**: After large test runs, CI logs, or compiler errors exceeding 50 lines.
- **Usage**:
  - `pack --source <log> [--contains <text>] [--context 2]`: Extracts matching lines, error frames, head, and tail within a strict character budget (default 4000).
  - `expand --pack <pack.json> --start <L1> --end <L2>`: Retrieves exact source lines after validating SHA-256 integrity.

### 2.3 Deterministic Local Handoff & Circuit Breaker (`scripts/agy_handoff.py`)
- **When to invoke**: When preparing payloads for subagent delegation or phase handoffs.
- **Usage (Local Threshold Routing)**:
  - `prepare --source <file> [--full-limit 24000] [--pack-limit 3500]`:
    - Content ≤ 24 KB (~6k tokens): Routes `full` in 1 turn, preventing multi-turn expansion overhead (+97% tokens).
    - Content > 24 KB: Routes `pack` as a bounded view.
  - **Circuit Breaker**: If ≥ 2 recovery attempts occur on unchanged source hash, halts repeated packing and directs the agent to focused direct reading.

### 2.4 Dependency Capsules (`scripts/agy_capsule.py`)
- **When to invoke**: For static specifications, schemas, or directory trees that must remain unchanged.
- **Usage**: `seal --claim <text> --file <path> --kind static` creates a cryptographic baseline. `status --capsule <file>` returns `dependencies_match` (exit code 0) if disk state is identical.

### 2.5 Token Accounting Ledger (`scripts/agy_ledger.py`)
- **When to invoke**: Track Gemini input, cached input, output, and reasoning tokens in JSONL format to calculate cost per accepted outcome without saving prompts.
- **Usage**: `record --task-id <id> --variant <var> ...` and `summary --ledger <file>`.

### 2.6 Hardware Prefix-Locking Engine (`scripts/agy_prefix_lock.py`)
- **When to invoke**: Freeze Layers 1 & 2 to surpass the 2,048/4,096 token cache threshold and guarantee >85% cache hit rate.
- **Usage**: `build --root <dir> [--target-tokens 2500] --out prefix_lock.json` and `verify --manifest prefix_lock.json`.

### 2.7 FastMCP Symbol & Graph Server (`scripts/agy_mcp_server.py`)
- **When to invoke**: Exposes surgical tools via stdio MCP (`get_repo_map`, `get_symbol_subgraph`, `get_file_skeleton`, `get_bounded_slice`).
- **Usage**: Configured in `.agents/mcp_config.json`. Self-test with `python scripts/agy_mcp_server.py --test`.

### 2.8 Cognitive Scaffolding & Swarm Decomposition (`scripts/agy_pipeline.py`)
- **When to invoke**: Orchestrates the 3-stage Architect -> Implementer -> Gatekeeper Critic workflow, and partitions complex specifications into parallel worker manifests.
- **Usage**:
  - `init --task-id <id> --objective <goal> --state-file <f>`: Initializes stage machine.
  - `spec --state-file <f> --contract <c> --file <f>`: Records immutable architectural contracts.
  - `decompose --state-file <f> [--num-workers <n>] [--out-dir <d>]`: Partitions spec into contract-isolated, parallel worker manifests.
  - `receipt --state-file <f> --file <f> --tests-passed true`: Records implementer verification.
  - `review --state-file <f> --verdict SHIP|FIX_FIRST|RETHINK`: Evaluates gatekeeper shipment.

### 2.9 Persistent Zero-Tax Memory (`scripts/agy_memory.py`)
- **When to invoke**: Preserves immutable decisions, conventions, bug lessons, and architecture choices across sessions without paying MCP Tool Schema Tax.
- **Usage**:
  - `save --key <family/desc> --title <title> --content <text> [--category architecture|bug|decision|pattern|config]`: Upserts memory with revision tracking.
  - `search --query <text>`: Lexical full-text search with FTS5 and BM25 ranking.
  - `context [--project <name>]`: Renders a compact Layer-2 context block ready for Prefix-Locked caching.

---

## 3. Compact Working Handoff

Every 3 to 5 turns or after completing an exploratory phase, consolidate session state into Layer 3 format:

```markdown
### HANDOFF COMPACT
- **Objective**: [Exact, unambiguous goal]
- **Verified Facts**:
  - [Empirically verified fact 1]
  - [Empirically verified fact 2]
- **Touched Files**:
  - [Relative path and line ranges inspected or changed]
  - [Discarded hypotheses to prevent loops]
- **Next Actions**:
  - [Immediate next command or edit]
```

---

## 4. Visible Lifecycle Tags

Prepend lifecycle tags to responses to enforce attention discipline:

| Tag | Meaning |
| :--- | :--- |
| `[ROUTE]` | Routing choice (e.g. `agy_ast.py` vs. direct read; `full` vs `pack`). |
| `[DELEGATE]` | Subagent delegation in a clean conversation context. |
| `[RESULT]` | Synthesized conclusion after noise stripping. |
| `[REVIEW]` | Transfer of git diff and test evidence to gatekeeper reviewer. |

---

## 5. Technical References

- **[4-Layer Context Architecture (Gemini Context Caching)](references/context_layers.md)**: Prefix stability rules, caching thresholds (2048/4096 tokens), and 90% discount preservation.
- **[Read-Only Reviewer Protocol (Gatekeeper)](references/reviewer_protocol.md)**: Tri-state gatekeeper verification (`ship`, `fix-first`, `rethink`).
