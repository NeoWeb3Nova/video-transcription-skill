#!/usr/bin/env python3
"""Stdlib self-check for the manual/auto approval boundary."""
from __future__ import annotations

import tempfile
from pathlib import Path

from run_pipeline import gate

with tempfile.TemporaryDirectory() as raw:
    project = Path(raw)
    for name in ("assets/background.png", "assets/opening.png", "assets/cover.png",
                 "scripts/en.md", "scripts/zh.md", "work/paras.json",
                 "audio/master.wav", "work/hooks.json", "work/cover_typography_mode.txt"):
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("model-typeset" if path.name == "cover_typography_mode.txt" else "x")
    (project / "work/cover_approval.txt").write_text("auto-approved")
    gate(project, "sample", auto=True)
    try:
        gate(project, "sample", auto=False)
    except SystemExit:
        pass
    else:
        raise AssertionError("manual mode accepted auto-approved cover")
print("auto approval self-check ok")
