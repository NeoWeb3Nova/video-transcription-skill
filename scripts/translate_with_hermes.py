#!/usr/bin/env python3
"""Translate a project with the active Hermes model, preserving sentence counts."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from html import unescape
from pathlib import Path


def sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r'(?<=[.!?])\s+', text.strip()) if p.strip()]


def clean_sentence(text: str) -> str | None:
    text = unescape(text)
    text = re.sub(r"\[music\]", "", text, flags=re.IGNORECASE)
    text = text.replace(">>", " ")
    text = re.sub(r"\s+", " ", text).strip(" .")
    return (text + ("." if text[-1] not in ".!?" else "")) if text else None


def ask(batch: list[str]) -> list[str]:
    payload = json.dumps(batch, ensure_ascii=False)
    prompt = (
        "Translate each English sentence into natural, faithful Simplified Chinese. "
        "Preserve meaning, names, numbers, and sentence order. Do not summarize or "
        "add commentary. Return ONLY a JSON object with one key `translations`, whose "
        "value is an array of exactly the same length. Each item must be one Chinese sentence.\n\n"
        f"INPUT JSON ARRAY:\n{payload}"
    )
    result = subprocess.run(["hermes", "chat", "-Q", "-q", prompt], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    text = result.stdout.strip()
    text = text[text.find("{"):] if "{" in text else text
    data = json.loads(text)
    out = data.get("translations")
    if (not isinstance(out, list) or len(out) != len(batch)
            or not all(isinstance(x, str) and x.strip() and re.search(r"[\u4e00-\u9fff]", x) for x in out)):
        raise ValueError(f"Hermes returned invalid translation count/content: expected {len(batch)}")
    normalized = []
    for x in out:
        x = re.sub(r"\s+", " ", x).strip(" ，。")
        x = re.sub(r"[。！？]+", "，", x).rstrip("，")
        normalized.append(x + "。")
    return normalized


def translate_batch(batch: list[str]) -> list[str]:
    for attempt in range(1, 4):
        try:
            return ask(batch)
        except ValueError:
            if len(batch) > 1:
                mid = len(batch) // 2
                return translate_batch(batch[:mid]) + translate_batch(batch[mid:])
            raise
        except RuntimeError as exc:
            if attempt == 3:
                raise
            print(f"retry batch: {exc}", flush=True)
    raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=24)
    args = parser.parse_args()
    root = args.project.resolve()
    en_blocks = [b for b in (root / "scripts/en.md").read_text(encoding="utf-8").strip().split("\n\n") if b.strip()]
    cleaned = [[s for raw in sentences(block) if (s := clean_sentence(raw))] for block in en_blocks]
    flat = [s for block in cleaned for s in block]
    translated: list[str] = []
    for start in range(0, len(flat), args.batch_size):
        batch = flat[start:start + args.batch_size]
        translated.extend(translate_batch(batch))
        print(f"translated {min(start + len(batch), len(flat))}/{len(flat)}", flush=True)
        
    if len(translated) != len(flat):
        raise SystemExit("translation count mismatch")
    paragraphs, index = [], 0
    for block in cleaned:
        count = len(block)
        paragraphs.append("".join(translated[index:index + count]))
        index += count
    (root / "scripts/en.md").write_text("\n\n".join(" ".join(block) for block in cleaned) + "\n", encoding="utf-8")
    (root / "scripts/zh.md").write_text("\n\n".join(paragraphs) + "\n", encoding="utf-8")
    print(json.dumps({"paragraphs": len(paragraphs), "sentences": len(flat), "translator": "active-hermes-model"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
