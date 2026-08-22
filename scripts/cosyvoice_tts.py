#!/usr/bin/env python3
"""CosyVoice2 sentence-level TTS adapter for the video pipeline."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COSYVOICE_ROOT = Path(os.environ.get("COSYVOICE_ROOT", "/home/neo/.cache/cosyvoice/CosyVoice"))
MODEL_DIR = Path(os.environ.get("COSYVOICE_MODEL_DIR", "/home/neo/.cache/cosyvoice/models/CosyVoice2-0.5B"))
PROMPT_AUDIO = Path(os.environ.get("COSYVOICE_PROMPT_AUDIO", str(COSYVOICE_ROOT / "asset/zero_shot_prompt.wav")))
PROMPT_TEXT = os.environ.get("COSYVOICE_PROMPT_TEXT", "希望你以后能够做的比我还好呦。")
FFMPEG = ROOT / "tools/ffmpeg-static/bin/ffmpeg"


def load_model():
    import sys
    sys.path = [p for p in sys.path if Path(p or ".").resolve() != (ROOT / "scripts").resolve()]
    sys.path.insert(0, str(COSYVOICE_ROOT))
    sys.path.insert(0, str(COSYVOICE_ROOT / "third_party/Matcha-TTS"))
    from cosyvoice.cli.cosyvoice import AutoModel
    return AutoModel(model_dir=str(MODEL_DIR))


def render_text(model, text: str, wav: Path) -> float:
    import torchaudio
    chunks = []
    for item in model.inference_zero_shot(text, PROMPT_TEXT, str(PROMPT_AUDIO), stream=False):
        chunks.append(item["tts_speech"])
    if not chunks:
        raise RuntimeError(f"CosyVoice returned no audio for: {text[:80]}")
    audio = __import__("torch").cat(chunks, dim=1)
    torchaudio.save(str(wav), audio, model.sample_rate)
    return audio.shape[1] / model.sample_rate


def wav_to_mp3(wav: Path, mp3: Path) -> None:
    subprocess.run([str(FFMPEG), "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "128k", str(mp3)], check=True)


def render_paragraphs(paras_path: Path, out_dir: Path) -> None:
    paras = json.loads(paras_path.read_text())
    model = load_model()
    out_dir.mkdir(parents=True, exist_ok=True)
    progress = {}
    for para in paras:
        n = int(para["para"])
        wav = out_dir / f"para{n:02d}.wav"
        mp3 = out_dir / f"para{n:02d}.mp3"
        events, offset = [], 0.0
        for text in para["zh"]:
            duration = render_text(model, "".join(text), wav.with_name(f"para{n:02d}-{len(events):03d}.wav"))
            part = wav.with_name(f"para{n:02d}-{len(events):03d}.wav")
            events.append({"offset": round(offset * 10_000_000), "duration": round(duration * 10_000_000), "text": text})
            offset += duration
            if len(events) == 1:
                subprocess.run([str(FFMPEG), "-y", "-loglevel", "error", "-i", str(part), "-c:a", "pcm_s16le", str(wav)], check=True)
            else:
                subprocess.run([str(FFMPEG), "-y", "-loglevel", "error", "-i", str(wav), "-i", str(part), "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1", "-c:a", "pcm_s16le", str(wav.with_suffix('.join.wav'))], check=True)
                wav.with_suffix('.join.wav').replace(wav)
            part.unlink(missing_ok=True)
        wav_to_mp3(wav, mp3)
        wav.unlink(missing_ok=True)
        (out_dir / f"para{n:02d}.events.json").write_text(json.dumps(events, ensure_ascii=False, indent=1) + "\n")
        progress[str(n)] = "ok"
        print(f"[ok] cosyvoice para{n:02d} events={len(events)}", flush=True)
    (out_dir / "progress.json").write_text(json.dumps(progress, indent=1) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paras", type=Path)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    if not args.paras or not args.out_dir:
        parser.error("--paras and --out-dir are required")
    render_paragraphs(args.paras, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
