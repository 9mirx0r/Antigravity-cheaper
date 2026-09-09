#!/usr/bin/env python3
"""Stage 1 Test Suite: SQLite Binary B-Tree Engine."""

import os
from pathlib import Path
import struct
import sys
import unittest

# Dynamic import helper for current variant
VARIANT_ROOT = Path(os.environ.get("TRIATHLON_VARIANT_DIR", ".")).resolve()
STAGE_DIR = VARIANT_ROOT / "stage1_sqlite"
if str(STAGE_DIR) not in sys.path:
    sys.path.insert(0, str(STAGE_DIR))

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
DB_PATH = FIXTURES_DIR / "sample_database.db"

from src.db_header import DatabaseHeader
from src.varint import read_varint, write_varint
from src.btree_page import BTreePage
from src.record_decoder import RecordDecoder
from src.table_scanner import SQLiteEngine


class TestStage1SQLite(unittest.TestCase):

    def setUp(self):
        self.assertTrue(DB_PATH.is_file(), f"Database fixture not found: {DB_PATH}")

    def test_database_header(self):
        with open(DB_PATH, "rb") as f:
            header_bytes = f.read(100)
        hdr = DatabaseHeader.parse(header_bytes)
        self.assertEqual(hdr.page_size, 4096)
        self.assertEqual(hdr.write_version, 1)
        self.assertEqual(hdr.read_version, 1)
        self.assertEqual(hdr.reserved_space, 0)
        self.assertGreaterEqual(hdr.schema_cookie, 1)

    def test_varint_read_write(self):
        test_values = [0, 1, 127, 128, 255, 16383, 16384, 2097151, 268435455, 1000000000]
        for val in test_values:
            encoded = write_varint(val)
            decoded, consumed = read_varint(encoded)
            self.assertEqual(val, decoded, f"Varint mismatch for {val}")
            self.assertEqual(len(encoded), consumed)

    def test_record_decoder_serial_types(self):
        # Build raw SQLite record payload:
        # Header length: varint
        # Types: [1 (int8), 4 (int32), 7 (float64), 0 (null), 23 (text of len 5)]
        # Body: [0x42, 100000, 3.14159, "faker"]
        body_val1 = struct.pack(">b", 42)
        body_val2 = struct.pack(">i", 100000)
        body_val3 = struct.pack(">d", 3.14159)
        body_val4 = b"faker"
        body = body_val1 + body_val2 + body_val3 + body_val4

        # Types varints: 1, 4, 7, 0, 13 + 2*5 = 23
        types_bytes = bytes([1, 4, 7, 0, 23])
        header_len = 1 + len(types_bytes)
        header = write_varint(header_len) + types_bytes
        payload = header + body

        record = RecordDecoder.decode_record(payload)
        self.assertEqual(len(record), 5)
        self.assertEqual(record[0], 42)
        self.assertEqual(record[1], 100000)
        self.assertAlmostEqual(record[2], 3.14159, places=4)
        self.assertIsNone(record[3])
        self.assertEqual(record[4], "faker")

    def test_table_scanner_schema(self):
        engine = SQLiteEngine(str(DB_PATH))
        tables = engine.get_tables()
        table_names = [t["tbl_name"] for t in tables]
        self.assertIn("users", table_names)
        self.assertIn("products", table_names)

    def test_table_scanner_users_all(self):
        engine = SQLiteEngine(str(DB_PATH))
        users = engine.scan_table("users")
        self.assertGreaterEqual(len(users), 8)
        usernames = [u["username"] for u in users]
        self.assertIn("faker", usernames)
        self.assertIn("chovy", usernames)
        self.assertIn("caps", usernames)

    def test_table_scanner_filter_query(self):
        engine = SQLiteEngine(str(DB_PATH))
        res = engine.scan_table("users", where_col="username", where_val="faker")
        self.assertEqual(len(res), 1)
        faker = res[0]
        self.assertEqual(faker["username"], "faker")
        self.assertEqual(faker["email"], "faker@t1.gg")
        self.assertEqual(faker["karma"], 9999)

    def test_table_scanner_products(self):
        engine = SQLiteEngine(str(DB_PATH))
        products = engine.scan_table("products", where_col="sku", where_val="SKU-100")
        self.assertEqual(len(products), 1)
        p = products[0]
        self.assertEqual(p["name"], "Hextech Blade")
        self.assertAlmostEqual(p["price"], 3200.50, places=2)
        self.assertEqual(p["stock"], 15)


if __name__ == "__main__":
    unittest.main()
