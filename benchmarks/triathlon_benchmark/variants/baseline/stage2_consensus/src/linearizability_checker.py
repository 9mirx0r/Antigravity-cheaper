"""Linearizability and Sequential Consistency Checker."""

from __future__ import annotations
from typing import Any, Dict, List


class LinearizabilityChecker:
    """Verifies that an execution history adheres to sequential consistency."""

    def __init__(self) -> None:
        self.history: List[Dict[str, Any]] = []

    def record_op(
        self,
        client: str,
        op_type: str,
        key: str,
        val: Any,
        start_time: float,
        end_time: float,
    ) -> None:
        self.history.append({
            "client": client,
            "op_type": op_type.upper(),
            "key": key,
            "val": val,
            "start_time": start_time,
            "end_time": end_time,
        })

    def verify_sequential_consistency(self) -> bool:
        """Verifies that all observed reads match valid serialization order of writes."""
        # Group operations per key
        key_ops: Dict[str, List[Dict[str, Any]]] = {}
        for op in self.history:
            key_ops.setdefault(op["key"], []).append(op)

        for key, ops in key_ops.items():
            # Order operations by real-time precedence (end_time, then start_time)
            sorted_ops = sorted(ops, key=lambda x: (x["end_time"], x["start_time"]))

            last_written_val = None
            has_written = False

            for op in sorted_ops:
                if op["op_type"] == "WRITE":
                    last_written_val = op["val"]
                    has_written = True
                elif op["op_type"] == "READ":
                    if has_written and op["val"] != last_written_val:
                        return False

        return True
