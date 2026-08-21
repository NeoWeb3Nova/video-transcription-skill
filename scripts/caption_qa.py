#!/usr/bin/env python3
"""OCR-based burned-subtitle QA; works without a multimodal LLM."""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def ass_time(value: str) -> float:
    h, m, s = value.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def clean_ass(text: str) -> str:
    text = re.sub(r"\{[^}]*\}", "", text)
    return text.replace(r"\N", " ").strip()


def norm(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text.lower())


def match_score(style: str, expected: str, actual: str) -> float:
    """Allow OCR edge truncation while still requiring most text to match."""
    if style == "EN":
        left = re.findall(r"[a-z0-9]+", expected.lower())
        right = re.findall(r"[a-z0-9]+", actual.lower())
    else:
        left = re.findall(r"[\u4e00-\u9fff]", expected)
        right = re.findall(r"[\u4e00-\u9fff]", actual)
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def events(ass: Path) -> list[dict]:
    out, seen = [], set()
    for line in ass.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        fields = line.split(",", 9)
        if len(fields) != 10 or fields[3] not in {"ZH", "ZH2", "EN"}:
            continue
        start, end = ass_time(fields[1]), ass_time(fields[2])
        text = clean_ass(fields[9])
        key = (start, end, fields[3], text)
        if end > start and text and key not in seen:
            seen.add(key)
            out.append({"start": start, "end": end, "style": fields[3], "text": text})
    return out


def frame_text_paddle(ocr, frame: Path) -> str:
    texts = []
    for result in ocr.predict(str(frame)):
        data = result.json if hasattr(result, "json") else result
        if callable(data):
            data = data()
        if isinstance(data, str):
            data = json.loads(data)
        data = data.get("res", data) if isinstance(data, dict) else {}
        texts.extend(str(text) for text in data.get("rec_texts", []))
    return " ".join(texts)


def frame_text_tesseract(tesseract: str, frame: Path) -> str:
    return subprocess.run(
        [tesseract, str(frame), "stdout", "-l", "chi_sim+eng", "--psm", "6"],
        capture_output=True, text=True, check=True,
    ).stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--ass", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    result = {"ok": False, "status": "manual_review_required", "engine": None, "events": 0, "checked": 0, "errors": []}
    evs = events(args.ass)
    result["events"] = len(evs)
    ffmpeg = shutil.which("ffmpeg") or str(Path(__file__).resolve().parent.parent / "tools/ffmpeg-static/bin/ffmpeg")
    ffprobe = shutil.which("ffprobe") or str(Path(__file__).resolve().parent.parent / "tools/ffmpeg-static/bin/ffprobe")
    if not Path(ffmpeg).exists() or not Path(ffprobe).exists():
        result["errors"].append("ffmpeg/ffprobe is unavailable; frames cannot be extracted")
    else:
        duration = float(subprocess.check_output([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(args.video)]).decode())
        evs = [event for event in evs if (event["start"] + event["end"]) / 2 < duration]
        ocr = None
        reader = None
        try:
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]
            ocr = PaddleOCR(lang="ch", use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, device=os.environ.get("PADDLEOCR_DEVICE", "gpu:0"))
            reader = lambda frame: frame_text_paddle(ocr, frame)
            result["engine"] = "paddleocr"
        except Exception as exc:
            paddle_error = f"PaddleOCR unavailable: {exc}"
            tesseract = shutil.which("tesseract")
            if not tesseract:
                result["errors"].append(paddle_error)
                result["errors"].append("tesseract is unavailable; OCR was not run")
            else:
                langs = subprocess.run([tesseract, "--list-langs"], capture_output=True, text=True).stdout
                if "chi_sim" not in langs:
                    result["errors"].append(paddle_error)
                    result["errors"].append("tesseract chi_sim language data is unavailable")
                else:
                    reader = lambda frame: frame_text_tesseract(tesseract, frame)
                    result["engine"] = "tesseract"
        if result["engine"] and reader:
            failures = []
            with tempfile.TemporaryDirectory(prefix="caption-qa-") as tmp:
                for i, event in enumerate(evs):
                    frame = Path(tmp) / f"{i:05d}.png"
                    # OCR only the active language row; background texture and
                    # the paired language must not substitute for this event.
                    crop = "crop=1150:220:760:400" if event["style"] == "ZH" else "crop=1150:150:760:600"
                    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", str((event["start"] + event["end"]) / 2), "-i", str(args.video), "-vf", crop, "-frames:v", "1", str(frame)], check=True)
                    text = reader(frame)
                    score = match_score(event["style"], event["text"], text)
                    if norm(event["text"]) not in norm(text) and score < 0.70:
                        failures.append({"style": event["style"], "start": event["start"], "score": round(score, 3), "expected": event["text"], "ocr": text.strip()})
                    result["checked"] += 1
            result["errors"] = failures
            result["ok"] = not failures and result["checked"] == len(evs)
            result["status"] = "pass" if result["ok"] else "fail"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
