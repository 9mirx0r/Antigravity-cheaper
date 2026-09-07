# Empirical Benchmarks & Reproducibility Suite

This directory contains the reproducible benchmark harnesses, evaluation runners, and raw JSONL execution ledgers comparing **Antigravity-Cheaper** against standard **Baseline Coding Agents**.

## Benchmark Overview

| ID | Workload | Baseline Tokens | Cheaper Tokens | Token Savings | Baseline Cost | Cheaper Cost | Cost Savings | Speedup | Result |
|---|---|---|---|---|---|---|---|---|---|
| **BM-1** | Distributed Saga Compensation Debugger | 35,120 | 7,840 | **-77.7%** | $0.038 | $0.009 | **-76.3%** | **2.8x** | PASS |
| **BM-2** | Split-Brain 2PC & Raft (35k-line log) | 771,836 | 142,654 | **-81.5%** | $0.849 | $0.157 | **-81.5%** | **3.0x** | PASS |
| **BM-3** | Greenfield HNSW Vector Engine & Persistence | 341,200 | 138,912 | **-59.3%** | $0.221 | $0.090 | **-59.3%** | **1.8x** | PASS |
| **BM-4** | AresDB Storage Engine (MVCC + ARIES Recovery) | 329,410 | 108,321 | **-67.1%** | $0.356 | $0.057 | **-84.1%** | **1.5x** | PASS |

---

## Reproducing the Benchmarks

Each benchmark script sets up isolated sandbox environments with identical bugs, architectural specifications, and integration test suites:

### 1. AresDB Storage Engine (MVCC + ARIES Recovery)
```bash
python benchmarks/setup_ares_benchmark.py
```
- Sets up `benchmark_mvcc_engine/variants/baseline` and `benchmark_mvcc_engine/variants/token_guard`.
- Tests snapshot isolation, concurrent B+tree page splits, Write-Ahead Log (WAL) CRC32 verification, and ARIES crash recovery with Compensation Log Records (CLRs).

### 2. Split-Brain Consensus & Two-Phase Commit Deadlock
```bash
python benchmarks/setup_extreme_benchmark.py
```
- Sets up a 15-microservice distributed cluster with a 35,000-line (3.6 MB) production trace log.
- Tests distributed lock acquisition, Raft leader election, and 2PC abort rollbacks.

### 3. Greenfield Hierarchical Navigable Small World (HNSW) Engine
```bash
python benchmarks/setup_hnsw_benchmark.py
```
- Greenfield implementation of multi-layer graph skip-lists, heuristic neighbor pruning, Euclidean/Cosine distance metrics, and binary persistence.

---

## Raw Telemetry Data

Raw run telemetry ledgers containing exact token usage (input, cached input, output, and reasoning tokens), elapsed time, and model parameters are available in `benchmarks/data/`:
- `benchmarks/data/benchmark_ares_ledger.jsonl`
- `benchmarks/data/benchmark_extreme_ledger.jsonl`
- `benchmarks/data/benchmark_hnsw_ledger.jsonl`
- `benchmarks/data/benchmark_usage.jsonl`
