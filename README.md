<div align="center">

<img src="assets/banner.png" alt="Antigravity Cheaper Banner" width="100%" />

# Antigravity Cheaper

**High-precision token economization &amp; cognitive scaffolding for Google Antigravity &amp; Gemini Agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=flat-square)](https://www.python.org/)
[![FastMCP](https://img.shields.io/badge/FastMCP-2.0-green.svg?style=flat-square)](https://github.com/jlowin/fastmcp)
[![Tests: 49/49 Passing](https://img.shields.io/badge/Tests-49%2F49%20Passing-emerald.svg?style=flat-square)](#tests)
[![Gemini Cache Hit](https://img.shields.io/badge/Gemini%20Cache-94.2%25%20Locked-purple.svg?style=flat-square)](docs/ARCHITECTURE.md#pillar-2-hardware-invariant-prefix-locking)

</div>

---

## Overview

Autonomous coding agents suffer from **Context Bloat & Token Degradation**. Blindly dumping 35,000-line logs, inspecting entire files instead of signatures, and invalidating prompt caches with volatile nonces leads to massive API bills and diluted model reasoning.

**Antigravity-Cheaper** is an agentic framework designed specifically for **Google Antigravity** and **Gemini 2.5/3.x models** that slashes token consumption by up to **81.5%** and API costs by **84.1%** while maintaining 100% test pass rates on severe engineering workloads.

---

## Empirical Benchmarks

Measured on identical bug baselines using **Gemini 3.8 Flash Thinking / High Reasoning**:

<div align="center">
  <img src="assets/benchmark_comparison.png" alt="Benchmark Comparison" width="100%" />
</div>

| Benchmark Workload | Baseline Tokens | Cheaper Tokens | Token Savings | Baseline Cost | Cheaper Cost | Cost Savings | Speedup |
|---|---|---|---|---|---|---|---|
| **Split-Brain 2PC &amp; Raft (35k-line log)** | 771,836 | 142,654 | **-81.5%** | $0.849 | $0.157 | **-81.5%** | **3.0x** |
| **AresDB Storage Engine (MVCC + ARIES)** | 329,410 | 108,321 | **-67.1%** | $0.356 | $0.057 | **-84.1%** | **1.5x** |
| **HNSW Vector Search Engine** | 341,200 | 138,912 | **-59.3%** | $0.221 | $0.090 | **-59.3%** | **1.8x** |
| **Distributed Saga Orchestrator** | 35,120 | 7,840 | **-77.7%** | $0.038 | $0.009 | **-76.3%** | **2.8x** |

> Raw run ledgers and reproduction instructions are in [`benchmarks/`](benchmarks/).

---

## System Architecture

<div align="center">
  <img src="assets/architecture.png" alt="Architecture Topology" width="100%" />
</div>

Antigravity-Cheaper organizes agent execution into 4 distinct context layers:

1. **Prefix Lock Layer (`agy_prefix_lock.py`)**: Freezes Layer 1 &amp; 2 invariants (>2,048 tokens) with SHA-256 Merkle validation to guarantee **94.2% Gemini context cache hits** (90% price discount).
2. **Personalized PageRank RepoMap (`agy_repomap.py`)**: Generates an AST-driven dependency map of the entire workspace in **<1,200 tokens**.
3. **Surgical FastMCP Server (`agy_mcp_server.py`)**: Exposes 4 low-overhead stdio tools (`get_repo_map`, `get_symbol_subgraph`, `get_file_skeleton`, `get_bounded_slice`).
4. **Cognitive State Machine &amp; Swarms (`agy_pipeline.py`)**: Implements an autonomous `Architect` $\to$ `Implementer` $\to$ `Gatekeeper Critic` tri-state loop with contract-isolated subagent manifests.
5. **Zero-Tax Memory (`agy_memory.py`)**: SQLite FTS5 store providing sub-millisecond BM25 retrieval for cross-turn invariants.
6. **AST Skeletons &amp; Bounded Slicing (`agy_ast.py`, `agy_pack.py`)**: Strips function bodies with `...` and slices multi-megabyte trace logs down to exact causal errors.

> 📖 **Read the Full Deep Dive**: For mathematical formulations, power iteration formulas, and complete module specs, see [**docs/ARCHITECTURE.md**](docs/ARCHITECTURE.md).

---

## Quickstart

### 1. Install
```bash
git clone https://github.com/9mirx0r/Antigravity-cheaper.git
cd Antigravity-cheaper
pip install -e .
```

### 2. Configure Antigravity
The workspace skills, governance rules, and hooks are ready to use out of the box in `.agents/`:
- `.agents/skills/token-guard`: Core progressive disclosure & token economization.
- `.agents/rules/token_discipline.md`: Antigravity context governance.
- `.agents/scripts/noise_sanitizer.py`: Automatic test-log noise interception.

To register the FastMCP symbol server in your Antigravity MCP settings:
```json
{
  "mcpServers": {
    "agy-symbol-server": {
      "command": "python",
      "args": [".agents/skills/token-guard/scripts/agy_mcp_server.py"]
    }
  }
}
```

---

## Tests

Run the complete deterministic test suite (49 passing unit tests):

```bash
python tests/test_suite.py
```

```text
Ran 49 tests in 1.510s

OK
```

Validate skill compliance with [agentskills.io](https://agentskills.io):
```bash
python .agents/skills/skill-creator/scripts/quick_validate.py --skills-dir .agents/skills
# Summary: 3 evaluated | 3 passed | 0 failed | 0 warning(s)
```

---

## License

Distributed under the [MIT License](LICENSE).
