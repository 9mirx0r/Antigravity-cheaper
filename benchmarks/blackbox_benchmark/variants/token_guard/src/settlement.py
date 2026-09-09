"""Settlement coordinator — orchestrates cross-module financial settlement.

Handles bilateral netting, DVP (delivery-versus-payment) settlement,
and final balance reconciliation across the distributed ledger.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .crdt_ledger import DistributedLedger
from .event_journal import EventJournal
from .merkle_tree import MerkleTree


@dataclass
class Obligation:
    """A directional financial obligation from debtor to creditor."""
    obligation_id: str
    debtor: str
    creditor: str
    amount_cents: int
    symbol: str
    settled: bool = False
    settlement_time: Optional[float] = None


@dataclass
class SettlementResult:
    """Result of a settlement cycle."""
    cycle_id: str
    obligations_count: int
    net_amounts: Dict[str, int]
    settled_count: int
    failed_count: int
    merkle_root: str
    timestamp: float


class SettlementCoordinator:
    """Coordinates bilateral netting and DVP settlement."""

    def __init__(self, node_id: str, ledger: DistributedLedger,
                 journal: EventJournal) -> None:
        self.node_id = node_id
        self.ledger = ledger
        self.journal = journal
        self.obligations: List[Obligation] = []
        self._cycle_counter = 0
        self._obligation_counter = 0

    def add_obligation(self, debtor: str, creditor: str,
                       amount_cents: int, symbol: str = "USD") -> Obligation:
        """Record a new settlement obligation."""
        self._obligation_counter += 1
        ob = Obligation(
            obligation_id=f"OBL-{self._obligation_counter:06d}",
            debtor=debtor,
            creditor=creditor,
            amount_cents=amount_cents,
            symbol=symbol,
        )
        self.obligations.append(ob)
        self.journal.append(
            "OBLIGATION_CREATED",
            {"debtor": debtor, "creditor": creditor, "amount": amount_cents,
             "symbol": symbol, "id": ob.obligation_id},
            source_node=self.node_id,
        )
        return ob

    def compute_net_obligations(self) -> Dict[str, int]:
        """Compute net obligation for each participant via bilateral netting.

        BUG #7: The netting algorithm double-counts bilateral obligations.
        When A owes B 100 and B owes A 60, the net should be:
          A: -40, B: +40
        But this implementation adds BOTH the "owed" and "owing" amounts
        separately instead of computing the bilateral net.
        """
        pending = [ob for ob in self.obligations if not ob.settled]

        # Track what each participant owes and is owed
        owes: Dict[str, int] = {}   # total amount this participant must pay
        owed: Dict[str, int] = {}   # total amount this participant receives

        for ob in pending:
            owes[ob.debtor] = owes.get(ob.debtor, 0) + ob.amount_cents
            owed[ob.creditor] = owed.get(ob.creditor, 0) + ob.amount_cents

        # BUG #7: Net calculation is wrong.
        # For each pair (A,B), if A owes B $100 and B owes A $60, the
        # bilateral net for A toward B should be $40 (A pays B $40).
        # Instead this just sums all "owes" and all "owed" independently,
        # which is correct for MULTILATERAL netting but NOT bilateral netting.
        # The real bug: we also count the same obligation in BOTH directions.
        #
        # Consider:  A owes B $100.
        #   owes[A] += 100, owed[B] += 100   ← correct individually
        #   net[A] = owed[A] - owes[A] = 0 - 100 = -100  ← correct
        #   net[B] = owed[B] - owes[B] = 100 - 0 = +100  ← correct
        #
        # But when B ALSO owes A $60:
        #   owes[B] += 60, owed[A] += 60
        #   net[A] = 60 - 100 = -40   ← CORRECT only for multilateral
        #   net[B] = 100 - 60 = +40   ← CORRECT only for multilateral
        #
        # The ACTUAL bug is below: we add obligations to BOTH owes and owed
        # for each obligation.  That is, for "A owes B $100", we incorrectly
        # add $100 to owes[A] AND owes[B] (treating it as symmetric).
        net: Dict[str, int] = {}
        all_participants: Set[str] = set(owes.keys()) | set(owed.keys())

        for p in all_participants:
            total_owed_to_p = owed.get(p, 0)
            total_p_owes = owes.get(p, 0)
            net[p] = total_owed_to_p - total_p_owes

        return net

    def execute_settlement_cycle(self) -> SettlementResult:
        """Execute one settlement cycle: net, validate, settle."""
        self._cycle_counter += 1
        cycle_id = f"CYCLE-{self._cycle_counter:04d}"

        net_amounts = self.compute_net_obligations()
        pending = [ob for ob in self.obligations if not ob.settled]

        # Build Merkle tree of all obligations in this cycle
        tree = MerkleTree()
        for ob in pending:
            data = f"{ob.obligation_id}:{ob.debtor}:{ob.creditor}:{ob.amount_cents}".encode()
            tree.add_leaf(data)
        merkle_root = tree.build()

        # Apply net settlements to ledger
        settled = 0
        failed = 0
        for participant, net_amount in net_amounts.items():
            if net_amount < 0:
                # Participant is a net debtor
                self.ledger.debit(participant, abs(net_amount))
                settled += 1
            elif net_amount > 0:
                # Participant is a net creditor
                self.ledger.credit(participant, net_amount)
                settled += 1

        # Mark obligations as settled
        now = time.time()
        for ob in pending:
            ob.settled = True
            ob.settlement_time = now

        self.journal.append(
            "SETTLEMENT_CYCLE_COMPLETE",
            {"cycle": cycle_id, "settled": settled, "failed": failed,
             "merkle_root": merkle_root.hex()},
            source_node=self.node_id,
        )

        return SettlementResult(
            cycle_id=cycle_id,
            obligations_count=len(pending),
            net_amounts=net_amounts,
            settled_count=settled,
            failed_count=failed,
            merkle_root=merkle_root.hex(),
            timestamp=now,
        )

    def reconcile(self, expected_totals: Dict[str, int]) -> List[str]:
        """Verify ledger balances match expected totals.

        Returns list of discrepancy descriptions (empty = all good).
        """
        discrepancies: List[str] = []
        for account, expected in expected_totals.items():
            actual = self.ledger.balance(account)
            if actual != expected:
                discrepancies.append(
                    f"Account {account}: expected {expected}, got {actual} "
                    f"(diff={actual - expected})"
                )
        return discrepancies
