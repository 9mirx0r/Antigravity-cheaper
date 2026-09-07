#!/usr/bin/env python3
"""Setup script for Challenge 1: Pure-Python HNSW Vector Search Engine.

Scaffolds the specification (SPEC.md) and full integration test suite (test_hnsw.py)
for both benchmark variants:
  - benchmark_challenge/variants/baseline/
  - benchmark_challenge/variants/token_guard/
"""

import os
import shutil
from pathlib import Path

ROOT = Path("benchmark_challenge").resolve()

SPEC_CONTENT = """# Specification: Pure-Python HNSW Vector Search Engine with Persistence

## 1. Overview
Build an end-to-end, zero-dependency Hierarchical Navigable Small World (HNSW) vector index in pure Python (standard library: `math`, `random`, `heapq`, `struct`, `zlib`, `threading`, `typing`, `pathlib`).

---

## 2. Required Modules (`src/`)

### Module 1: `src/distance.py`
- Functions:
  - `l2_distance(a: Sequence[float], b: Sequence[float]) -> float`: Squared Euclidean distance $\sum (a_i - b_i)^2$.
  - `cosine_distance(a: Sequence[float], b: Sequence[float]) -> float`: $1.0 - \\frac{a \cdot b}{\|a\| \|b\|}$ (handles zero-norm defensively).
  - `inner_product_distance(a: Sequence[float], b: Sequence[float]) -> float`: Negative dot product $- (a \cdot b)$.
- Supported metric names: `"l2"`, `"cosine"`, `"ip"`.

### Module 2: `src/graph.py`
- Multi-layer graph representation.
- Functions & Classes:
  - `assign_level(m_l: float) -> int`: Samples layer index using logarithmic distribution: $\lfloor -\ln(\text{uniform}(0,1)) \cdot m_L \rfloor$.
  - `select_neighbors_heuristic(candidates: list[tuple[float, int]], max_m: int, dist_fn) -> list[int]`: Pruning heuristic to select diverse neighbors.
  - `LayerGraph`: Node-to-neighbors adjacency dictionary supporting directional edge addition and capacity capping.

### Module 3: `src/index.py`
- Class `HNSWIndex`:
  - `__init__(dim: int, metric: str = "l2", M: int = 16, ef_construction: int = 64, ef_search: int = 32, seed: int = 42)`
  - `add_item(vector: Sequence[float], item_id: int) -> None`: Inserts a vector into the HNSW graph across layers.
  - `search_knn(query: Sequence[float], k: int = 10, ef: Optional[int] = None) -> list[tuple[int, float]]`: Greedy search from top layer down, beam search at layer 0. Returns top-$k$ nearest neighbors sorted by distance ascending: `[(item_id, distance), ...]`.
  - `size() -> int`: Number of indexed vectors.

### Module 4: `src/persistence.py`
- Functions:
  - `save_index(index: HNSWIndex, file_path: str | Path) -> None`: Serializes vectors, hyper-parameters (`dim`, `metric`, `M`, `ef_construction`, `m_l`), enter point, and all layer graphs with magic header `b"HNSW\\x01"` and CRC-32 checksum.
  - `load_index(file_path: str | Path) -> HNSWIndex`: Restores index state and validates CRC-32 integrity.

### Module 5: `src/concurrency.py`
- Class `ConcurrentHNSWIndex`:
  - Wraps `HNSWIndex` with fine-grained reader-writer lock (`threading.RLock` or multi-reader single-writer lock) ensuring thread-safe concurrent searches and insertions.

---

## 3. Verification Criteria
All tests in `tests/test_hnsw.py` must pass:
1. `test_distance_metrics`: Precision across metric functions.
2. `test_hnsw_insertion_and_search`: Inserts 150 synthetic 8-dimensional vectors, verifies $k$-NN search against brute-force baseline with $\ge 90\%$ recall@5.
3. `test_persistence_roundtrip`: Verifies save and reload produces identical query results.
4. `test_concurrency`: Verifies thread-safe simultaneous queries and inserts across multiple threads.
"""

TEST_CODE = '''"""Integration & correctness tests for HNSW vector search engine."""
from __future__ import annotations
import math
import random
import sys
import tempfile
import threading
import unittest
from pathlib import Path

# Add variant root to sys.path
VARIANT_ROOT = Path(__file__).resolve().parent.parent
if str(VARIANT_ROOT) not in sys.path:
    sys.path.insert(0, str(VARIANT_ROOT))

from src.distance import l2_distance, cosine_distance, inner_product_distance
from src.index import HNSWIndex
from src.persistence import save_index, load_index
from src.concurrency import ConcurrentHNSWIndex


class TestHNSWVectorEngine(unittest.TestCase):
    def setUp(self):
        random.seed(42)

    def test_distance_metrics(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        v3 = [2.0, 0.0, 0.0]

        # L2 squared distance
        self.assertAlmostEqual(l2_distance(v1, v2), 2.0)
        self.assertAlmostEqual(l2_distance(v1, v3), 1.0)

        # Cosine distance
        self.assertAlmostEqual(cosine_distance(v1, v2), 1.0)
        self.assertAlmostEqual(cosine_distance(v1, v3), 0.0)

        # Inner product
        self.assertAlmostEqual(inner_product_distance(v1, v3), -2.0)

    def test_hnsw_insertion_and_search(self):
        dim = 8
        num_items = 150
        index = HNSWIndex(dim=dim, metric="l2", M=16, ef_construction=64, ef_search=32, seed=42)

        # Generate synthetic vectors
        vectors = {}
        for i in range(num_items):
            vec = [random.uniform(-1.0, 1.0) for _ in range(dim)]
            vectors[i] = vec
            index.add_item(vec, i)

        self.assertEqual(index.size(), num_items)

        # Test KNN queries against brute-force ground truth
        num_queries = 20
        k = 5
        total_recall = 0.0

        for q in range(num_queries):
            query = [random.uniform(-1.0, 1.0) for _ in range(dim)]

            # Brute-force ground truth
            ground_truth = sorted(
                [(i, l2_distance(query, vec)) for i, vec in vectors.items()],
                key=lambda x: x[1]
            )[:k]
            gt_ids = {item[0] for item in ground_truth}

            # HNSW search
            results = index.search_knn(query, k=k)
            self.assertEqual(len(results), k)
            hnsw_ids = {item[0] for item in results}

            # Calculate recall for this query
            overlap = len(gt_ids.intersection(hnsw_ids))
            total_recall += overlap / k

        mean_recall = total_recall / num_queries
        print(f"HNSW Recall@{k}: {mean_recall * 100:.1f}%")
        self.assertGreaterEqual(mean_recall, 0.90, "HNSW must achieve >= 90% recall@5")

    def test_persistence_roundtrip(self):
        dim = 6
        index = HNSWIndex(dim=dim, metric="cosine", M=12, ef_construction=32, ef_search=20, seed=123)
        vectors = {i: [random.gauss(0, 1) for _ in range(dim)] for i in range(50)}
        for i, vec in vectors.items():
            index.add_item(vec, i)

        with tempfile.NamedTemporaryFile(suffix=".hnsw", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            save_index(index, tmp_path)
            loaded_index = load_index(tmp_path)

            self.assertEqual(loaded_index.size(), 50)
            self.assertEqual(loaded_index.dim, dim)
            self.assertEqual(loaded_index.metric, "cosine")

            query = [random.gauss(0, 1) for _ in range(dim)]
            orig_res = index.search_knn(query, k=5)
            load_res = loaded_index.search_knn(query, k=5)

            self.assertEqual([x[0] for x in orig_res], [x[0] for x in load_res])
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_concurrency(self):
        dim = 4
        base_index = HNSWIndex(dim=dim, metric="l2", M=8, ef_construction=24, ef_search=16, seed=99)
        concurrent_idx = ConcurrentHNSWIndex(base_index)

        # Pre-populate with 20 items
        for i in range(20):
            concurrent_idx.add_item([random.random() for _ in range(dim)], i)

        errors = []

        def worker_insert(start_id, count):
            try:
                for i in range(start_id, start_id + count):
                    concurrent_idx.add_item([random.random() for _ in range(dim)], i)
            except Exception as e:
                errors.append(e)

        def worker_search(num_searches):
            try:
                for _ in range(num_searches):
                    q = [random.random() for _ in range(dim)]
                    res = concurrent_idx.search_knn(q, k=3)
                    self.assertGreater(len(res), 0)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker_insert, args=(100, 30)),
            threading.Thread(target=worker_insert, args=(200, 30)),
            threading.Thread(target=worker_search, args=(50,)),
            threading.Thread(target=worker_search, args=(50,)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent operations encountered errors: {errors}")
        self.assertEqual(concurrent_idx.size(), 80)


if __name__ == "__main__":
    unittest.main()
'''


def setup_variant(target_dir: Path):
    target_dir.mkdir(parents=True, exist_ok=True)
    src_dir = target_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = target_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    # Write SPEC.md
    (target_dir / "SPEC.md").write_text(SPEC_CONTENT, encoding="utf-8")

    # Write test suite
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_hnsw.py").write_text(TEST_CODE, encoding="utf-8")

    # Write empty stubs in src/
    (src_dir / "__init__.py").write_text("", encoding="utf-8")
    for mod in ["distance.py", "graph.py", "index.py", "persistence.py", "concurrency.py"]:
        p = src_dir / mod
        if not p.exists():
            p.write_text(f'"""Module {mod} (To be implemented)."""\n', encoding="utf-8")


def main():
    print(f"Setting up Challenge 1 in {ROOT}...")
    baseline_dir = ROOT / "variants" / "baseline"
    tg_dir = ROOT / "variants" / "token_guard"

    setup_variant(baseline_dir)
    print("Baseline environment scaffolded.")

    setup_variant(tg_dir)
    print("Token-Guard environment scaffolded.")

    print("Challenge 1 setup complete!")


if __name__ == "__main__":
    main()
