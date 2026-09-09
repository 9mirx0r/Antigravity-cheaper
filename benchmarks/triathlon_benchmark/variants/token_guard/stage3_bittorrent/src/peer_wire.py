from __future__ import annotations
import struct
from typing import Tuple

PROTOCOL_STRING = b"BitTorrent protocol"

MSG_CHOKE = 0
MSG_UNCHOKE = 1
MSG_INTERESTED = 2
MSG_NOT_INTERESTED = 3
MSG_HAVE = 4
MSG_BITFIELD = 5
MSG_REQUEST = 6
MSG_PIECE = 7


def create_handshake(info_hash: bytes, peer_id: bytes) -> bytes:
    """Creates a 68-byte BitTorrent handshake packet."""
    if len(info_hash) != 20:
        raise ValueError(f"info_hash must be 20 bytes, got {len(info_hash)}")
    if len(peer_id) != 20:
        raise ValueError(f"peer_id must be 20 bytes, got {len(peer_id)}")

    pstrlen = bytes([len(PROTOCOL_STRING)])  # 19
    reserved = b"\x00" * 8
    return pstrlen + PROTOCOL_STRING + reserved + info_hash + peer_id


def parse_handshake(raw: bytes) -> Tuple[bytes, bytes]:
    """Parses and validates a 68-byte BitTorrent handshake packet."""
    if len(raw) < 68:
        raise ValueError(f"Handshake packet too short: {len(raw)} bytes")

    pstrlen = raw[0]
    if pstrlen != len(PROTOCOL_STRING):
        raise ValueError(f"Invalid protocol length prefix: {pstrlen}")

    pstr = raw[1 : 1 + pstrlen]
    if pstr != PROTOCOL_STRING:
        raise ValueError(f"Invalid protocol string: {pstr}")

    info_hash = raw[28:48]
    peer_id = raw[48:68]
    return info_hash, peer_id


def create_message(msg_id: int, payload: bytes = b"") -> bytes:
    """Creates a length-prefixed peer wire message."""
    length_prefix = len(payload) + 1
    return struct.pack(">IB", length_prefix, msg_id) + payload


def create_request(piece_index: int, block_offset: int, block_length: int = 16384) -> bytes:
    """Creates a REQUEST message (ID 6)."""
    payload = struct.pack(">III", piece_index, block_offset, block_length)
    return create_message(MSG_REQUEST, payload)
