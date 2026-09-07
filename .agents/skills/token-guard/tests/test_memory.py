#!/usr/bin/env python3
"""Unit tests for agy_memory.py."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from agy_memory import MemoryEngine


class TestAgyMemory(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="memory_test_")
        self.db_path = Path(self.test_dir) / "test_memory.db"
        self.engine = MemoryEngine(self.db_path)

    def tearDown(self):
        self.engine.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_save_and_upsert(self):
        # 1. First save (insert)
        res1 = self.engine.save(
            topic_key="architecture/wal-format",
            title="WAL Record Format",
            content="Use b'AWAL\\x01' with CRC32 checksums.",
            category="architecture",
            project="ares_db",
        )
        self.assertEqual(res1["action"], "created")
        self.assertEqual(res1["revision"], 1)

        # 2. Second save with same topic_key (upsert)
        res2 = self.engine.save(
            topic_key="architecture/wal-format",
            title="WAL Record Format V2",
            content="Updated to include CLR undo_next_lsn pointer.",
            category="architecture",
            project="ares_db",
        )
        self.assertEqual(res2["action"], "updated")
        self.assertEqual(res2["revision"], 2)

        # 3. Verify single entry exists in DB
        mem = self.engine.get(topic_key="architecture/wal-format", project="ares_db")
        self.assertIsNotNone(mem)
        self.assertEqual(mem["revision_count"], 2)
        self.assertIn("undo_next_lsn", mem["content"])

    def test_fts5_search(self):
        self.engine.save(
            topic_key="bug/deadlock-rwlock",
            title="Deadlock in RWLock",
            content="Writer priority caused starvation when readers re-entered without release.",
            category="bug",
            project="ares_db",
        )
        self.engine.save(
            topic_key="decision/crc32-unsigned",
            title="CRC32 Invariant",
            content="Always mask CRC32 with 0xFFFFFFFF for unsigned 32-bit compliance.",
            category="decision",
            project="ares_db",
        )

        # Search for "starvation"
        results = self.engine.search("starvation", project="ares_db")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["topic_key"], "bug/deadlock-rwlock")

        # Search for "CRC32"
        results_crc = self.engine.search("CRC32", project="ares_db")
        self.assertEqual(len(results_crc), 1)
        self.assertEqual(results_crc[0]["topic_key"], "decision/crc32-unsigned")

    def test_project_context_and_stats(self):
        self.engine.save(
            topic_key="config/python-version",
            title="Python Runtime",
            content="Target Python 3.12+ only.",
            category="config",
            project="ares_db",
        )

        ctx = self.engine.get_project_context(project="ares_db")
        self.assertIn("Project Knowledge Invariants", ctx)
        self.assertIn("config/python-version", ctx)

        stats = self.engine.stats()
        self.assertEqual(stats["total_memories"], 1)
        self.assertEqual(stats["categories"]["config"], 1)

    def test_delete(self):
        self.engine.save(
            topic_key="temp/deprecated-note",
            title="Deprecated Note",
            content="To be removed.",
            category="discovery",
            project="ares_db",
        )
        ok = self.engine.delete("temp/deprecated-note", project="ares_db")
        self.assertTrue(ok)
        self.assertIsNone(self.engine.get(topic_key="temp/deprecated-note", project="ares_db"))


if __name__ == "__main__":
    unittest.main()
