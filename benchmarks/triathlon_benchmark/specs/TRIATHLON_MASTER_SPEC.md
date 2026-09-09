# Triathlon Benchmark: Master Execution Contract

## Overview
This benchmark evaluates an AI software engineering agent across three heavy, sequential systems engineering challenges in a single continuous trajectory:

1. **Stage 1**: Pure-Python SQLite B-Tree & Binary File Format Engine (`stage1_sqlite/`)
   - Spec: `specs/STAGE_1_SQLITE_SPEC.md`
   - Test Runner: `test_runners/test_stage1_sqlite.py`
2. **Stage 2**: Distributed Raft Consensus & 2PC Coordinator with Network Partitions (`stage2_consensus/`)
   - Spec: `specs/STAGE_2_CONSENSUS_SPEC.md`
   - Test Runner: `test_runners/test_stage2_consensus.py`
3. **Stage 3**: BitTorrent Wire Protocol, P2P Handshake & SHA-1 Piece Assembler (`stage3_bittorrent/`)
   - Spec: `specs/STAGE_3_BITTORRENT_SPEC.md`
   - Test Runner: `test_runners/test_stage3_bittorrent.py`

## Rules of Execution
1. Each variant develops inside its dedicated workspace folder:
   - Baseline: `benchmarks/triathlon_benchmark/variants/baseline/`
   - Token Guard: `benchmarks/triathlon_benchmark/variants/token_guard/`
2. The agent must proceed strictly stage by stage:
   - Implement Stage 1 and verify tests pass.
   - Implement Stage 2 and verify tests pass.
   - Implement Stage 3 and verify tests pass.
3. Once all 3 stages pass, report back with final completion confirmation.
