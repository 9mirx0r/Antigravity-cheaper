#!/usr/bin/env python3
"""Setup script for 1M-Token Extreme Stress Benchmark.

Scaffolds a 16-module distributed Raft storage and 2PC consensus engine
with a 35,000-line realistic cluster log (~450k raw tokens) and test suites.
Deploys identical copies to variants/baseline and variants/token_guard.
"""

import os
import random
import shutil
import time
from pathlib import Path

ROOT = Path("benchmark_extreme").resolve()


def generate_source_code() -> dict[str, str]:
    """Return dictionary of 16 source files."""
    code: dict[str, str] = {}

    code["consensus/term_tracker.py"] = '''"""Term and epoch state tracker for Raft consensus."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

class TermTracker:
    def __init__(self, node_id: str, state_path: Optional[Path] = None):
        self.node_id = node_id
        self.state_path = state_path
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.commit_index = 0
        self.last_applied = 0

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

    def vote(self, candidate_id: str, term: int) -> bool:
        if term > self.current_term:
            self.update_term(term)
        if term == self.current_term and (self.voted_for is None or self.voted_for == candidate_id):
            self.voted_for = candidate_id
            return True
        return False
'''

    code["consensus/rpc_transport.py"] = '''"""Simulated RPC network transport with partition injection."""
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Set

class NetworkPartitionError(Exception):
    pass

class RPCTransport:
    def __init__(self):
        self.handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.partitions: Set[frozenset[str]] = set()
        self.drop_rate: float = 0.0

    def register_endpoint(self, endpoint: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self.handlers[endpoint] = handler

    def isolate_nodes(self, isolated_nodes: Set[str]):
        """Create a network partition separating isolated_nodes from the rest."""
        self.partitions.add(frozenset(isolated_nodes))

    def heal_partitions(self):
        """Heal all network partitions."""
        self.partitions.clear()

    def send_rpc(self, sender: str, recipient: str, message: Dict[str, Any]) -> Dict[str, Any]:
        for part in self.partitions:
            if (sender in part) != (recipient in part):
                raise NetworkPartitionError(f"Partition active between {sender} and {recipient}")
        if recipient not in self.handlers:
            raise ConnectionRefusedError(f"Endpoint {recipient} not registered")
        return self.handlers[recipient](message)
'''

    code["consensus/raft_node.py"] = '''"""Raft consensus node with leader election and log replication."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from .term_tracker import TermTracker
from .rpc_transport import RPCTransport, NetworkPartitionError

class SplitBrainConsensusException(Exception):
    pass

class RaftNode:
    def __init__(self, node_id: str, peers: List[str], transport: RPCTransport):
        self.node_id = node_id
        self.peers = peers
        self.transport = transport
        self.term_tracker = TermTracker(node_id)
        self.state = "FOLLOWER"  # FOLLOWER, CANDIDATE, LEADER
        self.log: List[Dict[str, Any]] = []
        self.transport.register_endpoint(node_id, self.handle_rpc)

    def start_election(self) -> bool:
        self.state = "CANDIDATE"
        term = self.term_tracker.increment_term()
        votes = 1
        for peer in self.peers:
            try:
                resp = self.transport.send_rpc(self.node_id, peer, {
                    "type": "REQUEST_VOTE",
                    "term": term,
                    "candidate_id": self.node_id
                })
                if resp.get("vote_granted"):
                    votes += 1
            except (NetworkPartitionError, ConnectionRefusedError):
                pass
        quorum = (len(self.peers) + 1) // 2 + 1
        if votes >= quorum:
            self.state = "LEADER"
            return True
        self.state = "FOLLOWER"
        return False

    def handle_rpc(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = msg.get("type")
        msg_term = msg.get("term", 0)
        if msg_term > self.term_tracker.current_term:
            self.term_tracker.update_term(msg_term)
            self.state = "FOLLOWER"

        if msg_type == "REQUEST_VOTE":
            granted = self.term_tracker.vote(msg["candidate_id"], msg_term)
            return {"vote_granted": granted, "term": self.term_tracker.current_term}

        elif msg_type == "APPEND_ENTRIES":
            if msg_term < self.term_tracker.current_term:
                return {"success": False, "term": self.term_tracker.current_term}
            return {"success": True, "term": self.term_tracker.current_term}

        return {"error": "Unknown RPC"}

    def append_command(self, command: Dict[str, Any]) -> bool:
        if self.state != "LEADER":
            raise SplitBrainConsensusException(
                f"Node {self.node_id} is not leader in term {self.term_tracker.current_term}"
            )
        entry = {"term": self.term_tracker.current_term, "index": len(self.log) + 1, "command": command}
        self.log.append(entry)
        return True
'''

    code["storage/wal_manager.py"] = '''"""Write-Ahead Log (WAL) with segment rotation and CRC validation."""
from __future__ import annotations
import zlib
from typing import Any, Dict, List, Optional

class WALManager:
    def __init__(self, segment_size_limit: int = 1000):
        self.segment_size_limit = segment_size_limit
        self.segments: List[List[Dict[str, Any]]] = [[]]
        self.total_entries = 0

    def append(self, record: Dict[str, Any]) -> int:
        raw_bytes = str(sorted(record.items())).encode("utf-8")
        crc = zlib.crc32(raw_bytes)
        entry = {"seq": self.total_entries + 1, "data": record, "crc": crc}
        
        current_segment = self.segments[-1]
        if len(current_segment) >= self.segment_size_limit:
            self.segments.append([])
            current_segment = self.segments[-1]

        current_segment.append(entry)
        self.total_entries += 1
        return entry["seq"]

    def read_all(self) -> List[Dict[str, Any]]:
        entries = []
        for segment in self.segments:
            for entry in segment:
                raw = str(sorted(entry["data"].items())).encode("utf-8")
                if zlib.crc32(raw) != entry["crc"]:
                    raise ValueError(f"Corrupt entry at seq {entry['seq']}")
                entries.append(entry["data"])
        return entries
'''

    code["storage/block_cache.py"] = '''"""LRU Block Cache with lease eviction management."""
from __future__ import annotations
from collections import OrderedDict
from typing import Any, Optional

class BlockCache:
    def __init__(self, capacity: int = 500):
        self.capacity = capacity
        self.cache: OrderedDict[str, Any] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            self.hits += 1
            self.cache.move_to_end(key)
            return self.cache[key]
        self.misses += 1
        return None

    def put(self, key: str, value: Any):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
'''

    code["storage/lsm_tree.py"] = '''"""LSM Tree with MemTable and multi-level SSTables."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from .wal_manager import WALManager
from .block_cache import BlockCache

class LSMTree:
    def __init__(self, memtable_threshold: int = 50):
        self.memtable_threshold = memtable_threshold
        self.memtable: Dict[str, Any] = {}
        self.sstables: List[Dict[str, Any]] = []
        self.wal = WALManager()
        self.cache = BlockCache()

    def put(self, key: str, value: Any):
        self.wal.append({"key": key, "val": value})
        self.memtable[key] = value
        self.cache.put(key, value)
        if len(self.memtable) >= self.memtable_threshold:
            self.flush_memtable()

    def get(self, key: str) -> Optional[Any]:
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        if key in self.memtable:
            return self.memtable[key]
        for sstable in reversed(self.sstables):
            if key in sstable:
                val = sstable[key]
                self.cache.put(key, val)
                return val
        return None

    def flush_memtable(self):
        if self.memtable:
            self.sstables.append(dict(self.memtable))
            self.memtable.clear()
'''

    code["storage/snapshot_engine.py"] = '''"""Point-in-time state checkpointing and log compaction."""
from __future__ import annotations
from typing import Any, Dict, Optional
from .lsm_tree import LSMTree

class SnapshotEngine:
    def __init__(self, lsm: LSMTree):
        self.lsm = lsm
        self.snapshots: Dict[int, Dict[str, Any]] = {}
        self.latest_version = 0

    def create_snapshot(self) -> int:
        self.latest_version += 1
        state = {}
        for sstable in self.lsm.sstables:
            state.update(sstable)
        state.update(self.lsm.memtable)
        self.snapshots[self.latest_version] = state
        return self.latest_version

    def read_snapshot(self, version: int, key: str) -> Optional[Any]:
        if version not in self.snapshots:
            raise KeyError(f"Snapshot version {version} expired or not found")
        return self.snapshots[version].get(key)
'''

    code["transaction/lock_manager.py"] = '''"""Distributed multi-granularity lock manager with lease expiration."""
from __future__ import annotations
import time
from typing import Dict, Optional, Set

class LockLeaseDeadlockError(Exception):
    pass

class LockManager:
    def __init__(self):
        # lock_key -> {holder_tx, lease_id, term, expires_at}
        self.locks: Dict[str, Dict[str, Any]] = {}
        self.tx_locks: Dict[str, Set[str]] = {}

    def acquire_lock(self, tx_id: str, key: str, term: int, lease_id: str, ttl_seconds: float = 30.0) -> bool:
        now = time.time()
        if key in self.locks:
            curr = self.locks[key]
            # Check lease expiration
            if now > curr["expires_at"]:
                self.release_lock(curr["holder_tx"], key)
            elif curr["holder_tx"] != tx_id:
                raise LockLeaseDeadlockError(
                    f"Lock on {key} held by {curr['holder_tx']} with lease {curr['lease_id']} in term {curr['term']}"
                )

        self.locks[key] = {
            "holder_tx": tx_id,
            "lease_id": lease_id,
            "term": term,
            "expires_at": now + ttl_seconds,
        }
        if tx_id not in self.tx_locks:
            self.tx_locks[tx_id] = set()
        self.tx_locks[tx_id].add(key)
        return True

    def release_lock(self, tx_id: str, key: str) -> bool:
        if key in self.locks and self.locks[key]["holder_tx"] == tx_id:
            del self.locks[key]
            if tx_id in self.tx_locks:
                self.tx_locks[tx_id].discard(key)
            return True
        return False

    def release_all_for_tx(self, tx_id: str):
        keys = list(self.tx_locks.get(tx_id, set()))
        for k in keys:
            self.release_lock(tx_id, k)

    def abort_orphaned_leases_for_term(self, active_term: int):
        """Clean up locks granted under superseded terms."""
        orphaned = []
        for key, info in self.locks.items():
            if info["term"] < active_term:
                orphaned.append((info["holder_tx"], key))
        for tx_id, key in orphaned:
            self.release_lock(tx_id, key)
'''

    code["transaction/deadlock_detector.py"] = '''"""Wait-for graph cycle detector for distributed transactions."""
from __future__ import annotations
from typing import Dict, List, Optional, Set

class DeadlockDetector:
    def __init__(self):
        # waiter_tx -> set(blocker_tx)
        self.wait_for: Dict[str, Set[str]] = {}

    def add_dependency(self, waiter: str, blocker: str):
        if waiter not in self.wait_for:
            self.wait_for[waiter] = set()
        self.wait_for[waiter].add(blocker)

    def remove_tx(self, tx_id: str):
        self.wait_for.pop(tx_id, None)
        for blockers in self.wait_for.values():
            blockers.discard(tx_id)

    def detect_cycle(self) -> Optional[List[str]]:
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycle_path: List[str] = []

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            cycle_path.append(node)
            for neighbor in self.wait_for.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    cycle_path.append(neighbor)
                    return True
            rec_stack.remove(node)
            cycle_path.pop()
            return False

        for tx in list(self.wait_for.keys()):
            if tx not in visited:
                if dfs(tx):
                    return cycle_path
        return None
'''

    code["transaction/isolation_guard.py"] = '''"""Snapshot Isolation and write skew validator."""
from __future__ import annotations
from typing import Any, Dict, Set

class WriteSkewException(Exception):
    pass

class IsolationGuard:
    def __init__(self):
        # tx_id -> set(read_keys)
        self.read_sets: Dict[str, Set[str]] = {}
        # tx_id -> set(written_keys)
        self.write_sets: Dict[str, Set[str]] = {}

    def record_read(self, tx_id: str, key: str):
        self.read_sets.setdefault(tx_id, set()).add(key)

    def record_write(self, tx_id: str, key: str):
        self.write_sets.setdefault(tx_id, set()).add(key)

    def validate_commit(self, tx_id: str, active_txs: Set[str]):
        my_writes = self.write_sets.get(tx_id, set())
        for other_tx in active_txs:
            if other_tx == tx_id:
                continue
            other_reads = self.read_sets.get(other_tx, set())
            overlap = my_writes.intersection(other_reads)
            if len(overlap) > 1:
                raise WriteSkewException(f"Write skew detected between {tx_id} and {other_tx} on {overlap}")
'''

    # THIS IS THE TARGET FILE CONTAINING THE SPLIT-BRAIN CONCURRENCY BUG
    code["transaction/two_phase_commit.py"] = '''"""Two-Phase Commit Coordinator with term-fenced consensus integration."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..consensus.raft_node import RaftNode, SplitBrainConsensusException
from .lock_manager import LockManager, LockLeaseDeadlockError

class TransactionAbortedException(Exception):
    pass

class TwoPhaseCommitCoordinator:
    def __init__(self, coordinator_id: str, raft_nodes: Dict[str, RaftNode], lock_manager: LockManager):
        self.coordinator_id = coordinator_id
        self.raft_nodes = raft_nodes
        self.lock_manager = lock_manager
        self.active_transactions: Dict[str, Dict[str, Any]] = {}

    def begin_transaction(self, tx_id: str) -> str:
        self.active_transactions[tx_id] = {
            "state": "INIT",
            "participants": [],
            "operations": [],
            "lease_ids": [],
            "term": 0,
        }
        return tx_id

    def prepare(self, tx_id: str, operations: List[Dict[str, Any]]) -> bool:
        tx = self.active_transactions.get(tx_id)
        if not tx:
            raise ValueError(f"Transaction {tx_id} not found")

        tx["operations"] = operations
        tx["state"] = "PREPARING"

        # Acquire locks on each partition
        for op in operations:
            node_id = op["node_id"]
            key = op["key"]
            raft = self.raft_nodes[node_id]
            current_term = raft.term_tracker.current_term
            lease_id = f"lease_{node_id}_{tx_id}"

            # Acquire lock
            self.lock_manager.acquire_lock(
                tx_id=tx_id,
                key=key,
                term=current_term,
                lease_id=lease_id,
                ttl_seconds=15.0
            )
            tx["lease_ids"].append(lease_id)
            tx["term"] = current_term
            tx["participants"].append(node_id)

        tx["state"] = "PREPARED"
        return True

    def commit(self, tx_id: str) -> bool:
        tx = self.active_transactions.get(tx_id)
        if not tx or tx["state"] != "PREPARED":
            raise ValueError(f"Transaction {tx_id} is not in PREPARED state")

        # Replicate commit to participants via Raft
        # BUG: Does not verify term fencing when communicating with leader nodes!
        # When a network partition heals and a higher term has taken over, raft.append_command()
        # throws SplitBrainConsensusException. The coordinator catches the exception but leaves
        # the acquired lock leases stuck in lock_manager without aborting/fencing them!
        try:
            for node_id in tx["participants"]:
                raft = self.raft_nodes[node_id]
                raft.append_command({"action": "COMMIT", "tx_id": tx_id, "operations": tx["operations"]})
        except SplitBrainConsensusException as e:
            # BUGGY BEHAVIOR: Leaves locks orphaned, raising SplitBrainConsensusException
            # without aborting the locks under the superseded term!
            raise e

        # Release locks on success
        self.lock_manager.release_all_for_tx(tx_id)
        tx["state"] = "COMMITTED"
        return True

    def abort(self, tx_id: str) -> bool:
        tx = self.active_transactions.get(tx_id)
        if tx:
            self.lock_manager.release_all_for_tx(tx_id)
            tx["state"] = "ABORTED"
            return True
        return False
'''

    code["service/kv_gateway.py"] = '''"""Sharded Key-Value Gateway with routing and consensus dispatch."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..consensus.raft_node import RaftNode
from ..transaction.two_phase_commit import TwoPhaseCommitCoordinator

class KVGateway:
    def __init__(self, coordinator: TwoPhaseCommitCoordinator, shard_map: Dict[str, str]):
        self.coordinator = coordinator
        self.shard_map = shard_map  # key_prefix -> node_id

    def execute_write_batch(self, tx_id: str, writes: Dict[str, Any]) -> bool:
        self.coordinator.begin_transaction(tx_id)
        ops = []
        for key, val in writes.items():
            prefix = key.split(":")[0]
            node_id = self.shard_map.get(prefix, "node-1")
            ops.append({"node_id": node_id, "key": key, "val": val})

        if not self.coordinator.prepare(tx_id, ops):
            self.coordinator.abort(tx_id)
            return False

        return self.coordinator.commit(tx_id)
'''

    code["service/membership_registry.py"] = '''"""Cluster membership registry and heartbeat gossip tracker."""
from __future__ import annotations
import time
from typing import Dict, List, Set

class MembershipRegistry:
    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}

    def register_node(self, node_id: str, address: str):
        self.nodes[node_id] = {"address": address, "last_heartbeat": time.time(), "status": "ALIVE"}

    def record_heartbeat(self, node_id: str):
        if node_id in self.nodes:
            self.nodes[node_id]["last_heartbeat"] = time.time()
            self.nodes[node_id]["status"] = "ALIVE"

    def mark_dead(self, node_id: str):
        if node_id in self.nodes:
            self.nodes[node_id]["status"] = "DEAD"

    def get_alive_nodes(self) -> List[str]:
        return [nid for nid, info in self.nodes.items() if info["status"] == "ALIVE"]
'''

    code["service/metrics_collector.py"] = '''"""Metrics collector for cluster latency, throughput, and error rates."""
from __future__ import annotations
from typing import Dict, List

class MetricsCollector:
    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.histograms: Dict[str, List[float]] = {}

    def inc(self, metric: str, amount: int = 1):
        self.counters[metric] = self.counters.get(metric, 0) + amount

    def observe(self, metric: str, value: float):
        self.histograms.setdefault(metric, []).append(value)

    def summary(self) -> Dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "averages": {m: sum(v)/len(v) for m, v in self.histograms.items() if v}
        }
'''

    return code


def generate_cluster_log(log_path: Path, total_lines: int = 35000):
    """Generate a realistic 35,000-line cluster log with subtle partition bug."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        ts = 1725700000.0
        # Generate lines
        for i in range(1, total_lines + 1):
            ts += random.uniform(0.01, 0.08)
            time_str = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)) + f".{int((ts % 1)*1000):03d}Z"
            node = f"node-{(i % 3) + 1}"

            # Normal background operations
            if i < 28400 or i > 28490:
                kind = i % 10
                if kind == 0:
                    f.write(f"[{time_str}] [INFO] [{node}] [RaftHeartbeat] Leader heartbeat ACK from peers term=41 elapsed_ms=1.2\n")
                elif kind == 1:
                    f.write(f"[{time_str}] [DEBUG] [{node}] [LSMCompaction] MemTable flushed to SSTable L0 size_kb=64 entries=50\n")
                elif kind == 2:
                    f.write(f"[{time_str}] [INFO] [{node}] [WAL] Segment rotation: committed wal_seg_{i//500}.log entries=500\n")
                elif kind == 3:
                    f.write(f"[{time_str}] [DEBUG] [{node}] [BlockCache] Cache query hits=4812 misses=104 hit_ratio=0.978\n")
                elif kind == 4:
                    f.write(f"[{time_str}] [INFO] [{node}] [Gossip] Node membership alive: ['node-1', 'node-2', 'node-3']\n")
                elif kind == 5:
                    f.write(f"[{time_str}] [DEBUG] [{node}] [Snapshot] Checkpoint barrier verified snapshot_id={i//1000}\n")
                elif kind == 6:
                    f.write(f"[{time_str}] [INFO] [{node}] [KVGateway] Client PUT routed shard=shard_{i%4} latency_us=230\n")
                elif kind == 7:
                    f.write(f"[{time_str}] [WARN] [{node}] [BlockCache] Memory pressure warning: resident_set_kb=49120 threshold_kb=65536\n")
                elif kind == 8:
                    f.write(f"[{time_str}] [DEBUG] [{node}] [Deadlock] Wait-for-graph cycle check clean: active_txs=3\n")
                else:
                    f.write(f"[{time_str}] [INFO] [{node}] [RPC] Replicated batch size=16 bytes=2048 to peer node-{((i+1)%3)+1}\n")

            # The critical failure cascade (L28400 - L28480)
            else:
                if i == 28400:
                    f.write(f"[{time_str}] [WARN] [network] INJECTING SIMULATED ASYMMETRIC PARTITION: node-1 isolated from quorum [node-2, node-3]\n")
                elif i == 28410:
                    f.write(f"[{time_str}] [WARN] [node-2] [RaftElection] Heartbeat timeout on leader node-1 (term=41). Converting to CANDIDATE.\n")
                elif i == 28420:
                    f.write(f"[{time_str}] [INFO] [node-2] [RaftElection] Elected as NEW LEADER for term=42 with votes from [node-2, node-3]\n")
                elif i == 28430:
                    f.write(f"[{time_str}] [INFO] [2PC-Coord] Starting cross-partition transaction tx_split_brain_902 on keys ['user:balance', 'order:status']\n")
                elif i == 28440:
                    f.write(f"[{time_str}] [INFO] [LockManager] Acquired lock 'user:balance' for tx_split_brain_902 lease_id=lease_node-1_tx_split_brain_902 term=41\n")
                elif i == 28445:
                    f.write(f"[{time_str}] [INFO] [LockManager] Acquired lock 'order:status' for tx_split_brain_902 lease_id=lease_node-2_tx_split_brain_902 term=42\n")
                elif i == 28450:
                    f.write(f"[{time_str}] [ERROR] [2PC-Coord] COMMIT FAILED on node-1: SplitBrainConsensusException: Quorum unreachable for term 41: Active leader term is 42\n")
                elif i == 28455:
                    f.write(f"[{time_str}] [ERROR] [2PC-Coord] Coordinator caught SplitBrainConsensusException without clearing orphaned term-41 locks!\n")
                elif i == 28460:
                    f.write(f"[{time_str}] [FATAL] [LockManager] LockLeaseDeadlockError: Orphaned lock 'user:balance' (lease_id=lease_node-1_tx_split_brain_902, term=41) blocks subsequent transaction tx_split_brain_903\n")
                elif i == 28470:
                    f.write(f"[{time_str}] [FATAL] [Cluster] Cluster transaction coordinator permanently stalled on partition healing!\n")
                else:
                    f.write(f"[{time_str}] [ERROR] [2PC-Coord] Retry attempt rejected: Lock held by orphaned lease from superseded term 41\n")


def generate_tests() -> str:
    return '''"""Integration tests for cluster recovery and 2PC consensus under network partitions."""
from __future__ import annotations
import unittest
import sys
from pathlib import Path

# Add variant root to sys.path
VARIANT_DIR = Path(__file__).resolve().parent.parent
if str(VARIANT_DIR) not in sys.path:
    sys.path.insert(0, str(VARIANT_DIR))

from benchmark_extreme.src.consensus.raft_node import RaftNode, SplitBrainConsensusException
from benchmark_extreme.src.consensus.rpc_transport import RPCTransport
from benchmark_extreme.src.transaction.lock_manager import LockManager, LockLeaseDeadlockError
from benchmark_extreme.src.transaction.two_phase_commit import TwoPhaseCommitCoordinator
from benchmark_extreme.src.service.kv_gateway import KVGateway


class TestClusterRecovery(unittest.TestCase):
    def setUp(self):
        self.transport = RPCTransport()
        self.node1 = RaftNode("node-1", ["node-2", "node-3"], self.transport)
        self.node2 = RaftNode("node-2", ["node-1", "node-3"], self.transport)
        self.node3 = RaftNode("node-3", ["node-1", "node-2"], self.transport)
        self.nodes = {"node-1": self.node1, "node-2": self.node2, "node-3": self.node3}

        # Initialize node1 as leader of term 1
        self.node1.start_election()
        self.assertEqual(self.node1.state, "LEADER")
        self.assertEqual(self.node1.term_tracker.current_term, 1)

        self.lock_mgr = LockManager()
        self.coordinator = TwoPhaseCommitCoordinator("coord-1", self.nodes, self.lock_mgr)
        self.gateway = KVGateway(self.coordinator, {"user": "node-1", "order": "node-2"})

    def test_split_brain_partition_healing_and_2pc_recovery(self):
        """Simulate a network partition, term election, and assert 2PC cleanly recovers."""
        # 1. Normal transaction under term 1 succeeds
        tx1_success = self.gateway.execute_write_batch("tx_001", {"user:101": {"balance": 500}})
        self.assertTrue(tx1_success)

        # 2. Isolate node-1 (network partition)
        self.transport.isolate_nodes({"node-1"})

        # 3. Node-2 initiates election in majority partition [node-2, node-3] and becomes term 2 leader
        elected = self.node2.start_election()
        self.assertTrue(elected)
        self.assertEqual(self.node2.state, "LEADER")
        self.assertEqual(self.node2.term_tracker.current_term, 2)

        # 4. Attempt a cross-partition transaction touching node-1 (stale term 1) and node-2 (term 2)
        # In unpatched code, this raises SplitBrainConsensusException and leaves orphaned locks
        self.coordinator.begin_transaction("tx_split_brain")
        ops = [
            {"node_id": "node-1", "key": "user:101", "val": {"balance": 400}},
            {"node_id": "node-2", "key": "order:501", "val": {"status": "PENDING"}},
        ]
        self.coordinator.prepare("tx_split_brain", ops)

        # Heal network partition before commit
        self.transport.heal_partitions()

        # Update node-1 term to heal split-brain
        self.node1.term_tracker.update_term(2)
        self.node1.state = "FOLLOWER"

        # Calling commit or handling the split brain must NOT crash with uncaught exception
        # or leave orphaned lock leases blocking future transactions
        try:
            self.coordinator.commit("tx_split_brain")
        except SplitBrainConsensusException:
            # If commit fails due to split brain, coordinator MUST abort cleanly
            self.coordinator.abort("tx_split_brain")

        # 5. VERIFICATION: Next transaction on the same keys MUST succeed without LockLeaseDeadlockError!
        tx_after_healing = self.gateway.execute_write_batch("tx_002", {"user:101": {"balance": 450}})
        self.assertTrue(tx_after_healing, "Subsequent transaction after healing must succeed!")


if __name__ == "__main__":
    unittest.main()
'''


def deploy_variant(target_dir: Path, source_files: dict[str, str], log_source: Path):
    target_dir.mkdir(parents=True, exist_ok=True)
    src_dir = target_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    # Write source files
    for rel_path, content in source_files.items():
        dest = src_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    # Add __init__.py files
    for sub in ["", "consensus", "storage", "transaction", "service"]:
        p = src_dir / sub / "__init__.py"
        if not p.exists():
            p.write_text("", encoding="utf-8")

    # Copy log
    logs_dir = target_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(log_source, logs_dir / "cluster_split_brain.log")

    # Write test
    tests_dir = target_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    
    # Adjust import path in test for the variant
    test_code = generate_tests().replace(
        "from benchmark_extreme.src.", "from src."
    )
    (tests_dir / "test_cluster_recovery.py").write_text(test_code, encoding="utf-8")


def main():
    print(f"Setting up 1M-Token Extreme Stress Benchmark in {ROOT}...")
    source_files = generate_source_code()

    # Generate master log
    master_log = ROOT / "logs" / "cluster_split_brain.log"
    print("Generating 35,000-line realistic cluster trace log...")
    generate_cluster_log(master_log, total_lines=35000)
    print(f"Master log generated: {master_log.stat().st_size / (1024*1024):.2f} MB")

    # Deploy variants
    baseline_dir = ROOT / "variants" / "baseline"
    token_guard_dir = ROOT / "variants" / "token_guard"

    print("Deploying variants/baseline...")
    deploy_variant(baseline_dir, source_files, master_log)

    print("Deploying variants/token_guard...")
    deploy_variant(token_guard_dir, source_files, master_log)

    print("Extreme Benchmark environment ready!")


if __name__ == "__main__":
    main()
