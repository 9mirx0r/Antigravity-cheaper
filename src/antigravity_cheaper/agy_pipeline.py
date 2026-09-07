#!/usr/bin/env python3
"""Dual-Model Cognitive Scaffolding Pipeline (agy_pipeline.py).

Implements an autonomous 3-stage agentic workflow:
  Stage 1: ARCHITECT (Planner & Disambiguator)
  Stage 2: IMPLEMENTER (Surgical TDD Coder)
  Stage 3: GATEKEEPER CRITIC (Read-Only Evaluator)

Eliminates reasoning token loops, resolves ambiguity proactively,
and guarantees quality through clean-context gatekeeping.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Pipeline Stage Constants
STAGE_ARCHITECT = "ARCHITECT"
STAGE_IMPLEMENTER = "IMPLEMENTER"
STAGE_CRITIC = "CRITIC"

# Gatekeeper Verdicts
VERDICT_SHIP = "SHIP"
VERDICT_FIX_FIRST = "FIX_FIRST"
VERDICT_RETHINK = "RETHINK"


class WorkerManifest:
    """Represents a partitioned subagent worker task manifest."""

    def __init__(
        self,
        worker_id: str,
        role: str,
        model_tier: str,
        contracts: List[str],
        target_files: List[str],
        context_files: Optional[List[str]] = None,
    ):
        self.worker_id = worker_id
        self.role = role
        self.model_tier = model_tier  # 'flash', 'flash_lite', 'pro'
        self.contracts = contracts
        self.target_files = target_files
        self.context_files = context_files or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "role": self.role,
            "model_tier": self.model_tier,
            "contracts": self.contracts,
            "target_files": self.target_files,
            "context_files": self.context_files,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkerManifest:
        return cls(
            worker_id=data["worker_id"],
            role=data["role"],
            model_tier=data.get("model_tier", "flash"),
            contracts=data.get("contracts", []),
            target_files=data.get("target_files", []),
            context_files=data.get("context_files", []),
        )


class PipelineState:
    """Encapsulates the immutable state machine of the cognitive pipeline."""

    def __init__(self, task_id: str, objective: str, workspace_root: str):
        self.task_id = task_id
        self.objective = objective
        self.workspace_root = str(Path(workspace_root).resolve()).replace("\\", "/")
        self.stage = STAGE_ARCHITECT
        self.iteration = 1
        self.max_iterations = 3
        self.spec: Optional[Dict[str, Any]] = None
        self.swarm_manifests: List[Dict[str, Any]] = []
        self.implementation_receipt: Optional[Dict[str, Any]] = None
        self.critique_history: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "workspace_root": self.workspace_root,
            "stage": self.stage,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "spec": self.spec,
            "swarm_manifests": self.swarm_manifests,
            "implementation_receipt": self.implementation_receipt,
            "critique_history": self.critique_history,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PipelineState:
        obj = cls(
            task_id=data["task_id"],
            objective=data["objective"],
            workspace_root=data["workspace_root"],
        )
        obj.stage = data.get("stage", STAGE_ARCHITECT)
        obj.iteration = data.get("iteration", 1)
        obj.max_iterations = data.get("max_iterations", 3)
        obj.spec = data.get("spec")
        obj.swarm_manifests = data.get("swarm_manifests", [])
        obj.implementation_receipt = data.get("implementation_receipt")
        obj.critique_history = data.get("critique_history", [])
        return obj

    def save(self, file_path: Path):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, file_path: Path) -> PipelineState:
        return cls.from_dict(json.loads(file_path.read_text(encoding="utf-8")))


class CognitivePipeline:
    """Orchestrates stage handoffs and enforces the Gatekeeper protocol."""

    def __init__(self, state_file: Path):
        self.state_file = Path(state_file)
        if self.state_file.exists():
            self.state = PipelineState.load(self.state_file)
        else:
            raise FileNotFoundError(f"Pipeline state not found: {state_file}")

    @classmethod
    def initialize(
        cls, task_id: str, objective: str, workspace_root: str, state_file: Path
    ) -> PipelineState:
        """Create a new pipeline state."""
        state = PipelineState(task_id, objective, workspace_root)
        state.save(state_file)
        return state

    def record_architect_spec(
        self,
        contracts: List[str],
        surgical_files: List[str],
        resolved_ambiguities: List[str],
    ) -> Dict[str, Any]:
        """Stage 1: Architect records immutable specification and advances to Implementer."""
        if self.state.stage != STAGE_ARCHITECT:
            raise ValueError(f"Cannot record spec in stage '{self.state.stage}'")

        self.state.spec = {
            "contracts": contracts,
            "surgical_files": surgical_files,
            "resolved_ambiguities": resolved_ambiguities,
        }
        self.state.stage = STAGE_IMPLEMENTER
        self.state.save(self.state_file)
        return self.state.to_dict()

    def record_implementation_receipt(
        self,
        touched_files: List[str],
        tests_passed: bool,
        test_summary: str,
        git_diff_stat: str,
    ) -> Dict[str, Any]:
        """Stage 2: Implementer records compact receipt and advances to Critic."""
        if self.state.stage != STAGE_IMPLEMENTER:
            raise ValueError(f"Cannot record receipt in stage '{self.state.stage}'")

        self.state.implementation_receipt = {
            "touched_files": touched_files,
            "tests_passed": tests_passed,
            "test_summary": test_summary,
            "git_diff_stat": git_diff_stat,
        }
        self.state.stage = STAGE_CRITIC
        self.state.save(self.state_file)
        return self.state.to_dict()

    def evaluate_verdict(
        self, verdict: str, feedback: str
    ) -> Tuple[str, str]:
        """Stage 3: Critic evaluates implementation with tri-state verdict."""
        if self.state.stage != STAGE_CRITIC:
            raise ValueError(f"Cannot evaluate verdict in stage '{self.state.stage}'")

        critique_entry = {
            "iteration": self.state.iteration,
            "verdict": verdict,
            "feedback": feedback,
        }
        self.state.critique_history.append(critique_entry)

        if verdict == VERDICT_SHIP:
            self.state.stage = "COMPLETED"
            self.state.save(self.state_file)
            distill_msg = ""
            try:
                mem_res = self.distill_receipt_to_memory()
                distill_msg = f" (Distilled to memory: [{mem_res.get('category', 'architecture')}] {mem_res.get('topic_key')} rev {mem_res.get('revision', 1)})"
            except Exception as e:
                distill_msg = f" (Memory distillation note: {e})"
            return "SUCCESS", f"Task {self.state.task_id} approved for shipment!{distill_msg}"

        elif verdict == VERDICT_FIX_FIRST:
            if self.state.iteration >= self.state.max_iterations:
                self.state.stage = "FAILED"
                self.state.save(self.state_file)
                return (
                    "CIRCUIT_BREAKER",
                    f"Max retry iterations ({self.state.max_iterations}) exceeded.",
                )
            # Cycle back to Implementer with feedback
            self.state.iteration += 1
            self.state.stage = STAGE_IMPLEMENTER
            self.state.save(self.state_file)
            return "RETRY_IMPLEMENTER", f"Feedback routed to Implementer: {feedback}"

        elif verdict == VERDICT_RETHINK:
            # Cycle back to Architect
            self.state.iteration += 1
            self.state.stage = STAGE_ARCHITECT
            self.state.save(self.state_file)
            return "RETHINK_SPEC", f"Architect must redesign spec: {feedback}"

        raise ValueError(f"Unknown verdict: {verdict}")

    def distill_receipt_to_memory(self, db_path: Optional[str] = None) -> Dict[str, Any]:
        """Automatically extract and persist verified task invariants to agy_memory."""
        try:
            from agy_memory import MemoryEngine
        except ImportError:
            # Fallback when running relative
            from .agy_memory import MemoryEngine

        # Use root .local/memory.db or default
        target_db = db_path or ".local/memory.db"
        engine = MemoryEngine(target_db)
        try:
            project_name = Path(self.state.workspace_root).name or "default"
            raw_key = self.state.task_id.replace("_", "-").lower()
            topic_key = f"architecture/{raw_key}"

            receipt = self.state.implementation_receipt or {}
            touched = ", ".join(receipt.get("touched_files", []))
            test_summary = receipt.get("test_summary", "Tests verified")
            contracts = ", ".join(self.state.spec.get("contracts", [])) if self.state.spec else ""

            content_lines = [
                f"Objective: {self.state.objective}",
                f"Verified Contracts: {contracts}",
                f"Surgical Files: {touched}",
                f"Verification: {test_summary}",
            ]
            if self.state.critique_history:
                last_critique = self.state.critique_history[-1].get("feedback", "")
                if last_critique:
                    content_lines.append(f"Critic Assessment: {last_critique}")

            content = "\n".join(content_lines)
            res = engine.save(
                topic_key=topic_key,
                title=self.state.objective[:80],
                content=content,
                category="architecture",
                project=project_name,
            )
            return res
        finally:
            engine.close()


    def decompose_spec(
        self,
        num_workers: Optional[int] = None,
        model_tier: str = "flash",
        out_dir: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Partitions Architect spec into contract-isolated parallel worker manifests."""
        if not self.state.spec:
            raise ValueError("Cannot decompose: Architect specification not recorded.")

        contracts = self.state.spec.get("contracts", [])
        surgical_files = self.state.spec.get("surgical_files", [])

        if not surgical_files:
            raise ValueError("No surgical files specified in architect spec.")

        n_workers = num_workers or min(len(surgical_files), 3)
        n_workers = max(1, n_workers)

        file_chunks: List[List[str]] = [[] for _ in range(n_workers)]
        for idx, f in enumerate(surgical_files):
            file_chunks[idx % n_workers].append(f)

        manifests: List[Dict[str, Any]] = []
        for i, chunk in enumerate(file_chunks):
            if not chunk:
                continue
            worker_id = f"worker_{i+1}"
            chunk_basenames = [Path(f).stem.lower() for f in chunk]
            matched_contracts = [
                c for c in contracts
                if any(base in c.lower() for base in chunk_basenames)
            ]
            if not matched_contracts:
                matched_contracts = contracts[i::n_workers] or contracts

            role = f"Worker {i+1} ({', '.join([Path(f).name for f in chunk])})"

            manifest = WorkerManifest(
                worker_id=worker_id,
                role=role,
                model_tier=model_tier,
                contracts=matched_contracts,
                target_files=chunk,
                context_files=[f for f in surgical_files if f not in chunk],
            )
            manifests.append(manifest.to_dict())

        self.state.swarm_manifests = manifests
        self.state.save(self.state_file)

        if out_dir:
            out_p = Path(out_dir)
            out_p.mkdir(parents=True, exist_ok=True)
            for m in manifests:
                mf = out_p / f"{m['worker_id']}_manifest.json"
                mf.write_text(json.dumps(m, indent=2), encoding="utf-8")

        return manifests


def main():
    parser = argparse.ArgumentParser(description="Antigravity Cognitive Pipeline Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: init
    init_p = subparsers.add_parser("init", help="Initialize pipeline state")
    init_p.add_argument("--task-id", required=True, help="Task identifier")
    init_p.add_argument("--objective", required=True, help="Task objective")
    init_p.add_argument("--workspace", default=".", help="Workspace root directory")
    init_p.add_argument("--state-file", required=True, help="Path to state.json")

    # Command: spec (Architect)
    spec_p = subparsers.add_parser("spec", help="Record Architect specification")
    spec_p.add_argument("--state-file", required=True, help="Path to state.json")
    spec_p.add_argument("--contract", action="append", required=True, help="Acceptance test contract")
    spec_p.add_argument("--file", action="append", required=True, help="Surgical target file")
    spec_p.add_argument("--resolved", action="append", default=[], help="Resolved ambiguity")

    # Command: decompose (Swarm)
    dec_p = subparsers.add_parser("decompose", help="Decompose Architect spec into parallel worker manifests")
    dec_p.add_argument("--state-file", required=True, help="Path to state.json")
    dec_p.add_argument("--num-workers", type=int, default=None, help="Number of workers (default: auto)")
    dec_p.add_argument("--model-tier", default="flash", choices=["flash", "flash_lite", "pro"], help="Worker model tier")
    dec_p.add_argument("--out-dir", default=None, help="Optional directory to write individual worker manifests")

    # Command: receipt (Implementer)
    rec_p = subparsers.add_parser("receipt", help="Record Implementer receipt")
    rec_p.add_argument("--state-file", required=True, help="Path to state.json")
    rec_p.add_argument("--file", action="append", required=True, help="Touched file")
    rec_p.add_argument("--tests-passed", type=str, choices=["true", "false"], required=True)
    rec_p.add_argument("--test-summary", required=True, help="Test summary string")
    rec_p.add_argument("--diff-stat", default="", help="Git diff stat")

    # Command: review (Critic)
    rev_p = subparsers.add_parser("review", help="Evaluate Critic verdict")
    rev_p.add_argument("--state-file", required=True, help="Path to state.json")
    rev_p.add_argument(
        "--verdict", choices=[VERDICT_SHIP, VERDICT_FIX_FIRST, VERDICT_RETHINK], required=True
    )
    rev_p.add_argument("--feedback", required=True, help="Review feedback")

    # Command: status
    status_p = subparsers.add_parser("status", help="Display current pipeline status")
    status_p.add_argument("--state-file", required=True, help="Path to state.json")

    args = parser.parse_args()

    if args.command == "init":
        state = CognitivePipeline.initialize(
            task_id=args.task_id,
            objective=args.objective,
            workspace_root=args.workspace,
            state_file=Path(args.state_file),
        )
        print(f"Pipeline initialized: Stage = {state.stage} (Task: {state.task_id})")

    elif args.command == "spec":
        pipe = CognitivePipeline(Path(args.state_file))
        res = pipe.record_architect_spec(
            contracts=args.contract,
            surgical_files=args.file,
            resolved_ambiguities=args.resolved,
        )
        print(f"Architect spec recorded. Advanced to: {res['stage']}")

    elif args.command == "decompose":
        pipe = CognitivePipeline(Path(args.state_file))
        manifests = pipe.decompose_spec(
            num_workers=args.num_workers,
            model_tier=args.model_tier,
            out_dir=args.out_dir,
        )
        print(f"Spec decomposed into {len(manifests)} parallel worker manifests:")
        for m in manifests:
            print(f"  - [{m['worker_id']}] {m['role']} (Tier: {m['model_tier']})")
            print(f"    Target files: {', '.join(m['target_files'])}")
            print(f"    Contracts: {', '.join(m['contracts'])}")

    elif args.command == "receipt":
        pipe = CognitivePipeline(Path(args.state_file))
        passed = args.tests_passed.lower() == "true"
        res = pipe.record_implementation_receipt(
            touched_files=args.file,
            tests_passed=passed,
            test_summary=args.test_summary,
            git_diff_stat=args.diff_stat,
        )
        print(f"Implementation receipt recorded. Advanced to: {res['stage']}")

    elif args.command == "review":
        pipe = CognitivePipeline(Path(args.state_file))
        status, msg = pipe.evaluate_verdict(args.verdict, args.feedback)
        print(f"[{status}] {msg}")

    elif args.command == "status":
        pipe = CognitivePipeline(Path(args.state_file))
        print(json.dumps(pipe.state.to_dict(), indent=2))


if __name__ == "__main__":
    main()
