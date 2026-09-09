"""CRDT-based eventually-consistent distributed counter for account balances.

Implements a state-based G-Counter (grow-only counter) and PN-Counter
(positive-negative counter) with vector-clock merge semantics.  Each node
maintains its own increment/decrement slots and merges take the element-wise
maximum.
"""

from __future__ import annotations

import copy
from typing import Dict, Optional, Set


class GCounter:
    """Grow-only counter: each node can only increment its own slot."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.counts: Dict[str, int] = {node_id: 0}

    def increment(self, amount: int = 1) -> None:
        if amount < 0:
            raise ValueError("GCounter only supports non-negative increments")
        self.counts[self.node_id] = self.counts.get(self.node_id, 0) + amount

    def value(self) -> int:
        return sum(self.counts.values())

    def merge(self, other: "GCounter") -> None:
        """Merge state from *other* by taking element-wise maximum."""
        for node, count in other.counts.items():
            self.counts[node] = max(self.counts.get(node, 0), count)


class PNCounter:
    """Positive-Negative counter using two G-Counters."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.pos = GCounter(node_id)
        self.neg = GCounter(node_id)

    def increment(self, amount: int = 1) -> None:
        self.pos.increment(amount)

    def decrement(self, amount: int = 1) -> None:
        self.neg.increment(amount)

    def value(self) -> int:
        return self.pos.value() - self.neg.value()

    def merge(self, other: "PNCounter") -> None:
        self.pos.merge(other.pos)
        self.neg.merge(other.neg)


class DistributedLedger:
    """Multi-account distributed ledger built on PN-Counters.

    Each account has an independent PN-Counter.  Nodes replicate state
    by periodically merging their full ledger snapshot.
    """

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.accounts: Dict[str, PNCounter] = {}
        self._pending_deltas: list[Dict] = []

    def _ensure_account(self, account_id: str) -> PNCounter:
        if account_id not in self.accounts:
            self.accounts[account_id] = PNCounter(self.node_id)
        return self.accounts[account_id]

    def credit(self, account_id: str, amount_cents: int) -> int:
        """Credit (increase) an account balance.  Returns new balance."""
        ctr = self._ensure_account(account_id)
        ctr.increment(amount_cents)
        self._pending_deltas.append(
            {"op": "credit", "account": account_id, "amount": amount_cents}
        )
        return ctr.value()

    def debit(self, account_id: str, amount_cents: int) -> int:
        """Debit (decrease) an account balance.  Returns new balance."""
        ctr = self._ensure_account(account_id)
        ctr.decrement(amount_cents)
        self._pending_deltas.append(
            {"op": "debit", "account": account_id, "amount": amount_cents}
        )
        return ctr.value()

    def balance(self, account_id: str) -> int:
        ctr = self.accounts.get(account_id)
        return ctr.value() if ctr else 0

    def merge(self, other: "DistributedLedger") -> None:
        """Merge full ledger state from a peer node.

        BUG #3: After merging, pending deltas from 'other' are appended to
        self._pending_deltas.  This means if merge() is called twice with
        the same peer state, the deltas accumulate and downstream event
        replay double-counts operations.  A correct implementation would
        NOT copy pending deltas during merge (they are transient local state).
        """
        for acct_id, other_counter in other.accounts.items():
            if acct_id in self.accounts:
                self.accounts[acct_id].merge(other_counter)
            else:
                self.accounts[acct_id] = copy.deepcopy(other_counter)

        # BUG: should NOT append other's deltas
        self._pending_deltas.extend(other._pending_deltas)

    def drain_deltas(self) -> list[Dict]:
        """Return and clear pending deltas for event journal."""
        deltas = list(self._pending_deltas)
        self._pending_deltas.clear()
        return deltas

    def snapshot(self) -> Dict[str, int]:
        return {acct: ctr.value() for acct, ctr in self.accounts.items()}
