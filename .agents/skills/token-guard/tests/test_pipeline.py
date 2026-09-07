#!/usr/bin/env python3
"""Unit tests for agy_pipeline.py."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from agy_pipeline import (
    STAGE_ARCHITECT,
    STAGE_CRITIC,
    STAGE_IMPLEMENTER,
    VERDICT_FIX_FIRST,
    VERDICT_RETHINK,
    VERDICT_SHIP,
    CognitivePipeline,
)


class TestCognitivePipeline(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pipeline_test_")
        self.state_file = Path(self.test_dir) / "state.json"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_happy_path_ship(self):
        # 1. Initialize
        CognitivePipeline.initialize(
            task_id="task_001",
            objective="Build HNSW vector index",
            workspace_root=self.test_dir,
            state_file=self.state_file,
        )
        pipe = CognitivePipeline(self.state_file)
        self.assertEqual(pipe.state.stage, STAGE_ARCHITECT)

        # 2. Architect records spec
        pipe.record_architect_spec(
            contracts=["test_hnsw_insert", "test_hnsw_search"],
            surgical_files=["src/hnsw.py", "tests/test_hnsw.py"],
            resolved_ambiguities=["Use L2 squared distance metric"],
        )
        self.assertEqual(pipe.state.stage, STAGE_IMPLEMENTER)
        self.assertIsNotNone(pipe.state.spec)

        # 3. Implementer records receipt
        pipe.record_implementation_receipt(
            touched_files=["src/hnsw.py", "tests/test_hnsw.py"],
            tests_passed=True,
            test_summary="2 tests passed",
            git_diff_stat="2 files changed, 140 insertions(+)",
        )
        self.assertEqual(pipe.state.stage, STAGE_CRITIC)
        self.assertIsNotNone(pipe.state.implementation_receipt)

        # 4. Critic approves SHIP
        status, msg = pipe.evaluate_verdict(VERDICT_SHIP, "Clean implementation and tests pass.")
        self.assertEqual(status, "SUCCESS")
        self.assertEqual(pipe.state.stage, "COMPLETED")

    def test_fix_first_retry_and_circuit_breaker(self):
        CognitivePipeline.initialize(
            task_id="task_002",
            objective="Refactor WAL manager",
            workspace_root=self.test_dir,
            state_file=self.state_file,
        )
        pipe = CognitivePipeline(self.state_file)
        pipe.record_architect_spec(["test_wal"], ["src/wal.py"], [])

        # Turn 1: Implementer passes to Critic
        pipe.record_implementation_receipt(["src/wal.py"], True, "ok", "1 file")
        self.assertEqual(pipe.state.iteration, 1)

        # Critic returns FIX_FIRST
        status, msg = pipe.evaluate_verdict(VERDICT_FIX_FIRST, "Missing CRC validation.")
        self.assertEqual(status, "RETRY_IMPLEMENTER")
        self.assertEqual(pipe.state.stage, STAGE_IMPLEMENTER)
        self.assertEqual(pipe.state.iteration, 2)

        # Turn 2: Implementer passes to Critic
        pipe.record_implementation_receipt(["src/wal.py"], True, "ok", "1 file")
        status, msg = pipe.evaluate_verdict(VERDICT_FIX_FIRST, "Still missing CRC check.")
        self.assertEqual(pipe.state.iteration, 3)

        # Turn 3: Implementer passes to Critic
        pipe.record_implementation_receipt(["src/wal.py"], True, "ok", "1 file")
        status, msg = pipe.evaluate_verdict(VERDICT_FIX_FIRST, "CRC check still failing.")
        self.assertEqual(status, "CIRCUIT_BREAKER")
        self.assertEqual(pipe.state.stage, "FAILED")

    def test_rethink_spec_loop(self):
        CognitivePipeline.initialize(
            task_id="task_003",
            objective="Design cache",
            workspace_root=self.test_dir,
            state_file=self.state_file,
        )
        pipe = CognitivePipeline(self.state_file)
        pipe.record_architect_spec(["test_cache"], ["src/cache.py"], [])
        pipe.record_implementation_receipt(["src/cache.py"], True, "ok", "1 file")

        status, msg = pipe.evaluate_verdict(VERDICT_RETHINK, "Architecture violated invariant.")
        self.assertEqual(status, "RETHINK_SPEC")
        self.assertEqual(pipe.state.stage, STAGE_ARCHITECT)

    def test_swarm_decomposition(self):
        CognitivePipeline.initialize(
            task_id="task_004",
            objective="Build distributed search engine",
            workspace_root=self.test_dir,
            state_file=self.state_file,
        )
        pipe = CognitivePipeline(self.state_file)
        pipe.record_architect_spec(
            contracts=[
                "test_distance_metrics",
                "test_graph_construction",
                "test_persistence_roundtrip",
                "test_concurrency_locks",
            ],
            surgical_files=[
                "src/distance.py",
                "src/graph.py",
                "src/persistence.py",
                "src/concurrency.py",
            ],
            resolved_ambiguities=[],
        )

        out_dir = Path(self.test_dir) / "manifests"
        manifests = pipe.decompose_spec(num_workers=2, model_tier="flash", out_dir=str(out_dir))

        self.assertEqual(len(manifests), 2)
        self.assertEqual(len(pipe.state.swarm_manifests), 2)
        self.assertEqual(manifests[0]["worker_id"], "worker_1")
        self.assertEqual(manifests[1]["worker_id"], "worker_2")

        # Verify files were partitioned without overlap
        files_w1 = set(manifests[0]["target_files"])
        files_w2 = set(manifests[1]["target_files"])
        self.assertTrue(files_w1.isdisjoint(files_w2))
        self.assertEqual(files_w1 | files_w2, {
            "src/distance.py",
            "src/graph.py",
            "src/persistence.py",
            "src/concurrency.py",
        })

        # Verify manifest files written to disk
        self.assertTrue((out_dir / "worker_1_manifest.json").exists())
        self.assertTrue((out_dir / "worker_2_manifest.json").exists())


if __name__ == "__main__":
    unittest.main()

