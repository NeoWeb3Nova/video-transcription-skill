#!/usr/bin/env python3
"""Portable gated runner for the repository's bilingual render pipeline."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = ("manifest", "tts", "hooks-tts", "timeline", "audio", "sample", "full", "spotcheck", "caption_qa", "preflight")


def require(project: Path, *paths: str) -> None:
    missing = [str(project / path) for path in paths if not (project / path).exists()]
    if missing:
        raise SystemExit("blocked; missing: " + ", ".join(missing))


def run(project: Path, step: str) -> None:
    env = os.environ.copy()
    env["PROJECT_SLUG"] = project.name
    if os.environ.get("AUTO_MODE") == "1":
        env["AUTO_MODE"] = "1"
    subprocess.run([sys.executable, str(ROOT / "scripts/produce.py"), step], cwd=ROOT, env=env, check=True)


def gate(project: Path, step: str, auto: bool = False) -> None:
    if step in {"manifest", "tts", "hooks-tts", "timeline", "audio"}:
        require(project, "scripts/en.md", "scripts/zh.md")
    if step in {"hooks-tts", "timeline", "audio", "sample", "full"}:
        require(project, "work/hooks.json")
    if step in {"sample", "full"}:
        require(project, "assets/background.png", "assets/opening.png", "assets/cover.png", "scripts/en.md", "scripts/zh.md", "work/paras.json", "audio/master.wav", "work/cover_approval.txt", "work/cover_typography_mode.txt")
        allowed = {"approved", "auto-approved"} if auto else {"approved"}
        if (project / "work/cover_approval.txt").read_text().strip() not in allowed:
            raise SystemExit("blocked; user must approve work/cover_approval.txt before rendering")
        if (project / "work/cover_typography_mode.txt").read_text().strip() != "model-typeset":
            raise SystemExit("blocked; work/cover_typography_mode.txt must be model-typeset")
    if step == "sample":
        if (project / "work/sample_approval.txt").exists() and (project / "work/sample_approval.txt").read_text().strip() == "approved":
            raise SystemExit("sample already approved; run full when ready")
    if step == "full":
        require(project, "work/sample_approval.txt")
        allowed = {"approved", "auto-approved"} if auto else {"approved"}
        if (project / "work/sample_approval.txt").read_text().strip() not in allowed:
            raise SystemExit("blocked; user must approve work/sample_approval.txt before full render")
    if step == "caption_qa":
        require(project, "output/make_it_full.mp4")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--step", choices=STEPS + ("prepare", "all"), default="all")
    parser.add_argument("--auto", action="store_true", help="Use machine-reviewed auto approval markers")
    args = parser.parse_args()
    if args.auto:
        os.environ["AUTO_MODE"] = "1"
    project = args.project.resolve()
    if args.step == "prepare":
        for step in ("manifest", "tts", "hooks-tts", "timeline", "audio", "sample"):
            gate(project, step, args.auto)
            run(project, step)
        print("sample rendered; stop for user approval in work/sample_approval.txt")
        return 0
    if args.step == "all":
        allowed = {"approved", "auto-approved"} if args.auto else {"approved"}
        approved = (project / "work/sample_approval.txt").exists() and (project / "work/sample_approval.txt").read_text().strip() in allowed
        steps = ["full", "spotcheck", "caption_qa", "preflight"] if approved else ["manifest", "tts", "hooks-tts", "timeline", "audio", "sample"]
    else:
        steps = [args.step]
    for step in steps:
        gate(project, step, args.auto)
        run(project, step)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
