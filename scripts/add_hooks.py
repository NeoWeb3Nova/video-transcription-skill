#!/usr/bin/env python3
"""Add the persisted editorial hooks around the existing source pipeline."""
from __future__ import annotations
import asyncio, json, re, subprocess, sys
from pathlib import Path
import edge_tts

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "projects" / "youtube-csT_7txNnOQ"
FFMPEG = ROOT / "tools/ffmpeg-static/bin/ffmpeg"
FFPROBE = ROOT / "tools/ffmpeg-static/bin/ffprobe"
FONTSDIR = "/mnt/c/Windows/Fonts"
VOICE = "zh-CN-YunjianNeural"

FIXED_OUTRO = {
    "zh": "一键三连，关注我的账号，持续更新。行动起来，成为更好的自己。",
    "en": "Like, share, and follow my account for continuous updates. Take action and become a better version of yourself.",
}
OPENING = 3.0
GAP = 0.35


def run(cmd):
    subprocess.run([str(x) for x in cmd], check=True)


def dur(path: Path) -> float:
    return float(subprocess.check_output([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).decode().strip())


def ts(sec: float) -> str:
    h, rem = divmod(max(0.0, sec), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


async def synth(name: str, text: str) -> Path:
    out = P / "work/tts/zh" / f"{name}.mp3"
    events = P / "work/tts/zh" / f"{name}.events.json"
    if not out.exists() or not events.exists():
        comm = edge_tts.Communicate(text, VOICE)
        got = []
        with out.open("wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] in {"WordBoundary", "SentenceBoundary"}:
                    got.append({"offset": chunk["offset"], "duration": chunk["duration"], "text": chunk["text"]})
        events.write_text(json.dumps(got, ensure_ascii=False, indent=1))
    return out


def wrap_zh(text: str, width: int = 13) -> str:
    return "\\N".join(text[i:i + width] for i in range(0, len(text), width))


def wrap_en(text: str, width: int = 8) -> str:
    words = text.split()
    return "\\N".join(" ".join(words[i:i + width]) for i in range(0, len(words), width))


def karaoke(text: str, duration: float, lang: str) -> str:
    parts = text.split("\\N")
    units = [list(p) for p in parts] if lang == "ZH" else [p.split() for p in parts]
    total = sum(len(p) for p in units) or 1
    per = max(1, round(duration * 100 / total))
    if lang == "ZH":
        return "\\N".join("".join(f"{{\\k{per}}}{u}" for u in part) for part in units)
    return "\\N".join(" ".join(f"{{\\k{per}}}{u}" for u in part) for part in units)


def hook_lines(name: str, start: float, zh: str, en: str) -> list[str]:
    """Render hooks as normal subtitle-sized sentence events, not one giant card."""
    events = json.loads((P / "work/tts/zh" / f"{name}.events.json").read_text())
    zh_parts = [e["text"] for e in events]
    raw_en = re.split(r"(?<=[.!?])\s+", en.strip())
    if len(raw_en) == len(zh_parts):
        en_parts = raw_en
    else:
        # Keep source order when English punctuation is finer than the
        # Chinese TTS event (for example, "Now what?" after one Chinese cue).
        en_parts = [" ".join(raw_en[round(i * len(raw_en) / len(zh_parts)):round((i + 1) * len(raw_en) / len(zh_parts))])
                    for i in range(len(zh_parts))]
    lines = []
    for event, z, e in zip(events, zh_parts, en_parts):
        a = start + event["offset"] / 10_000_000
        b = a + event["duration"] / 10_000_000
        lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},ZH,,420,200,0,,{karaoke(wrap_zh(z), b-a, 'ZH')}")
        lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},EN,,420,200,170,,{karaoke(wrap_en(e), b-a, 'EN')}")
    return lines


def shift_ass(src: Path, dst: Path, offset: float, hooks: list[tuple[str, float, str, str]]) -> None:
    text = src.read_text(encoding="utf-8-sig")
    out = []
    pat = re.compile(r"^(Dialogue: 0,)(\d+):(\d+):([\d.]+),(\d+):(\d+):([\d.]+),(.*)$")
    for line in text.splitlines():
        m = pat.match(line)
        if m and not line.startswith("Dialogue: 0,0:00:00"):
            a = int(m[2])*3600 + int(m[3])*60 + float(m[4]) + offset
            b = int(m[5])*3600 + int(m[6])*60 + float(m[7]) + offset
            line = f"{m[1]}{ts(a)},{ts(b)},{m[8]}"
        out.append(line)
    for name, start, zh, en in hooks:
        out.extend(hook_lines(name, start, zh, en))
    dst.write_text("\ufeff" + "\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    hooks = json.loads((P / "work/hooks.json").read_text())
    hooks["outro"] = FIXED_OUTRO
    intro = asyncio.run(synth("hook_intro", hooks["intro"]["zh"]))
    outro = asyncio.run(synth("hook_outro", hooks["outro"]["zh"]))
    source = P / "audio/master.wav"
    source_d = dur(source)
    intro_d, outro_d = map(dur, [intro, outro])
    build = P / "work/hooks_audio"
    build.mkdir(exist_ok=True)
    silence = build / "silence.wav"
    tail = build / "tail.wav"
    run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(GAP), silence])
    run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "4", tail])
    wavs = []
    for i, mp3 in enumerate([intro, source, outro]):
        w = build / f"{i:02d}.wav"
        run([FFMPEG, "-y", "-loglevel", "error", "-i", mp3, "-ar", "24000", "-ac", "1", w])
        wavs.append(w)
    entries = [wavs[0], silence, wavs[1], silence, wavs[2], tail]
    concat = build / "concat.txt"
    concat.write_text("".join(f"file '{x}'\n" for x in entries))
    master = P / "audio/master_hooks.wav"
    run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", master])

    source_offset = intro_d + GAP
    outro_start = OPENING + source_offset + source_d + GAP
    ass_hooks = [("hook_intro", OPENING, hooks["intro"]["zh"], hooks["intro"]["en"]),
                 ("hook_outro", outro_start, hooks["outro"]["zh"], hooks["outro"]["en"])]
    shift_ass(P / "subs/karaoke_follow_gold.ass", P / "subs/karaoke_hooks.ass", source_offset, ass_hooks)

    audio_d = dur(master)
    vf = (f"[0:v]scale=1920:1080,format=yuv420p,setpts=PTS-STARTPTS[v0];"
          f"[1:v]scale=1920:1080,format=yuv420p,setpts=PTS-STARTPTS[v1];"
          f"[v0][v1]concat=n=2:v=1:a=0[vx];"
          f"[vx]subtitles=filename='{P / 'subs/karaoke_hooks.ass'}':fontsdir='{FONTSDIR}'[v];"
          f"[2:a]adelay=3000|3000,atrim=0:{audio_d+OPENING},asetpts=PTS-STARTPTS[a]")
    def render(name, seconds=None):
        total = 15.0 if seconds else audio_d + OPENING
        bg = 12.0 if seconds else audio_d
        out = P / "output" / name
        partial = out.with_name(out.stem + ".partial.mp4")
        run([FFMPEG, "-y", "-loglevel", "warning", "-loop", "1", "-t", str(OPENING), "-i", P / "assets/opening.png",
             "-loop", "1", "-t", str(bg), "-i", P / "assets/background.png", "-i", master,
             "-filter_complex", vf, "-map", "[v]", "-map", "[a]", "-t", str(total), "-c:v", "libx264",
             "-preset", "veryfast" if seconds else "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", partial])
        partial.replace(out)
        print(name, out.stat().st_size, "bytes", dur(out), "seconds")
    render("sample15_hooks.mp4", 15)
    render("jim_rohn_5_habits_full.mp4")
    (P / "work/hooks_manifest.json").write_text(json.dumps({"ok": True, "intro_duration_s": intro_d, "source_duration_s": source_d, "outro_duration_s": outro_d, "master_duration_s": audio_d, "source_offset_s": source_offset, "outro_start_s": outro_start}, indent=1))


if __name__ == "__main__":
    main()
