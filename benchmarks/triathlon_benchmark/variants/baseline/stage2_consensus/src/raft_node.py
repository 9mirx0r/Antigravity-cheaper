"""Raft Consensus Node with Monotonic Term Tracking and Replication."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.rpc_network import RPCNetwork, NetworkPartitionError


class TermTracker:
    """Monotonic term counter with voted_for persistence."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.current_term: int = 0
        self.voted_for: Optional[str] = None

    def increment_term(self) -> int:
        self.current_term += 1
        self.voted_for = self.node_id
        return self.current_term

    def update_term(self, new_term: int) -> bool:
        if new_term > self.current_term:
            self.current_term = new_term
            self.voted_for = None
            return True
        return False


class RaftNode:
    """Raft consensus node."""

    def __init__(self, node_id: str, peers: List[str], network: RPCNetwork) -> None:
        self.node_id = node_id
        self.peers = list(peers)
        self.network = network
        self.state: str = "FOLLOWER"  # "FOLLOWER", "CANDIDATE", "LEADER"
        self.term_tracker = TermTracker(node_id)
        self.log: List[Dict[str, Any]] = []
        self.commit_index: int = 0
        self.locks: Dict[str, str] = {}  # key -> tx_id
        self.storage: Dict[str, Any] = {}

        self.network.register_node(node_id, self.handle_rpc)

    def start_election(self) -> bool:
        term = self.term_tracker.increment_term()
        self.state = "CANDIDATE"
        votes = 1  # Vote for self

        last_log_index = len(self.log)
        last_log_term = self.log[-1]["term"] if self.log else 0

        for peer in self.peers:
            try:
                msg = {
                    "type": "REQUEST_VOTE",
                    "term": term,
                    "candidate_id": self.node_id,
                    "last_log_index": last_log_index,
                    "last_log_term": last_log_term,
                }
                resp = self.network.send_rpc(self.node_id, peer, msg)
                resp_term = resp.get("term", 0)
                if resp_term > self.term_tracker.current_term:
                    self.term_tracker.update_term(resp_term)
                    self.state = "FOLLOWER"
                    return False
                if resp.get("vote_granted"):
                    votes += 1
            except Exception:
                pass

        total_nodes = len(self.peers) + 1
        majority = (total_nodes // 2) + 1
        if votes >= majority and self.state == "CANDIDATE":
            self.state = "LEADER"
            return True
        else:
            self.state = "FOLLOWER"
            return False

    def handle_rpc(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = msg.get("type")
        msg_term = msg.get("term", 0)

        if msg_term > self.term_tracker.current_term:
            self.term_tracker.update_term(msg_term)
            self.state = "FOLLOWER"

        if msg_type == "REQUEST_VOTE":
            if msg_term < self.term_tracker.current_term:
                return {"term": self.term_tracker.current_term, "vote_granted": False}

            can_vote = (
                self.term_tracker.voted_for is None
                or self.term_tracker.voted_for == msg.get("candidate_id")
            )
            if can_vote:
                self.term_tracker.voted_for = msg.get("candidate_id")
                return {"term": self.term_tracker.current_term, "vote_granted": True}
            return {"term": self.term_tracker.current_term, "vote_granted": False}

        elif msg_type == "APPEND_ENTRIES":
            if msg_term < self.term_tracker.current_term:
                return {"term": self.term_tracker.current_term, "success": False}

            if self.state == "CANDIDATE":
                self.state = "FOLLOWER"

            entries = msg.get("entries", [])
            for entry in entries:
                self.log.append(entry)

            return {"term": self.term_tracker.current_term, "success": True}

        return {"term": self.term_tracker.current_term, "error": "unknown_rpc"}

    def append_entry(self, command: Dict[str, Any]) -> int:
        if self.state != "LEADER":
            raise Exception(f"Node {self.node_id} is not the leader")

        entry = {
            "term": self.term_tracker.current_term,
            "index": len(self.log) + 1,
            "command": command,
        }
        self.log.append(entry)

        for peer in self.peers:
            try:
                msg = {
                    "type": "APPEND_ENTRIES",
                    "term": self.term_tracker.current_term,
                    "leader_id": self.node_id,
                    "entries": [entry],
                }
                self.network.send_rpc(self.node_id, peer, msg)
            except Exception:
                pass

        return entry["index"]
