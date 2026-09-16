#!/usr/bin/env python3
"""Unit tests verifying Phase 2 robustness upgrades in Antigravity-Cheaper."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from antigravity_cheaper.agy_ast import js_ts_skeleton
from antigravity_cheaper.agy_handoff import prepare_handoff
from antigravity_cheaper.agy_memory import MemoryEngine
from antigravity_cheaper.agy_prefix_lock import PrefixLockBuilder
from antigravity_cheaper.agy_repomap import RepoMapGraph


class TestPhase2Improvements(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.root = Path(self.tmp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_gitignore_filtering(self):
        # Create .gitignore
        (self.root / ".gitignore").write_text("""
# Comments should be ignored
custom_env/
*.generated.py
secret_*.py
""", encoding="utf-8")

        # Create valid source file
        (self.root / "main.py").write_text("def hello(): pass", encoding="utf-8")

        # Create ignored files
        custom_env = self.root / "custom_env"
        custom_env.mkdir()
        (custom_env / "dep.py").write_text("def dep(): pass", encoding="utf-8")

        (self.root / "build.generated.py").write_text("def build(): pass", encoding="utf-8")
        (self.root / "secret_keys.py").write_text("API_KEY = '123'", encoding="utf-8")

        graph = RepoMapGraph(self.root)
        graph.scan()

        files = list(graph.files.keys())
        self.assertIn("main.py", files)
        self.assertNotIn("custom_env/dep.py", files)
        self.assertNotIn("build.generated.py", files)
        self.assertNotIn("secret_keys.py", files)

    def test_js_ts_braces_in_strings_and_comments(self):
        js_code = """
export class ParserService {
  parse(input: string): string {
    const braceInString = "{ this should not break parser }";
    const template = `template {with} braces`;
    // single line comment with { brace
    /* multi-line comment
       with { open brace
    */
    return input;
  }

  nextFunction(): boolean {
    return true;
  }
}
"""
        skeleton = js_ts_skeleton(js_code)
        self.assertIn("export class ParserService {", skeleton)
        self.assertIn("parse(input: string): string { ... }", skeleton)
        self.assertIn("nextFunction(): boolean { ... }", skeleton)
        self.assertNotIn("braceInString", skeleton)

    def test_prefix_lock_memory_invalidation(self):
        # Create a source file
        (self.root / "app.py").write_text("def run(): pass\n", encoding="utf-8")

        # Initialize memory database
        mem_dir = self.root / ".local"
        mem_dir.mkdir()
        db_path = mem_dir / "memory.db"
        engine = MemoryEngine(db_path)
        engine.save(topic_key="architecture/auth", title="Auth Model", content="Use JWT tokens", project=self.root.name)
        engine.close()

        builder = PrefixLockBuilder(self.root, target_tokens=50)
        manifest = builder.build_prefix()

        self.assertIn(".local/memory.db", manifest["files"])
        valid, _ = builder.verify_manifest(manifest)
        self.assertTrue(valid)

        # Modify memory database
        engine = MemoryEngine(db_path)
        engine.save(topic_key="architecture/auth", title="Auth Model Rev 2", content="Switched to OAuth2 / PKCE", project=self.root.name)
        engine.close()

        valid_after, msg = builder.verify_manifest(manifest)
        self.assertFalse(valid_after)
        self.assertIn(".local/memory.db", msg)

    def test_handoff_large_file_streaming_safe(self):
        sample_file = self.root / "log.txt"
        sample_file.write_text("line\n" * 1000, encoding="utf-8")

        res = prepare_handoff(
            source_path=str(sample_file),
            full_limit=100,  # force pack route
            pack_limit=500,
        )
        self.assertEqual(res["route"], "pack")
        self.assertTrue(len(res["sha256"]) == 64)

    def test_unified_cli_dispatches(self):
        import io

        from antigravity_cheaper import cli

        old_argv = sys.argv
        old_stdout = sys.stdout
        try:
            sys.stdout = io.StringIO()
            sys.argv = ["agy", "--version"]
            exit_code = cli.main()
            self.assertEqual(exit_code, 0)
            self.assertIn("antigravity-cheaper v1.0.0", sys.stdout.getvalue())

            sys.stdout = io.StringIO()
            sys.argv = ["agy", "--help"]
            exit_code = cli.main()
            self.assertEqual(exit_code, 0)
            self.assertIn("Usage:\n  agy <command>", sys.stdout.getvalue())
        finally:
            sys.argv = old_argv
            sys.stdout = old_stdout

    def test_ledger_gemini_3_pricing(self):
        from antigravity_cheaper.agy_ledger import get_model_rates
        rates = get_model_rates("gemini-3.8-flash")
        self.assertEqual(rates, (0.075, 0.01875, 0.30))
        rates_pro = get_model_rates("gemini-3.8-pro")
        self.assertEqual(rates_pro, (1.25, 0.3125, 5.00))


if __name__ == "__main__":
    unittest.main()
