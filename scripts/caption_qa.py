#!/usr/bin/env python3
"""OCR-based burned-subtitle QA; works without a multimodal LLM."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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
    text = text.lower().replace("voure", "youre").replace("vou", "you")
    text = re.sub(r"&(?:gt|lt);|\[?music\]?|音乐", "", text)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def match_score(style: str, expected: str, actual: str) -> float:
    """Allow OCR edge truncation while still requiring most text to match."""
    if style == "EN":
        left = re.findall(r"[a-z0-9]+", expected.lower())
        right = [token.replace("voure", "youre").replace("vou", "you") for token in re.findall(r"[a-z0-9]+", actual.lower())]
    else:
        left = re.findall(r"[\u4e00-\u9fff]", expected)
        right = re.findall(r"[\u4e00-\u9fff]", actual)
    if not left or not right:
        return 0.0
    score = difflib.SequenceMatcher(None, left, right).ratio()
    if style == "EN" and len(left) >= 8:
        prefix = left[:8]
        for i in range(max(0, len(right) - len(prefix) + 1)):
            if right[i:i + len(prefix)] == prefix:
                return max(score, 0.70)
    return score


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


def frame_text_rapid(ocr, frame: Path) -> str:
    result, _ = ocr(str(frame))
    return " ".join(str(item[1]) for item in (result or []) if len(item) > 1)


def frame_text_tesseract(tesseract: str, frame: Path, language: str, psm: int) -> str:
    return subprocess.run(
        [tesseract, str(frame), "stdout", "-l", language, "--psm", str(psm)],
        capture_output=True, text=True, check=True, timeout=30,
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
        rapid_reader = None
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]
            rapid_reader = RapidOCR()
        except Exception as exc:
            result["errors"].append(f"RapidOCR fallback unavailable: {exc}")
        tesseract = shutil.which("tesseract")
        if tesseract:
            langs = subprocess.run([tesseract, "--list-langs"], capture_output=True, text=True).stdout
            if "chi_sim" in langs:
                reader = lambda frame, style: frame_text_tesseract(
                    tesseract,
                    frame,
                    "chi_sim" if style in {"ZH", "ZH2"} else "eng",
                    11 if style in {"ZH", "ZH2"} else 6,
                )
                result["engine"] = "tesseract"
        if not reader and rapid_reader:
            reader = lambda frame, style: frame_text_rapid(rapid_reader, frame)
            result["engine"] = "rapidocr"
        if not reader:
            result["errors"].append("tesseract is unavailable; OCR was not run")
        if result["engine"] and reader:
            def check_event(item: tuple[int, dict]) -> dict | None:
                i, event = item
                frame = Path(tmp) / f"{i:05d}.png"
                crop = "crop=1400:220:400:360" if event["style"] in {"ZH", "ZH2"} else "crop=1400:500:400:300"
                try:
                    subprocess.run([
                        ffmpeg, "-y", "-loglevel", "error", "-ss",
                        str((event["start"] + event["end"]) / 2), "-i", str(args.video),
                        "-vf", crop, "-frames:v", "1", str(frame),
                    ], check=True, timeout=30)
                    text = reader(frame, event["style"])
                except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                    return {"style": event["style"], "start": event["start"], "score": 0.0,
                            "expected": event["text"], "ocr": f"OCR error: {exc}"}
                score = match_score(event["style"], event["text"], text)
                expected = norm(event["text"])
                if not expected:
                    return None
                if expected not in norm(text) and score < 0.55 and rapid_reader and result["engine"] == "tesseract":
                    rapid_text = frame_text_rapid(rapid_reader, frame)
                    rapid_score = match_score(event["style"], event["text"], rapid_text)
                    if expected in norm(rapid_text) or rapid_score > score:
                        text, score = rapid_text, rapid_score
                if expected not in norm(text) and score < 0.55 and event["style"] in {"ZH", "ZH2"}:
                    fallback = Path(tmp) / f"{i:05d}-wide.png"
                    primary_text, primary_score = text, score
                    try:
                        subprocess.run([
                            ffmpeg, "-y", "-loglevel", "error", "-ss",
                            str((event["start"] + event["end"]) / 2), "-i", str(args.video),
                            "-vf", "crop=1400:500:400:300", "-frames:v", "1", str(fallback),
                        ], check=True, timeout=30)
                        if result["engine"] == "tesseract":
                            ocr_bin = shutil.which("tesseract")
                            fallback_text = frame_text_tesseract(ocr_bin, fallback, "chi_sim+eng", 6) if ocr_bin else text
                            fallback_score = match_score(event["style"], event["text"], fallback_text)
                            text, score = (fallback_text, fallback_score) if fallback_score > primary_score else (primary_text, primary_score)
                        else:
                            fallback_text = reader(fallback, event["style"])
                            fallback_score = match_score(event["style"], event["text"], fallback_text)
                            text, score = (fallback_text, fallback_score) if fallback_score > primary_score else (primary_text, primary_score)
                    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                        pass
                if expected not in norm(text) and score < 0.55:
                    return {"style": event["style"], "start": event["start"], "score": round(score, 3),
                            "expected": event["text"], "ocr": text.strip()}
                return None

            with tempfile.TemporaryDirectory(prefix="caption-qa-") as tmp:
                with ThreadPoolExecutor(max_workers=8, thread_name_prefix="caption-qa") as pool:
                    failures = [failure for failure in pool.map(check_event, enumerate(evs)) if failure]
                result["checked"] = len(evs)
            result["errors"] = failures
            result["ok"] = not failures and result["checked"] == len(evs)
            result["status"] = "pass" if result["ok"] else "fail"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
