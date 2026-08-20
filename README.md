# Video Transcription Skill

A portable Hermes skill for turning video URLs or local video files into timestamped transcripts, cleaned text, summaries, translations, and structured notes.

## What it does

- prefers native captions via `yt-dlp`;
- falls back to Whisper via Groq or OpenAI when captions are unavailable;
- extracts selected video frames with `ffmpeg` for visual context;
- removes rolling subtitle duplicates and formats timestamped text;
- guides the agent to distinguish transcript evidence, edited synthesis, and uncertain ASR.
- production visual workflows now enforce identity references, source-mechanism cover checks, model-typeset poster typography, and poster-grade Chinese thumbnail QA; see `references/cover-typography-policy.md`.

## Install for Hermes

```bash
git clone https://github.com/NeoWeb3Nova/video-transcription-skill.git ~/.hermes/skills/video-transcription
```

Restart Hermes or start a new session. The skill is then available automatically; it can also be loaded explicitly with `/skill video-transcription`.

Claude Code / pi: clone the repository into the agent's workspace. `AGENTS.md` and `CLAUDE.md` provide the adapter instructions; the agent must read `SKILL.md` before production. The workflow does not depend on Hermes-only commands.

## Dependencies

Linux/WSL:

```bash
sudo apt update
sudo apt install ffmpeg
uv venv .venv
uv pip install --python .venv/bin/python edge-tts yt-dlp
```

macOS:

```bash
brew install ffmpeg yt-dlp
```

Windows PowerShell:

```powershell
winget install Gyan.FFmpeg
a py -m pip install --user yt-dlp
```

Run the preflight from the cloned skill directory:

```bash
python3 ~/.hermes/skills/video-transcription/scripts/setup.py --json
```

## Optional Whisper fallback

Create `~/.config/watch/.env` and add your own key:

```env
GROQ_API_KEY=...
```

or:

```env
OPENAI_API_KEY=...
```

Keys are never included in this repository. Native captions work without an API key.

## Usage

```text
/watch https://example.com/video
```

For local files:

```text
/watch /absolute/path/to/video.mp4
```

The bundled script can also be run directly:

```bash
python3 ~/.hermes/skills/video-transcription/scripts/watch.py VIDEO --detail transcript
```

See `SKILL.md` for the complete workflow and quality rules.

## Bilingual video production pipeline

`scripts/produce.py` turns a normalized bilingual script pair (`scripts/en.md` + `scripts/zh.md`, paragraph-aligned) into a narrated karaoke video:

```bash
uv venv .venv && uv pip install --python .venv/bin/python edge-tts
.venv/bin/python scripts/produce.py manifest   # paragraph+sentence alignment check -> work/paras.json
.venv/bin/python scripts/produce.py tts        # edge-tts narration + sentence events (71 paragraphs, resumable)
.venv/bin/python scripts/produce.py hooks-tts  # default opening/ending hook narration + events
.venv/bin/python scripts/produce.py timeline   # bilingual ASS + karaoke ASS
.venv/bin/python scripts/produce.py audio      # concat narration -> audio/master.wav
.venv/bin/python scripts/produce.py sample     # 15s sample render (user approval gate)
.venv/bin/python scripts/produce.py full       # full render
.venv/bin/python scripts/produce.py spotcheck  # automatic sync audit -> work/spotcheck.json (ok:true)
.venv/bin/python scripts/produce.py caption_qa # OCR burned-subtitle audit -> work/caption_qa.json
.venv/bin/python scripts/produce.py preflight  # fail-closed gate report
```

The pipeline mirrors the proven run in `projects/youtube-977PU9FtGA0` (3s opening, 0.35s paragraph gaps, SentenceBoundary events, uniform karaoke `\k`, fontsdir `/mnt/c/Windows/Fonts`). Prerelease gates: cover approval (`work/cover_approval.txt`) and sample approval (`work/sample_approval.txt`) must be `approved`; the sync audit must pass before final preflight.

`caption_qa` prefers PaddleOCR PP-OCRv6 (`PADDLEOCR_PYTHON=/home/neo/.cache/video-transcription-ocr/venv/bin/python`) and falls back to Tesseract. It verifies burned subtitles from rendered frames. If OCR is unavailable, it writes `manual_review_required` and preflight fails closed instead of claiming visual verification.

## Portable end-to-end workflow

Bootstrap a project from a URL or local video:

```bash
python3 scripts/bootstrap_project.py https://www.youtube.com/watch?v=VIDEO_ID
```

Complete `scripts/zh.md`, complete and approve `work/visual_brief.md`, choose `work/image_mode.txt`, and provide approved `assets/background.png`, `assets/opening.png`, and independent `assets/cover.png`. New projects use the fixed bilingual hook layer by default (`manifest → tts → hooks-tts → timeline → audio`). Then render the gated 15-second sample:

```bash
python3 scripts/run_pipeline.py --project projects/youtube-VIDEO_ID --step prepare
```

After the user writes `approved` to `work/sample_approval.txt`, run the remaining gated pipeline:

```bash
PADDLEOCR_PYTHON=/home/neo/.cache/video-transcription-ocr/venv/bin/python \
PADDLEOCR_DEVICE=gpu:0 \
python3 scripts/run_pipeline.py --project projects/youtube-VIDEO_ID --step all
```

The runner stops at missing inputs and approval gates. It never fabricates visual assets or approval markers. If an agent has no image-generation capability, it must stop at the asset gate and request the approved uploads.

Hook layer: the opening hook is persisted per project in `work/hooks.json`; the ending uses one fixed combined action/follow CTA — `一键三连，关注我的账号，持续更新。行动起来，成为更好的自己。` — rendered with the same bilingual subtitle safe area and karaoke rules. The final sequence is opening, intro hook, source, combined ending hook, then the four-second music tail.

Auto image mode has separate rules for the two text-bearing assets: covers are complete model-typeset posters with no deterministic text overlay; openings reuse the approved background and use only a deterministic exact-text title layer (kicker, dominant Chinese title, English subline, byline) in the right safe area. An opening is not a second cover and must not contain the cover mechanism sequence.

## License

MIT
