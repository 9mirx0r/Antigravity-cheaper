from __future__ import annotations
from typing import Any, Dict, List, Optional, Set

from .raft_node import RaftNode
from .rpc_network import NetworkPartitionError


class SplitBrainConsensusException(Exception):
    """Raised when term fencing detects a split-brain or superseded term."""
    pass


class TwoPhaseCommitCoordinator:
    """Two-Phase Commit (2PC) coordinator with Term-Fencing for Raft clusters."""

    def __init__(self, coord_id: str, nodes: Dict[str, RaftNode]):
        self.coord_id = coord_id
        self.nodes = nodes
        self.transactions: Dict[str, Dict[str, Any]] = {}
        self.locked_keys: Dict[str, str] = {}  # key -> tx_id

    def begin_transaction(self, tx_id: str) -> str:
        self.transactions[tx_id] = {
            "tx_id": tx_id,
            "state": "ACTIVE",
            "participants": [],
            "operations": [],
            "prepare_terms": {},
            "locked_keys": set(),
        }
        return tx_id

    def prepare(
        self,
        tx_id: str,
        participants: List[str],
        operations: List[Dict[str, Any]],
    ) -> bool:
        if tx_id not in self.transactions:
            raise ValueError(f"Unknown transaction {tx_id}")

        tx = self.transactions[tx_id]
        tx["participants"] = list(participants)
        tx["operations"] = list(operations)

        # Acquire lock leases on keys
        for op in operations:
            key = op.get("key")
            if key:
                if key in self.locked_keys and self.locked_keys[key] != tx_id:
                    self.abort(tx_id)
                    return False
                self.locked_keys[key] = tx_id
                tx["locked_keys"].add(key)

        # Record terms at prepare time
        for p in participants:
            if p not in self.nodes:
                self.abort(tx_id)
                return False
            node = self.nodes[p]
            tx["prepare_terms"][p] = node.term_tracker.current_term

        tx["state"] = "PREPARED"
        return True

    def commit(self, tx_id: str) -> bool:
        if tx_id not in self.transactions:
            raise ValueError(f"Unknown transaction {tx_id}")

        tx = self.transactions[tx_id]

        # Verify Term Fencing across all participants
        for p in tx["participants"]:
            node = self.nodes[p]
            prep_term = tx["prepare_terms"].get(p, 0)
            curr_term = node.term_tracker.current_term

            # Check if term has been superseded or split-brain detected
            if curr_term > prep_term:
                self.abort(tx_id)
                raise SplitBrainConsensusException(
                    f"Term fencing violation: participant {p} term advanced from {prep_term} to {curr_term}"
                )

            # Check network reachability if network is attached
            if hasattr(node, "network") and node.network:
                # Check if isolated from coordinator or majority
                for other_p in tx["participants"]:
                    if other_p != p and node.network._is_partitioned(p, other_p):
                        self.abort(tx_id)
                        raise SplitBrainConsensusException(
                            f"Network partition detected between participant {p} and {other_p}"
                        )

        # Apply operations to node logs
        for p in tx["participants"]:
            node = self.nodes[p]
            for op in tx["operations"]:
                if node.state == "LEADER":
                    node.append_entry({"tx_id": tx_id, "op": op})

        # Release locks and mark committed
        for key in tx["locked_keys"]:
            self.locked_keys.pop(key, None)
        tx["locked_keys"].clear()
        tx["state"] = "COMMITTED"
        return True

    def abort(self, tx_id: str) -> bool:
        if tx_id not in self.transactions:
            return False

        tx = self.transactions[tx_id]
        # Release all locked keys
        for key in list(tx.get("locked_keys", [])):
            if self.locked_keys.get(key) == tx_id:
                self.locked_keys.pop(key, None)
        tx["locked_keys"].clear()
        tx["state"] = "ABORTED"
        return True
