"""Financial Settlement Engine — Buggy Reference Implementation.

This package contains 6 modules that together implement a distributed
financial settlement system.  There are 8 bugs planted across the codebase.
"""

from .merkle_tree import MerkleTree
from .wire_protocol import WireCodec, MessageType, BalanceUpdateMessage, OrderSubmitMessage
from .crdt_ledger import GCounter, PNCounter, DistributedLedger
from .order_book import OrderBook, Order, Side, OrderType, Trade
from .event_journal import EventJournal, Event
from .settlement import SettlementCoordinator, Obligation, SettlementResult
from .signatures import SignatureVerifier, SignedMessage, generate_key_pair

__all__ = [
    "MerkleTree",
    "WireCodec", "MessageType", "BalanceUpdateMessage", "OrderSubmitMessage",
    "GCounter", "PNCounter", "DistributedLedger",
    "OrderBook", "Order", "Side", "OrderType", "Trade",
    "EventJournal", "Event",
    "SettlementCoordinator", "Obligation", "SettlementResult",
    "SignatureVerifier", "SignedMessage", "generate_key_pair",
]
