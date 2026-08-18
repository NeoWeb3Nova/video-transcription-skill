#!/usr/bin/env python3
"""Portable gated runner for the repository's bilingual render pipeline."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = ("manifest", "tts", "timeline", "audio", "sample", "full", "spotcheck", "caption_qa", "preflight")


def require(project: Path, *paths: str) -> None:
    missing = [str(project / path) for path in paths if not (project / path).exists()]
    if missing:
        raise SystemExit("blocked; missing: " + ", ".join(missing))


def run(project: Path, step: str) -> None:
    env = os.environ.copy()
    env["PROJECT_SLUG"] = project.name
    subprocess.run([sys.executable, str(ROOT / "scripts/produce.py"), step], cwd=ROOT, env=env, check=True)


def gate(project: Path, step: str) -> None:
    if step in {"manifest", "tts", "timeline", "audio"}:
        require(project, "scripts/en.md", "scripts/zh.md")
    if step in {"sample", "full"}:
        require(project, "assets/background.png", "assets/opening.png", "scripts/en.md", "scripts/zh.md", "work/paras.json", "audio/master.wav")
    if step == "sample":
        require(project, "work/sample_approval.txt")
        if (project / "work/sample_approval.txt").read_text().strip() == "approved":
            raise SystemExit("sample already approved; run full when ready")
    if step == "full":
        require(project, "work/sample_approval.txt")
        if (project / "work/sample_approval.txt").read_text().strip() != "approved":
            raise SystemExit("blocked; user must approve work/sample_approval.txt before full render")
    if step == "caption_qa":
        require(project, "output/make_it_full.mp4")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--step", choices=STEPS + ("prepare", "all"), default="all")
    args = parser.parse_args()
    project = args.project.resolve()
    if args.step == "prepare":
        for step in ("manifest", "tts", "timeline", "audio", "sample"):
            gate(project, step)
            run(project, step)
        print("sample rendered; stop for user approval in work/sample_approval.txt")
        return 0
    if args.step == "all":
        approved = (project / "work/sample_approval.txt").exists() and (project / "work/sample_approval.txt").read_text().strip() == "approved"
        steps = ["full", "spotcheck", "caption_qa", "preflight"] if approved else ["manifest", "tts", "timeline", "audio", "sample"]
    else:
        steps = [args.step]
    for step in steps:
        gate(project, step)
        run(project, step)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
