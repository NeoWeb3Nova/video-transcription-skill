#!/usr/bin/env python3
"""Portable gated runner for the repository's bilingual render pipeline."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = ("manifest", "tts", "hooks-tts", "timeline", "audio", "sample", "full", "spotcheck", "caption_qa", "preflight")
STEP_TIMEOUT_SECONDS = 15 * 60


def require(project: Path, *paths: str) -> None:
    missing = [str(project / path) for path in paths if not (project / path).exists()]
    if missing:
        raise SystemExit("blocked; missing: " + ", ".join(missing))


def require_identity_gate(project: Path, auto: bool) -> None:
    require(project, "work/identity_gate.json", "source/identity_reference.jpg")
    try:
        data = json.loads((project / "work/identity_gate.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"blocked; invalid work/identity_gate.json: {exc}")
    allowed = {"approved", "auto-approved"} if auto else {"approved"}
    if data.get("status") not in allowed:
        raise SystemExit("blocked; identity gate must be approved after comparing assets to source/identity_reference.jpg")
    if data.get("assets") != ["assets/background.png", "assets/opening.png", "assets/cover.png"]:
        raise SystemExit("blocked; identity gate must cover background, opening, and cover assets")


def require_caption_provenance(project: Path) -> None:
    require(project, "source/metadata.json")
    try:
        data = json.loads((project / "source/metadata.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"blocked; invalid source/metadata.json: {exc}")
    source = data.get("caption_source")
    if source == "youtube_auto" or source not in {"youtube_manual", "local_whisper", "whisper_groq", "whisper_openai"}:
        raise SystemExit(
            "blocked; production requires youtube_manual or Whisper-retranscribed captions; "
            f"found {source!r}"
        )


def run(project: Path, step: str) -> None:
    env = os.environ.copy()
    env["PROJECT_SLUG"] = project.name
    if os.environ.get("AUTO_MODE") == "1":
        env["AUTO_MODE"] = "1"
    command = [sys.executable, str(ROOT / "scripts/produce.py"), step]
    process = subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=True)
    try:
        returncode = process.wait(timeout=STEP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        # Kill the whole step session so ffmpeg/tesseract descendants do not linger.
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        raise SystemExit(
            f"step {step!r} exceeded {STEP_TIMEOUT_SECONDS // 60} minutes; "
            "process considered stuck and terminated"
        ) from None
    if returncode:
        raise subprocess.CalledProcessError(returncode, command)


def gate(project: Path, step: str, auto: bool = False) -> None:
    if step in {"manifest", "tts", "hooks-tts", "timeline", "audio"}:
        require(project, "scripts/en.md", "scripts/zh.md")
    if step in {"hooks-tts", "timeline", "audio", "sample", "full"}:
        require(project, "work/hooks.json")
    if step in {"sample", "full"}:
        require_caption_provenance(project)
        require_identity_gate(project, auto)
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
