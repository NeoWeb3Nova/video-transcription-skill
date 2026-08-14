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

6. Clean and structure the transcript:

- remove rolling subtitle duplicates, filler loops, and broken line wrapping;
- restore punctuation and coherent paragraphs;
- preserve timestamps for important claims;
- mark uncertain recognition as `[unclear]` or `[疑似：...]` instead of inventing words;
- distinguish verbatim quotes from edited summaries;
- translate directly with the language model when requested; do not install translation libraries.

7. Choose the requested output:

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
