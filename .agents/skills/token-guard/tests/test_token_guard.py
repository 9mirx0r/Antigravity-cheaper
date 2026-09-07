#!/usr/bin/env python3
"""Comprehensive Unit Test Suite for Token Guard Skill.

Tests:
  - agy_ast.py: AST skeleton elision, docstring & signature preservation, JS/TS support, symbols extraction.
  - agy_pack.py: Bounded packing with priority (failures, tail, head, diagnostics), sha256, clipped/complete flags, verified line range expansion.
  - agy_capsule.py: Dependency sealing, file/tree deterministic hashing, TTL expiration, live kind handling, and status verification.
  - agy_ledger.py: Prompt-free telemetry recording, metrics aggregation, cache hit rate, and cost_per_accepted_outcome calculation.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import agy_ast
import agy_capsule
import agy_ledger
import agy_pack
import agy_handoff

# Add workspace .agents/scripts to sys.path for noise_sanitizer
AGENTS_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(AGENTS_SCRIPTS_DIR))
import noise_sanitizer


class TestAgyAst(unittest.TestCase):
    """Test AST skeleton elision and symbols extraction."""

    def test_python_skeleton_functions_and_methods(self):
        code = '''
"""Module docstring."""
import math
from typing import List, Optional

@decorator_a
@decorator_b(123)
def calculate_metrics(values: List[float], scale: float = 1.0) -> float:
    """Calculate normalized metrics from input values."""
    temp = [v * scale for v in values]
    res = math.sqrt(sum(temp))
    return res

async def fetch_async(url: str, timeout: int = 30) -> Optional[dict]:
    # No docstring here
    data = await http_client.get(url, timeout=timeout)
    return data

def stream_chunks(data: bytes, chunk_size: int = 1024):
    """Stream chunks generator."""
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]

class MetricProcessor:
    """Handles pipeline processing of metrics."""
    version: str = "2.1.0"
    count: int = 0

    def __init__(self, name: str) -> None:
        """Init processor."""
        self.name = name

    @property
    def ready(self) -> bool:
        return True

    def process(self, item: dict) -> bool:
        return True
'''
        skeleton = agy_ast.python_skeleton(code, style="ellipsis")
        # Check that signatures, decorators, types, and docstrings are preserved
        self.assertIn("def calculate_metrics(values: List[float], scale: float=1.0) -> float:", skeleton)
        self.assertIn('"""Calculate normalized metrics from input values."""', skeleton)
        self.assertIn("@decorator_a", skeleton)
        self.assertIn("@decorator_b(123)", skeleton)
        self.assertIn("async def fetch_async(url: str, timeout: int=30) -> Optional[dict]:", skeleton)
        self.assertIn("class MetricProcessor:", skeleton)
        self.assertIn('"""Handles pipeline processing of metrics."""', skeleton)
        self.assertTrue('version: str = "2.1.0"' in skeleton or "version: str = '2.1.0'" in skeleton)
        self.assertIn("@property", skeleton)
        self.assertIn("...", skeleton)

        # Ensure implementation bodies are elided
        self.assertNotIn("temp = [v * scale for v in values]", skeleton)
        self.assertNotIn("data = await http_client.get", skeleton)
        self.assertNotIn("yield data[i:i + chunk_size]", skeleton)

        # Must parse as valid Python
        ast.parse(skeleton)

    def test_python_skeleton_pass_style(self):
        code = '''
def simple_fn(x: int) -> int:
    return x * 2
'''
        skeleton = agy_ast.python_skeleton(code, style="pass")
        self.assertIn("pass", skeleton)
        self.assertNotIn("...", skeleton)
        ast.parse(skeleton)

    def test_python_skeleton_main_block(self):
        code = '''
def main():
    print("hello")

if __name__ == "__main__":
    print("running directly")
    main()
'''
        skeleton = agy_ast.python_skeleton(code)
        self.assertTrue('if __name__ == "__main__":' in skeleton or "if __name__ == '__main__':" in skeleton)
        self.assertNotIn('print("running directly")', skeleton)
        ast.parse(skeleton)

    def test_python_symbols_extraction(self):
        code = '''
class ServiceA:
    """Core service."""
    def start(self, port: int = 8080) -> bool:
        """Start server."""
        return True

    def gen(self):
        yield 1

def helper(a: str, b: int = 0) -> str:
    """Helper func."""
    return a * b

PORT_CONST: int = 8080
'''
        symbols = agy_ast.python_symbols(code)
        names = [s["name"] for s in symbols]
        self.assertIn("ServiceA", names)
        self.assertIn("helper", names)
        self.assertIn("PORT_CONST", names)

        # Check ServiceA methods
        service_sym = next(s for s in symbols if s["name"] == "ServiceA")
        method_names = [m["name"] for m in service_sym["methods"]]
        self.assertIn("start", method_names)
        self.assertIn("gen", method_names)

        gen_sym = next(m for m in service_sym["methods"] if m["name"] == "gen")
        self.assertEqual(gen_sym["kind"], "generator")

    def test_js_ts_skeleton_and_symbols(self):
        ts_code = '''
import { Logger } from "./logger";

export interface UserConfig {
  id: string;
  timeout: number;
}

export type Status = "active" | "inactive";

/** User service description */
export class UserService {
  private count: number = 0;

  async getUser(id: string): Promise<UserConfig> {
    const user = await db.find(id);
    return user;
  }
}

export async function authenticate(token: string): Promise<boolean> {
  if (!token) return false;
  return verify(token);
}

export const validateToken = (t: string): boolean => {
  return t.length > 10;
};
'''
        skeleton = agy_ast.js_ts_skeleton(ts_code)
        self.assertIn("export interface UserConfig", skeleton)
        self.assertIn("export type Status", skeleton)
        self.assertIn("export class UserService", skeleton)
        self.assertIn("async getUser(id: string): Promise<UserConfig> { ... }", skeleton)
        self.assertIn("export async function authenticate(token: string): Promise<boolean> { ... }", skeleton)
        self.assertIn("export const validateToken = (t: string): boolean => { ... }", skeleton)
        # Ensure internal logic is elided
        self.assertNotIn("const user = await db.find(id)", skeleton)
        self.assertNotIn("if (!token) return false", skeleton)

        symbols = agy_ast.js_ts_symbols(ts_code)
        sym_names = [s["name"] for s in symbols]
        self.assertIn("UserConfig", sym_names)
        self.assertIn("Status", sym_names)
        self.assertIn("UserService", sym_names)
        self.assertIn("authenticate", sym_names)
        self.assertIn("validateToken", sym_names)
        self.assertIn("getUser", sym_names)

    def test_ast_cli(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src_file = Path(tmp_dir) / "sample.py"
            src_file.write_text("def test_cli():\n    return 42\n", encoding="utf-8")
            out_file = Path(tmp_dir) / "out.py"

            # Test skeleton CLI
            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "agy_ast.py"),
                    "skeleton",
                    "--source",
                    str(src_file),
                    "--out",
                    str(out_file),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0)
            self.assertTrue(out_file.exists())
            self.assertIn("...", out_file.read_text(encoding="utf-8"))

            # Test symbols CLI
            res_sym = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "agy_ast.py"),
                    "symbols",
                    "--source",
                    str(src_file),
                    "--json",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res_sym.returncode, 0)
            symbols_data = json.loads(res_sym.stdout)
            self.assertEqual(symbols_data[0]["name"], "test_cli")


class TestAgyPack(unittest.TestCase):
    """Test bounded packing and verified expansion."""

    def test_pack_complete_under_budget(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "test.log"
            content = "Line 1: init\nLine 2: running\nLine 3: finished\n"
            source.write_text(content, encoding="utf-8")

            res = agy_pack.pack_file(source, root_dir=tmp_path, max_chars=4000)
            self.assertTrue(res["complete"])
            self.assertFalse(res["clipped"])
            self.assertEqual(len(res["lines"]), 3)
            self.assertEqual(res["lines"][0]["line"], 1)
            self.assertEqual(res["lines"][0]["content"], "Line 1: init")
            self.assertIn("sha256", res)

    def test_pack_clipped_priorities_and_deduplication(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "heavy.log"

            # Create 100 lines with duplicates and failures
            lines = []
            lines.append("Header Line 1: Build Starting")
            lines.append("Header Line 2: Environment Setup")
            lines.append("Header Line 3: Compiler Flags")
            lines.append("Header Line 4: Dependency Check")
            lines.append("Header Line 5: Ready")

            for i in range(6, 80):
                if i in (15, 25, 35):
                    # Duplicate failure message across different lines
                    lines.append(f"FAILURE: SocketTimeoutException in test_fetch")
                elif i == 45:
                    # Unique failure
                    lines.append("AssertionError: expected 200 but got 500")
                else:
                    lines.append(f"Info line {i}: routine operation in progress with extra padding chars")

            for j in range(80, 101):
                lines.append(f"Tail line {j}: final summary status")

            content = "\n".join(lines)
            source.write_text(content, encoding="utf-8")

            # Pack with low max_chars budget to trigger clipping
            res = agy_pack.pack_file(source, root_dir=tmp_path, max_chars=1200)

            self.assertFalse(res["complete"])
            self.assertTrue(res["clipped"])

            # Verify priorities included:
            selected_lines = [item["content"] for item in res["lines"]]
            selected_indices = [item["line"] for item in res["lines"]]

            # Head (first 5 lines) should be present
            self.assertIn(1, selected_indices)
            self.assertIn(5, selected_indices)

            # Tail lines should be present
            self.assertIn(100, selected_indices)

            # Unique failures should be present
            self.assertTrue(any("AssertionError" in c for c in selected_lines))
            self.assertTrue(any("SocketTimeoutException" in c for c in selected_lines))

            # Deduplication: SocketTimeoutException occurred at lines 15, 25, 35,
            # but should be deduplicated so it does not waste slots repeatedly
            failure_count = sum(1 for c in selected_lines if "SocketTimeoutException" in c)
            self.assertEqual(failure_count, 1)

            # Lines should be 1-based and strictly sorted
            self.assertEqual(selected_indices, sorted(selected_indices))

    def test_pack_root_security_boundary(self):
        with tempfile.TemporaryDirectory() as root_a, tempfile.TemporaryDirectory() as root_b:
            outside_file = Path(root_b) / "secret.txt"
            outside_file.write_text("secret", encoding="utf-8")

            with self.assertRaises(ValueError):
                agy_pack.pack_file(outside_file, root_dir=root_a)

    def test_expand_valid_and_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "app.py"
            code = "\n".join(f"line_{i} = {i}" for i in range(1, 51))
            source.write_text(code, encoding="utf-8")

            pack_data = agy_pack.pack_file(source, root_dir=tmp_path, max_chars=200)

            # 1. Valid expansion
            expanded = agy_pack.expand_pack(pack_data, start_line=10, end_line=15)
            self.assertEqual(len(expanded["lines"]), 6)
            self.assertEqual(expanded["lines"][0]["line"], 10)
            self.assertEqual(expanded["lines"][0]["content"], "line_10 = 10")
            self.assertEqual(expanded["lines"][-1]["line"], 15)
            self.assertEqual(expanded["lines"][-1]["content"], "line_15 = 15")

            # 2. Modify source on disk -> Integrity mismatch should fail
            source.write_text(code + "\n# Modified after seal!", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                agy_pack.expand_pack(pack_data, start_line=10, end_line=15)
            self.assertIn("Integrity check failed", str(ctx.exception))

    def test_pack_expand_cli(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            src_file = tmp_path / "log.txt"
            src_file.write_text("L1\nL2\nL3: FAILURE occurred\nL4\nL5\n", encoding="utf-8")
            pack_file_path = tmp_path / "pack.json"

            # CLI pack
            res_pack = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "agy_pack.py"),
                    "pack",
                    "--source",
                    str(src_file),
                    "--root",
                    str(tmp_path),
                    "--out",
                    str(pack_file_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res_pack.returncode, 0)
            self.assertTrue(pack_file_path.exists())

            # CLI expand
            res_exp = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "agy_pack.py"),
                    "expand",
                    "--pack",
                    str(pack_file_path),
                    "--start",
                    "2",
                    "--end",
                    "4",
                    "--json",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res_exp.returncode, 0)
            exp_json = json.loads(res_exp.stdout)
            self.assertEqual(len(exp_json["lines"]), 3)
            self.assertEqual(exp_json["lines"][1]["content"], "L3: FAILURE occurred")


class TestAgyCapsule(unittest.TestCase):
    """Test dependency sealing, status verification, and lifecycle states."""

    def test_seal_and_status_dependencies_match(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            f1 = tmp_path / "mod1.py"
            f1.write_text("a = 1\n", encoding="utf-8")

            tree_dir = tmp_path / "lib"
            tree_dir.mkdir()
            (tree_dir / "helper.py").write_text("def h(): pass\n", encoding="utf-8")
            (tree_dir / "utils.py").write_text("def u(): pass\n", encoding="utf-8")

            capsule = agy_capsule.seal_capsule(
                claim="Unit test dependencies",
                files=[str(f1)],
                trees=[str(tree_dir)],
                kind="static",
                ttl_seconds=3600,
                base_dir=tmp_path,
            )

            res = agy_capsule.check_status(capsule, base_dir_override=tmp_path)
            self.assertEqual(res["status"], "dependencies_match")
            self.assertEqual(res["exit_code"], 0)
            self.assertEqual(len(res["changed_paths"]), 0)

    def test_status_file_modified(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            f1 = tmp_path / "config.json"
            f1.write_text('{"v": 1}', encoding="utf-8")

            capsule = agy_capsule.seal_capsule(
                claim="Config file",
                files=[str(f1)],
                base_dir=tmp_path,
            )

            # Modify file
            f1.write_text('{"v": 2}', encoding="utf-8")

            res = agy_capsule.check_status(capsule, base_dir_override=tmp_path)
            self.assertEqual(res["status"], "stale")
            self.assertEqual(res["exit_code"], 1)
            self.assertTrue(any("config.json" in p for p in res["changed_paths"]))

    def test_status_tree_directory_changed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            tree_dir = tmp_path / "src"
            tree_dir.mkdir()
            (tree_dir / "main.py").write_text("print(1)", encoding="utf-8")

            capsule = agy_capsule.seal_capsule(
                claim="Src tree",
                trees=[str(tree_dir)],
                base_dir=tmp_path,
            )

            # Add a new file inside the sealed tree
            (tree_dir / "extra.py").write_text("print(2)", encoding="utf-8")

            res = agy_capsule.check_status(capsule, base_dir_override=tmp_path)
            self.assertEqual(res["status"], "stale")
            self.assertEqual(res["exit_code"], 1)

    def test_status_expired_ttl(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            f = tmp_path / "file.txt"
            f.write_text("constant", encoding="utf-8")

            # Tiny TTL of 0.05s
            capsule = agy_capsule.seal_capsule(
                claim="Expiring capsule",
                files=[str(f)],
                ttl_seconds=0.05,
                base_dir=tmp_path,
            )

            time.sleep(0.08)
            res = agy_capsule.check_status(capsule, base_dir_override=tmp_path)
            self.assertEqual(res["status"], "stale")
            self.assertIn("expired", res["reason"].lower())

    def test_status_live_kind_always_refresh_required(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            f = tmp_path / "data.csv"
            f.write_text("col1,col2\n1,2\n", encoding="utf-8")

            capsule = agy_capsule.seal_capsule(
                claim="Live API dataset",
                files=[str(f)],
                kind="live",
                base_dir=tmp_path,
            )

            # Even if file is unchanged, kind='live' requires refresh
            res = agy_capsule.check_status(capsule, base_dir_override=tmp_path)
            self.assertEqual(res["status"], "refresh_required")
            self.assertEqual(res["exit_code"], 1)

    def test_capsule_cli(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            f = tmp_path / "hello.txt"
            f.write_text("hello", encoding="utf-8")
            cap_file = tmp_path / "capsule.json"

            # Seal CLI
            seal_cmd = [
                sys.executable,
                str(SCRIPTS_DIR / "agy_capsule.py"),
                "seal",
                "--claim",
                "CLI seal test",
                "--file",
                str(f),
                "--kind",
                "static",
                "--out",
                str(cap_file),
            ]
            res_seal = subprocess.run(seal_cmd, capture_output=True, text=True)
            self.assertEqual(res_seal.returncode, 0)
            self.assertTrue(cap_file.exists())

            # Status CLI match -> exit code 0
            status_cmd = [
                sys.executable,
                str(SCRIPTS_DIR / "agy_capsule.py"),
                "status",
                "--capsule",
                str(cap_file),
                "--json",
            ]
            res_status = subprocess.run(status_cmd, capture_output=True, text=True)
            self.assertEqual(res_status.returncode, 0)
            stat_json = json.loads(res_status.stdout)
            self.assertEqual(stat_json["status"], "dependencies_match")


class TestAgyLedger(unittest.TestCase):
    """Test prompt-free telemetry recording and variant cost accounting."""

    def test_record_telemetry_schema(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger_file = Path(tmp_dir) / "test_ledger.jsonl"

            rec = agy_ledger.record_telemetry(
                task_id="task-100",
                variant="token-guard",
                model="gemini-1.5-pro",
                effort="high",
                status="ship",
                accepted=True,
                input_tokens=3000,
                cached_input_tokens=45000,
                output_tokens=1500,
                reasoning_output_tokens=400,
                retries=0,
                elapsed_seconds=5.25,
                ledger_path=ledger_file,
            )

            self.assertTrue(ledger_file.exists())
            lines = ledger_file.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)

            entry = json.loads(lines[0])
            self.assertEqual(entry["task_id"], "task-100")
            self.assertEqual(entry["variant"], "token-guard")
            self.assertEqual(entry["model"], "gemini-1.5-pro")
            self.assertTrue(entry["accepted"])
            self.assertEqual(entry["input_tokens"], 3000)
            self.assertEqual(entry["cached_input_tokens"], 45000)
            self.assertEqual(entry["output_tokens"], 1500)
            self.assertEqual(entry["reasoning_output_tokens"], 400)
            self.assertEqual(entry["retries"], 0)
            self.assertEqual(entry["elapsed_seconds"], 5.25)
            self.assertIn("timestamp", entry)

            # Security requirement: verify prompt text is NOT persisted
            self.assertNotIn("prompt", entry)
            self.assertNotIn("messages", entry)
            self.assertNotIn("system_prompt", entry)

    def test_summary_aggregation_and_cost_per_accepted_outcome(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger_file = Path(tmp_dir) / "summary_test.jsonl"

            # Variant 1: Baseline (Uncached, higher tokens, 1 failure, 1 success)
            # Baseline task 1: Failed / fix-first (accepted=False)
            agy_ledger.record_telemetry(
                task_id="base-1",
                variant="baseline",
                model="gemini-1.5-pro",
                effort="medium",
                status="fix-first",
                accepted=False,
                input_tokens=40000,
                cached_input_tokens=0,
                output_tokens=2000,
                reasoning_output_tokens=0,
                retries=2,
                elapsed_seconds=10.0,
                ledger_path=ledger_file,
            )
            # Baseline task 2: Accepted (accepted=True)
            agy_ledger.record_telemetry(
                task_id="base-2",
                variant="baseline",
                model="gemini-1.5-pro",
                effort="medium",
                status="ship",
                accepted=True,
                input_tokens=60000,
                cached_input_tokens=0,
                output_tokens=3000,
                reasoning_output_tokens=0,
                retries=1,
                elapsed_seconds=15.0,
                ledger_path=ledger_file,
            )

            # Variant 2: Token-Guard (Warm cache, Progressive AST, 2 successes)
            # Task 1: Accepted
            agy_ledger.record_telemetry(
                task_id="guard-1",
                variant="token-guard",
                model="gemini-1.5-pro",
                effort="medium",
                status="ship",
                accepted=True,
                input_tokens=4000,
                cached_input_tokens=50000,
                output_tokens=1000,
                reasoning_output_tokens=200,
                retries=0,
                elapsed_seconds=3.5,
                ledger_path=ledger_file,
            )
            # Task 2: Accepted
            agy_ledger.record_telemetry(
                task_id="guard-2",
                variant="token-guard",
                model="gemini-1.5-pro",
                effort="medium",
                status="ship",
                accepted=True,
                input_tokens=5000,
                cached_input_tokens=50000,
                output_tokens=1200,
                reasoning_output_tokens=250,
                retries=0,
                elapsed_seconds=4.0,
                ledger_path=ledger_file,
            )

            records = agy_ledger.load_ledger(ledger_file)
            summary = agy_ledger.compute_summary(records)

            self.assertIn("baseline", summary["variants"])
            self.assertIn("token-guard", summary["variants"])

            base_res = summary["variants"]["baseline"]
            guard_res = summary["variants"]["token-guard"]

            # Acceptance rates
            self.assertEqual(base_res["total_tasks"], 2)
            self.assertEqual(base_res["accepted_tasks"], 1)
            self.assertAlmostEqual(base_res["acceptance_rate"], 0.5)

            self.assertEqual(guard_res["total_tasks"], 2)
            self.assertEqual(guard_res["accepted_tasks"], 2)
            self.assertAlmostEqual(guard_res["acceptance_rate"], 1.0)

            # Cache hit rates
            self.assertEqual(base_res["cache_hit_rate"], 0.0)
            self.assertGreater(guard_res["cache_hit_rate"], 0.90)  # > 90% cache hit!

            # Cost per accepted outcome:
            # Baseline had 2 tasks worth of cost divided by 1 accepted task
            # Token-Guard had 2 tasks worth of cost divided by 2 accepted tasks
            self.assertIsNotNone(base_res["cost_per_accepted_outcome"])
            self.assertIsNotNone(guard_res["cost_per_accepted_outcome"])
            self.assertLess(
                guard_res["cost_per_accepted_outcome"],
                base_res["cost_per_accepted_outcome"],
            )

    def test_summary_no_accepted_outcomes(self):
        records = [
            {
                "task_id": "fail-1",
                "variant": "experimental",
                "model": "gemini-1.5-flash",
                "accepted": False,
                "input_tokens": 1000,
                "cached_input_tokens": 0,
                "output_tokens": 200,
            }
        ]
        summary = agy_ledger.compute_summary(records)
        exp = summary["variants"]["experimental"]
        self.assertEqual(exp["accepted_tasks"], 0)
        self.assertIsNone(exp["cost_per_accepted_outcome"])

    def test_ledger_cli(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger_path = Path(tmp_dir) / "cli_ledger.jsonl"

            # CLI record
            rec_cmd = [
                sys.executable,
                str(SCRIPTS_DIR / "agy_ledger.py"),
                "record",
                "--task-id",
                "cli-001",
                "--variant",
                "cli-test",
                "--model",
                "gemini-1.5-flash",
                "--effort",
                "low",
                "--status",
                "ship",
                "--accepted",
                "true",
                "--input-tokens",
                "500",
                "--cached-input-tokens",
                "2000",
                "--output-tokens",
                "150",
                "--reasoning-output-tokens",
                "50",
                "--retries",
                "0",
                "--elapsed-seconds",
                "1.2",
                "--ledger",
                str(ledger_path),
            ]
            res_rec = subprocess.run(rec_cmd, capture_output=True, text=True)
            self.assertEqual(res_rec.returncode, 0)
            self.assertTrue(ledger_path.exists())

            # CLI summary JSON
            sum_cmd = [
                sys.executable,
                str(SCRIPTS_DIR / "agy_ledger.py"),
                "summary",
                "--ledger",
                str(ledger_path),
                "--json",
            ]
            res_sum = subprocess.run(sum_cmd, capture_output=True, text=True)
            self.assertEqual(res_sum.returncode, 0)
            sum_data = json.loads(res_sum.stdout)
            self.assertIn("cli-test", sum_data["variants"])
            self.assertEqual(sum_data["variants"]["cli-test"]["total_tasks"], 1)


class TestAgyHandoff(unittest.TestCase):
    """Test deterministic local threshold routing and circuit breaker."""

    def test_prepare_handoff_full_route(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "small.txt"
            file_path.write_text("Small content under full limit.", encoding="utf-8")
            res = agy_handoff.prepare_handoff(
                source_path=str(file_path),
                full_limit=1000,
                pack_limit=200,
            )
            self.assertEqual(res["route"], "full")
            self.assertEqual(res["content"], "Small content under full limit.")
            self.assertIn("under full threshold", res["reason"])

    def test_prepare_handoff_pack_route(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "large.txt"
            # 50 lines of data
            lines = [f"Line {i}: test information payload" for i in range(1, 60)]
            file_path.write_text("\n".join(lines), encoding="utf-8")
            res = agy_handoff.prepare_handoff(
                source_path=str(file_path),
                full_limit=200,
                pack_limit=300,
            )
            self.assertEqual(res["route"], "pack")
            self.assertIn("pack", res)
            self.assertTrue(res["pack"]["clipped"])

    def test_circuit_breaker_tripped(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "large.txt"
            file_path.write_text("A" * 500, encoding="utf-8")
            sha = agy_handoff.compute_sha256(file_path.read_bytes())

            with self.assertRaises(agy_handoff.CircuitBreakerError) as ctx:
                agy_handoff.prepare_handoff(
                    source_path=str(file_path),
                    full_limit=100,
                    pack_limit=50,
                    recovery_attempts=2,
                    previous_sha256=sha,
                )
            self.assertIn("Circuit breaker tripped: 2 consecutive recovery attempts", str(ctx.exception))

    def test_handoff_cli(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "test.txt"
            file_path.write_text("Hello from handoff CLI", encoding="utf-8")
            cmd = [
                sys.executable,
                str(SCRIPTS_DIR / "agy_handoff.py"),
                "prepare",
                "--source",
                str(file_path),
                "--full-limit",
                "500",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout)
            self.assertEqual(data["route"], "full")


class TestAgyPackContains(unittest.TestCase):
    """Test pack with --contains and --context parameters."""

    def test_pack_with_contains_and_context(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "build.log"
            lines = [f"Step {i}: normal background worker ping" for i in range(1, 100)]
            lines[49] = "CRITICAL_ERROR: specific failure signature in payment worker"
            file_path.write_text("\n".join(lines), encoding="utf-8")

            packed = agy_pack.pack_file(
                source_path=str(file_path),
                root_dir=tmp_dir,
                max_chars=800,
                contains="CRITICAL_ERROR",
                context=2,
            )

            self.assertTrue(packed["clipped"])
            self.assertEqual(packed["metadata"]["contains"], "CRITICAL_ERROR")
            self.assertEqual(packed["metadata"]["context"], 2)
            self.assertEqual(packed["metadata"]["contains_matches_count"], 1)

            # Check that line 50 (index 50) and its context lines (48, 49, 51, 52) are in lines
            found_lines = {item["line"] for item in packed["lines"]}
            self.assertIn(50, found_lines)
            self.assertIn(49, found_lines)
            self.assertIn(51, found_lines)

    def test_pack_with_contains_no_match(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "build.log"
            lines = [f"Step {i}: ping" for i in range(1, 80)]
            file_path.write_text("\n".join(lines), encoding="utf-8")

            packed = agy_pack.pack_file(
                source_path=str(file_path),
                root_dir=tmp_dir,
                max_chars=600,
                contains="NON_EXISTENT_SUBSTRING",
                context=2,
            )
            self.assertEqual(packed["metadata"]["contains_matches_count"], 0)


class TestNoiseSanitizer(unittest.TestCase):
    """Test noise_sanitizer features: never_worse, strip_ansi, pipeline safety, clean states."""

    def test_never_worse_guard(self):
        raw = "short line"
        long_filtered = "much longer text that would cost more tokens than raw"
        self.assertEqual(noise_sanitizer.never_worse(raw, long_filtered), raw)
        self.assertEqual(noise_sanitizer.never_worse(long_filtered, raw), raw)

    def test_strip_ansi(self):
        raw_ansi = "\x1b[32mSUCCESS\x1b[0m: Test passed in \x1b[1m0.45s\x1b[0m"
        clean = noise_sanitizer.strip_ansi(raw_ansi)
        self.assertEqual(clean, "SUCCESS: Test passed in 0.45s")

    def test_pipeline_safety_does_not_alter(self):
        cmd = "find src -name '*.py' | xargs wc -l"
        decision = noise_sanitizer.process_command(cmd, "")
        self.assertEqual(decision["decision"], "allow")
        self.assertNotIn("overwrite", decision)
        self.assertIn("Machine pipeline detected", decision["reason"])

    def test_clean_state_short_circuit(self):
        git_clean = "On branch main\nNothing to commit, working tree clean\n"
        self.assertEqual(noise_sanitizer.sanitize_output(git_clean, "git status"), "ok (working tree clean)")

        npm_clean = "up to date, audited 45 packages in 850ms\nfound 0 vulnerabilities\n"
        self.assertEqual(noise_sanitizer.sanitize_output(npm_clean, "npm install"), "ok (up to date)")


if __name__ == "__main__":
    unittest.main(verbosity=2)

