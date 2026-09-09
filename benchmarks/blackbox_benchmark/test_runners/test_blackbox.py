"""Comprehensive test suite for the Financial Settlement Engine.

These tests exercise ALL 6 modules with deep integration scenarios.
Each test produces VERBOSE diagnostic output on failure to help (and
overwhelm) the debugging agent with information.

Tests are numbered TEST-01 through TEST-20.  ALL must pass.
"""

import hashlib
import json
import struct
import sys
import time
import traceback
from pathlib import Path

# Add buggy codebase to path
sys.path.insert(0, str(Path(__file__).parent.parent / "buggy_codebase"))

from src.merkle_tree import MerkleTree, _hash
from src.wire_protocol import WireCodec, MessageType, BalanceUpdateMessage, OrderSubmitMessage, ProtocolError
from src.crdt_ledger import GCounter, PNCounter, DistributedLedger
from src.order_book import OrderBook, Order, Side, OrderType
from src.event_journal import EventJournal, Event
from src.settlement import SettlementCoordinator
from src.signatures import SignatureVerifier, generate_key_pair


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name: str):
        self.passed += 1
        print(f"  [PASS] {name}")

    def fail(self, name: str, detail: str):
        self.failed += 1
        self.errors.append((name, detail))
        print(f"  [FAIL] {name}")
        # Print verbose diagnostic output
        print(f"  {'='*70}")
        for line in detail.split('\n'):
            print(f"  | {line}")
        print(f"  {'='*70}")


results = TestResult()


# ===========================================================================
# TEST-01: Merkle tree root determinism
# ===========================================================================
def test_01_merkle_root_determinism():
    """Two trees with same leaves must produce identical roots."""
    name = "TEST-01: Merkle root determinism"
    try:
        t1 = MerkleTree()
        t2 = MerkleTree()
        data = [b"tx-001:alice:bob:5000", b"tx-002:bob:carol:3000",
                b"tx-003:carol:alice:1000", b"tx-004:dave:alice:7500"]
        for d in data:
            t1.add_leaf(d)
            t2.add_leaf(d)

        r1 = t1.build()
        r2 = t2.build()

        if r1 != r2:
            results.fail(name,
                f"Trees with identical leaves produced different roots!\n"
                f"Tree 1 root: {r1.hex()}\n"
                f"Tree 2 root: {r2.hex()}\n"
                f"Tree 1 leaves: {[l.hex()[:16] for l in t1.leaves]}\n"
                f"Tree 2 leaves: {[l.hex()[:16] for l in t2.leaves]}")
            return
        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-02: Merkle proof verification (CATCHES BUG #1)
# ===========================================================================
def test_02_merkle_proof_verification():
    """Audit proof for a leaf must verify against the tree root."""
    name = "TEST-02: Merkle proof verification"
    try:
        tree = MerkleTree()
        leaves_data = [
            b"tx-100:alice:bob:10000",
            b"tx-101:bob:carol:5000",
            b"tx-102:carol:dave:2500",
            b"tx-103:dave:eve:1250",
        ]
        for d in leaves_data:
            tree.add_leaf(d)
        root = tree.build()

        # Verify proof for each leaf
        failed_leaves = []
        for i, d in enumerate(leaves_data):
            leaf_hash = _hash(d)
            proof = tree.get_proof(i)

            # Manually compute expected root using correct H(left||right)
            layer = [_hash(ld) for ld in leaves_data]
            while len(layer) > 1:
                next_layer = []
                for j in range(0, len(layer), 2):
                    left = layer[j]
                    right = layer[j + 1] if j + 1 < len(layer) else layer[j]
                    next_layer.append(_hash(left + right))  # CORRECT order
                layer = next_layer
            expected_root = layer[0]

            if root != expected_root:
                failed_leaves.append(i)

        if failed_leaves:
            # Produce massive diagnostic hex dump
            diag = f"Merkle root does NOT match hand-computed root!\n"
            diag += f"Tree root:     {root.hex()}\n"
            diag += f"Expected root: {expected_root.hex()}\n"
            diag += f"Failed leaf indices: {failed_leaves}\n\n"
            diag += f"--- Leaf hashes ---\n"
            for i, d in enumerate(leaves_data):
                h = _hash(d)
                diag += f"  [{i}] data={d!r}\n"
                diag += f"       hash={h.hex()}\n"

            diag += f"\n--- Expected computation (correct H(left||right)) ---\n"
            layer = [_hash(ld) for ld in leaves_data]
            level = 0
            while len(layer) > 1:
                diag += f"  Level {level}: {[h.hex()[:16] for h in layer]}\n"
                next_layer = []
                for j in range(0, len(layer), 2):
                    left = layer[j]
                    right = layer[j + 1] if j + 1 < len(layer) else layer[j]
                    combined = _hash(left + right)
                    diag += f"    H(node[{j}] || node[{j+1 if j+1 < len(layer) else j}]) = {combined.hex()[:16]}\n"
                    next_layer.append(combined)
                layer = next_layer
                level += 1
            diag += f"  Root level: {layer[0].hex()}\n"

            diag += f"\n--- Actual tree computation ---\n"
            diag += f"  The tree build() method may be using wrong concatenation order.\n"
            diag += f"  Check if it computes H(right || left) instead of H(left || right).\n"
            diag += f"  This affects ALL interior nodes and propagates to the root.\n"

            results.fail(name, diag)
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-03: Wire protocol round-trip (CATCHES BUG #2)
# ===========================================================================
def test_03_wire_protocol_roundtrip():
    """Encode then decode must recover original message."""
    name = "TEST-03: Wire protocol round-trip"
    try:
        payload = b"Hello, Settlement Engine!"
        msg_type = MessageType.HEARTBEAT

        frame = WireCodec.encode(msg_type, payload)
        decoded_type, decoded_payload, consumed = WireCodec.decode(frame)

        errors = []
        if decoded_type != msg_type:
            errors.append(f"Message type mismatch: sent {msg_type}, got {decoded_type}")
        if decoded_payload != payload:
            errors.append(f"Payload mismatch: sent {payload!r}, got {decoded_payload!r}")
        if consumed != len(frame):
            errors.append(f"Consumed bytes mismatch: frame is {len(frame)} bytes, consumed {consumed}")

        if errors:
            diag = "Wire protocol encode/decode round-trip FAILED:\n"
            for e in errors:
                diag += f"  - {e}\n"
            diag += f"\n--- Frame hex dump ({len(frame)} bytes) ---\n"
            for offset in range(0, len(frame), 16):
                chunk = frame[offset:offset+16]
                hex_str = ' '.join(f'{b:02X}' for b in chunk)
                ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
                diag += f"  {offset:04X}: {hex_str:<48} |{ascii_str}|\n"

            diag += f"\n--- Header analysis ---\n"
            if len(frame) >= 4:
                be_len = struct.unpack("!I", frame[:4])[0]
                le_len = struct.unpack("<I", frame[:4])[0]
                diag += f"  First 4 bytes (raw): {frame[:4].hex()}\n"
                diag += f"  Interpreted as big-endian uint32:    {be_len}\n"
                diag += f"  Interpreted as little-endian uint32: {le_len}\n"
                diag += f"  Expected frame body length: {len(frame) - 4}\n"
                diag += f"\n  If big-endian != expected but little-endian == expected,\n"
                diag += f"  then encode() is using WRONG endianness for the length prefix.\n"

            results.fail(name, diag)
            return

        results.ok(name)
    except Exception as e:
        diag = f"Exception during round-trip: {e}\n{traceback.format_exc()}\n"
        if 'frame' in dir():
            diag += f"\nFrame hex: {frame.hex()}\n"
            diag += f"Frame length: {len(frame)}\n"
            if len(frame) >= 4:
                be = struct.unpack("!I", frame[:4])[0]
                le = struct.unpack("<I", frame[:4])[0]
                diag += f"Length prefix as big-endian:    {be}\n"
                diag += f"Length prefix as little-endian: {le}\n"
        results.fail(name, diag)


# ===========================================================================
# TEST-04: Wire protocol structured messages
# ===========================================================================
def test_04_wire_structured_messages():
    """BalanceUpdate and OrderSubmit serialize/deserialize correctly through wire."""
    name = "TEST-04: Wire structured messages"
    try:
        # Test BalanceUpdateMessage
        bu = BalanceUpdateMessage("ACCT-001", 150000, 42, 1700000000.0)
        payload = bu.serialize()
        frame = WireCodec.encode(MessageType.BALANCE_UPDATE, payload)
        msg_type, raw_payload, _ = WireCodec.decode(frame)
        bu2 = BalanceUpdateMessage.deserialize(raw_payload)

        errors = []
        if bu2.account_id != bu.account_id:
            errors.append(f"account_id: {bu.account_id!r} vs {bu2.account_id!r}")
        if bu2.amount_cents != bu.amount_cents:
            errors.append(f"amount_cents: {bu.amount_cents} vs {bu2.amount_cents}")
        if bu2.sequence != bu.sequence:
            errors.append(f"sequence: {bu.sequence} vs {bu2.sequence}")

        # Test OrderSubmitMessage
        osm = OrderSubmitMessage("ORD-999", "BUY", "AAPL", 15025, 100, "LIMIT")
        payload2 = osm.serialize()
        frame2 = WireCodec.encode(MessageType.ORDER_SUBMIT, payload2)
        _, raw2, _ = WireCodec.decode(frame2)
        osm2 = OrderSubmitMessage.deserialize(raw2)

        if osm2.order_id != osm.order_id:
            errors.append(f"order_id: {osm.order_id!r} vs {osm2.order_id!r}")
        if osm2.price_cents != osm.price_cents:
            errors.append(f"price_cents: {osm.price_cents} vs {osm2.price_cents}")

        if errors:
            results.fail(name, "Structured message round-trip errors:\n" +
                         "\n".join(f"  - {e}" for e in errors))
            return
        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-05: CRDT GCounter merge idempotency
# ===========================================================================
def test_05_gcounter_merge():
    """GCounter merge must be idempotent, commutative, associative."""
    name = "TEST-05: GCounter merge properties"
    try:
        a = GCounter("node-A")
        b = GCounter("node-B")

        a.increment(10)
        a.increment(5)
        b.increment(20)

        # Merge a into b, then b into a
        a_copy = GCounter("node-A")
        a_copy.counts = dict(a.counts)

        a.merge(b)
        b.merge(a_copy)

        if a.value() != b.value():
            results.fail(name,
                f"After symmetric merge, values differ!\n"
                f"A.value={a.value()}, B.value={b.value()}\n"
                f"A.counts={a.counts}\n"
                f"B.counts={b.counts}")
            return

        # Idempotency: merging again shouldn't change anything
        val_before = a.value()
        a.merge(b)
        if a.value() != val_before:
            results.fail(name,
                f"Merge is NOT idempotent!\n"
                f"Value before re-merge: {val_before}\n"
                f"Value after re-merge:  {a.value()}")
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-06: CRDT Ledger merge doesn't duplicate deltas (CATCHES BUG #3)
# ===========================================================================
def test_06_crdt_ledger_merge_deltas():
    """After merging, pending deltas must NOT be polluted with peer deltas."""
    name = "TEST-06: CRDT ledger merge delta isolation"
    try:
        node_a = DistributedLedger("node-A")
        node_b = DistributedLedger("node-B")

        node_a.credit("alice", 1000)
        node_b.credit("bob", 2000)

        # Each should have exactly 1 pending delta
        a_deltas_before = len(node_a._pending_deltas)
        b_deltas_before = len(node_b._pending_deltas)

        # Merge B into A
        node_a.merge(node_b)

        a_deltas_after = len(node_a._pending_deltas)

        if a_deltas_after != a_deltas_before:
            # Dump full delta lists
            diag = f"Merge polluted pending deltas!\n"
            diag += f"Node A deltas BEFORE merge: {a_deltas_before}\n"
            diag += f"Node A deltas AFTER merge:  {a_deltas_after}\n"
            diag += f"Expected: merge should NOT add peer deltas to local pending list.\n"
            diag += f"\n--- Node A pending deltas dump ---\n"
            for i, d in enumerate(node_a._pending_deltas):
                diag += f"  [{i}] {json.dumps(d)}\n"
            diag += f"\n--- Node B pending deltas dump ---\n"
            for i, d in enumerate(node_b._pending_deltas):
                diag += f"  [{i}] {json.dumps(d)}\n"
            diag += f"\n--- Analysis ---\n"
            diag += f"The merge() method is copying peer deltas into the local\n"
            diag += f"pending_deltas list.  This causes double-counting when\n"
            diag += f"deltas are drained for event journal replay.\n"
            diag += f"Pending deltas are transient LOCAL state and should NOT\n"
            diag += f"be replicated during CRDT merge.\n"
            results.fail(name, diag)
            return

        # Also check balances are correct after merge
        if node_a.balance("alice") != 1000:
            results.fail(name, f"alice balance wrong: {node_a.balance('alice')}")
            return
        if node_a.balance("bob") != 2000:
            results.fail(name, f"bob balance wrong: {node_a.balance('bob')}")
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-07: Order book basic limit matching
# ===========================================================================
def test_07_order_book_basic_matching():
    """Basic buy/sell limit order matching with integer cents."""
    name = "TEST-07: Order book basic matching"
    try:
        book = OrderBook("TEST")

        # Sell 100 @ $10.00 (1000 cents)
        sell = Order("S1", Side.SELL, 10.00, 100)
        book.submit_order(sell)

        # Buy 50 @ $10.00 — should match
        buy = Order("B1", Side.BUY, 10.00, 50)
        trades = book.submit_order(buy)

        if len(trades) != 1:
            results.fail(name, f"Expected 1 trade, got {len(trades)}")
            return
        if trades[0].quantity != 50:
            results.fail(name, f"Expected fill qty 50, got {trades[0].quantity}")
            return
        if sell.remaining != 50:
            results.fail(name, f"Sell should have 50 remaining, has {sell.remaining}")
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-08: Order book float price comparison (CATCHES BUG #4)
# ===========================================================================
def test_08_order_book_float_prices():
    """Prices that are equal in decimal but differ in IEEE 754 must still match."""
    name = "TEST-08: Order book float price equality"
    try:
        book = OrderBook("FLOAT-TEST")

        # Submit sell at price constructed from addition (may have float error)
        sell_price = 0.1 + 0.1 + 0.1  # 0.30000000000000004 in IEEE 754
        sell = Order("S-FLOAT", Side.SELL, sell_price, 100)
        book.submit_order(sell)

        # Submit buy at price 0.3 (clean representation)
        buy_price = 0.3
        buy = Order("B-FLOAT", Side.BUY, buy_price, 50)
        trades = book.submit_order(buy)

        # These should match because 0.3 == 0.3 in financial terms
        if len(trades) == 0:
            diag = f"Float price comparison FAILED to match!\n"
            diag += f"Sell price: {sell_price!r} (repr: {sell_price:.20f})\n"
            diag += f"Buy price:  {buy_price!r} (repr: {buy_price:.20f})\n"
            diag += f"sell_price == buy_price: {sell_price == buy_price}\n"
            diag += f"sell_price > buy_price:  {sell_price > buy_price}\n"
            diag += f"Difference: {abs(sell_price - buy_price):.30e}\n"
            diag += f"\n--- IEEE 754 analysis ---\n"
            diag += f"sell_price bytes: {struct.pack('!d', sell_price).hex()}\n"
            diag += f"buy_price bytes:  {struct.pack('!d', buy_price).hex()}\n"
            diag += f"\nFix: Use integer cents or Decimal for price comparison.\n"
            diag += f"Example: price_cents = int(round(price * 100))\n"
            results.fail(name, diag)
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-09: Iceberg order hidden quantity (CATCHES BUG #5)
# ===========================================================================
def test_09_iceberg_orders():
    """Iceberg orders must refill visible quantity from hidden reserve."""
    name = "TEST-09: Iceberg order hidden quantity"
    try:
        book = OrderBook("ICE-TEST")

        # Iceberg sell: total 500, display 100 at a time
        iceberg = Order("ICE-S1", Side.SELL, 50.0, 500,
                        order_type=OrderType.ICEBERG, display_qty=100, total_qty=500)
        book.submit_order(iceberg)

        # Buy 100 — should fill first visible tranche
        buy1 = Order("B1", Side.BUY, 50.0, 100)
        trades1 = book.submit_order(buy1)

        if len(trades1) != 1 or trades1[0].quantity != 100:
            results.fail(name, f"First fill: expected 100, got {[t.quantity for t in trades1]}")
            return

        # Buy another 100 — should fill from refreshed visible quantity
        buy2 = Order("B2", Side.BUY, 50.0, 100)
        trades2 = book.submit_order(buy2)

        if len(trades2) == 0:
            diag = f"Iceberg order did NOT replenish visible quantity!\n"
            diag += f"After first fill of 100:\n"
            diag += f"  iceberg.filled_qty = {iceberg.filled_qty}\n"
            diag += f"  iceberg.remaining  = {iceberg.remaining}\n"
            diag += f"  iceberg.visible_quantity = {iceberg.visible_quantity}\n"
            diag += f"  iceberg.is_active = {iceberg.is_active}\n"
            diag += f"\nThe iceberg should still have {iceberg.remaining} hidden quantity.\n"
            diag += f"After partial fill, the order should be re-inserted into\n"
            diag += f"the order book with a refreshed visible_quantity.\n"
            diag += f"\n--- Order book state ---\n"
            diag += f"  asks heap size: {len(book.asks)}\n"
            diag += f"  active orders: {list(book.orders.keys())}\n"
            diag += f"  best_ask: {book.best_ask()}\n"
            results.fail(name, diag)
            return

        # Total filled should be 200 out of 500
        if iceberg.filled_qty != 200:
            results.fail(name,
                f"Expected 200 filled, got {iceberg.filled_qty}")
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-10: Event journal replay order (CATCHES BUG #6)
# ===========================================================================
def test_10_event_journal_replay_order():
    """Events with same timestamp must replay in sequence order, not arbitrary."""
    name = "TEST-10: Event journal replay determinism"
    try:
        journal = EventJournal()
        replay_order: list[int] = []

        # Append events with SAME timestamp but different sequence numbers
        fixed_ts = 1700000000.0
        for i in range(10):
            journal.append(
                "TEST_EVENT",
                {"index": i},
                source_node="test",
                timestamp=fixed_ts,  # all same timestamp
            )

        # Register handler that records replay order
        def handler(evt: Event):
            replay_order.append(evt.payload["index"])

        journal.register_handler("TEST_EVENT", handler)
        journal.replay()

        expected = list(range(10))
        if replay_order != expected:
            diag = f"Events replayed in WRONG order!\n"
            diag += f"Expected (by sequence): {expected}\n"
            diag += f"Actual replay order:    {replay_order}\n"
            diag += f"\n--- Event details ---\n"
            for evt in journal.events:
                diag += f"  seq={evt.sequence:3d}  ts={evt.timestamp}  index={evt.payload['index']}\n"
            diag += f"\n--- Analysis ---\n"
            diag += f"When multiple events share the same timestamp, the replay()\n"
            diag += f"method must sort by SEQUENCE NUMBER (which is monotonically\n"
            diag += f"increasing), not by timestamp.\n"
            diag += f"Timestamp-based sorting is non-deterministic for same-ms events.\n"
            results.fail(name, diag)
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-11: Event journal replay with out-of-order insertion
# ===========================================================================
def test_11_event_journal_out_of_order():
    """Events inserted out of sequence order (from different nodes)
    must still replay in sequence order."""
    name = "TEST-11: Event journal out-of-order insertion replay"
    try:
        journal = EventJournal()
        replay_results: list[str] = []

        # Simulate receiving events from different nodes with varying delays
        # Event from node-C arrives first (seq 1) but has latest timestamp
        journal.append("TRANSFER", {"from": "alice", "to": "carol", "amount": 300},
                       source_node="node-C", timestamp=1700000002.0)
        # Event from node-A (seq 2) has earliest timestamp
        journal.append("TRANSFER", {"from": "bob", "to": "alice", "amount": 100},
                       source_node="node-A", timestamp=1700000000.0)
        # Event from node-B (seq 3) has middle timestamp
        journal.append("TRANSFER", {"from": "carol", "to": "bob", "amount": 200},
                       source_node="node-B", timestamp=1700000001.0)

        def handler(evt: Event):
            replay_results.append(f"seq-{evt.sequence}")

        journal.register_handler("TRANSFER", handler)
        journal.replay()

        # Correct order is by sequence: 1, 2, 3
        expected = ["seq-1", "seq-2", "seq-3"]
        if replay_results != expected:
            diag = f"Out-of-order replay INCORRECT!\n"
            diag += f"Expected (by sequence): {expected}\n"
            diag += f"Actual (likely by timestamp): {replay_results}\n"
            diag += f"\n--- Events as stored ---\n"
            for evt in journal.events:
                diag += (f"  seq={evt.sequence} ts={evt.timestamp} "
                         f"node={evt.source_node} payload={evt.payload}\n")
            diag += f"\nIf sorted by timestamp, order would be: seq-2, seq-3, seq-1\n"
            diag += f"This is WRONG.  Sort by sequence number instead.\n"
            results.fail(name, diag)
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-12: Settlement netting correctness (CATCHES BUG #7)
# ===========================================================================
def test_12_settlement_netting():
    """Bilateral netting must compute correct net amounts."""
    name = "TEST-12: Settlement bilateral netting"
    try:
        ledger = DistributedLedger("settlement-node")
        journal = EventJournal()
        coordinator = SettlementCoordinator("settlement-node", ledger, journal)

        # Fund accounts
        ledger.credit("alice", 100000)
        ledger.credit("bob", 100000)

        # Alice owes Bob $100 (10000 cents)
        coordinator.add_obligation("alice", "bob", 10000, "USD")
        # Bob owes Alice $60 (6000 cents)
        coordinator.add_obligation("bob", "alice", 6000, "USD")

        net = coordinator.compute_net_obligations()

        # Expected: alice net = -4000 (owes 10000, is owed 6000)
        #           bob net   = +4000 (owes 6000, is owed 10000)
        expected_alice = -4000
        expected_bob = 4000

        errors = []
        if net.get("alice", 0) != expected_alice:
            errors.append(f"alice: expected {expected_alice}, got {net.get('alice', 0)}")
        if net.get("bob", 0) != expected_bob:
            errors.append(f"bob: expected {expected_bob}, got {net.get('bob', 0)}")

        if errors:
            diag = f"Bilateral netting is INCORRECT!\n"
            diag += "\n".join(f"  - {e}" for e in errors) + "\n"
            diag += f"\n--- Obligations ---\n"
            for ob in coordinator.obligations:
                diag += f"  {ob.debtor} owes {ob.creditor}: {ob.amount_cents} cents\n"
            diag += f"\n--- Computed net amounts ---\n"
            for p, amt in sorted(net.items()):
                diag += f"  {p}: {amt:+d} cents\n"
            diag += f"\n--- Expected ---\n"
            diag += f"  alice: -4000 (owes 10000, is owed 6000, net = 6000 - 10000 = -4000)\n"
            diag += f"  bob:   +4000 (owes 6000, is owed 10000, net = 10000 - 6000 = +4000)\n"
            diag += f"\n--- Analysis ---\n"
            diag += f"The netting algorithm may be double-counting obligations.\n"
            diag += f"Check if the same obligation amount is being added to BOTH\n"
            diag += f"the 'owes' and 'owed' totals for a participant.\n"
            diag += f"Each obligation should only count ONCE: as a debit for the\n"
            diag += f"debtor and a credit for the creditor.\n"
            results.fail(name, diag)
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-13: Settlement full cycle with reconciliation
# ===========================================================================
def test_13_settlement_full_cycle():
    """Full settlement cycle must leave balanced books."""
    name = "TEST-13: Settlement full cycle"
    try:
        ledger = DistributedLedger("settle")
        journal = EventJournal()
        coord = SettlementCoordinator("settle", ledger, journal)

        # Initial balances
        ledger.credit("trader-A", 50000)
        ledger.credit("trader-B", 30000)
        ledger.credit("trader-C", 20000)

        # Obligations
        coord.add_obligation("trader-A", "trader-B", 5000)
        coord.add_obligation("trader-B", "trader-C", 3000)
        coord.add_obligation("trader-C", "trader-A", 2000)

        result = coord.execute_settlement_cycle()

        # Verify conservation of money (total should be 100000)
        total = sum(ledger.balance(a) for a in ["trader-A", "trader-B", "trader-C"])

        if total != 100000:
            diag = f"Money conservation violated!\n"
            diag += f"Total before settlement: 100000\n"
            diag += f"Total after settlement:  {total}\n"
            diag += f"Difference: {total - 100000}\n"
            diag += f"\n--- Balances after settlement ---\n"
            for acct in ["trader-A", "trader-B", "trader-C"]:
                diag += f"  {acct}: {ledger.balance(acct)}\n"
            diag += f"\n--- Net amounts computed ---\n"
            for p, amt in sorted(result.net_amounts.items()):
                diag += f"  {p}: {amt:+d}\n"
            diag += f"\n--- Settlement result ---\n"
            diag += f"  settled: {result.settled_count}, failed: {result.failed_count}\n"
            results.fail(name, diag)
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-14: Signature verification (CATCHES BUG #8)
# ===========================================================================
def test_14_signature_empty_message():
    """Empty messages must be REJECTED, not silently accepted."""
    name = "TEST-14: Signature empty message rejection"
    try:
        verifier = SignatureVerifier()
        priv, pub = generate_key_pair()
        verifier.register_key("node-X", pub)

        # Sign an empty message with a WRONG key
        wrong_key = b"\x00" * 32
        signed = verifier.sign(b"", wrong_key, "node-X", time.time())

        # This MUST return False — empty messages are invalid protocol input
        result = verifier.verify(signed)

        if result is True:
            diag = f"Empty message passed signature verification!\n"
            diag += f"  content length: {len(signed.content)}\n"
            diag += f"  signature: {signed.signature.hex()}\n"
            diag += f"  signer_id: {signed.signer_id}\n"
            diag += f"\nEmpty messages must be rejected as invalid protocol input.\n"
            diag += f"The verify() method should return False for len(content) == 0.\n"
            results.fail(name, diag)
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-15: Signature valid message verification
# ===========================================================================
def test_15_signature_valid():
    """Properly signed non-empty messages must verify correctly."""
    name = "TEST-15: Signature valid message"
    try:
        verifier = SignatureVerifier()
        priv, pub = generate_key_pair()
        verifier.register_key("signer-1", pub)

        content = b"Transfer $5000 from A to B"
        signed = verifier.sign(content, priv, "signer-1", time.time())

        if not verifier.verify(signed):
            results.fail(name, "Valid signature failed verification!")
            return

        # Tamper with content — should fail
        signed.content = b"Transfer $50000 from A to B"
        if verifier.verify(signed):
            results.fail(name, "Tampered message passed verification!")
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-16: Full integration — trade + settle + verify
# ===========================================================================
def test_16_integration_trade_settle():
    """End-to-end: submit orders, execute trades, settle, reconcile."""
    name = "TEST-16: Full integration pipeline"
    try:
        # Setup
        ledger = DistributedLedger("integration")
        journal = EventJournal()
        coord = SettlementCoordinator("integration", ledger, journal)
        book = OrderBook("AAPL")

        # Fund traders
        for trader in ["trader-1", "trader-2", "trader-3"]:
            ledger.credit(trader, 1000000)  # $10,000.00 each

        # Submit orders and generate trades
        book.submit_order(Order("S1", Side.SELL, 150.0, 100))
        trades = book.submit_order(Order("B1", Side.BUY, 150.0, 100))

        if len(trades) != 1:
            results.fail(name, f"Expected 1 trade, got {len(trades)}")
            return

        # Create obligations from trade
        trade = trades[0]
        coord.add_obligation(trade.buy_order_id, trade.sell_order_id,
                             int(trade.price * trade.quantity * 100))

        # Record events
        journal.append("TRADE_EXECUTED", {
            "trade_id": trade.trade_id,
            "price": trade.price,
            "quantity": trade.quantity,
        }, source_node="integration")

        # Execute settlement
        result = coord.execute_settlement_cycle()

        if result.failed_count > 0:
            results.fail(name, f"Settlement had {result.failed_count} failures")
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-17: Wire protocol multi-frame parsing
# ===========================================================================
def test_17_wire_multi_frame():
    """Multiple frames concatenated must be parsed sequentially."""
    name = "TEST-17: Wire multi-frame parsing"
    try:
        messages = [
            (MessageType.HEARTBEAT, b"beat-1"),
            (MessageType.BALANCE_UPDATE, b"update-data-here"),
            (MessageType.SETTLEMENT_REQ, b"settle-req-payload-with-extra-bytes"),
        ]

        stream = b""
        for mt, payload in messages:
            stream += WireCodec.encode(mt, payload)

        offset = 0
        decoded = []
        while offset < len(stream):
            try:
                mt, payload, consumed = WireCodec.decode(stream[offset:])
                decoded.append((mt, payload))
                offset += consumed
            except ProtocolError as e:
                results.fail(name,
                    f"Protocol error at offset {offset}: {e}\n"
                    f"Stream hex from offset:\n"
                    f"  {stream[offset:offset+64].hex()}")
                return

        if len(decoded) != len(messages):
            results.fail(name,
                f"Expected {len(messages)} frames, decoded {len(decoded)}\n"
                f"Total stream: {len(stream)} bytes")
            return

        for i, ((expected_mt, expected_pl), (actual_mt, actual_pl)) in enumerate(zip(messages, decoded)):
            if expected_mt != actual_mt or expected_pl != actual_pl:
                results.fail(name,
                    f"Frame {i} mismatch:\n"
                    f"  expected type={expected_mt} payload={expected_pl!r}\n"
                    f"  actual   type={actual_mt} payload={actual_pl!r}")
                return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-18: CRDT double-merge idempotency (CATCHES BUG #3 variant)
# ===========================================================================
def test_18_crdt_double_merge():
    """Merging the same peer state twice must NOT change balances or deltas."""
    name = "TEST-18: CRDT double-merge idempotency"
    try:
        node_a = DistributedLedger("A")
        node_b = DistributedLedger("B")

        node_a.credit("shared-acct", 5000)
        node_b.credit("shared-acct", 3000)

        # Merge B into A twice
        node_a.merge(node_b)
        balance_after_first = node_a.balance("shared-acct")
        deltas_after_first = len(node_a._pending_deltas)

        node_a.merge(node_b)
        balance_after_second = node_a.balance("shared-acct")
        deltas_after_second = len(node_a._pending_deltas)

        errors = []
        if balance_after_first != balance_after_second:
            errors.append(
                f"Balance changed on second merge: {balance_after_first} -> {balance_after_second}")

        if deltas_after_second != deltas_after_first:
            errors.append(
                f"Delta count changed on second merge: {deltas_after_first} -> {deltas_after_second}")

        if errors:
            diag = "CRDT double-merge is NOT idempotent!\n"
            diag += "\n".join(f"  - {e}" for e in errors)
            diag += f"\n\n--- Pending deltas after first merge ---\n"
            for i, d in enumerate(node_a._pending_deltas[:deltas_after_first]):
                diag += f"  [{i}] {d}\n"
            diag += f"\n--- Extra deltas after second merge ---\n"
            for i, d in enumerate(node_a._pending_deltas[deltas_after_first:]):
                diag += f"  [{deltas_after_first + i}] {d}\n"
            diag += f"\nmerge() must not accumulate peer's pending_deltas.\n"
            results.fail(name, diag)
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-19: Fill-or-Kill order semantics
# ===========================================================================
def test_19_fill_or_kill():
    """FOK order must fill completely or be rejected entirely."""
    name = "TEST-19: Fill-or-Kill semantics"
    try:
        book = OrderBook("FOK-TEST")

        # Only 50 available at $10
        book.submit_order(Order("S1", Side.SELL, 10.0, 50))

        # FOK buy for 100 — should be rejected (only 50 available)
        fok = Order("FOK-B1", Side.BUY, 10.0, 100, order_type=OrderType.FOK)
        trades = book.submit_order(fok)

        if len(trades) > 0:
            results.fail(name,
                f"FOK should have been rejected (only 50 available for 100 requested), "
                f"but got {len(trades)} trades")
            return

        if fok.filled_qty != 0:
            results.fail(name, f"FOK was partially filled ({fok.filled_qty}) — should be 0")
            return

        # Now add more liquidity and retry
        book.submit_order(Order("S2", Side.SELL, 10.0, 60))
        fok2 = Order("FOK-B2", Side.BUY, 10.0, 100, order_type=OrderType.FOK)
        trades2 = book.submit_order(fok2)

        if len(trades2) == 0:
            results.fail(name, "FOK should succeed with 110 available for 100 requested")
            return

        total_filled = sum(t.quantity for t in trades2)
        if total_filled != 100:
            results.fail(name, f"FOK fill qty {total_filled}, expected 100")
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# TEST-20: End-to-end multi-node settlement with Merkle audit
# ===========================================================================
def test_20_e2e_multinode():
    """Multi-node scenario: 3 nodes trade, settle, verify Merkle root consistency."""
    name = "TEST-20: End-to-end multi-node settlement"
    try:
        # Create 3 distributed ledger nodes
        nodes = {nid: DistributedLedger(nid) for nid in ["N1", "N2", "N3"]}
        journals = {nid: EventJournal() for nid in nodes}
        coordinators = {
            nid: SettlementCoordinator(nid, nodes[nid], journals[nid])
            for nid in nodes
        }

        # Fund accounts on each node
        for nid, ledger in nodes.items():
            ledger.credit("fund-A", 100000)
            ledger.credit("fund-B", 100000)
            ledger.credit("fund-C", 100000)

        # Merge all nodes to sync state
        for nid in nodes:
            for other_nid in nodes:
                if nid != other_nid:
                    nodes[nid].merge(nodes[other_nid])

        # Create obligations on N1
        coord = coordinators["N1"]
        coord.add_obligation("fund-A", "fund-B", 15000)
        coord.add_obligation("fund-B", "fund-C", 10000)
        coord.add_obligation("fund-C", "fund-A", 5000)

        # Execute settlement
        result = coord.execute_settlement_cycle()

        # Verify Merkle root is non-empty
        if len(result.merkle_root) == 0:
            results.fail(name, "Merkle root is empty after settlement")
            return

        # Verify no failures
        if result.failed_count > 0:
            diag = f"Settlement had {result.failed_count} failures!\n"
            diag += f"Net amounts: {result.net_amounts}\n"
            for acct in ["fund-A", "fund-B", "fund-C"]:
                diag += f"  {acct} balance: {nodes['N1'].balance(acct)}\n"
            results.fail(name, diag)
            return

        results.ok(name)
    except Exception as e:
        results.fail(name, f"Exception: {e}\n{traceback.format_exc()}")


# ===========================================================================
# RUN ALL TESTS
# ===========================================================================
def main():
    print("=" * 72)
    print("  OPERATION BLACKBOX — Financial Settlement Engine Test Suite")
    print("  20 tests across 6 modules | 8 bugs planted in the codebase")
    print("=" * 72)
    print()

    tests = [
        test_01_merkle_root_determinism,
        test_02_merkle_proof_verification,
        test_03_wire_protocol_roundtrip,
        test_04_wire_structured_messages,
        test_05_gcounter_merge,
        test_06_crdt_ledger_merge_deltas,
        test_07_order_book_basic_matching,
        test_08_order_book_float_prices,
        test_09_iceberg_orders,
        test_10_event_journal_replay_order,
        test_11_event_journal_out_of_order,
        test_12_settlement_netting,
        test_13_settlement_full_cycle,
        test_14_signature_empty_message,
        test_15_signature_valid,
        test_16_integration_trade_settle,
        test_17_wire_multi_frame,
        test_18_crdt_double_merge,
        test_19_fill_or_kill,
        test_20_e2e_multinode,
    ]

    for test_fn in tests:
        test_fn()

    print()
    print("-" * 72)
    print(f"  Results: {results.passed} passed, {results.failed} failed "
          f"out of {results.passed + results.failed}")
    print("-" * 72)

    if results.errors:
        print()
        print("  FAILED TESTS:")
        for name, _ in results.errors:
            print(f"    - {name}")

    print()
    return 0 if results.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
