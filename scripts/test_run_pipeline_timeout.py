#!/usr/bin/env python3
"""Small self-check for the pipeline step timeout guard."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_pipeline  # noqa: E402


class FakeProcess:
    pid = 4242

    def __init__(self) -> None:
        self.wait_calls: list[float] = []

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)  # type: ignore[arg-type]
        if len(self.wait_calls) == 1:
            raise subprocess.TimeoutExpired("test", timeout if timeout is not None else 0)
        return 0


process = FakeProcess()
kills: list[tuple[int, signal.Signals]] = []
original_popen = run_pipeline.subprocess.Popen
original_killpg = os.killpg
run_pipeline.subprocess.Popen = lambda *args, **kwargs: process  # type: ignore[assignment]
os.killpg = lambda pid, sig: kills.append((pid, sig))  # type: ignore[assignment]
try:
    try:
        run_pipeline.run(Path("."), "caption_qa")
    except SystemExit as exc:
        assert "15 minutes" in str(exc)
    else:
        raise AssertionError("timeout did not stop the step")
finally:
    run_pipeline.subprocess.Popen = original_popen
    os.killpg = original_killpg

assert process.wait_calls == [900, 10]
assert kills == [(4242, signal.SIGTERM)]
print("timeout guard ok")
