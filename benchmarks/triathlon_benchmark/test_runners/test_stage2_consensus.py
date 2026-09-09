#!/usr/bin/env python3
"""Stage 2 Test Suite: Distributed Consensus & 2PC Fault Tolerance."""

import os
from pathlib import Path
import sys
import unittest

VARIANT_ROOT = Path(os.environ.get("TRIATHLON_VARIANT_DIR", ".")).resolve()
STAGE_DIR = VARIANT_ROOT / "stage2_consensus"
if str(STAGE_DIR) not in sys.path:
    sys.path.insert(0, str(STAGE_DIR))

from src.rpc_network import RPCNetwork, NetworkPartitionError
from src.raft_node import RaftNode, TermTracker
from src.two_phase_commit import TwoPhaseCommitCoordinator, SplitBrainConsensusException
from src.linearizability_checker import LinearizabilityChecker


class TestStage2Consensus(unittest.TestCase):

    def test_term_tracker_monotonicity(self):
        tracker = TermTracker("node-1")
        self.assertEqual(tracker.current_term, 0)
        self.assertEqual(tracker.increment_term(), 1)
        self.assertEqual(tracker.voted_for, "node-1")
        self.assertTrue(tracker.update_term(5))
        self.assertEqual(tracker.current_term, 5)
        self.assertIsNone(tracker.voted_for)
        self.assertFalse(tracker.update_term(3))  # Must not regress

    def test_raft_election_quorum(self):
        network = RPCNetwork()
        nodes = {}
        for nid in ["node-1", "node-2", "node-3"]:
            peers = [p for p in ["node-1", "node-2", "node-3"] if p != nid]
            nodes[nid] = RaftNode(nid, peers, network)

        # Start election on node-1
        elected = nodes["node-1"].start_election()
        self.assertTrue(elected)
        self.assertEqual(nodes["node-1"].state, "LEADER")
        self.assertEqual(nodes["node-1"].term_tracker.current_term, 1)

    def test_raft_log_replication(self):
        network = RPCNetwork()
        nodes = {}
        for nid in ["node-1", "node-2", "node-3"]:
            peers = [p for p in ["node-1", "node-2", "node-3"] if p != nid]
            nodes[nid] = RaftNode(nid, peers, network)

        nodes["node-1"].start_election()
        idx = nodes["node-1"].append_entry({"action": "SET", "key": "x", "val": 100})
        self.assertEqual(idx, 1)

    def test_two_phase_commit_normal(self):
        network = RPCNetwork()
        nodes = {}
        for nid in ["node-1", "node-2", "node-3"]:
            peers = [p for p in ["node-1", "node-2", "node-3"] if p != nid]
            nodes[nid] = RaftNode(nid, peers, network)
        nodes["node-1"].start_election()

        coord = TwoPhaseCommitCoordinator("coord-1", nodes)
        tx_id = coord.begin_transaction("tx-100")
        prepared = coord.prepare(tx_id, ["node-1", "node-2"], [{"key": "acc:1", "delta": -50}])
        self.assertTrue(prepared)
        committed = coord.commit(tx_id)
        self.assertTrue(committed)

    def test_two_phase_commit_term_fencing_partition(self):
        network = RPCNetwork()
        nodes = {}
        for nid in ["node-1", "node-2", "node-3"]:
            peers = [p for p in ["node-1", "node-2", "node-3"] if p != nid]
            nodes[nid] = RaftNode(nid, peers, network)
        nodes["node-1"].start_election()  # Term 1 leader

        coord = TwoPhaseCommitCoordinator("coord-1", nodes)
        tx_id = coord.begin_transaction("tx-split")
        coord.prepare(tx_id, ["node-1", "node-2"], [{"key": "vault:10", "op": "LOCK"}])

        # Simulate partition: isolate node-1, node-2 and node-3 elect node-2 in Term 2
        network.isolate_partition({"node-1"})
        nodes["node-2"].start_election()  # Becomes Term 2 leader on majority
        self.assertEqual(nodes["node-2"].state, "LEADER")
        self.assertEqual(nodes["node-2"].term_tracker.current_term, 2)

        # Old coordinator tries to commit under superseded term -> Term Fencing must trigger
        with self.assertRaises(Exception):
            coord.commit(tx_id)

        # Verify coordinator cleans up and aborts transaction
        aborted = coord.abort(tx_id)
        self.assertTrue(aborted)

    def test_linearizability_checker(self):
        checker = LinearizabilityChecker()
        checker.record_op("client-1", "WRITE", "key-a", "v1", 0.1, 0.2)
        checker.record_op("client-2", "READ", "key-a", "v1", 0.25, 0.3)
        self.assertTrue(checker.verify_sequential_consistency())


if __name__ == "__main__":
    unittest.main()
