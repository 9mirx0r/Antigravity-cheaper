"""Two-Phase Commit (2PC) Transaction Coordinator with Term Fencing."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.raft_node import RaftNode
from src.rpc_network import NetworkPartitionError


class SplitBrainConsensusException(Exception):
    """Raised when term fencing detects a superseded term or network partition."""
    pass


class TransactionAbortedException(SplitBrainConsensusException):
    """Raised when a transaction is aborted due to consensus mismatch."""
    pass


class TwoPhaseCommitCoordinator:
    """Coordinates 2PC transactions across Raft nodes with term fencing."""

    def __init__(self, coordinator_id: str, nodes: Dict[str, RaftNode]) -> None:
        self.coordinator_id = coordinator_id
        self.nodes = nodes
        self.transactions: Dict[str, Dict[str, Any]] = {}

    def begin_transaction(self, tx_id: str) -> str:
        self.transactions[tx_id] = {
            "tx_id": tx_id,
            "status": "INITIATED",
            "participants": [],
            "operations": [],
            "terms": {},
            "locked_keys": {},  # participant_id -> list of keys
        }
        return tx_id

    def prepare(
        self,
        tx_id: str,
        participants: List[str],
        operations: List[Dict[str, Any]],
    ) -> bool:
        if tx_id not in self.transactions:
            self.begin_transaction(tx_id)

        tx = self.transactions[tx_id]
        tx["participants"] = list(participants)
        tx["operations"] = list(operations)

        for p in participants:
            if p not in self.nodes:
                self.abort(tx_id)
                return False

            node = self.nodes[p]
            tx["terms"][p] = node.term_tracker.current_term

            tx["locked_keys"].setdefault(p, [])
            for op in operations:
                key = op.get("key")
                if key:
                    if key in node.locks and node.locks[key] != tx_id:
                        self.abort(tx_id)
                        return False
                    node.locks[key] = tx_id
                    tx["locked_keys"][p].append(key)

        tx["status"] = "PREPARED"
        return True

    def commit(self, tx_id: str) -> bool:
        tx = self.transactions.get(tx_id)
        if not tx or tx["status"] != "PREPARED":
            raise TransactionAbortedException("Transaction is not in PREPARED state")

        participants: List[str] = tx["participants"]
        terms: Dict[str, int] = tx["terms"]

        # Term Fencing & Partition Verification:
        # Check if any participant's term changed or if network partition occurred
        for p in participants:
            node = self.nodes.get(p)
            if not node:
                self.abort(tx_id)
                raise TransactionAbortedException(f"Participant {p} missing from cluster")

            # Check network partition connectivity
            for other_p in participants:
                if other_p != p and node.network.is_partitioned(p, other_p):
                    self.abort(tx_id)
                    raise SplitBrainConsensusException(
                        f"Network partition detected between {p} and {other_p}"
                    )

            # Check term fencing: current term must not exceed prepare term
            if node.term_tracker.current_term > terms.get(p, 0):
                self.abort(tx_id)
                raise SplitBrainConsensusException(
                    f"Term fencing violation: {p} term {node.term_tracker.current_term} > {terms.get(p)}"
                )

        # Apply operations to all participants
        for p in participants:
            node = self.nodes[p]
            for op in tx["operations"]:
                key = op.get("key")
                if key:
                    if "val" in op:
                        node.storage[key] = op["val"]
                    elif "delta" in op:
                        node.storage[key] = node.storage.get(key, 0) + op["delta"]
                    elif "op" in op:
                        node.storage[key] = op["op"]

            # Release acquired locks
            for key in tx["locked_keys"].get(p, []):
                if node.locks.get(key) == tx_id:
                    del node.locks[key]

        tx["status"] = "COMMITTED"
        return True

    def abort(self, tx_id: str) -> bool:
        tx = self.transactions.get(tx_id)
        if not tx:
            return True

        # Release all locks held by this transaction on all participants
        for p, keys in tx.get("locked_keys", {}).items():
            node = self.nodes.get(p)
            if node:
                for key in keys:
                    if node.locks.get(key) == tx_id:
                        del node.locks[key]

        tx["status"] = "ABORTED"
        return True
