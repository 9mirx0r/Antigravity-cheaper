#!/usr/bin/env python3
"""Unit tests for agy_repomap.py."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from agy_repomap import (
    RepoMapGraph,
    estimate_tokens,
    extract_python_symbols,
    extract_regex_symbols,
)


class TestAgyRepoMap(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="repomap_test_")
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertGreaterEqual(estimate_tokens("def hello(): pass"), 3)

    def test_extract_python_symbols(self):
        code = '''"""Module docstring."""
class Calculator:
    """Class doc."""
    def add(self, a: int, b: int) -> int:
        """Add numbers."""
        return a + b

def helper():
    calc = Calculator()
    return calc.add(1, 2)
'''
        fs = extract_python_symbols(code, "calc.py")
        self.assertEqual(fs.lang, "python")
        self.assertEqual(fs.rel_path, "calc.py")

        def_names = {d.name: d for d in fs.defs}
        self.assertIn("Calculator", def_names)
        self.assertIn("add", def_names)
        self.assertIn("helper", def_names)

        calc_def = def_names["Calculator"]
        self.assertEqual(calc_def.kind, "class")
        self.assertEqual(calc_def.docstring, "Class doc.")

        add_def = def_names["add"]
        self.assertEqual(add_def.kind, "method")
        self.assertEqual(add_def.parent, "Calculator")
        self.assertIn("a: int, b: int", add_def.signature)
        self.assertIn("-> int", add_def.signature)

        self.assertIn("Calculator", fs.refs)
        self.assertIn("add", fs.refs)

    def test_extract_regex_symbols(self):
        js_code = """
export class UserService {
    findUser(id) {
        return db.query(id);
    }
}

export function formatName(user) {
    return user.first + ' ' + user.last;
}
"""
        fs = extract_regex_symbols(js_code, "user.js", "javascript")
        def_names = {d.name: d for d in fs.defs}
        self.assertIn("UserService", def_names)
        self.assertIn("formatName", def_names)
        self.assertIn("UserService", fs.refs)
        self.assertIn("formatName", fs.refs)

    def test_pagerank_and_budget_fitting(self):
        # Create a mini repository with a dependency structure:
        # main.py -> service.py -> db.py
        (self.root / "db.py").write_text(
            """class Database:
    def connect(self): ...
    def query(self, sql: str): ...
""",
            encoding="utf-8",
        )
        (self.root / "service.py").write_text(
            """from db import Database

class UserService:
    def __init__(self):
        self.db = Database()
    def get_user(self, user_id: str):
        return self.db.query("SELECT * FROM users")
""",
            encoding="utf-8",
        )
        (self.root / "main.py").write_text(
            """from service import UserService

def run():
    srv = UserService()
    print(srv.get_user("u1"))
""",
            encoding="utf-8",
        )

        graph = RepoMapGraph(self.root)
        graph.scan()
        self.assertEqual(len(graph.files), 3)

        nodes, adj = graph.build_adj_matrix()
        self.assertEqual(len(nodes), 3)

        # Database is referenced by UserService, UserService is referenced by main.py
        # PageRank should flow toward db.py and service.py
        ranks = graph.compute_pagerank()
        self.assertEqual(len(ranks), 3)
        self.assertAlmostEqual(sum(ranks.values()), 1.0, places=4)

        # Focus PageRank
        focus_ranks = graph.compute_pagerank(focus_files=["main.py"])
        self.assertIn("main.py", focus_ranks)

        # Render within budget
        repomap = graph.render_map(budget_tokens=500)
        self.assertIn("Database", repomap)
        self.assertIn("UserService", repomap)
        self.assertLessEqual(estimate_tokens(repomap), 550)

    def test_symbol_subgraph(self):
        (self.root / "a.py").write_text(
            "class SharedComponent: pass\n", encoding="utf-8"
        )
        (self.root / "b.py").write_text(
            "from a import SharedComponent\nx = SharedComponent()\n",
            encoding="utf-8",
        )

        graph = RepoMapGraph(self.root)
        graph.scan()

        sub = graph.get_symbol_subgraph("SharedComponent")
        self.assertEqual(sub["symbol"], "SharedComponent")
        self.assertEqual(len(sub["definitions"]), 1)
        self.assertEqual(sub["definitions"][0]["file"], "a.py")
        self.assertIn("b.py", sub["referencing_files"])

    def test_causal_path_and_query(self):
        # Setup call chain: Controller -> Service -> Repository
        (self.root / "repo.py").write_text(
            """class ItemRepository:
    def fetch_item(self, item_id: int):
        pass
""",
            encoding="utf-8",
        )
        (self.root / "service.py").write_text(
            """class ItemService:
    def get_data(self, item_id: int):
        repo = ItemRepository()
        return repo.fetch_item(item_id)
""",
            encoding="utf-8",
        )
        (self.root / "controller.py").write_text(
            """class ItemController:
    def handle_request(self, req_id: int):
        srv = ItemService()
        return srv.get_data(req_id)
""",
            encoding="utf-8",
        )

        graph = RepoMapGraph(self.root)
        graph.scan()

        # 1. Test causal path finding
        path = graph.find_causal_path("handle_request", "fetch_item")
        self.assertIsNotNone(path)
        path_names = [p["name"] for p in path]
        self.assertEqual(path_names[0], "handle_request")
        self.assertEqual(path_names[-1], "fetch_item")
        self.assertIn("get_data", path_names)

        # 2. Test causal chain query resolution
        chains = graph.find_causal_chain_for_query("ConnectionError in fetch_item")
        self.assertEqual(len(chains), 1)
        target = chains[0]["target_symbol"]
        self.assertEqual(target["name"], "fetch_item")
        caller_names = [c["name"] for c in chains[0]["upstream_callers"]]
        self.assertIn("get_data", caller_names)


if __name__ == "__main__":
    unittest.main()

