---
name: video-transcription
version: "1.0.0"
description: Use when a user provides a video URL or local video and wants timestamped speech transcription, cleaned text, summary, translation, or structured notes.
argument-hint: "<video-url-or-path> [question]"
author: NeoWeb3Nova
license: MIT
metadata:
  hermes:
    tags: [video, transcription, subtitles, whisper, captions, notes]
    related_skills: [transcript-processing]
---

# Video Transcription

Turn a public video URL or local video into evidence-grounded, timestamped text. For production workflows, request a user-provided overview first and reconcile it with the linked video's metadata, captions, and visual evidence before downstream work.

## Workflow

1. Collect the user's overview before production. Save it as a project-level `source/user_overview.md`; if missing, stop before visual assets, translation, TTS, or rendering.

2. Run the preflight:

```bash
python3 "${SKILL_DIR}/scripts/setup.py" --json
```

`SKILL_DIR` is the absolute directory containing this file. If binaries are missing, run the installer and follow its platform-specific hints:

```bash
python3 "${SKILL_DIR}/scripts/setup.py"
```

3. Run the bundled extractor:

```bash
python3 "${SKILL_DIR}/scripts/watch.py" "<video-url-or-path>"
```

Use `--detail transcript` for transcript-only work, `--detail balanced` for normal speech + visual context, and `--start`/`--end` for a specific section.

4. Use the report's timestamped transcript as the source text. If frame paths are listed, inspect the relevant frames with the host's image/vision tool before making claims about on-screen content.

5. Reconcile the overview with the YouTube title, metadata, transcript, and relevant frames. Save `work/content_reconciliation.md` with `confirmed`, `overview_only`, `source_only`, and `conflict` sections. Resolve all conflicts before production; do not treat overview-only claims as source quotations.

6. If the workflow includes generated visual assets, create `work/visual_brief.md` before any image call. The brief must state the source mechanism, approved title, identity references, supported visual metaphors, and forbidden interpretations. For an identity-bearing subject, pass the source portrait/thumbnail and the strongest approved project asset as `reference_image_urls`; never substitute soft wording such as `Jim Rohn-like` or `mature motivational speaker` for identity control.

7. Apply two visual hard gates before audio or rendering:

- **Identity gate:** compare every generated subject against the references. If it reads as a generic substitute or changes critical observable cues, reject it even when dimensions and composition pass.
- **Cover-to-topic gate:** the cover must show the source's causal mechanism, not merely its mood. For problem-solving content, require a visible chain such as `problem fragments -> calm analysis -> solution route`; a generic road, staircase, or inspirational portrait fails.

For Chinese covers, use a deterministic text layer when exact wording matters. Treat the cover as a promotional poster, not a subtitle overlay: use a small kicker/section marker, a dominant headline with intentional line breaks and contrasting emphasis, one subordinate supporting line, and at most one thematic auxiliary sequence such as `问题 -> 冷静分析 -> 解决方案`. Align the system to a visible grid with an anchor rule or divider. Inspect the final raster at full size and 320x180; exact but tiny, flat, clipped, low-contrast, or subordinate title text fails. Keep user approval pending until the actual thumbnail is approved.

8. Clean and structure the transcript:

- remove rolling subtitle duplicates, filler loops, and broken line wrapping;
- restore punctuation and coherent paragraphs;
- preserve timestamps for important claims;
- mark uncertain recognition as `[unclear]` or `[疑似：...]` instead of inventing words;
- distinguish verbatim quotes from edited summaries;
- translate directly with the language model when requested; do not install translation libraries.

9. Choose the requested output:

- full cleaned transcript;
- transcript plus summary and key points;
- interview Q&A;
- meeting notes and action items;
- article or learning notes;
- original transcript plus translation.

## Transcription sources

The script prefers native captions from `yt-dlp`. If captions are unavailable, it extracts mono 16 kHz audio with `ffmpeg` and can use Whisper through Groq or OpenAI.

Configure optional fallback keys in `~/.config/watch/.env`:

```env
GROQ_API_KEY=...
OPENAI_API_KEY=...
```

Do not commit this file or share API keys. Without a key, videos with no native captions can still be inspected visually, but speech transcription may be unavailable.

## Commands

```bash
# Transcript only
python3 "${SKILL_DIR}/scripts/watch.py" VIDEO --detail transcript

# Normal balanced pass
python3 "${SKILL_DIR}/scripts/watch.py" VIDEO --detail balanced

# Focus on a range
python3 "${SKILL_DIR}/scripts/watch.py" VIDEO --start 00:45 --end 02:00

# Disable external Whisper fallback
python3 "${SKILL_DIR}/scripts/watch.py" VIDEO --no-whisper
```

## Output quality rules

- Do not present ASR output as exact quotation unless verified against the audio.
- Preserve source URL/path, language, speakers if known, transcript source, and uncertainty notes.
- For long videos, process a named section first rather than spending tokens on a sparse full scan.
- Do not claim that a transcript exists when captions and ASR both failed; report the limitation.

## Runtime files

The scripts write temporary downloads, extracted audio, subtitles, and frames under a temporary working directory unless `--out-dir` is supplied. Delete the working directory after follow-up questions are finished.

See `references/` for Chinese ASR cleanup, subtitle ingestion, YouTube formatting, and content-library patterns.
