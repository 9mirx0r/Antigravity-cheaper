#!/usr/bin/env python3
"""Token Guard Forwarder (delegating to canonical antigravity_cheaper.agy_ledger)."""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import antigravity_cheaper.agy_ledger as _canonical

# Re-export all public attributes
for _k, _v in _canonical.__dict__.items():
    if not _k.startswith("__") or _k in ("__version__", "__all__"):
        globals()[_k] = _v

if __name__ == "__main__":
    if hasattr(_canonical, "main"):
        sys.exit(_canonical.main())
