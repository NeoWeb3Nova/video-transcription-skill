#!/usr/bin/env python3
"""Stdlib self-check for the identity-reference render gate."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from run_pipeline import require_identity_gate

with tempfile.TemporaryDirectory() as raw:
    project = Path(raw)
    (project / "source").mkdir()
    (project / "work").mkdir()
    (project / "source/identity_reference.jpg").write_bytes(b"reference")
    (project / "work/identity_gate.json").write_text(json.dumps({
        "status": "pending",
        "reference": "source/identity_reference.jpg",
        "assets": ["assets/background.png", "assets/opening.png", "assets/cover.png"],
    }))
    try:
        require_identity_gate(project, auto=True)
    except SystemExit:
        pass
    else:
        raise AssertionError("pending identity gate was accepted")
    data = json.loads((project / "work/identity_gate.json").read_text())
    data["status"] = "auto-approved"
    (project / "work/identity_gate.json").write_text(json.dumps(data))
    require_identity_gate(project, auto=True)

print("identity gate self-check ok")
