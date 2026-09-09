"""Simulated In-Memory RPC Network with Partition and Drop Support."""

from __future__ import annotations
import random
from typing import Any, Callable, Dict, List, Optional, Set


class NetworkPartitionError(Exception):
    """Raised when an RPC cannot be delivered due to network partition."""
    pass


class RPCNetwork:
    """In-memory RPC network supporting bidirectional partitions and simulated packet drops."""

    def __init__(self, drop_rate: float = 0.0) -> None:
        self.drop_rate: float = drop_rate
        self.handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.partitions: List[Set[str]] = []

    def register_node(
        self,
        node_id: str,
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        self.handlers[node_id] = handler

    def isolate_partition(self, partition_nodes: Set[str]) -> None:
        """Creates a bidirectional network partition isolating partition_nodes."""
        self.partitions.append(set(partition_nodes))

    def heal_partitions(self) -> None:
        """Restores full network connectivity."""
        self.partitions.clear()

    def is_partitioned(self, sender: str, recipient: str) -> bool:
        for p in self.partitions:
            if (sender in p) != (recipient in p):
                return True
        return False

    def send_rpc(
        self, sender: str, recipient: str, msg: Dict[str, Any]
    ) -> Dict[str, Any]:
        if self.is_partitioned(sender, recipient):
            raise NetworkPartitionError(
                f"Network partition prevents communication between {sender} and {recipient}"
            )

        if self.drop_rate > 0.0 and random.random() < self.drop_rate:
            raise NetworkPartitionError(
                f"Simulated packet drop between {sender} and {recipient}"
            )

        if recipient not in self.handlers:
            raise KeyError(f"Recipient node '{recipient}' is not registered")

        handler = self.handlers[recipient]
        return handler(dict(msg))
