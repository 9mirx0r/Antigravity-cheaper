# Operation Blackbox: Debug & Fix a Broken Financial Settlement Engine

## Mission

You are given a **pre-built Financial Settlement Engine** (~2500 lines across
6 Python modules) that has **multiple critical bugs** planted throughout the
codebase.  Your mission is to:

1. **Read and understand** the existing codebase
2. **Run the test suite** to identify failing tests
3. **Diagnose the root cause** of each failure
4. **Fix the bugs** in the source code
5. **Re-run the tests** until ALL 20 tests pass

## Architecture Overview

The engine consists of 6 modules in `buggy_codebase/src/`:

| Module            | Purpose                                   | Lines |
|-------------------|-------------------------------------------|-------|
| `merkle_tree.py`  | Binary Merkle hash tree for audit proofs  | ~100  |
| `wire_protocol.py`| Binary wire protocol with CRC framing     | ~160  |
| `crdt_ledger.py`  | CRDT-based distributed ledger balances    | ~120  |
| `order_book.py`   | Price-time priority order matching engine | ~230  |
| `event_journal.py`| Event sourcing with deterministic replay  | ~130  |
| `settlement.py`   | Bilateral netting & DVP settlement        | ~170  |
| `signatures.py`   | HMAC signature verification               | ~80   |

## Test Suite

Run the test suite with:
```
python benchmarks/blackbox_benchmark/test_runners/test_blackbox.py
```

There are **20 tests** (TEST-01 through TEST-20).  Currently **13 fail**.
ALL 20 must pass for the task to be complete.

## Rules

1. You may ONLY modify files in `benchmarks/blackbox_benchmark/buggy_codebase/src/`
2. You may NOT modify the test file `test_blackbox.py`
3. Each bug fix should be surgical — fix the actual bug, don't rewrite the module
4. The test suite must run without any external dependencies (stdlib only)

## Success Criteria

```
Results: 20 passed, 0 failed out of 20
```
