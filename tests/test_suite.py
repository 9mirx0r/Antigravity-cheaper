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
SCRIPTS_DIR = ROOT / ".agents" / "skills" / "token-guard" / "scripts"
AGENTS_SCRIPTS = ROOT / ".agents" / "scripts"
SRC_DIR = ROOT / "src" / "antigravity_cheaper"

for d in [SCRIPTS_DIR, AGENTS_SCRIPTS, SRC_DIR]:
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

def main():
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / ".agents" / "skills" / "token-guard" / "tests"))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

if __name__ == "__main__":
    main()
