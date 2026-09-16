#!/usr/bin/env python3
"""Unit tests for Phase A improvements: agy setup, agy cache, and agy stats."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from antigravity_cheaper import agy_cache_advisor, agy_setup, agy_stats, cli


class TestPhaseA(unittest.TestCase):
    """Test suite for Phase A QOL and diagnostic tooling."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_setup_configure_dry_run(self):
        cfg_file = self.root / "mcp_config.json"
        cfg_file.write_text("{}", encoding="utf-8")

        ok, msg = agy_setup.configure_mcp_file(cfg_file, dry_run=True)
        self.assertTrue(ok)
        self.assertIn("Would register", msg)

        # File must remain untouched in dry run
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        self.assertEqual(data, {})

    def test_setup_configure_and_remove(self):
        cfg_file = self.root / "mcp_config.json"
        cfg_file.write_text("{}", encoding="utf-8")

        # Configure
        ok, msg = agy_setup.configure_mcp_file(cfg_file, python_bin="python3", dry_run=False)
        self.assertTrue(ok)
        self.assertIn("Successfully registered", msg)

        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        self.assertIn("mcpServers", data)
        self.assertIn("agy-symbol-server", data["mcpServers"])
        self.assertEqual(data["mcpServers"]["agy-symbol-server"]["command"], "python3")

        # Remove
        ok_rem, msg_rem = agy_setup.configure_mcp_file(cfg_file, remove=True)
        self.assertTrue(ok_rem)
        self.assertIn("Removed", msg_rem)

        data_rem = json.loads(cfg_file.read_text(encoding="utf-8"))
        self.assertNotIn("agy-symbol-server", data_rem.get("mcpServers", {}))

    def test_setup_preserves_existing_servers(self):
        cfg_file = self.root / "mcp_config.json"
        initial = {
            "mcpServers": {
                "custom-tools": {"command": "node", "args": ["index.js"]}
            }
        }
        cfg_file.write_text(json.dumps(initial), encoding="utf-8")

        ok, msg = agy_setup.configure_mcp_file(cfg_file, dry_run=False)
        self.assertTrue(ok)

        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        self.assertIn("custom-tools", data["mcpServers"])
        self.assertIn("agy-symbol-server", data["mcpServers"])

    def test_cache_advisor_below_threshold(self):
        analysis = agy_cache_advisor.analyze_prefix(self.root, repomap_budget=500)
        self.assertFalse(analysis["is_eligible"])
        self.assertEqual(analysis["deficit"], 2048 - 500)

        card = agy_cache_advisor.format_card(analysis)
        self.assertIn("[BELOW THRESHOLD]", card)
        self.assertIn("Needs 1548 more tokens", card)

    def test_cache_advisor_above_threshold(self):
        # Create a mock invariant file
        invariants_file = self.root / "INVARIANTS.md"
        invariants_file.write_text("word " * 1200, encoding="utf-8")

        analysis = agy_cache_advisor.analyze_prefix(self.root, repomap_budget=1200)
        self.assertTrue(analysis["is_eligible"])
        self.assertEqual(analysis["deficit"], 0)

        card = agy_cache_advisor.format_card(analysis)
        self.assertIn("[ACTIVE] ELIGIBLE FOR 90% DISCOUNT", card)

    def test_stats_collection_and_formatting(self):
        stats = agy_stats.collect_stats(self.root)
        self.assertIn("version", stats)
        self.assertIn("source_code", stats)
        self.assertIn("memory", stats)
        self.assertIn("prefix_lock", stats)
        self.assertIn("cache", stats)
        self.assertIn("ledger", stats)

        dashboard = agy_stats.format_dashboard(stats)
        self.assertIn("ANTIGRAVITY-CHEAPER WORKSPACE DASHBOARD", dashboard)
        self.assertIn("SQLite Memory:", dashboard)

    def test_cli_subcommands_dispatch(self):
        import io
        import sys

        old_argv = sys.argv
        old_stdout = sys.stdout
        try:
            sys.stdout = io.StringIO()
            res = cli.main(["cli.py", "cache", "--root", str(self.root), "--json"])
            self.assertEqual(res, 0)
            self.assertIn("total_prefix_tokens", sys.stdout.getvalue())

            sys.stdout = io.StringIO()
            res2 = cli.main(["cli.py", "stats", "--root", str(self.root), "--json"])
            self.assertEqual(res2, 0)
            self.assertIn("version", sys.stdout.getvalue())
        finally:
            sys.argv = old_argv
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
