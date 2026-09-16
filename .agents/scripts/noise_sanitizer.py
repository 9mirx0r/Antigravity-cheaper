#!/usr/bin/env python3
"""Forwarder shim for noise_sanitizer delegating to canonical antigravity_cheaper package."""
from antigravity_cheaper.noise_sanitizer import *
import antigravity_cheaper.noise_sanitizer as _canon

__all__ = [a for a in dir(_canon) if not a.startswith("__")]

if __name__ == "__main__":
    import sys
    sys.exit(_canon.main())
