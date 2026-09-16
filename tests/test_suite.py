#!/usr/bin/env python3
"""Top-level test runner for Antigravity-Cheaper.

Discovers and executes all 49 unit tests across:
- Tree-sitter AST & Personalized PageRank RepoMap (agy_repomap)
- Hardware-Invariant Prefix Locking & Merkle trees (agy_prefix_lock)
- Zero-Tax SQLite FTS5 Persistent Memory (agy_memory)
- Autonomous Cognitive Pipeline & Swarm Decomposer (agy_pipeline)
- AST Elision, Bounded Slicing, Dependency Capsules & Telemetry Ledger
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
SCRIPTS_DIR = ROOT / ".agents" / "skills" / "token-guard" / "scripts"
AGENTS_SCRIPTS = ROOT / ".agents" / "scripts"

for d in [SRC_DIR, SCRIPTS_DIR, AGENTS_SCRIPTS]:
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

def main():
    loader = unittest.TestLoader()
    suite1 = loader.discover(str(ROOT / ".agents" / "skills" / "token-guard" / "tests"))
    suite2 = loader.discover(str(ROOT / "tests"), pattern="test_*.py")
    all_tests = unittest.TestSuite([suite1, suite2])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(all_tests)
    sys.exit(0 if result.wasSuccessful() else 1)

if __name__ == "__main__":
    main()
