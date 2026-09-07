# Technical Architecture & Core Pillars Deep Dive

This document provides the exhaustive technical specifications, mathematical foundations, and implementation details of **Antigravity-Cheaper**.

---

## 1. Mathematical Formulations

### 1.1 Personalized PageRank (PPR) Power Iteration
In codebases with thousands of symbols, dumping full directory trees overwhelms the LLM context window. Antigravity-Cheaper constructs an AST call-and-import graph $G = (V, E)$ where nodes $V$ represent classes and functions, and directed edges $E$ represent references.

The centrality vector $\mathbf{r}$ is computed using Personalized PageRank with inverse document frequency (IDF) edge weighting:

$$\mathbf{r}^{(k+1)} = (1 - d) \mathbf{p} + d \mathbf{M} \mathbf{r}^{(k)}$$

Where:
- $d = 0.85$ is the damping factor.
- $\mathbf{p}$ is the personalization vector, heavily weighting top-level interfaces and core modules.
- $\mathbf{M}$ is the column-stochastic transition matrix:

$$M_{ij} = \frac{\text{IDF}(s_j)}{\sum_{k \in \text{Out}(i)} \text{IDF}(s_k)}$$

A binary search budget fitter iteratively prunes low-centrality symbols until the serialized ASCII skeleton precisely fits within a strict token budget (default: 1,200 tokens).

---

### 1.2 Gemini Context Caching Cost Model
Google Gemini 2.5 and 3.x models offer an automatic **90% price discount** on input tokens matching a cached prefix (minimum threshold $\ge 2,048$ tokens).

Total task financial cost $C_{\text{task}}$ across $N$ conversational turns:

$$C_{\text{task}} = \sum_{t=1}^N \left[ (1 - \alpha_t) P_{\text{uncached}} T_{\text{prefix}} + \alpha_t P_{\text{cached}} T_{\text{prefix}} + P_{\text{input}} T_{\text{dynamic}} + P_{\text{output}} T_{\text{out}} \right]$$

Because $P_{\text{cached}} = 0.10 \times P_{\text{uncached}}$, locking the prefix ($\alpha_t \to 1.0$) eliminates the overwhelming majority of recurring API costs.

---

### 1.3 Cost Per Accepted Outcome (CPAO)
Token-saving benchmarks often report raw per-turn tokens, which can be gamed by generating short, incomplete responses. Antigravity-Cheaper enforces strict true-cost accounting:

$$\text{CPAO} = \frac{\sum_{i \in \text{Runs}} \text{Cost}_i}{\text{Count}(\text{Accepted Outcomes})}$$

Where an outcome is strictly accepted only when 100% of integration test suites pass and the Gatekeeper Critic issues a `SHIP` verdict.

---

## 2. Core Pillars

### Pillar 1: Zero-Bloat RepoMap (`agy_repomap.py`)
- **AST Parsing**: Parses Python ASTs and tree-sitter symbol graphs.
- **Topological PageRank**: Identifies critical dependencies without dumping file contents.
- **Directed Causal Pathfinding (`--path`)**: Computes shortest AST call chain between arbitrary symbols:
  ```bash
  python .agents/skills/token-guard/scripts/agy_repomap.py path --root . --from-sym OrderService --to-sym PaymentGateway
  ```
- **Error Lineage Resolution (`--causal`)**: Traces runtime stack traces back to root causes:
  ```bash
  python .agents/skills/token-guard/scripts/agy_repomap.py causal --root . --error "PartitionLeaseExpired"
  ```

---

### Pillar 2: Hardware-Invariant Prefix Locking (`agy_prefix_lock.py`)
- **Merkle SHA-256 Validation**: Validates Layer 1 (System Prompt) and Layer 2 (Project Invariants) byte-for-byte.
- **CRLF/LF Canonicalization**: Eliminates OS git-checkout differences that invalidate hashes.
- **Dynamic Invariant Injection**: Queries `agy_memory.py` and bakes verified truths into the frozen prefix layer.

```bash
python .agents/skills/token-guard/scripts/agy_prefix_lock.py build --workspace . --manifest .local/prefix_lock.json
python .agents/skills/token-guard/scripts/agy_prefix_lock.py verify --manifest .local/prefix_lock.json
```

---

### Pillar 3: FastMCP Surgical Symbol Server (`agy_mcp_server.py`)
Exposes 4 low-overhead stdio tools over JSON-RPC 2.0:
1. `get_repo_map(budget=1200)`: Compact ASCII dependency graph ranked by PageRank.
2. `get_symbol_subgraph(symbol_name="...", hops=2)`: Caller/callee micro-graph.
3. `get_file_skeleton(file_path="...")`: Interface definitions with bodies elided.
4. `get_bounded_slice(file_path="...", needle="...", context_lines=5)`: Exact match slice with hash validation.

---

### Pillar 4: Cognitive State Machine & Swarm Engine (`agy_pipeline.py`)
Implements a 3-stage finite state machine:

```
[ ARCHITECT ] --(Spec Contract)--> [ IMPLEMENTER ] --(Receipt)--> [ GATEKEEPER CRITIC ]
                                                                        |
                                          +-----------------------------+
                                          |
                      +-------------------+-------------------+
                      |                   |                   |
                  [ SHIP ]          [ FIX-FIRST ]        [ RETHINK ]
                      |                   |                   |
               (Persist Memory)      (Retry Loop)      (Abort & Redesign)
```

- **Swarm Decomposition**: Splits specifications into isolated worker manifests with strict file access boundaries:
  ```bash
  python .agents/skills/token-guard/scripts/agy_pipeline.py decompose --state-file .pipeline_state.json --num-workers 3
  ```
- **Gatekeeper Critic**: Read-only reviewer with tri-state verdict (`SHIP`, `FIX-FIRST`, `RETHINK`).

---

### Pillar 5: Zero-Tax Persistent Memory (`agy_memory.py`)
- Sub-millisecond SQLite FTS5 full-text search with BM25 ranking.
- Topic-Key upserts prevent duplicate knowledge.
- Injects persistent rules into Layer 2 prefix caching.

```bash
python .agents/skills/token-guard/scripts/agy_memory.py save --family architecture --key db_engine --content "Uses WAL with CRC32 framing and 24-byte alignment."
python .agents/skills/token-guard/scripts/agy_memory.py search --query "WAL CRC32"
```

---

### Pillar 6: AST Skeletons (`agy_ast.py`)
- Elides function/method bodies with `...` or `pass`.
- Preserves type hints, signatures, and docstrings.
- Cuts token overhead by 70–85% compared to full file views.

```bash
python .agents/skills/token-guard/scripts/agy_ast.py skeleton --source src/engine.py
```

---

### Pillar 7: Bounded Trace Slicing (`agy_pack.py` & `noise_sanitizer.py`)
- Slices massive trace logs (e.g. 35,000 lines) to exact causal failures with context.
- Pre-Tool hook intercepts commands:
  - Blocks `cat` / `type` on files larger than 15 KB.
  - Redirects test commands (`pytest`, `cargo test`, `npm test`) to disk logs and surfaces only tracebacks.

---

### Pillar 8: Telemetry Ledger (`agy_ledger.py`)
- Tracks raw input tokens, cached tokens, output tokens, and reasoning tokens.
- Calculates true Cost Per Accepted Outcome across runs.
