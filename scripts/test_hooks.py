#!/usr/bin/env python3
"""Small stdlib self-check for the default hook contract."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from produce import select_hook_index, validate_events  # noqa: E402

assert select_hook_index(0) == 0
assert select_hook_index(59) == 3
valid = [{"offset": 0, "duration": 10_000_000, "text": "hook"}]
assert validate_events(valid, 1.0)[0]["duration"] == 10_000_000
for bad in (
    [{"offset": math.nan, "duration": 1, "text": "hook"}],
    [{"offset": 0, "duration": math.inf, "text": "hook"}],
    [{"offset": True, "duration": 1, "text": "hook"}],
    [{"offset": -1, "duration": 1, "text": "hook"}],
):
    try:
        validate_events(bad, 1.0)
    except ValueError:
        pass
    else:
        raise AssertionError(f"malformed event accepted: {bad}")
print("hook self-check ok")
