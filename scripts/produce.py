#!/usr/bin/env python3
"""Bilingual karaoke video production pipeline (repo-reusable).

Steps (run in order):
  python3 scripts/produce.py manifest   # build work/paras.json from scripts/en.md + zh.md
  python3 scripts/produce.py tts        # edge-tts narration + word events per paragraph
  python3 scripts/produce.py hooks-tts  # fixed bilingual hook narration + events
  python3 scripts/produce.py timeline   # bilingual ASS + karaoke ASS from events
  python3 scripts/produce.py audio      # intro + source + ending + 4s tail -> audio/master.wav
  python3 scripts/produce.py sample     # 15s sample render
  python3 scripts/produce.py full       # full render
  python3 scripts/produce.py spotcheck  # automatic sync audit (manifest ok:true)
  python3 scripts/produce.py preflight  # gate report

Derived from the proven pipeline recorded in projects/youtube-977PU9FtGA0 logs
(edge-tts, 0.35s inter-paragraph silence, 3s opening offset, karaoke ASS,
fontsdir /mnt/c/Windows/Fonts).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = ROOT / "tools/ffmpeg-static/bin/ffmpeg"
FFPROBE = ROOT / "tools/ffmpeg-static/bin/ffprobe"
FONTSDIR = "/mnt/c/Windows/Fonts"
OPENING_S = 3.0
SILENCE_S = 0.35
SENTENCE_GAP_S = 0.05
MUSIC_TAIL_S = 4.0
VOICE = "zh-CN-YunjianNeural"

HOOK_INTRO = "HOOK_INTRO"
SOURCE = "SOURCE"
HOOK_ENDING = "HOOK_ENDING"

# Target project: PROJECT_SLUG env var, default the first completed pipeline.
P = ROOT / "projects" / os.environ.get("PROJECT_SLUG", "youtube-eD3KNmSlu24")
HOOK_CATALOG = ROOT / "references/fixed-opening-hooks.json"
HOOK_EN = (
    "Spend 30 minutes before bed listening to this, and start changing tomorrow.",
    "Spend 30 minutes before bed quietly changing your life.",
    "Spend 30 minutes before bed listening closely, and your life will begin to turn.",
    "Spend 30 minutes before bed giving yourself a chance to change your life.",
    "Spend 30 minutes before bed; do not let who you are today ruin tomorrow's life.",
    "Spend 30 minutes before bed listening closely, and you will never be the same.",
    "Spend 30 minutes before bed, becoming different one step at a time.",
)
HOOK_ENDING_COPY = {
    "zh": "一键三连，关注我的账号，持续更新。行动起来，成为更好的自己。",
    "en": "Like, share, and follow my account for continuous updates. Take action and become a better version of yourself.",
}


def select_hook_index(second: int) -> int:
    if isinstance(second, bool) or not isinstance(second, int) or not 0 <= second <= 59:
        raise ValueError("second must be in [0, 59]")
    return second % 7


def _valid_hooks(manifest: object) -> bool:
    if not isinstance(manifest, dict):
        return False
    required = {"version", "source", "topic", "hook_index", "selection_second",
                "selection_method", "catalog_zh", "catalog_en", "intro", "ending"}
    if (set(manifest) != required or isinstance(manifest["version"], bool)
            or manifest["version"] != 1 or manifest["source"] != "editorial_hook"):
        return False
    if not isinstance(manifest["topic"], str) or not manifest["topic"].strip() or manifest["topic"] != P.name:
        return False
    if (isinstance(manifest["hook_index"], bool) or not isinstance(manifest["hook_index"], int)
            or isinstance(manifest["selection_second"], bool)
            or not isinstance(manifest["selection_second"], int)):
        return False
    if not 0 <= manifest["hook_index"] < 7 or not 0 <= manifest["selection_second"] <= 59:
        return False
    if select_hook_index(manifest["selection_second"]) != manifest["hook_index"]:
        return False
    if manifest["selection_method"] != "current_second_mod_7":
        return False
    catalog = json.loads(HOOK_CATALOG.read_text())
    if not isinstance(catalog, list) or len(catalog) != 7 or any(not isinstance(item, str) or not item for item in catalog):
        return False
    if manifest["catalog_zh"] != catalog[manifest["hook_index"]] or manifest["catalog_en"] != HOOK_EN[manifest["hook_index"]]:
        return False
    if manifest["intro"] != {"zh": manifest["catalog_zh"], "en": manifest["catalog_en"]}:
        return False
    return manifest["ending"] == HOOK_ENDING_COPY


def hooks_fingerprint(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validate_events(events: object, duration: float) -> list[dict]:
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("audio duration is invalid")
    if not isinstance(events, list) or not events:
        raise ValueError("events must be a non-empty list")
    out = []
    previous = -1.0
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("text"), str):
            raise ValueError("event is malformed")
        try:
            raw_offset, raw_duration = event["offset"], event["duration"]
            if isinstance(raw_offset, bool) or not isinstance(raw_offset, (int, float)):
                raise ValueError
            if isinstance(raw_duration, bool) or not isinstance(raw_duration, (int, float)):
                raise ValueError
            offset = float(raw_offset) / 10_000_000
            length = float(raw_duration) / 10_000_000
        except (KeyError, TypeError, ValueError):
            raise ValueError("event offset or duration is malformed")
        if (not math.isfinite(offset) or not math.isfinite(length) or offset < 0 or offset < previous
                or length <= 0 or offset + length > duration + 0.05 or not event["text"].strip()):
            raise ValueError("event timing is invalid")
        previous = offset
        out.append({**event, "offset": offset * 10_000_000, "duration": length * 10_000_000})
    return out


def ensure_hooks() -> dict:
    path = P / "work/hooks.json"
    if path.exists():
        manifest = json.loads(path.read_text())
        if not _valid_hooks(manifest):
            raise ValueError(f"invalid hooks manifest: {path}")
        return manifest
    catalog_zh = json.loads(HOOK_CATALOG.read_text())
    if len(catalog_zh) != 7 or any(not isinstance(item, str) or not item for item in catalog_zh):
        raise ValueError(f"invalid fixed hook catalog: {HOOK_CATALOG}")
    second = datetime.now().second
    index = select_hook_index(second)
    manifest = {
        "version": 1,
        "source": "editorial_hook",
        "topic": P.name,
        "hook_index": index,
        "selection_second": second,
        "selection_method": "current_second_mod_7",
        "catalog_zh": catalog_zh[index],
        "catalog_en": HOOK_EN[index],
        "intro": {"zh": catalog_zh[index], "en": HOOK_EN[index]},
        "ending": HOOK_ENDING_COPY,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


ASS_HEADER = """\ufeff[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ZH,Microsoft YaHei UI,84,&H0042C5F5,&H0060606B,&H00101010,&H96000000,-1,0,0,0,100,100,0,0,1,4,2,6,420,200,0,1
Style: EN,Segoe UI,54,&H0042C5F5,&H0060606B,&H00101010,&H96000000,0,0,0,0,100,100,0,0,1,4,2,6,420,200,170,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def sentences(text: str) -> list[str]:
    # split on sentence-final punctuation, keep the punctuation
    if re.search(r"[\u4e00-\u9fff]", text):
        parts = re.split(r"(?<=[。！？])", text.strip())
    else:
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("+", " ".join(map(str, cmd)))
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def require_render_assets() -> None:
    required = ("assets/background.png", "assets/opening.png", "assets/cover.png",
                "work/cover_approval.txt", "work/cover_typography_mode.txt")
    missing = [str(P / path) for path in required if not (P / path).exists()]
    if missing:
        raise SystemExit("blocked; missing render inputs: " + ", ".join(missing))
    allowed = {"approved", "auto-approved"} if os.environ.get("AUTO_MODE") == "1" else {"approved"}
    if (P / "work/cover_approval.txt").read_text().strip() not in allowed:
        raise SystemExit("blocked; user must approve work/cover_approval.txt before rendering")
    if (P / "work/cover_typography_mode.txt").read_text().strip() != "model-typeset":
        raise SystemExit("blocked; cover typography mode must be model-typeset")


def ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_time(value: str) -> float:
    h, m, s = value.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


# ---------------- manifest ----------------

def cmd_manifest(*, no_hooks: bool = False) -> None:
    if not no_hooks:
        ensure_hooks()
    en = [b for b in (P / "scripts/en.md").read_text().strip().split("\n\n") if b.strip()]
    zh = [b for b in (P / "scripts/zh.md").read_text().strip().split("\n\n") if b.strip()]
    assert len(en) == len(zh), f"paragraph mismatch en={len(en)} zh={len(zh)}"
    paras = []
    for i, (e, z) in enumerate(zip(en, zh), 1):
        se, sz = sentences(e), sentences(z)
        assert len(se) == len(sz), f"para {i}: sentence mismatch en={len(se)} zh={len(sz)}"
        paras.append({"para": i, "zh": sz, "en": se})
    work = P / "work"
    work.mkdir(parents=True, exist_ok=True)
    (work / "paras.json").write_text(json.dumps(paras, ensure_ascii=False, indent=1))
    print(f"manifest ok: {len(paras)} paragraphs")


# ---------------- tts ----------------

async def synth(para: dict) -> None:
    n = para["para"]
    out_dir = P / "work/tts/zh"
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3, ev = out_dir / f"para{n:02d}.mp3", out_dir / f"para{n:02d}.events.json"
    if mp3.exists() and ev.exists():
        print(f"[skip] zh para{n:02d}")
        return
    text = "".join(para["zh"])
    comm = edge_tts.Communicate(text, VOICE)  # SentenceBoundary events, proven pipeline
    events = []
    with open(mp3, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                events.append({"offset": chunk["offset"], "duration": chunk["duration"], "text": chunk["text"]})
    (ev).write_text(json.dumps(events, ensure_ascii=False, indent=1))
    print(f"[ok] zh para{n:02d} events={len(events)}")


async def synth_hook(name: str, text: str, mp3: Path, events_path: Path) -> None:
    """Synthesize one hook; ``text`` is deliberately Chinese-only."""
    comm = edge_tts.Communicate(text, VOICE)
    events = []
    with mp3.open("wb") as audio:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                events.append({"offset": chunk["offset"], "duration": chunk["duration"], "text": chunk["text"]})
    events_path.write_text(json.dumps(events, ensure_ascii=False, indent=1) + "\n")
    print(f"[ok] hook {name} events={len(events)}")


def cmd_hooks_tts() -> None:
    manifest = ensure_hooks()
    out_dir = P / "work/tts/hooks"
    out_dir.mkdir(parents=True, exist_ok=True)
    progress_path = out_dir / "progress.json"
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
    if not isinstance(progress, dict):
        raise ValueError(f"invalid hook progress manifest: {progress_path}")
    fingerprint = hooks_fingerprint(manifest)
    if progress.get("hooks_fingerprint") != fingerprint:
        progress = {"hooks_fingerprint": fingerprint}
    segments = (("intro", manifest["intro"]), ("ending", manifest["ending"]))
    failed = []

    async def generate() -> None:
        for name, copy in segments:
            mp3, events = out_dir / f"{name}.mp3", out_dir / f"{name}.events.json"
            if progress.get(name) == "ok" and mp3.exists() and events.exists():
                progress[name] = "ok"
                print(f"[skip] hook {name}")
                progress_path.write_text(json.dumps(progress, indent=1) + "\n")
                continue
            for attempt in range(1, 4):
                try:
                    # English stays in hooks.json for subtitles; TTS receives zh only.
                    await synth_hook(name, copy["zh"], mp3, events)
                    if not (mp3.exists() and events.exists()):
                        raise RuntimeError("synthesis returned without both outputs")
                    progress[name] = "ok"
                    progress_path.write_text(json.dumps(progress, indent=1) + "\n")
                    break
                except Exception as exc:
                    print(f"[retry] hook {name} {attempt}/3: {exc}")
                    if attempt == 3:
                        progress[name] = "failed"
                        failed.append(name)
                        progress_path.write_text(json.dumps(progress, indent=1) + "\n")

    asyncio.run(generate())
    if failed:
        raise SystemExit(f"hooks-tts failed: {', '.join(failed)}")
    print("hooks-tts done: intro and ending")


def cmd_tts() -> None:
    paras = json.loads((P / "work/paras.json").read_text())
    progress = P / "work/tts/zh/progress.json"
    done = json.loads(progress.read_text()) if progress.exists() else {}
    todo = [p for p in paras if str(p["para"]) not in done or done[str(p["para"])] != "ok"]

    async def worker(q: asyncio.Queue) -> None:
        while True:
            para = await q.get()
            if para is None:
                return
            for attempt in range(1, 4):
                try:
                    await synth(para)
                    done[str(para["para"])] = "ok"
                    progress.write_text(json.dumps(done))
                    break
                except Exception as exc:  # edge-tts is flaky; bounded retries
                    print(f"[retry] zh para{para['para']:02d} {attempt}/3: {exc}")
                    await asyncio.sleep(2 * attempt)
            q.task_done()

    async def run_pool() -> None:
        q = asyncio.Queue()
        for p in todo:
            q.put_nowait(p)
        n = min(3, max(1, len(todo)))
        workers = [asyncio.create_task(worker(q)) for _ in range(n)]
        for _ in range(n):
            q.put_nowait(None)
        await asyncio.gather(*workers)

    asyncio.run(run_pool())
    remaining = [p["para"] for p in paras if done.get(str(p["para"])) != "ok"]
    print(f"tts done: {len(paras)-len(remaining)}/{len(paras)}; missing={remaining}")


# ---------------- timeline ----------------

def wrap_zh(s: str, width: int = 13) -> str:
    chars = list(s)
    return "\\N".join("".join(chars[i:i + width]) for i in range(0, len(chars), width))


def wrap_en(s: str, width: int = 8) -> str:
    words = s.split()
    return "\\N".join(" ".join(words[i:i + width]) for i in range(0, len(words), width))


def karaoke_line(text: str, dur_s: float, lang: str) -> str:
    segs = text.split("\\N")  # keep ASS line breaks intact
    units = [list(s) for s in segs] if lang == "ZH" else [s.split() for s in segs]
    total = sum(len(u) for u in units) or 1
    per = max(1, round(dur_s * 100 / total))  # centiseconds per unit, uniform
    k = f"{{\\k{per}}}"
    if lang == "EN":
        return "\\N".join(" ".join(k + u for u in seg) for seg in units)
    return "\\N".join("".join(k + u for u in seg) for seg in units)


def norm_zh(s: str) -> str:
    return re.sub(r'[\s。！？，、；：“”‘’「」…:：;—]', '', s)


def sent_times(n: int, paras: list, events: dict, para_start: dict) -> list[tuple[float, float]]:
    """(start, end) in master.wav time for each zh sentence of paragraph n.

    Resolution order — all grounded in real audio, never a cumulative model:
    1. word_events.json (WordBoundary, consecutive duplicates removed) matched
       sentence-by-sentence by normalized text — exact boundaries;
    2. SentenceBoundary events, exact offsets (1:1 with sentences);
    3. span-split: merged SentenceBoundary events split by char span when the
       event text concatenation equals the sentence text concatenation;
    4. proportional by char count within the paragraph audio (last resort).
    """
    import bisect
    evs = events[n]
    n_sent = len(paras[n - 1]["zh"])
    base = para_start[n]
    zh_all = "".join(norm_zh(s) for s in paras[n - 1]["zh"])

    wf = P / "work/tts/zh" / f"para{n:02d}.word_events.json"
    if wf.exists():
        w = json.loads(wf.read_text())
        kept, prev = [], None
        for e in w:  # edge WordBoundary repeats some words; drop consecutive dupes
            t = norm_zh(e["text"])
            if t == prev:
                continue
            kept.append(e)
            prev = t
        if "".join(norm_zh(e["text"]) for e in kept) == zh_all:
            starts, ends = [], []
            iw, ok = 0, True
            for s in paras[n - 1]["zh"]:
                target = norm_zh(s)
                acc, s0 = "", iw
                while iw < len(kept):
                    acc += norm_zh(kept[iw]["text"])
                    iw += 1
                    if acc.endswith(target) or len(acc) > len(target) + 40:
                        break
                if iw <= s0 or not acc.endswith(target):
                    ok = False
                    break
                starts.append(base + kept[s0]["offset"] / 10_000_000)
                ends.append(base + kept[iw - 1]["offset"] / 10_000_000
                            + kept[iw - 1]["duration"] / 10_000_000)
            if ok and iw == len(kept):
                return list(zip(starts, ends))

    if len(evs) == n_sent:
        starts = [base + e["offset"] / 10_000_000 for e in evs]
        ends = [starts[i + 1] - SENTENCE_GAP_S for i in range(n_sent - 1)]
        ends.append(starts[-1] + evs[-1]["duration"] / 10_000_000)
        return list(zip(starts, ends))

    ev_text = "".join(norm_zh(e["text"]) for e in evs)
    if ev_text == zh_all and len(evs) < n_sent:
        # split merged events proportionally by char span (real event edges kept)
        ev_lens = [len(norm_zh(e["text"])) for e in evs]
        sn_lens = [len(norm_zh(s)) for s in paras[n - 1]["zh"]]
        ev_cb = [0]
        for L in ev_lens:
            ev_cb.append(ev_cb[-1] + L)
        sn_cb = [0]
        for L in sn_lens:
            sn_cb.append(sn_cb[-1] + L)

        def ev_for(p: int) -> int:
            return min(len(evs) - 1, bisect.bisect_right(ev_cb, p) - 1)

        out = []
        for i in range(n_sent):
            a, b = sn_cb[i], sn_cb[i + 1]
            ea, eb = ev_for(a), ev_for(b)
            if ea == eb:
                fa = (a - ev_cb[ea]) / max(1, ev_lens[ea])
                fb = (b - ev_cb[ea]) / max(1, ev_lens[ea])
                out.append((base + evs[ea]["offset"] / 1e7 + fa * evs[ea]["duration"] / 1e7,
                            base + evs[ea]["offset"] / 1e7 + fb * evs[ea]["duration"] / 1e7))
            else:
                fa = (a - ev_cb[ea]) / max(1, ev_lens[ea])
                fb = (b - ev_cb[eb]) / max(1, ev_lens[eb])
                out.append((base + evs[ea]["offset"] / 1e7 + fa * evs[ea]["duration"] / 1e7,
                            base + evs[eb]["offset"] / 1e7 + fb * evs[eb]["duration"] / 1e7))
        return out

    # last resort: proportional distribution across the paragraph audio
    total = sum(e["duration"] for e in evs) / 10_000_000 or 1.0
    chars = [len(s) for s in paras[n - 1]["zh"]]
    csum = sum(chars) or 1
    acc, out = base, []
    for c in chars:
        d = total * c / csum
        out.append((acc, acc + d))
        acc += d
    return out


def probe_duration(path: Path) -> float:
    return float(subprocess.check_output(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]
    ).decode().strip())


def timeline_offsets(intro_duration: float, source_narration_duration: float) -> tuple[float, float]:
    source_start = OPENING_S + intro_duration + SILENCE_S
    return source_start, source_start + source_narration_duration + SILENCE_S


def _hook_bounds(events: list[dict], duration: float) -> tuple[float, float]:
    events = validate_events(events, duration)
    start = events[0].get("offset", 0) / 10_000_000
    end = (events[-1].get("offset", 0) + events[-1].get("duration", 0)) / 10_000_000
    return start, max(start, min(duration, end))


def _append_hook(lines_bil: list[str], lines_kar: list[str], copy: dict,
                 events: list[dict], duration: float, start: float, role: str) -> None:
    rel_start, rel_end = _hook_bounds(events, duration)
    begin, end = ts(start + rel_start), ts(start + rel_end)
    dur = max(0.01, rel_end - rel_start)
    z, en = copy["zh"], copy["en"]
    lines_bil.extend((f"Dialogue: 0,{begin},{end},ZH,{role},420,200,0,,{z}",
                      f"Dialogue: 0,{begin},{end},EN,{role},420,200,170,,{en}"))
    lines_kar.extend((f"Dialogue: 0,{begin},{end},ZH,{role},420,200,0,,{karaoke_line(wrap_zh(z), dur, 'ZH')}",
                      f"Dialogue: 0,{begin},{end},EN,{role},420,200,170,,{karaoke_line(wrap_en(en), dur, 'EN')}"))


def cmd_timeline() -> None:
    paras = sorted(json.loads((P / "work/paras.json").read_text()), key=lambda p: int(p["para"]))
    events = {}
    for p in paras:
        n = p["para"]
        mp3 = P / "work/tts/zh" / f"para{n:02d}.mp3"
        evf = P / "work/tts/zh" / f"para{n:02d}.events.json"
        events[n] = validate_events(json.loads(evf.read_text()), probe_duration(mp3))

    # Local source positions mirror cmd_audio: gaps occur between paragraphs only.
    para_start, source_duration, t = {}, 0.0, 0.0
    for index, p in enumerate(paras):
        n = int(p["para"])
        para_start[n] = t
        t += probe_duration(P / "work/tts/zh" / f"para{n:02d}.mp3")
        if index < len(paras) - 1:
            t += SILENCE_S
    source_duration = t

    hooks = ensure_hooks()
    intro_mp3 = P / "work/tts/hooks/intro.mp3"
    ending_mp3 = P / "work/tts/hooks/ending.mp3"
    intro_duration = probe_duration(intro_mp3)
    source_start, ending_start = timeline_offsets(intro_duration, source_duration)
    lines_bil, lines_kar = [], []
    _append_hook(lines_bil, lines_kar, hooks["intro"],
                 json.loads((intro_mp3.with_suffix(".events.json")).read_text()),
                 intro_duration, OPENING_S, HOOK_INTRO)
    for p in paras:
        n = int(p["para"])
        times = sent_times(n, paras, events, para_start)
        for i, (z, e) in enumerate(zip(p["zh"], p["en"])):
            start, end = times[i]
            zs, es = ts(source_start + start), ts(source_start + end)
            zb, eb = karaoke_line(wrap_zh(z), end - start, "ZH"), karaoke_line(wrap_en(e), end - start, "EN")
            lines_bil.extend((f"Dialogue: 0,{zs},{es},ZH,{SOURCE},420,200,0,,{z}", f"Dialogue: 0,{zs},{es},EN,{SOURCE},420,200,170,,{e}"))
            lines_kar.extend((f"Dialogue: 0,{zs},{es},ZH,{SOURCE},420,200,0,,{zb}", f"Dialogue: 0,{zs},{es},EN,{SOURCE},420,200,170,,{eb}"))
    ending_duration = probe_duration(ending_mp3)
    _append_hook(lines_bil, lines_kar, hooks["ending"],
                 json.loads((ending_mp3.with_suffix(".events.json")).read_text()),
                 ending_duration, ending_start, HOOK_ENDING)
    subs = P / "subs"
    subs.mkdir(parents=True, exist_ok=True)
    (subs / "bilingual.ass").write_text(ASS_HEADER + "\n".join(lines_bil))
    (subs / "karaoke_follow_gold.ass").write_text(ASS_HEADER + "\n".join(lines_kar))
    print(f"timeline ok: {len(lines_bil)} events, source_start={source_start:.3f}s ending_start={ending_start:.3f}s")


# ---------------- audio ----------------

def cmd_audio() -> None:
    paras = sorted(json.loads((P / "work/paras.json").read_text()), key=lambda p: int(p["para"]))
    build = P / "work/audio_build"
    build.mkdir(parents=True, exist_ok=True)
    silence = build / "silence.wav"
    if not silence.exists():
        run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
             "anullsrc=r=24000:cl=mono", "-t", str(SILENCE_S), silence])
    concat = build / "concat.txt"
    entries = []
    hook_dir = P / "work/tts/hooks"
    for name in ("intro",):
        mp3, wav = hook_dir / f"{name}.mp3", build / f"{name}.wav"
        if not wav.exists() or wav.stat().st_mtime < mp3.stat().st_mtime:
            run([FFMPEG, "-y", "-loglevel", "error", "-i", mp3, "-ar", "24000", "-ac", "1", wav])
        entries.extend((wav, silence))
    for index, p in enumerate(paras):
        n = int(p["para"])
        wav, mp3 = build / f"para{n:02d}.wav", P / "work/tts/zh" / f"para{n:02d}.mp3"
        if not wav.exists() or wav.stat().st_mtime < mp3.stat().st_mtime:
            run([FFMPEG, "-y", "-loglevel", "error", "-i", mp3, "-ar", "24000", "-ac", "1", wav])
        entries.append(wav)
        if index < len(paras) - 1:
            entries.append(silence)
    ending_mp3, ending_wav = hook_dir / "ending.mp3", build / "ending.wav"
    if not ending_wav.exists() or ending_wav.stat().st_mtime < ending_mp3.stat().st_mtime:
        run([FFMPEG, "-y", "-loglevel", "error", "-i", ending_mp3, "-ar", "24000", "-ac", "1", ending_wav])
    entries.extend((silence, ending_wav))
    # Preserve the legacy four-second tail slot; render/music mixing is Task 4.
    tail = build / "music_tail.wav"
    if not tail.exists():
        run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
             "anullsrc=r=24000:cl=mono", "-t", str(MUSIC_TAIL_S), tail])
    entries.append(tail)
    concat.write_text("".join(f"file '{x}'\n" for x in entries))
    master = P / "audio/master.wav"
    master.parent.mkdir(parents=True, exist_ok=True)
    run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", master])
    dur = subprocess.check_output([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", master]).decode().strip()
    print(f"audio ok: master.wav {dur}s")


# ---------------- renders ----------------

def render(kind: str, t: float, out: Path) -> None:
    require_render_assets()
    audio_dur = subprocess.check_output([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", P / "audio/master.wav"]).decode().strip()
    total = float(audio_dur) + OPENING_S
    bg_t = str(total - OPENING_S)
    if kind == "sample":
        bg_t = "12"
        total = 15.0
    vf = (
        f"[0:v]scale=1920:1080:flags=lanczos,format=yuv420p,setpts=PTS-STARTPTS[v0];"
        f"[1:v]scale=1920:1080:flags=lanczos,format=yuv420p,setpts=PTS-STARTPTS[v1];"
        f"[v0][v1]concat=n=2:v=1:a=0[vx];"
        f"[vx]subtitles=filename='{P / 'subs/karaoke_follow_gold.ass'}':fontsdir='{FONTSDIR}'[v];"
        f"[2:a]adelay={int(OPENING_S*1000)}|{int(OPENING_S*1000)},atrim=0:{total},asetpts=PTS-STARTPTS[a]"
    )
    partial = out.with_name(out.stem + ".partial.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "warning",
           "-loop", "1", "-t", str(OPENING_S), "-i", P / "assets/opening.png",
           "-loop", "1", "-t", bg_t, "-i", P / "assets/background.png",
           "-i", P / "audio/master.wav",
           "-filter_complex", vf, "-map", "[v]", "-map", "[a]", "-t", str(total),
           "-c:v", "libx264", "-preset", "medium" if kind == "full" else "veryfast",
           "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", partial]
    run(cmd)
    partial.replace(out)
    print(f"{kind} render ok: {out} ({out.stat().st_size} bytes)")


def cmd_sample() -> None:
    allowed = {"approved", "auto-approved"} if os.environ.get("AUTO_MODE") == "1" else {"approved"}
    if (P / "work/sample_approval.txt").exists() and (P / "work/sample_approval.txt").read_text().strip() in allowed:
        raise SystemExit("sample already approved; run full when ready")
    render("sample", 15.0, P / "output/sample15_gold.mp4")


def cmd_full() -> None:
    allowed = {"approved", "auto-approved"} if os.environ.get("AUTO_MODE") == "1" else {"approved"}
    if not (P / "work/sample_approval.txt").exists() or (P / "work/sample_approval.txt").read_text().strip() not in allowed:
        raise SystemExit("blocked; user must approve work/sample_approval.txt before full render")
    render("full", 0.0, P / "output/make_it_full.mp4")


# ---------------- spotcheck ----------------

def cmd_spotcheck() -> None:
    ass = (P / "subs/karaoke_follow_gold.ass").read_text()
    zh_lines = [l for l in ass.splitlines() if l.startswith("Dialogue:") and ",ZH,SOURCE," in l]
    paras = json.loads((P / "work/paras.json").read_text())
    events = {}
    for n in range(1, len(paras) + 1):
        evf = P / "work/tts/zh" / f"para{n:02d}.events.json"
        mp3 = P / "work/tts/zh" / f"para{n:02d}.mp3"
        events[n] = validate_events(json.loads(evf.read_text()), probe_duration(mp3))
    errors = []

    # --- real alignment audit: every subtitle start must match the actual
    # sentence audio position (sent_times resolves from real TTS events),
    # not a cumulative model. This is what catches voice/subtitle drift. ---
    def para_mp3_dur(n: int) -> float:
        return float(subprocess.check_output(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
             P / "work/tts/zh" / f"para{n:02d}.mp3"]).decode().strip())

    intro_duration = probe_duration(P / "work/tts/hooks/intro.mp3")
    intro_events = validate_events(json.loads((P / "work/tts/hooks/intro.events.json").read_text()), intro_duration)
    ending_duration = probe_duration(P / "work/tts/hooks/ending.mp3")
    ending_events = validate_events(json.loads((P / "work/tts/hooks/ending.events.json").read_text()), ending_duration)
    source_offset = OPENING_S + intro_duration + SILENCE_S
    source_duration = sum(para_mp3_dur(n) for n in range(1, len(paras) + 1)) + SILENCE_S * (len(paras) - 1)
    ending_start = source_offset + source_duration + SILENCE_S
    max_delta = 0.0
    audited = 0
    para_off = 0.0
    for n, p in enumerate(paras, 1):
        para_start_local = {n: para_off}
        times = sent_times(n, paras, events, para_start_local)
        previous_end = -1.0
        for i in range(len(p["zh"])):
            if audited >= len(zh_lines):
                errors.append("SOURCE subtitle lines are incomplete")
                break
            line = zh_lines[audited]
            m = re.match(r"Dialogue: 0,(\d+):(\d+):([\d.]+),", line)
            if not m:
                raise SystemExit(f"malformed ASS line: {line}")
            ass_st = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
            expected = source_offset + times[i][0]
            if times[i][1] <= times[i][0] or times[i][0] < previous_end:
                errors.append(f"SOURCE subtitle interval invalid in paragraph {n}")
            previous_end = times[i][1]
            delta = abs(ass_st - expected)
            max_delta = max(max_delta, delta)
            audited += 1
        para_off += para_mp3_dur(n) + SILENCE_S
    if max_delta > 0.1:
        errors.append(f"voice/subtitle alignment drift {max_delta:.3f}s > 0.1s")
    if audited != len(zh_lines) or audited != sum(len(p["zh"]) for p in paras):
        errors.append("SOURCE subtitle coverage is incomplete or duplicated")

    hook_lines = {role: [l for l in ass.splitlines() if l.startswith("Dialogue:") and f",{role}," in l]
                  for role in (HOOK_INTRO, HOOK_ENDING)}
    roles = [line.split(",", 9)[4] for line in ass.splitlines() if line.startswith("Dialogue:")]
    if (not roles or not all(role in roles for role in (HOOK_INTRO, SOURCE, HOOK_ENDING))
            or roles.index(HOOK_INTRO) > roles.index(SOURCE)
            or roles.index(SOURCE) > roles.index(HOOK_ENDING)):
        errors.append("subtitle roles are out of order")
    for role, expected_start, events_for_hook, duration in (
        (HOOK_INTRO, OPENING_S, intro_events, intro_duration),
        (HOOK_ENDING, ending_start, ending_events, ending_duration),
    ):
        if len(hook_lines[role]) != 2:
            errors.append(f"{role} subtitle pair missing or duplicated")
            continue
        rel_start, rel_end = _hook_bounds(events_for_hook, duration)
        starts = []
        ends = []
        for line in hook_lines[role]:
            fields = line.split(",", 9)
            starts.append(ass_time(fields[1]))
            ends.append(ass_time(fields[2]))
        if max(abs(s - (expected_start + rel_start)) for s in starts) > 0.1:
            errors.append(f"{role} start is not aligned to hook audio")
        if max(abs(e - (expected_start + rel_end)) for e in ends) > 0.1:
            errors.append(f"{role} end is not aligned to hook audio")

    audio_dur = float(subprocess.check_output(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         P / "audio/master.wav"]).decode().strip())

    def rms_at(sec: float) -> float:
        # ponytail: short TTS clips can place a checkpoint in a real inter-clip
        # gap; inspect a small neighborhood instead of treating that as silence.
        values = []
        for offset in (0.0, 0.5, 1.0, 1.5, 2.0):
            out = subprocess.check_output(
                [FFMPEG, "-v", "info", "-ss", str(sec + offset), "-t", "1", "-i", P / "audio/master.wav",
                 "-af", "astats=metadata=1:reset=0", "-f", "null", "-"],
                stderr=subprocess.STDOUT).decode()
            m = re.search(r"RMS level dB: (-?\d+\.?\d*)", out)
            if m:
                try:
                    values.append(float(m.group(1)))
                except ValueError:
                    pass
        return max(values, default=-99.0)

    checkpoints = {"start": 1.0, "middle": min(audio_dur - MUSIC_TAIL_S - 1.0, audio_dur / 2 + 5.0),
                   "end": max(1.0, audio_dur - MUSIC_TAIL_S - 1.0)}
    cps = []
    for label, sec in checkpoints.items():
        rms = rms_at(sec)
        cps.append({"label": label, "time": round(sec, 3), "rms_db": rms, "passed": rms > -60})
        if rms <= -60:
            errors.append(f"{label} checkpoint silent (rms {rms}dB)")
    manifest = {
        "ok": not errors,
        "final_video": str(P / "output/make_it_full.mp4"),
        "expected_tts_events": sum(len(p["zh"]) for p in paras),
        "subtitle_event_pairs": audited,
        "max_alignment_drift_s": round(max_delta, 3),
        "audio_duration_s": audio_dur,
        "checkpoints": cps,
        "errors": errors,
    }
    (P / "work/spotcheck.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps(manifest, indent=1))


# ---------------- caption QA ----------------

def cmd_caption_qa() -> None:
    ass = P / "subs/karaoke_follow_gold.ass"
    video = P / "output/make_it_full.mp4"
    ocr_python = os.environ.get("PADDLEOCR_PYTHON", sys.executable)
    result = subprocess.run([
        ocr_python, str(ROOT / "scripts/caption_qa.py"),
        "--video", str(video), "--ass", str(ass),
        "--out", str(P / "work/caption_qa.json"),
    ])
    sys.exit(result.returncode)


# ---------------- preflight ----------------

def cmd_preflight() -> None:
    checks = []
    def ck(name: str, ok: bool, note: str = "") -> None:
        checks.append((name, ok, note))
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {note}")
    def approved(name: str) -> bool:
        path = P / "work" / name
        allowed = {"approved", "auto-approved"} if os.environ.get("AUTO_MODE") == "1" else {"approved"}
        return path.exists() and path.read_text().strip() in allowed
    identity_ok = False
    try:
        gate = json.loads((P / "work/identity_gate.json").read_text())
        identity_ok = (gate.get("status") in {"approved", "auto-approved"}
                       and gate.get("reference") == "source/identity_reference.jpg"
                       and gate.get("assets") == ["assets/background.png", "assets/opening.png", "assets/cover.png"]
                       and (P / "source/identity_reference.jpg").exists())
    except (OSError, ValueError, json.JSONDecodeError):
        identity_ok = False
    ck("identity gate", identity_ok)
    ck("cover approved", approved("cover_approval.txt"))
    mode = P / "work/cover_typography_mode.txt"
    ck("typography mode", mode.exists() and mode.read_text().strip() == "model-typeset")
    manifest_path = P / "work/paras.json"
    manifest_data = []
    try:
        manifest_data = json.loads(manifest_path.read_text())
        en_blocks = [b for b in (P / "scripts/en.md").read_text().strip().split("\n\n") if b.strip()]
        zh_blocks = [b for b in (P / "scripts/zh.md").read_text().strip().split("\n\n") if b.strip()]
        manifest_ok = (isinstance(manifest_data, list) and all(isinstance(p, dict)
                                                               and set(p) == {"para", "zh", "en"}
                                                               and isinstance(p["para"], int)
                                                               and not isinstance(p["para"], bool)
                                                               for p in manifest_data)
                       and len(manifest_data) == len(en_blocks) == len(zh_blocks)
                       and [int(p.get("para", -1)) for p in manifest_data] == list(range(1, len(manifest_data) + 1))
                       and all(p.get("en") == sentences(e) and p.get("zh") == sentences(z)
                               for p, e, z in zip(manifest_data, en_blocks, zh_blocks)))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        manifest_ok = False
    ck("manifest", manifest_ok)
    expected = len(manifest_data) if manifest_ok else 0
    try:
        hook_path = P / "work/hooks.json"
        hooks_ok = hook_path.exists() and _valid_hooks(json.loads(hook_path.read_text()))
    except (OSError, ValueError, json.JSONDecodeError):
        hooks_ok = False
    ck("hooks manifest", hooks_ok)
    ck("hook audio", all((P / "work/tts/hooks" / f"{name}{suffix}").exists()
                          for name in ("intro", "ending") for suffix in (".mp3", ".events.json")))
    if hooks_ok:
        try:
            progress = json.loads((P / "work/tts/hooks/progress.json").read_text())
            hook_files_ok = (isinstance(progress, dict)
                             and all(progress.get(name) == "ok" for name in ("intro", "ending"))
                             and progress.get("hooks_fingerprint") == hooks_fingerprint(json.loads((P / "work/hooks.json").read_text())))
            for name in ("intro", "ending"):
                duration = probe_duration(P / "work/tts/hooks" / f"{name}.mp3")
                validate_events(json.loads((P / "work/tts/hooks" / f"{name}.events.json").read_text()), duration)
        except (OSError, ValueError, json.JSONDecodeError):
            hook_files_ok = False
    else:
        hook_files_ok = False
    ck("hook events valid", hook_files_ok)
    source_tts = [P / "work/tts/zh" / f"para{n:02d}.mp3" for n in range(1, expected + 1)]
    source_events = [P / "work/tts/zh" / f"para{n:02d}.events.json" for n in range(1, expected + 1)]
    try:
        source_events_ok = all(p.exists() for p in source_tts + source_events)
        for mp3, event_file in zip(source_tts, source_events):
            validate_events(json.loads(event_file.read_text()), probe_duration(mp3))
    except (OSError, ValueError, TypeError, json.JSONDecodeError, subprocess.CalledProcessError):
        source_events_ok = False
    ck("tts complete", source_events_ok)
    ck("timeline", (P / "subs/karaoke_follow_gold.ass").exists())
    ck("master audio", (P / "audio/master.wav").exists())
    ck("sample", (P / "output/sample15_gold.mp4").exists())
    ck("spotcheck", (P / "work/spotcheck.json").exists())
    if (P / "work/spotcheck.json").exists():
        ck("spotcheck ok", json.loads((P / "work/spotcheck.json").read_text()).get("ok") is True)
        artifacts = [P / "work/hooks.json", P / "work/tts/hooks/progress.json",
                     P / "work/tts/hooks/intro.mp3", P / "work/tts/hooks/intro.events.json",
                     P / "work/tts/hooks/ending.mp3", P / "work/tts/hooks/ending.events.json",
                     P / "subs/karaoke_follow_gold.ass", P / "audio/master.wav",
                     P / "output/make_it_full.mp4", P / "output/sample15_gold.mp4",
                     P / "scripts/en.md", P / "scripts/zh.md", P / "work/paras.json",
                     P / "assets/background.png", P / "assets/opening.png", P / "assets/cover.png",
                     P / "subs/bilingual.ass", P / "work/tts/zh/progress.json",
                     P / "work/cover_approval.txt", P / "work/cover_typography_mode.txt",
                     ROOT / "references/fixed-opening-hooks.json"]
        artifacts.extend((P / "work/tts/zh").glob("para*.mp3"))
        artifacts.extend((P / "work/tts/zh").glob("para*.events.json"))
        artifacts.extend((P / "work/tts/zh").glob("para*.word_events.json"))
        missing = [str(p) for p in artifacts if not p.exists()]
        ck("spotcheck inputs", not missing)
        if not missing:
            ck("spotcheck fresh", (P / "work/spotcheck.json").stat().st_mtime >= max(p.stat().st_mtime for p in artifacts))
    ck("final video", (P / "output/make_it_full.mp4").exists())
    if (P / "output/make_it_full.mp4").exists():
        try:
            streams = json.loads(subprocess.check_output([
                FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height",
                "-of", "json", P / "output/make_it_full.mp4",
            ]).decode()).get("streams", [])
            video_stream = next(s for s in streams if s.get("codec_type") == "video")
            audio_stream = next(s for s in streams if s.get("codec_type") == "audio")
            media_ok = (video_stream.get("width") == 1920 and video_stream.get("height") == 1080
                        and audio_stream.get("codec_name") == "aac")
        except (OSError, ValueError, TypeError, StopIteration, json.JSONDecodeError, subprocess.CalledProcessError):
            media_ok = False
        ck("final media format", media_ok)
    if (P / "output/make_it_full.mp4").exists() and (P / "audio/master.wav").exists():
        ck("final duration", abs(probe_duration(P / "output/make_it_full.mp4") - (OPENING_S + probe_duration(P / "audio/master.wav"))) <= 0.1)
    caption_qa = P / "work/caption_qa.json"
    ck("caption qa", caption_qa.exists())
    if caption_qa.exists():
        ck("caption qa ok", json.loads(caption_qa.read_text()).get("status") == "pass")
    ck("bilibili publish pack", (P / "publish/bilibili_title_recommendations.md").exists())
    sys.exit(0 if all(ok for _, ok, _ in checks) else 1)


CMDS = {"manifest": cmd_manifest, "tts": cmd_tts, "hooks-tts": cmd_hooks_tts, "timeline": cmd_timeline,
        "audio": cmd_audio, "sample": cmd_sample, "full": cmd_full,
        "spotcheck": cmd_spotcheck, "caption_qa": cmd_caption_qa, "preflight": cmd_preflight}

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in CMDS:
        CMDS[sys.argv[1]]()
    elif len(sys.argv) == 3 and sys.argv[1] == "manifest" and sys.argv[2] == "--no-hooks":
        cmd_manifest(no_hooks=True)
    else:
        raise SystemExit(f"usage: produce.py [{'|'.join(CMDS)}] (manifest also accepts --no-hooks)")
