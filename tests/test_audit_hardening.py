"""Unit tests verifying audit hardening, path boundary constraints, and bug fixes."""

import tempfile
import unittest
from pathlib import Path

from antigravity_cheaper import agy_ledger, agy_mcp_server, agy_stats


class TestAuditHardening(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_mcp_server_main_self_test(self):
        """Verify agy_mcp_server.main(['--test']) runs and exits cleanly."""
        res = agy_mcp_server.main(["--test"])
        self.assertEqual(res, 0)

    def test_mcp_get_file_skeleton_path_boundary_enforced(self):
        """Verify get_file_skeleton rejects files outside root_dir (CWE-22 defense)."""
        sandbox = self.root_dir / "sandbox"
        sandbox.mkdir()
        inside_file = sandbox / "inside.py"
        inside_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

        outside_dir = self.root_dir / "outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "secret.py"
        outside_file.write_text("SECRET_KEY = 'supersecret'\n", encoding="utf-8")

        # 1. Valid request inside root_dir
        res_ok = agy_mcp_server.execute_tool(
            "get_file_skeleton",
            {"file_path": "inside.py", "root_dir": str(sandbox)},
        )
        self.assertIn("def hello():", res_ok)

        # 2. Path traversal attack attempt: ../outside/secret.py
        res_traversal = agy_mcp_server.execute_tool(
            "get_file_skeleton",
            {"file_path": "../outside/secret.py", "root_dir": str(sandbox)},
        )
        self.assertIn("must reside within root directory", res_traversal)
        self.assertNotIn("SECRET_KEY", res_traversal)

    def test_summarize_ledger_api(self):
        """Verify summarize_ledger loads and computes aggregated metrics."""
        ledger_file = self.root_dir / "test_ledger.jsonl"
        agy_ledger.record_telemetry(
            task_id="t1",
            variant="baseline",
            model="gemini-2.5-flash",
            effort="none",
            status="success",
            accepted=True,
            input_tokens=1000,
            cached_input_tokens=500,
            output_tokens=200,
            reasoning_output_tokens=50,
            retries=0,
            elapsed_seconds=1.5,
            ledger_path=ledger_file,
        )

        summary = agy_ledger.summarize_ledger(ledger_file)
        self.assertIn("overall", summary)
        self.assertEqual(summary["overall"]["total_records"], 1)
        self.assertEqual(summary["overall"]["accepted_records"], 1)
        self.assertIn("baseline", summary["variants"])

    def test_stats_picks_up_ledger_summary(self):
        """Verify agy_stats collects and embeds real ledger telemetry."""
        ledger_dir = self.root_dir / ".local"
        ledger_dir.mkdir(parents=True)
        ledger_file = ledger_dir / "ledger.jsonl"
        agy_ledger.record_telemetry(
            task_id="t2",
            variant="guarded",
            model="gemini-2.5-pro",
            effort="high",
            status="success",
            accepted=True,
            input_tokens=2000,
            cached_input_tokens=1500,
            output_tokens=300,
            reasoning_output_tokens=100,
            retries=1,
            elapsed_seconds=3.2,
            ledger_path=ledger_file,
        )

        stats = agy_stats.collect_stats(self.root_dir)
        self.assertIsNotNone(stats["ledger"]["summary"])
        self.assertEqual(stats["ledger"]["summary"]["overall"]["total_records"], 1)


if __name__ == "__main__":
    unittest.main()
