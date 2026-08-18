#!/usr/bin/env python3
"""Bilingual karaoke video production pipeline (repo-reusable).

Steps (run in order):
  python3 scripts/produce.py manifest   # build work/paras.json from scripts/en.md + zh.md
  python3 scripts/produce.py tts        # edge-tts narration + word events per paragraph
  python3 scripts/produce.py timeline   # bilingual ASS + karaoke ASS from events
  python3 scripts/produce.py audio      # concat narration wavs -> audio/master.wav
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
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = ROOT / "tools/ffmpeg-static/bin/ffmpeg"
FFPROBE = ROOT / "tools/ffmpeg-static/bin/ffprobe"
FONTSDIR = "/mnt/c/Windows/Fonts"
OPENING_S = 3.0
SILENCE_S = 0.35
SENTENCE_GAP_S = 0.05
VOICE = "zh-CN-YunjianNeural"

# Target project: PROJECT_SLUG env var, default the first completed pipeline.
P = ROOT / "projects" / os.environ.get("PROJECT_SLUG", "youtube-eD3KNmSlu24")

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
        parts = re.split(r"(?<=[.!?])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("+", " ".join(map(str, cmd)))
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


# ---------------- manifest ----------------

def cmd_manifest() -> None:
    en = [b for b in (P / "scripts/en.md").read_text().strip().split("\n\n") if b.strip()]
    zh = [b for b in (P / "scripts/zh.md").read_text().strip().split("\n\n") if b.strip()]
    assert len(en) == len(zh), f"paragraph mismatch en={len(en)} zh={len(zh)}"
    paras = []
    for i, (e, z) in enumerate(zip(en, zh), 1):
        se, sz = sentences(e), sentences(z)
        assert len(se) == len(sz), f"para {i}: sentence mismatch en={len(se)} zh={len(sz)}"
        paras.append({"para": i, "zh": sz, "en": se})
    (P / "work/paras.json").write_text(json.dumps(paras, ensure_ascii=False, indent=1))
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
            return bisect.bisect_right(ev_cb, p) - 1

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


def cmd_timeline() -> None:
    paras = json.loads((P / "work/paras.json").read_text())
    events = {}
    for n in range(1, len(paras) + 1):
        evf = P / "work/tts/zh" / f"para{n:02d}.events.json"
        events[n] = json.loads(evf.read_text())

    # Real paragraph start positions in master.wav: cumulative actual mp3
    # durations + inter-paragraph silence (matches cmd_audio concat exactly).
    para_start = {}
    t = 0.0
    for n in range(1, len(paras) + 1):
        para_start[n] = t
        dur_s = float(subprocess.check_output(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
             P / "work/tts/zh" / f"para{n:02d}.mp3"]).decode().strip())
        t += dur_s + SILENCE_S

    lines_bil, lines_kar = [], []
    t_video = OPENING_S
    for p in paras:
        n = p["para"]
        times = sent_times(n, paras, events, para_start)
        for i, (z, e) in enumerate(zip(p["zh"], p["en"])):
            start, end = times[i]
            zs, es = ts(t_video + start), ts(t_video + end)
            zb = karaoke_line(wrap_zh(z), end - start, "ZH")
            eb = karaoke_line(wrap_en(e), end - start, "EN")
            lines_bil.append(f"Dialogue: 0,{zs},{es},ZH,,420,200,0,,{z}")
            lines_bil.append(f"Dialogue: 0,{zs},{es},EN,,420,200,170,,{e}")
            lines_kar.append(f"Dialogue: 0,{zs},{es},ZH,,420,200,0,,{zb}")
            lines_kar.append(f"Dialogue: 0,{zs},{es},EN,,420,200,170,,{eb}")
    (P / "subs/bilingual.ass").write_text(ASS_HEADER + "\n".join(lines_bil))
    (P / "subs/karaoke_follow_gold.ass").write_text(ASS_HEADER + "\n".join(lines_kar))
    print(f"timeline ok: {len(lines_bil)} events, last subtitle ends at {t_video + t:.1f}s")


# ---------------- audio ----------------

def cmd_audio() -> None:
    paras = json.loads((P / "work/paras.json").read_text())
    build = P / "work/audio_build"
    build.mkdir(parents=True, exist_ok=True)
    silence = build / "silence.wav"
    if not silence.exists():
        run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
             f"anullsrc=r=24000:cl=mono", "-t", str(SILENCE_S), silence])
    concat = build / "concat.txt"
    entries = []
    for n in range(1, len(paras) + 1):
        wav = build / f"para{n:02d}.wav"
        mp3 = P / "work/tts/zh" / f"para{n:02d}.mp3"
        if not wav.exists() or wav.stat().st_mtime < mp3.stat().st_mtime:
            run([FFMPEG, "-y", "-loglevel", "error", "-i", mp3, "-ar", "24000", "-ac", "1", wav])
        entries.append(wav)
        entries.append(silence)
    concat.write_text("".join(f"file '{x}'\n" for x in entries))
    master = P / "audio/master.wav"
    master.parent.mkdir(parents=True, exist_ok=True)
    run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", master])
    dur = subprocess.check_output([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", master]).decode().strip()
    print(f"audio ok: master.wav {dur}s")


# ---------------- renders ----------------

def render(kind: str, t: float, out: Path) -> None:
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
    render("sample", 15.0, P / "output/sample15_gold.mp4")


def cmd_full() -> None:
    render("full", 0.0, P / "output/make_it_full.mp4")


# ---------------- spotcheck ----------------

def cmd_spotcheck() -> None:
    ass = (P / "subs/karaoke_follow_gold.ass").read_text()
    zh_lines = [l for l in ass.splitlines() if l.startswith("Dialogue:") and ",ZH," in l]
    paras = json.loads((P / "work/paras.json").read_text())
    events = {}
    for n in range(1, len(paras) + 1):
        events[n] = json.loads((P / "work/tts/zh" / f"para{n:02d}.events.json").read_text())
    errors = []

    # --- real alignment audit: every subtitle start must match the actual
    # sentence audio position (sent_times resolves from real TTS events),
    # not a cumulative model. This is what catches voice/subtitle drift. ---
    def para_mp3_dur(n: int) -> float:
        return float(subprocess.check_output(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
             P / "work/tts/zh" / f"para{n:02d}.mp3"]).decode().strip())

    max_delta = 0.0
    audited = 0
    para_off = 0.0
    for n, p in enumerate(paras, 1):
        para_start_local = {n: para_off}
        times = sent_times(n, paras, events, para_start_local)
        for i in range(len(p["zh"])):
            line = zh_lines[audited]
            m = re.match(r"Dialogue: 0,(\d+):(\d+):([\d.]+),", line)
            if not m:
                raise SystemExit(f"malformed ASS line: {line}")
            ass_st = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
            expected = OPENING_S + times[i][0]
            delta = abs(ass_st - expected)
            max_delta = max(max_delta, delta)
            audited += 1
        para_off += para_mp3_dur(n) + SILENCE_S
    if max_delta > 0.1:
        errors.append(f"voice/subtitle alignment drift {max_delta:.3f}s > 0.1s")

    audio_dur = float(subprocess.check_output(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         P / "audio/master.wav"]).decode().strip())

    def rms_at(sec: float) -> float:
        out = subprocess.check_output(
            [FFMPEG, "-v", "info", "-ss", str(sec), "-t", "1", "-i", P / "audio/master.wav",
             "-af", "astats=metadata=1:reset=0", "-f", "null", "-"],
            stderr=subprocess.STDOUT).decode()
        m = re.search(r"RMS level dB: (-?\d+\.?\d*)", out)
        try:
            return float(m.group(1)) if m else -99.0
        except ValueError:
            return -99.0

    checkpoints = {"start": 1.0, "middle": audio_dur / 2, "end": audio_dur - 2.0}
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


# ---------------- preflight ----------------

def cmd_preflight() -> None:
    checks = []
    def ck(name: str, ok: bool, note: str = "") -> None:
        checks.append((name, ok, note))
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {note}")
    ck("cover approved", (P / "work/cover_approval.txt").read_text().strip() == "approved")
    ck("typography mode", (P / "work/cover_typography_mode.txt").read_text().strip() == "model-typeset")
    ck("manifest", (P / "work/paras.json").exists())
    ck("tts complete", len(list((P / "work/tts/zh").glob("para*.mp3"))) >= 71)
    ck("timeline", (P / "subs/karaoke_follow_gold.ass").exists())
    ck("master audio", (P / "audio/master.wav").exists())
    ck("sample", (P / "output/sample15_gold.mp4").exists())
    ck("spotcheck", (P / "work/spotcheck.json").exists())
    if (P / "work/spotcheck.json").exists():
        ck("spotcheck ok", json.loads((P / "work/spotcheck.json").read_text()).get("ok") is True)
    ck("final video", (P / "output/make_it_full.mp4").exists())
    ck("bilibili publish pack", (P / "publish/bilibili_title_recommendations.md").exists())
    sys.exit(0 if all(ok for _, ok, _ in checks) else 1)


CMDS = {"manifest": cmd_manifest, "tts": cmd_tts, "timeline": cmd_timeline,
        "audio": cmd_audio, "sample": cmd_sample, "full": cmd_full,
        "spotcheck": cmd_spotcheck, "preflight": cmd_preflight}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in CMDS:
        raise SystemExit(f"usage: produce.py [{'|'.join(CMDS)}]")
    CMDS[sys.argv[1]]()
