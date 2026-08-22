#!/usr/bin/env python3
"""Extract local audio and transcribe it with faster-whisper."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = os.environ.get("FFMPEG", str(ROOT / "tools/ffmpeg-static/bin/ffmpeg"))
MODEL_CACHE = Path("/home/neo/.cache/video-transcription-asr/models/faster-whisper-large-v3")
DEFAULT_MODEL = str(MODEL_CACHE) if (MODEL_CACHE / "model.bin").exists() else "large-v3"
PROMPT = (
    "English motivational speech about discipline, personal growth, success, "
    "habits, early mornings, and Jim Rohn."
)


def extract_audio(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destination)],
        capture_output=True, text=True,
    )
    if result.returncode or not destination.exists() or destination.stat().st_size == 0:
        raise SystemExit(f"audio extraction failed: {result.stderr.strip()}")


def transcribe(audio: Path, output: Path, model_name: str, device: str, compute_type: str) -> None:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        str(audio), language="en", beam_size=5, best_of=5,
        condition_on_previous_text=True, vad_filter=True,
        word_timestamps=True, initial_prompt=PROMPT,
    )
    rows = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        row = {"start": round(segment.start, 3), "end": round(segment.end, 3), "text": text}
        if segment.words:
            row["words"] = [
                {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word}
                for w in segment.words
            ]
        rows.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "model": model_name,
        "language": info.language,
        "language_probability": info.language_probability,
        "segments": rows,
    }, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"model": model_name, "segments": len(rows), "output": str(output)}))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--audio-out", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("ASR_MODEL", DEFAULT_MODEL))
    parser.add_argument("--device", default=os.environ.get("ASR_DEVICE", "cuda"))
    parser.add_argument("--compute-type", default=os.environ.get("ASR_COMPUTE_TYPE", "int8_float16"))
    args = parser.parse_args()
    extract_audio(args.input.resolve(), args.audio_out.resolve())
    transcribe(args.audio_out.resolve(), args.output.resolve(), args.model, args.device, args.compute_type)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
