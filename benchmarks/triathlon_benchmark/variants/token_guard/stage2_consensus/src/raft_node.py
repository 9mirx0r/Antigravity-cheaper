from __future__ import annotations
from typing import Any, Dict, List, Optional

from .rpc_network import RPCNetwork, NetworkPartitionError


class TermTracker:
    """Monotonic term counter and vote persistence for Raft nodes."""

    def __init__(self, node_id: str):
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
    """Raft consensus node supporting elections, term tracking, and log replication."""

    def __init__(self, node_id: str, peers: List[str], network: RPCNetwork):
        self.node_id = node_id
        self.peers = list(peers)
        self.network = network
        self.term_tracker = TermTracker(node_id)
        self.state: str = "FOLLOWER"  # FOLLOWER, CANDIDATE, LEADER
        self.log: List[Dict[str, Any]] = []
        self.commit_index: int = 0
        self.network.register_node(node_id, self.handle_rpc)

    def start_election(self) -> bool:
        """Starts an election, increments term, requests votes from peers."""
        self.state = "CANDIDATE"
        term = self.term_tracker.increment_term()
        votes = 1  # Self vote
        total_nodes = len(self.peers) + 1
        majority = (total_nodes // 2) + 1

        last_log_idx = len(self.log)
        last_log_term = self.log[-1]["term"] if self.log else 0

        for peer in self.peers:
            try:
                resp = self.network.send_rpc(
                    self.node_id,
                    peer,
                    {
                        "type": "REQUEST_VOTE",
                        "term": term,
                        "candidate_id": self.node_id,
                        "last_log_index": last_log_idx,
                        "last_log_term": last_log_term,
                    },
                )
                if resp.get("vote_granted"):
                    votes += 1
                if resp.get("term", 0) > self.term_tracker.current_term:
                    self.term_tracker.update_term(resp["term"])
                    self.state = "FOLLOWER"
                    return False
            except (NetworkPartitionError, Exception):
                pass

        if votes >= majority:
            self.state = "LEADER"
            return True
        else:
            self.state = "FOLLOWER"
            return False

    def handle_rpc(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """Handles incoming RPC messages."""
        msg_type = msg.get("type")
        msg_term = msg.get("term", 0)

        if msg_term > self.term_tracker.current_term:
            self.term_tracker.update_term(msg_term)
            self.state = "FOLLOWER"

        if msg_type == "REQUEST_VOTE":
            if msg_term < self.term_tracker.current_term:
                return {"term": self.term_tracker.current_term, "vote_granted": False}

            can_vote = self.term_tracker.voted_for in (None, msg.get("candidate_id"))
            if can_vote:
                last_log_idx = len(self.log)
                last_log_term = self.log[-1]["term"] if self.log else 0
                cand_idx = msg.get("last_log_index", 0)
                cand_term = msg.get("last_log_term", 0)

                uptodate = (cand_term > last_log_term) or (
                    cand_term == last_log_term and cand_idx >= last_log_idx
                )
                if uptodate:
                    self.term_tracker.voted_for = msg.get("candidate_id")
                    return {"term": self.term_tracker.current_term, "vote_granted": True}

            return {"term": self.term_tracker.current_term, "vote_granted": False}

        elif msg_type == "APPEND_ENTRIES":
            if msg_term < self.term_tracker.current_term:
                return {"term": self.term_tracker.current_term, "success": False}

            self.state = "FOLLOWER"
            entries = msg.get("entries", [])
            for entry in entries:
                idx = entry["index"]
                if idx <= len(self.log):
                    self.log[idx - 1] = entry
                else:
                    self.log.append(entry)

            return {"term": self.term_tracker.current_term, "success": True}

        return {"term": self.term_tracker.current_term, "error": "unknown_type"}

    def append_entry(self, command: Dict[str, Any]) -> int:
        """Appends entry to leader log and replicates to peers."""
        if self.state != "LEADER":
            raise ValueError(f"Node {self.node_id} is not LEADER")

        idx = len(self.log) + 1
        entry = {
            "term": self.term_tracker.current_term,
            "index": idx,
            "command": command,
        }
        self.log.append(entry)

        for peer in self.peers:
            try:
                self.network.send_rpc(
                    self.node_id,
                    peer,
                    {
                        "type": "APPEND_ENTRIES",
                        "term": self.term_tracker.current_term,
                        "leader_id": self.node_id,
                        "entries": [entry],
                        "commit_index": self.commit_index,
                    },
                )
            except Exception:
                pass

        return idx
