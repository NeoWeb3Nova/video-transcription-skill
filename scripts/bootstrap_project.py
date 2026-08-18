#!/usr/bin/env python3
"""Create an auditable project skeleton from a YouTube URL or local video."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from download import download
from transcribe import parse_vtt

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="YouTube URL or local video path")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--workspace", type=Path, default=ROOT / "projects")
    args = parser.parse_args()
    project = (args.workspace / args.slug).resolve()
    for name in ("assets", "source/raw", "scripts", "work", "subs", "audio", "output"):
        (project / name).mkdir(parents=True, exist_ok=True)

    fetched = download(args.source, project / "source/raw")
    metadata = {"source": args.source, **fetched.get("info", {})}
    (project / "source/metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    if fetched.get("video_path"):
        video = Path(fetched["video_path"])
        shutil.copy2(video, project / f"source/video{video.suffix}")
    subtitle = fetched.get("subtitle_path")
    cues = parse_vtt(subtitle) if subtitle else []
    if subtitle:
        # One cue per paragraph is deliberately boring but preserves source order.
        (project / "scripts/en.md").write_text("\n\n".join(c["text"] for c in cues) + "\n")
        shutil.copy2(subtitle, project / "source/raw/source.en.vtt")
    else:
        (project / "scripts/en.md").write_text("")
    (project / "scripts/zh.md").write_text("")
    (project / "work/translation_checkpoint.md").write_text(
        "# Translation checkpoint\n\n"
        "Translate `scripts/en.md` into `scripts/zh.md` paragraph by paragraph. "
        "Keep paragraph count/order identical and map one English sentence to one Chinese sentence.\n"
    )
    (project / "work/visual_brief.md").write_text(
        "# Source-grounded visual brief\n\n"
        f"- Source: {args.source}\n"
        f"- Title: {metadata.get('title', '')}\n"
        "- Core topic: [complete before assets]\n"
        "- Core mechanism: [complete before assets]\n"
        "- Approved Chinese title: [complete before assets]\n"
        "- Approved English title: [complete before assets]\n"
        "- Visual metaphors: [complete before assets]\n"
        "- Forbidden interpretations: [complete before assets]\n"
    )
    for name, value in (("image_mode.txt", "pending\n"), ("visual_brief_approval.txt", "pending\n"), ("cover_approval.txt", "pending\n"), ("sample_approval.txt", "pending\n")):
        (project / "work" / name).write_text(value)
    print(json.dumps({"project": str(project), "title": metadata.get("title"), "english_cues": len(cues), "next": ["complete scripts/zh.md", "complete and approve work/visual_brief.md", "choose image_mode", "provide assets/background.png and assets/opening.png"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
