#!/usr/bin/env python3
"""Scaffolds the Severe AresDB MVCC + ARIES Recovery Benchmark Challenge."""

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "benchmark_mvcc_engine"

SPEC_MD = """# Severe Benchmark Specification: AresDB (MVCC + ARIES Storage Engine)

## Objective
Build a zero-dependency, pure-Python transactional storage engine (`AresDB`) implementing:
1. **Multi-Version Concurrency Control (MVCC)** with Snapshot Isolation and First-Committer-Wins conflict aborts.
2. **Binary Write-Ahead Log (WAL)** with LSN, PrevLSN, CRC-32 checksums, and record framing.
3. **Concurrent B+ Tree Index** with thread-safe node splitting, right-sibling links, and range queries.
4. **IBM ARIES Crash Recovery Protocol** (Analysis phase, Redo phase repeating history, and Undo phase rolling back active transactions with Compensation Log Records / CLRs).
5. **High-Level Transaction Engine** exposing ACID transaction lifecycles.

---

## Required Modules in `src/`

### 1. `src/wal.py`
- `RecordType`: Enum or string constants: `BEGIN`, `UPDATE`, `COMMIT`, `ABORT`, `CLR`, `CHECKPOINT`.
- `WALRecord`:
  - Attributes: `lsn: int`, `prev_lsn: int`, `tx_id: str`, `record_type: str`, `key: str`, `old_val: bytes | str | None`, `new_val: bytes | str | None`, `undo_next_lsn: int = 0`.
- `WALManager(wal_path: str)`:
  - Magic header: `b"AWAL\\x01"` (5 bytes).
  - Appends formatted binary records to disk with CRC-32 checksum.
  - `append_record(tx_id, record_type, key="", old_val=None, new_val=None, prev_lsn=0, undo_next_lsn=0) -> int` (returns assigned LSN).
  - `read_all_records() -> List[WALRecord]`: Reads and validates records from disk, verifying CRC-32 integrity.
  - `flush()`: Flushes writes to disk.

### 2. `src/mvcc.py`
- `WriteConflictException`: Raised when a transaction attempts to modify a key modified by a concurrent committed transaction.
- `TupleVersion`:
  - `key: str`, `val: Any`, `xmin: int` (creating tx_id), `xmax: Optional[int]` (deleting/updating tx_id), `prev_version: Optional[TupleVersion]`.
- `Snapshot`:
  - `xmin: int` (lowest active tx_id), `xmax: int` (highest assigned tx_id + 1), `active_xids: Set[int]`.
  - `is_visible(version: TupleVersion) -> bool`:
    - Version is visible if `xmin` is committed before snapshot took effect and not in `active_xids`, AND `xmax` is either unset, aborted, or committed after snapshot took effect.
- `MVCCManager`:
  - `begin_tx() -> int`: Generates next monotonically increasing tx_id and creates snapshot.
  - `read(tx_id: int, key: str) -> Optional[Any]`: Traverses version chain from newest to oldest, returning first visible version under transaction's snapshot.
  - `write(tx_id: int, key: str, val: Any) -> Optional[TupleVersion]`:
    - Checks write-write conflict: if latest version has `xmax` or was modified by a transaction after this transaction's snapshot, raises `WriteConflictException`.
    - Creates new `TupleVersion` with `xmin = tx_id`, updates previous version's `xmax = tx_id`.
  - `commit_tx(tx_id: int)`: Marks tx as committed and removes from active list.
  - `abort_tx(tx_id: int)`: Rolls back changes by unsetting `xmax` on overwritten versions and marking created versions as dead.

### 3. `src/btree.py`
- `BPlusTree(max_degree: int = 4)`:
  - Thread-safe B+ Tree with `threading.RLock`.
  - Leaf nodes contain key-value pairs and pointer to `next_leaf` (right-sibling link) for fast range queries.
  - `insert(key: Any, value: Any)`: Inserts key-value pair, performing node splitting when node reaches `max_degree`.
  - `search(key: Any) -> Optional[Any]`: Point lookup returning value or `None`.
  - `scan_range(low_key: Any, high_key: Any) -> List[Tuple[Any, Any]]`: Returns all pairs where `low_key <= key <= high_key` in sorted order.

### 4. `src/recovery.py`
- `ARIESRecoveryEngine(wal_manager: WALManager)`:
  - Implements the 3-phase ARIES recovery algorithm:
  - **Phase 1: Analysis Pass**:
    - Scans log forward from last checkpoint (or start).
    - Identifies active uncommitted transactions (`TransactionTable`: `tx_id -> last_lsn`).
    - Identifies dirty keys/pages (`DirtyPageTable`: `key -> rec_lsn`).
  - **Phase 2: Redo Pass**:
    - Scans forward from smallest `rec_lsn` in DPT (or start) to the end of the log.
    - Reapplies all `UPDATE` and `CLR` operations ("repeats history") into the data store.
  - **Phase 3: Undo Pass**:
    - Follows active transactions backward using `prev_lsn` and `undo_next_lsn`.
    - For each active transaction update:
      - Reverts the change in the data store (restoring `old_val`).
      - Writes a `CLR` (Compensation Log Record) to the WAL with `undo_next_lsn = record.prev_lsn`.
    - When an active transaction reaches `prev_lsn == 0`, writes an `ABORT` record to the WAL.
  - `recover() -> Tuple[Dict[str, Any], int]`:
    - Reconstructs and returns the recovered key-value store and total CLRs written.

### 5. `src/engine.py`
- `AresStorageEngine(db_dir: str)`:
  - Unifies WAL, MVCC, B+ Tree, and Transactions.
  - `begin_transaction() -> int`: Returns tx_id.
  - `read(tx_id: int, key: str) -> Optional[Any]`
  - `write(tx_id: int, key: str, val: Any) -> bool`: Logs `UPDATE` to WAL before applying to MVCC & B-Tree.
  - `commit(tx_id: int) -> bool`: Logs `COMMIT` to WAL and flushes.
  - `abort(tx_id: int) -> bool`: Rolls back active changes and logs `ABORT` to WAL.
  - `crash_and_recover() -> AresStorageEngine`: Simulates sudden crash, instantiates fresh engine, runs ARIES recovery, and resumes state.
  - `close()`: Clean shutdown.
"""

TEST_ARES_PY = '''#!/usr/bin/env python3
"""Integration and Stress Test Suite for AresDB (MVCC + ARIES Storage Engine)."""

import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

# Relative imports from src/
import sys
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from wal import WALManager, WALRecord
from mvcc import MVCCManager, WriteConflictException
from btree import BPlusTree
from recovery import ARIESRecoveryEngine
from engine import AresStorageEngine


class TestAresDB(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="ares_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_mvcc_snapshot_isolation(self):
        """Test Snapshot Isolation visibility and First-Committer-Wins conflict aborts."""
        mvcc = MVCCManager()

        # Step 1: Tx1 initializes k1 = "v1"
        tx1 = mvcc.begin_tx()
        mvcc.write(tx1, "k1", "v1")
        mvcc.commit_tx(tx1)

        # Step 2: Tx2 starts and takes snapshot
        tx2 = mvcc.begin_tx()
        self.assertEqual(mvcc.read(tx2, "k1"), "v1")

        # Step 3: Concurrent Tx3 updates k1 to "v2" and commits
        tx3 = mvcc.begin_tx()
        mvcc.write(tx3, "k1", "v2")
        mvcc.commit_tx(tx3)

        # Step 4: Tx2 reads k1 -> MUST still see "v1" (Snapshot Isolation, no phantom or non-repeatable read)
        self.assertEqual(mvcc.read(tx2, "k1"), "v1")

        # Step 5: Tx2 attempts to write to k1 -> MUST raise WriteConflictException (First-Committer-Wins)
        with self.assertRaises(WriteConflictException):
            mvcc.write(tx2, "k1", "v2_from_tx2")

        mvcc.abort_tx(tx2)

        # Step 6: Fresh Tx4 must read "v2"
        tx4 = mvcc.begin_tx()
        self.assertEqual(mvcc.read(tx4, "k1"), "v2")
        mvcc.commit_tx(tx4)

    def test_concurrent_btree(self):
        """Test B+ Tree thread safety, node splits, and range scanning."""
        tree = BPlusTree(max_degree=4)

        # Concurrent insertions
        def insert_worker(start_idx, count):
            for i in range(start_idx, start_idx + count):
                tree.insert(i, f"val_{i}")

        threads = []
        num_threads = 4
        items_per_thread = 50
        for t in range(num_threads):
            th = threading.Thread(target=insert_worker, args=(t * items_per_thread, items_per_thread))
            threads.append(th)
            th.start()

        for th in threads:
            th.join()

        # Verify all 200 items exist
        for i in range(200):
            self.assertEqual(tree.search(i), f"val_{i}", f"Missing key {i}")

        # Verify range scan ordering
        range_res = tree.scan_range(20, 35)
        self.assertEqual(len(range_res), 16)
        keys = [k for k, v in range_res]
        self.assertEqual(keys, list(range(20, 36)))
        for k, v in range_res:
            self.assertEqual(v, f"val_{k}")

    def test_aries_crash_recovery(self):
        """Test ARIES crash recovery with Analysis, Redo, and Undo with CLRs."""
        engine = AresStorageEngine(self.test_dir)

        # Tx1: Committed write
        tx1 = engine.begin_transaction()
        engine.write(tx1, "user:1", "alice")
        engine.commit(tx1)

        # Tx2: Active uncommitted write (will crash!)
        tx2 = engine.begin_transaction()
        engine.write(tx2, "user:2", "bob_uncommitted")

        # Tx3: Committed write
        tx3 = engine.begin_transaction()
        engine.write(tx3, "user:3", "charlie")
        engine.commit(tx3)

        # Tx4: Active write to key updated by Tx1
        tx4 = engine.begin_transaction()
        engine.write(tx4, "user:1", "alice_corrupted")

        # Simulate sudden crash: close without commit or rollback of Tx2 and Tx4
        engine.close()

        # Perform ARIES recovery using recovery engine
        recovered_engine = engine.crash_and_recover()

        # In recovered state:
        # - user:1 MUST be "alice" (Tx4's uncommitted change undone)
        # - user:2 MUST be None (Tx2's uncommitted change undone)
        # - user:3 MUST be "charlie" (Tx3 was committed)
        tx_check = recovered_engine.begin_transaction()
        self.assertEqual(recovered_engine.read(tx_check, "user:1"), "alice")
        self.assertIsNone(recovered_engine.read(tx_check, "user:2"))
        self.assertEqual(recovered_engine.read(tx_check, "user:3"), "charlie")
        recovered_engine.commit(tx_check)

        # Verify idempotency: crash and recover again on the same log
        recovered_engine.close()
        second_recovery = recovered_engine.crash_and_recover()
        tx_check2 = second_recovery.begin_transaction()
        self.assertEqual(second_recovery.read(tx_check2, "user:1"), "alice")
        self.assertIsNone(second_recovery.read(tx_check2, "user:2"))
        self.assertEqual(second_recovery.read(tx_check2, "user:3"), "charlie")
        second_recovery.commit(tx_check2)
        second_recovery.close()

    def test_concurrent_acid_stress(self):
        """Stress test: 10 concurrent threads executing transactions under load."""
        engine = AresStorageEngine(self.test_dir)
        errors = []

        def worker(worker_id):
            try:
                for i in range(25):
                    key = f"acc:{worker_id}_{i % 5}"
                    tx = engine.begin_transaction()
                    val = engine.read(tx, key) or "0"
                    new_val = str(int(val) + 1)
                    engine.write(tx, key, new_val)
                    if i % 7 == 0:
                        engine.abort(tx)
                    else:
                        engine.commit(tx)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(w,)) for w in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        self.assertEqual(len(errors), 0, f"Encountered concurrency errors: {errors}")
        engine.close()


if __name__ == "__main__":
    unittest.main()
'''


def main():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)

    for variant in ("baseline", "token_guard"):
        v_dir = ROOT / "variants" / variant
        (v_dir / "src").mkdir(parents=True)
        (v_dir / "tests").mkdir(parents=True)

        (v_dir / "SPEC.md").write_text(SPEC_MD, encoding="utf-8")
        (v_dir / "tests" / "test_ares.py").write_text(TEST_ARES_PY, encoding="utf-8")

        # Initialize empty source stubs
        for mod in ("wal.py", "mvcc.py", "btree.py", "recovery.py", "engine.py"):
            (v_dir / "src" / mod).write_text(f'"""Module {mod} for AresDB."""\n', encoding="utf-8")

    print(f"Scaffolded AresDB Severe Benchmark at {ROOT}")


if __name__ == "__main__":
    main()
