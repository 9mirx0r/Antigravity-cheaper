from __future__ import annotations
import random
from typing import Any, Callable, Dict, List, Optional, Set


class NetworkPartitionError(Exception):
    """Raised when an RPC cannot be delivered due to network partition."""
    pass


class RPCNetwork:
    """Simulates an RPC network with partitions, message drops, and handlers."""

    def __init__(self, drop_rate: float = 0.0):
        self.drop_rate: float = drop_rate
        self.handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.partitions: List[Set[str]] = []

    def register_node(self, node_id: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self.handlers[node_id] = handler

    def isolate_partition(self, partition_nodes: Set[str]) -> None:
        """Isolates partition_nodes from the rest of the network."""
        self.partitions.append(set(partition_nodes))

    def heal_partitions(self) -> None:
        """Restores full network connectivity."""
        self.partitions.clear()

    def _is_partitioned(self, sender: str, recipient: str) -> bool:
        for part in self.partitions:
            sender_in = sender in part
            recipient_in = recipient in part
            if sender_in != recipient_in:
                return True
        return False

    def send_rpc(self, sender: str, recipient: str, msg: Dict[str, Any]) -> Dict[str, Any]:
        """Sends an RPC message from sender to recipient."""
        if self._is_partitioned(sender, recipient):
            raise NetworkPartitionError(f"Network partition between {sender} and {recipient}")

        if self.drop_rate > 0.0 and random.random() < self.drop_rate:
            raise NetworkPartitionError(f"Packet dropped between {sender} and {recipient}")

        if recipient not in self.handlers:
            raise ValueError(f"Recipient node not registered: {recipient}")

        handler = self.handlers[recipient]
        # Deliver message to handler
        return handler(dict(msg))
