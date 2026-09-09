"""BitTorrent Peer Wire Protocol Implementation."""

from __future__ import annotations
import struct
from typing import Tuple


PROTOCOL_STRING = b"BitTorrent protocol"

CHOKE = 0
UNCHOKE = 1
INTERESTED = 2
NOT_INTERESTED = 3
HAVE = 4
BITFIELD = 5
REQUEST = 6
PIECE = 7


def create_handshake(info_hash: bytes, peer_id: bytes) -> bytes:
    """Creates the standard 68-byte BitTorrent peer handshake."""
    if len(info_hash) != 20:
        raise ValueError(f"info_hash must be 20 bytes, got {len(info_hash)}")
    if len(peer_id) != 20:
        raise ValueError(f"peer_id must be 20 bytes, got {len(peer_id)}")

    pstrlen = bytes([len(PROTOCOL_STRING)])
    reserved = b"\x00" * 8
    return pstrlen + PROTOCOL_STRING + reserved + info_hash + peer_id


def parse_handshake(raw: bytes) -> Tuple[bytes, bytes]:
    """Parses and validates a 68-byte BitTorrent handshake.

    Returns (info_hash, peer_id).
    """
    if len(raw) < 68:
        raise ValueError(f"Handshake too short: {len(raw)} bytes (expected 68)")

    pstrlen = raw[0]
    pstr = raw[1 : 1 + pstrlen]
    if pstr != PROTOCOL_STRING:
        raise ValueError(f"Invalid protocol string: {pstr!r}")

    info_hash = raw[28:48]
    peer_id = raw[48:68]
    return info_hash, peer_id


def create_message(msg_id: int, payload: bytes = b"") -> bytes:
    """Creates a peer wire message with 4-byte length prefix and 1-byte ID."""
    length = len(payload) + 1
    return struct.pack(">IB", length, msg_id) + payload


def create_request(
    piece_index: int, block_offset: int, block_length: int = 16384
) -> bytes:
    """Creates a REQUEST message (ID 6) for a block of a piece."""
    payload = struct.pack(">III", piece_index, block_offset, block_length)
    return create_message(REQUEST, payload)
