#!/usr/bin/env python3
"""Create an auditable project skeleton from a YouTube URL or local video."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from urllib.parse import parse_qs, urlparse
import shutil
from pathlib import Path

from download import download, fetch_captions, is_url
from transcribe import parse_vtt
from whisper import load_api_key, transcribe_video

ROOT = Path(__file__).resolve().parent.parent
LOCAL_ASR = Path(os.environ.get(
    "LOCAL_ASR_PYTHON", "/home/neo/.cache/video-transcription-asr/venv/bin/python"
))


def transcribe_local(audio: str, audio_out: Path, transcript_out: Path) -> list[dict]:
    if not LOCAL_ASR.exists():
        return []
    subprocess.run([
        str(LOCAL_ASR), str(ROOT / "scripts/local_asr.py"),
        "--input", audio, "--audio-out", str(audio_out), "--output", str(transcript_out),
    ], check=True)
    return json.loads(transcript_out.read_text())["segments"]


def canonical_youtube_slug(source: str) -> str | None:
    parsed = urlparse(source)
    video_id = parse_qs(parsed.query).get("v", [None])[0]
    if not video_id and parsed.netloc.lower() in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/").split("/")[0]
    return f"youtube-{video_id}" if video_id else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="YouTube URL or local video path")
    parser.add_argument("--slug", help="Custom slug for local input only")
    parser.add_argument("--workspace", type=Path, default=ROOT / "projects")
    parser.add_argument("--overview", type=Path, help="User overview markdown file")
    args = parser.parse_args()
    canonical = canonical_youtube_slug(args.source) if is_url(args.source) else None
    if canonical and args.slug and args.slug != canonical:
        raise SystemExit(f"YouTube project slug must be {canonical}, not {args.slug}")
    slug = canonical or args.slug
    if not slug:
        raise SystemExit("--slug is required for local video input")
    project = (args.workspace / slug).resolve()
    for name in ("assets", "source/raw", "scripts", "work", "subs", "audio", "output"):
        (project / name).mkdir(parents=True, exist_ok=True)

    # ponytail: URL production only needs metadata/captions; download source
    # video only for an explicitly local input or a later frame-analysis path.
    fetched = (
        fetch_captions(args.source, project / "source/raw")
        if is_url(args.source)
        else download(args.source, project / "source/raw")
    )
    metadata = {
        "source": args.source,
        **fetched.get("info", {}),
        "caption_source": fetched.get("caption_source", "none"),
    }
    if fetched.get("video_path"):
        video = Path(fetched["video_path"])
        shutil.copy2(video, project / f"source/video{video.suffix}")
    if fetched.get("thumbnail_path"):
        shutil.copy2(fetched["thumbnail_path"], project / "source/identity_reference.jpg")
    subtitle = fetched.get("subtitle_path")
    caption_source = fetched.get("caption_source", "none")
    if caption_source in {"youtube_auto", "manual_unavailable", "none"}:
        derived_from = caption_source
        backend, api_key = load_api_key()
        audio = fetched.get("video_path")
        if not audio:
            audio = download(args.source, project / "source/raw", audio_only=True).get("video_path")
        if not audio:
            raise SystemExit("blocked; untrusted/missing captions require an audio download for Whisper")
        transcript_path = project / "source/raw/whisper.en.json"
        if LOCAL_ASR.exists():
            cues = transcribe_local(audio, project / "source/raw/whisper_audio.wav", transcript_path)
            caption_source = "local_whisper"
            caption_model = os.environ.get("ASR_MODEL", "large-v3")
        else:
            if not backend or not api_key:
                raise SystemExit(
                    "blocked; local ASR is not installed and no GROQ_API_KEY or OPENAI_API_KEY is configured"
                )
            cues, used_backend = transcribe_video(
                audio,
                project / "source/raw/whisper_audio.mp3",
                backend=backend,
                api_key=api_key,
            )
            transcript_path.write_text(json.dumps(cues, ensure_ascii=False, indent=2) + "\n")
            caption_source = f"whisper_{used_backend}"
            caption_model = "whisper-large-v3" if used_backend == "groq" else "whisper-1"
        metadata.update({
            "caption_source": caption_source,
            "caption_derived_from": derived_from,
            "caption_verified": False,
            "caption_model": caption_model,
        })
    else:
        cues = parse_vtt(subtitle) if subtitle else []
        metadata.update({
            "caption_verified": caption_source == "youtube_manual",
        })
    (project / "source/metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    timing = [
        {"para": i, "start": float(c["start"]), "end": float(c["end"])}
        for i, c in enumerate(cues, 1) if "start" in c and "end" in c
    ]
    (project / "work/source_timing.json").write_text(json.dumps(timing, indent=2) + "\n")
    if cues:
        # One cue per paragraph is deliberately boring but preserves source order.
        (project / "scripts/en.md").write_text("\n\n".join(c["text"] for c in cues) + "\n")
        if subtitle:
            shutil.copy2(subtitle, project / "source/raw/source.en.vtt")
    else:
        (project / "scripts/en.md").write_text("")
    if subtitle and not cues:
        shutil.copy2(subtitle, project / "source/raw/source.en.vtt")
    if args.overview:
        overview = args.overview.expanduser().resolve()
        if not overview.exists():
            raise SystemExit(f"overview file not found: {overview}")
        (project / "source/user_overview.md").write_text(overview.read_text(encoding="utf-8"))
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
    for name, value in (("image_mode.txt", "pending\n"), ("cover_typography_mode.txt", "model-typeset\n"), ("visual_brief_approval.txt", "pending\n"), ("cover_approval.txt", "pending\n"), ("sample_approval.txt", "pending\n")):
        (project / "work" / name).write_text(value)
    (project / "work/identity_gate.json").write_text(json.dumps({
        "status": "pending",
        "reference": "source/identity_reference.jpg" if fetched.get("thumbnail_path") else None,
        "assets": ["assets/background.png", "assets/opening.png", "assets/cover.png"],
        "review": "Compare every generated person against source/identity_reference.jpg before auto-approval.",
    }, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"project": str(project), "title": metadata.get("title"), "english_cues": len(cues), "next": ["complete scripts/zh.md", "complete and approve work/visual_brief.md", "choose image_mode", "provide and approve assets/cover.png, assets/background.png, and assets/opening.png"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
