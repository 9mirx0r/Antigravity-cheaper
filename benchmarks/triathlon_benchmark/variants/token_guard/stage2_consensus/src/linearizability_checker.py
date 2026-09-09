from __future__ import annotations
from typing import Any, Dict, List


class LinearizabilityChecker:
    """Verifies sequential consistency and linearizability of recorded operations."""

    def __init__(self):
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
        """Verifies that all observed reads are consistent with preceding writes."""
        # Group operations by key
        keys = set(op["key"] for op in self.history)

        for key in keys:
            key_ops = [op for op in self.history if op["key"] == key]
            writes = [op for op in key_ops if op["op_type"] in ("WRITE", "SET", "PUT")]
            reads = [op for op in key_ops if op["op_type"] in ("READ", "GET")]

            for read in reads:
                read_val = read["val"]
                read_start = read["start_time"]
                read_end = read["end_time"]

                # Find matching writes that started before the read completed
                matching_writes = [
                    w for w in writes
                    if w["val"] == read_val and w["start_time"] <= read_end
                ]

                if not matching_writes:
                    # Read observed a value that was never written or written in the future
                    return False

                # Verify that not all matching writes were strictly superseded before read started
                valid_match_found = False
                for mw in matching_writes:
                    # Check if there is another write strictly between mw and this read
                    superseded = False
                    for other_w in writes:
                        if other_w is not mw and other_w["val"] != read_val:
                            if mw["end_time"] <= other_w["start_time"] and other_w["end_time"] <= read_start:
                                superseded = True
                                break
                    if not superseded:
                        valid_match_found = True
                        break

                if not valid_match_found:
                    return False

        return True
