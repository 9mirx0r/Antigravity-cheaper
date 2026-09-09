"""Binary wire protocol for inter-node communication.

Messages are framed as:
    [4-byte big-endian length prefix][1-byte msg_type][payload][4-byte CRC-32]

The length prefix includes msg_type + payload + CRC (i.e. total frame minus
the 4-byte length field itself).
"""

from __future__ import annotations

import struct
import zlib
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple


class MessageType(IntEnum):
    HANDSHAKE = 0x01
    BALANCE_UPDATE = 0x02
    ORDER_SUBMIT = 0x03
    SETTLEMENT_REQ = 0x04
    SETTLEMENT_ACK = 0x05
    HEARTBEAT = 0x06
    MERKLE_SYNC = 0x07


class ProtocolError(Exception):
    pass


class WireCodec:
    """Encode and decode binary wire-protocol frames."""

    HEADER_SIZE = 4   # length prefix
    TYPE_SIZE = 1
    CRC_SIZE = 4

    @staticmethod
    def encode(msg_type: MessageType, payload: bytes) -> bytes:
        """Serialize a message into a wire frame."""
        body = struct.pack("!B", int(msg_type)) + payload
        crc = zlib.crc32(body) & 0xFFFFFFFF
        crc_bytes = struct.pack("!I", crc)
        frame_len = len(body) + WireCodec.CRC_SIZE

        # BUG #2: Length prefix encoded as LITTLE-endian but the spec and
        # decode() expect BIG-endian.
        length_bytes = struct.pack("<I", frame_len)

        return length_bytes + body + crc_bytes

    @staticmethod
    def decode(data: bytes) -> Tuple[MessageType, bytes, int]:
        """Decode one frame from *data*.

        Returns (msg_type, payload, total_bytes_consumed).
        Raises ProtocolError on CRC mismatch or insufficient data.
        """
        if len(data) < WireCodec.HEADER_SIZE:
            raise ProtocolError("Insufficient data for length header")

        frame_len = struct.unpack("!I", data[:4])[0]
        total = WireCodec.HEADER_SIZE + frame_len

        if len(data) < total:
            raise ProtocolError(
                f"Incomplete frame: need {total} bytes, have {len(data)}"
            )

        body_with_crc = data[4:total]
        body = body_with_crc[: -WireCodec.CRC_SIZE]
        crc_received = struct.unpack("!I", body_with_crc[-WireCodec.CRC_SIZE:])[0]
        crc_computed = zlib.crc32(body) & 0xFFFFFFFF

        if crc_received != crc_computed:
            raise ProtocolError(
                f"CRC mismatch: received 0x{crc_received:08X}, "
                f"computed 0x{crc_computed:08X}"
            )

        msg_type = MessageType(body[0])
        payload = body[1:]

        return msg_type, payload, total


class BalanceUpdateMessage:
    """Structured payload for BALANCE_UPDATE messages."""

    def __init__(self, account_id: str, amount_cents: int, sequence: int, timestamp: float):
        self.account_id = account_id
        self.amount_cents = amount_cents
        self.sequence = sequence
        self.timestamp = timestamp

    def serialize(self) -> bytes:
        acct_bytes = self.account_id.encode("utf-8")
        return (
            struct.pack("!H", len(acct_bytes))
            + acct_bytes
            + struct.pack("!q", self.amount_cents)
            + struct.pack("!I", self.sequence)
            + struct.pack("!d", self.timestamp)
        )

    @classmethod
    def deserialize(cls, data: bytes) -> "BalanceUpdateMessage":
        offset = 0
        acct_len = struct.unpack("!H", data[offset : offset + 2])[0]
        offset += 2
        account_id = data[offset : offset + acct_len].decode("utf-8")
        offset += acct_len
        amount_cents = struct.unpack("!q", data[offset : offset + 8])[0]
        offset += 8
        sequence = struct.unpack("!I", data[offset : offset + 4])[0]
        offset += 4
        timestamp = struct.unpack("!d", data[offset : offset + 8])[0]
        offset += 8
        return cls(account_id, amount_cents, sequence, timestamp)


class OrderSubmitMessage:
    """Structured payload for ORDER_SUBMIT messages."""

    def __init__(self, order_id: str, side: str, symbol: str,
                 price_cents: int, quantity: int, order_type: str = "LIMIT"):
        self.order_id = order_id
        self.side = side          # "BUY" or "SELL"
        self.symbol = symbol
        self.price_cents = price_cents
        self.quantity = quantity
        self.order_type = order_type

    def serialize(self) -> bytes:
        oid = self.order_id.encode("utf-8")
        side = self.side.encode("utf-8")
        sym = self.symbol.encode("utf-8")
        otype = self.order_type.encode("utf-8")
        return (
            struct.pack("!H", len(oid)) + oid
            + struct.pack("!H", len(side)) + side
            + struct.pack("!H", len(sym)) + sym
            + struct.pack("!q", self.price_cents)
            + struct.pack("!I", self.quantity)
            + struct.pack("!H", len(otype)) + otype
        )

    @classmethod
    def deserialize(cls, data: bytes) -> "OrderSubmitMessage":
        offset = 0

        def read_str() -> str:
            nonlocal offset
            slen = struct.unpack("!H", data[offset : offset + 2])[0]
            offset += 2
            s = data[offset : offset + slen].decode("utf-8")
            offset += slen
            return s

        order_id = read_str()
        side = read_str()
        symbol = read_str()
        price_cents = struct.unpack("!q", data[offset : offset + 8])[0]
        offset += 8
        quantity = struct.unpack("!I", data[offset : offset + 4])[0]
        offset += 4
        order_type = read_str()
        return cls(order_id, side, symbol, price_cents, quantity, order_type)
