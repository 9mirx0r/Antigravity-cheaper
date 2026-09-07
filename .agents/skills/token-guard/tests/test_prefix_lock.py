#!/usr/bin/env python3
"""Unit tests for agy_prefix_lock.py."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from agy_prefix_lock import (
    PrefixLockBuilder,
    canonicalize_text,
    compute_file_sha256,
    compute_merkle_root,
)


class TestPrefixLock(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="prefix_lock_test_")
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_canonicalize_text(self):
        raw = "line 1  \r\nline 2   \rline 3 \n"
        canon = canonicalize_text(raw)
        self.assertNotIn("\r", canon)
        self.assertIn("line 1\nline 2\nline 3\n", canon)

    def test_compute_file_sha256_crlf_invariance(self):
        p1 = self.root / "file1.txt"
        p2 = self.root / "file2.txt"
        p1.write_bytes(b"hello world\r\nsecond line\r\n")
        p2.write_bytes(b"hello world\nsecond line\n")

        h1 = compute_file_sha256(p1)
        h2 = compute_file_sha256(p2)
        self.assertEqual(h1, h2, "CRLF and LF must yield identical SHA-256")

    def test_compute_merkle_root_determinism(self):
        d1 = {"a.py": "hash1", "b.py": "hash2"}
        d2 = {"b.py": "hash2", "a.py": "hash1"}
        self.assertEqual(compute_merkle_root(d1), compute_merkle_root(d2))

    def test_build_and_verify_manifest(self):
        (self.root / "service.py").write_text(
            """class PaymentService:
    def process_payment(self, amount: float) -> bool:
        return amount > 0
""",
            encoding="utf-8",
        )
        (self.root / "helper.py").write_text(
            """def format_currency(val: float) -> str:
    return f"${val:.2f}"
""",
            encoding="utf-8",
        )

        builder = PrefixLockBuilder(self.root, target_tokens=100)
        manifest = builder.build_prefix()

        self.assertEqual(manifest["version"], 1)
        self.assertEqual(manifest["file_count"], 2)
        self.assertIn("PaymentService", manifest["prefix_content"])
        self.assertIn("format_currency", manifest["prefix_content"])
        self.assertTrue(manifest["meets_threshold"])

        # Verification on untouched files
        valid, msg = builder.verify_manifest(manifest)
        self.assertTrue(valid)
        self.assertIn("Dependencies match", msg)

        # Verification on modified file
        (self.root / "service.py").write_text(
            "class PaymentService:\n    pass\n", encoding="utf-8"
        )
        valid_after_mod, msg_mod = builder.verify_manifest(manifest)
        self.assertFalse(valid_after_mod)
        self.assertIn("Files modified on disk", msg_mod)

        # Verification on deleted file
        (self.root / "helper.py").unlink()
        valid_after_del, msg_del = builder.verify_manifest(manifest)
        self.assertFalse(valid_after_del)
        self.assertIn("File deleted", msg_del)


if __name__ == "__main__":
    unittest.main()
