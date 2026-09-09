#!/usr/bin/env python3
"""Stage 3 Test Suite: BitTorrent Wire Protocol & Block Assembler."""

import hashlib
import os
from pathlib import Path
import sys
import unittest

VARIANT_ROOT = Path(os.environ.get("TRIATHLON_VARIANT_DIR", ".")).resolve()
STAGE_DIR = VARIANT_ROOT / "stage3_bittorrent"
if str(STAGE_DIR) not in sys.path:
    sys.path.insert(0, str(STAGE_DIR))

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
TORRENT_PATH = FIXTURES_DIR / "test_file.torrent"
PAYLOAD_PATH = FIXTURES_DIR / "payload.bin"

from src.bencode import bencode_decode, bencode_encode
from src.torrent_parser import parse_torrent_file
from src.peer_wire import create_handshake, parse_handshake, create_message, create_request
from src.piece_manager import PieceManager


class TestStage3BitTorrent(unittest.TestCase):

    def test_bencode_primitives(self):
        # Integer
        self.assertEqual(bencode_decode(b"i42e"), 42)
        self.assertEqual(bencode_decode(b"i-10e"), -10)
        self.assertEqual(bencode_encode(42), b"i42e")

        # String
        self.assertEqual(bencode_decode(b"4:spam"), b"spam")
        self.assertEqual(bencode_encode(b"spam"), b"4:spam")

        # List
        self.assertEqual(bencode_decode(b"li1ei2e3:fooe"), [1, 2, b"foo"])
        self.assertEqual(bencode_encode([1, 2, b"foo"]), b"li1ei2e3:fooe")

        # Dict (keys sorted)
        d = {b"cow": b"moo", b"bar": b"spam"}
        encoded = bencode_encode(d)
        self.assertEqual(encoded, b"d3:bar4:spam3:cow3:mooe")
        self.assertEqual(bencode_decode(encoded), d)

    def test_torrent_metainfo_parsing(self):
        self.assertTrue(TORRENT_PATH.is_file(), f"Torrent fixture missing: {TORRENT_PATH}")
        meta = parse_torrent_file(TORRENT_PATH)
        self.assertEqual(meta.announce, "http://tracker.example.com/announce")
        self.assertEqual(meta.name, "payload.bin")
        self.assertEqual(meta.length, 65536)
        self.assertEqual(meta.piece_length, 32768)
        self.assertEqual(len(meta.pieces), 2)
        self.assertEqual(len(meta.info_hash), 20)

    def test_peer_wire_handshake(self):
        meta = parse_torrent_file(TORRENT_PATH)
        peer_id = b"-PY0001-123456789012"
        handshake = create_handshake(meta.info_hash, peer_id)

        self.assertEqual(len(handshake), 68)
        self.assertEqual(handshake[0], 19)
        self.assertEqual(handshake[1:20], b"BitTorrent protocol")

        parsed_info_hash, parsed_peer_id = parse_handshake(handshake)
        self.assertEqual(parsed_info_hash, meta.info_hash)
        self.assertEqual(parsed_peer_id, peer_id)

    def test_peer_wire_messages(self):
        # UNCHOKE message (ID 1, length 1)
        unchoke = create_message(1)
        self.assertEqual(unchoke, b"\x00\x00\x00\x01\x01")

        # REQUEST message (ID 6, index 0, begin 16384, length 16384)
        req = create_request(0, 16384, 16384)
        self.assertEqual(len(req), 17)
        self.assertEqual(req[4], 6)

    def test_piece_assembly_and_sha1_verification(self):
        meta = parse_torrent_file(TORRENT_PATH)
        mgr = PieceManager(meta)

        raw_payload = PAYLOAD_PATH.read_bytes()
        piece0_expected = raw_payload[:32768]
        piece1_expected = raw_payload[32768:]

        # Break piece 0 into two 16KB blocks
        blocks_piece0 = {
            0: piece0_expected[:16384],
            16384: piece0_expected[16384:]
        }
        valid, data = mgr.assemble_and_verify_piece(0, blocks_piece0)
        self.assertTrue(valid, "SHA-1 verification failed for piece 0")
        self.assertEqual(data, piece0_expected)

        # Corrupt block test
        corrupt_blocks = {
            0: b"CORRUPTED_DATA_BLOCK" + piece0_expected[20:16384],
            16384: piece0_expected[16384:]
        }
        valid_corrupt, _ = mgr.assemble_and_verify_piece(0, corrupt_blocks)
        self.assertFalse(valid_corrupt, "Corrupted piece passed SHA-1 hash check!")


if __name__ == "__main__":
    unittest.main()
