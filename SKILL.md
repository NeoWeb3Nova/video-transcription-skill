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

6. If the workflow includes generated visual assets, create `work/visual_brief.md` before any image call. The brief must state the source mechanism, approved title, identity references, supported visual metaphors, and forbidden interpretations. For an identity-bearing subject, persist `source/identity_reference.jpg`, pass it through `reference_image_urls`, and never substitute soft wording such as `Jim Rohn-like` or `mature motivational speaker` for identity control. Create `work/identity_gate.json` as `pending` before generation; only set it to `auto-approved` after side-by-side inspection of background, opening, and cover against the reference.

7. Apply two visual hard gates before audio or rendering:

- **Identity gate:** compare every generated subject against the references. If it reads as a generic substitute or changes critical observable cues, reject it even when dimensions and composition pass.
- **Cover-to-topic gate:** the cover must show the source's causal mechanism, not merely its mood. For problem-solving content, require a visible chain such as `problem fragments -> calm analysis -> solution route`; a generic road, staircase, or inspirational portrait fails.

For Chinese covers, always use a model-typeset poster. The image model must art-direct and render the display lettering as part of the complete advertising composition: deliberate line breaks, scale rhythm, grid, framing rules, badges, editorial markers, and restrained dimensional treatment. Provide every exact required string, forbid random text, preserve the source mechanism and identity, then inspect the full raster character-by-character and at 320x180. Do not generate a text-free cover background and add a fixed-font Pillow, SVG, ImageMagick, or FFmpeg overlay; deterministic overlays are prohibited on covers even when the wording is exact. Deterministic text remains allowed only for opening/title cards or non-cover subtitle-safe layers. Every cover must use a small kicker/section marker, a dominant headline, one subordinate supporting line, and at most one mechanism-reinforcing auxiliary sequence such as `问题 -> 冷静分析 -> 解决方案`. For Jim Rohn works, also include a visible but subordinate identity byline such as `JIM ROHN` or `吉姆·罗恩励志演讲`, integrated with a divider or small attribution block. The text must have a designed relationship to the artwork; do not merely fill an empty right-side zone. Exact but tiny, flat, clipped, low-contrast, or subordinate title text fails. Persist `work/cover_typography_mode.txt` as `model-typeset` before generation and keep user approval pending until the actual thumbnail is approved. See `references/cover-typography-policy.md`.

8. Clean and structure the transcript:

- remove rolling subtitle duplicates, filler loops, and broken line wrapping;
- restore punctuation and coherent paragraphs;
- preserve timestamps for important claims;
- mark uncertain recognition as `[unclear]` or `[疑似：...]` instead of inventing words;
- distinguish verbatim quotes from edited summaries;
- translate with the active Hermes model via `scripts/translate_with_hermes.py`; do not use Argos Translate for production copy.

9. Choose the requested output:

- full cleaned transcript;
- transcript plus summary and key points;
- interview Q&A;
- meeting notes and action items;
- article or learning notes;
- original transcript plus translation.

## Transcription sources

`yt-dlp` records caption provenance from its `subtitles` and
`automatic_captions` metadata. Declared manual English captions are preferred
and marked `youtube_manual`. Automatic captions are never production truth:
the bootstrap extracts local 16 kHz mono audio and re-transcribes it with the
isolated local `faster-whisper` large-v3 model when available, otherwise with
`whisper-large-v3` through Groq or `whisper-1` through OpenAI. It saves
`source/raw/whisper.en.json` and marks the project `local_whisper`,
`whisper_groq`, or `whisper_openai`. The production gate
rejects `youtube_auto` projects so raw automatic captions cannot silently reach
translation, TTS, or rendering.

The ASR segment boundaries are authoritative for bilingual alignment. Bootstrap
persists them as `work/source_timing.json`; Hermes translates each segment in
order without merging across boundaries. TTS may have different absolute
durations, so rendered subtitle timing still follows the real generated audio,
while the original segment structure remains one-to-one.

If captions are unavailable, the same Whisper fallback is used when an API key
is configured. Local/remote transcription must remain auditable in
`source/metadata.json`; missing credentials fail closed instead of using an
unverified automatic track.

Configure optional fallback keys in `~/.config/watch/.env`:

```env
GROQ_API_KEY=...
OPENAI_API_KEY=...
```

Do not commit this file or share API keys. Without a key, videos with no native captions can still be inspected visually, but speech transcription may be unavailable.

### Local ASR setup

For offline production on an NVIDIA GPU, install the isolated backend once:

```bash
uv venv /home/neo/.cache/video-transcription-asr/venv --python python3.12
uv pip install --python /home/neo/.cache/video-transcription-asr/venv/bin/python faster-whisper
```

The default model is `large-v3`, using CUDA `int8_float16` on the RTX 4060
class GPU. `scripts/local_asr.py` extracts 16 kHz mono PCM audio with the
repository FFmpeg binary and writes word-timestamped JSON. Set
`LOCAL_ASR_PYTHON`, `ASR_MODEL`, `ASR_DEVICE`, or `ASR_COMPUTE_TYPE` only when
the default local backend needs to be changed.

### Optional local TTS backend

Edge TTS remains the default. After deploying the isolated CosyVoice2
environment and model, opt in per run with:

```bash
TTS_BACKEND=cosyvoice \
COSYVOICE_PYTHON=/home/neo/.cache/cosyvoice/venv/bin/python \
COSYVOICE_ROOT=/home/neo/.cache/cosyvoice/CosyVoice \
COSYVOICE_MODEL_DIR=/home/neo/.cache/cosyvoice/models/CosyVoice2-0.5B \
python3 scripts/run_pipeline.py --project projects/<slug> --step prepare --auto
```

`scripts/cosyvoice_tts.py` generates each Chinese sentence separately and
records its real duration, so local TTS preserves the existing subtitle timing
contract. Set `COSYVOICE_PROMPT_AUDIO` and `COSYVOICE_PROMPT_TEXT` to choose a
consented reference voice. Omit `TTS_BACKEND` or set it to `edge` to keep the
current `zh-CN-YunjianNeural` path.

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

## Portable production extension

Use this extension when the repository is used to produce a finished translated or illustrated video rather than only a transcript.

### Artifact contract

Keep these layers separate and auditable:

1. `source/` — original URL/path, metadata, captions, thumbnail, user overview, and provenance notes.
2. `work/content_reconciliation.md` — confirmed claims, overview-only claims, source-only details, and conflicts.
3. `source/raw/` — immutable or lightly cleaned source transcript with timestamps and uncertainty notes.
4. `scripts/` — canonical translated script with stable paragraph identifiers and matching order.
5. `assets/` — background, opening, inline illustrations, and an independently designed cover.
6. `audio/` and `output/` — generated narration, samples, final video, and machine-readable QA manifests.
7. `publish/` — platform copy and title recommendations, separate from the source and render layers.

Never treat a filename or upload order as proof of an asset's semantic role. A cover is not the first inline image, and a text-heavy cover must never become the persistent subtitle background.

### Portable end-to-end entrypoints

This repository is usable by Hermes, Claude Code, pi, or another agent that reads `SKILL.md`. Use `AGENTS.md`/`CLAUDE.md` for agent-specific loading rules; do not assume Hermes slash commands exist.

1. Bootstrap source and project gates: YouTube URLs automatically use `projects/youtube-<id>`; local videos use `--slug <slug>`.
2. Complete `scripts/zh.md`, `work/visual_brief.md`, the explicit image-mode choice, and approved uploaded/generated `assets/background.png`, `assets/opening.png`, and the independent `assets/cover.png`.
3. Render the gated sample: `python3 scripts/run_pipeline.py --project projects/<slug> --step prepare`.
4. After user approval in `work/sample_approval.txt`, run `scripts/run_pipeline.py --project projects/<slug> --step all` with `PADDLEOCR_PYTHON`/`PADDLEOCR_DEVICE` set when using PaddleOCR.

#### Unattended auto mode

When the user provides only a YouTube URL and an overview, use the unattended
branch: save the overview, reconcile metadata/captions, choose `auto` image
mode, complete the visual brief and translation, generate the three assets,
and inspect each derivative before continuing. Record `auto-approved` only
after that machine/agent review, then run:

```bash
python3 scripts/run_pipeline.py --project projects/<slug> --step all --auto
```

Auto mode removes the user interaction pause, not the quality gates. It still
requires model-typeset cover typography, independent cover/background/opening
assets, hook-aware timing, OCR subtitle QA, spotcheck, and passing preflight.
Manual mode continues to require the literal `approved` marker.

For direct script execution, run `manifest → tts → hooks-tts → timeline → audio → sample`; only run `full` after `work/sample_approval.txt` is `approved` (manual) or `auto-approved` with `--auto`.

The runner stops on missing inputs and approval gates. It never invents translations, visual assets, or approval markers. Agents without image generation must stop at the asset gate and request approved uploads; this is a valid manual branch, not a silent bypass.

### Step timeout guard

`scripts/run_pipeline.py` gives every pipeline step a hard 15-minute timeout. A step that exceeds this limit is treated as stuck, terminated together with its child process group, and exits with a clear error. Do not wait indefinitely or mark a timed-out QA step as passed; investigate the step separately before retrying.

### Production gates

- Preserve the raw source before editorial cleanup and record actual duration, language, caption source, and uncertainty warnings.
- Reconcile the user's overview with source metadata, captions, and inspected visual evidence before translation, image generation, TTS, or rendering.
- Create `work/visual_brief.md` before any image call. It must contain the source thesis/mechanism, exact approved title, identity references, supported metaphors, and forbidden interpretations.
- For identity-bearing subjects, persist `source/identity_reference.jpg` and pass it through `reference_image_urls`. Identity is a hard gate; a generic substitute fails even if composition and dimensions pass. `work/identity_gate.json` must list the exact reference and all three assets and be `approved`/`auto-approved` before sample/full rendering; missing reference or gate fails closed.
- The cover must show the source mechanism, not only its mood. For problem-solving content require a visible causal chain such as `problem fragments -> calm analysis -> solution route`.
- All Chinese covers use model-typeset poster typography. Never use deterministic post-processing text on the cover. Treat the cover as a complete advertising poster: kicker/section marker, dominant headline with intentional line breaks and contrasting emphasis, subordinate support line, visible grid/framing, one subordinate speaker/series attribution layer for identity-bearing works, and at most one mechanism-reinforcing auxiliary sequence. For Jim Rohn covers, verify `JIM ROHN` or `吉姆·罗恩励志演讲` is visible without competing with the title. QA every visible string at full size and 320x180. The project must contain `work/cover_typography_mode.txt` with `model-typeset`; fail the cover gate if it is absent or different.
- Keep image mode (`auto` or `prompt`) explicit in the project checkpoint. Approval timeouts or interrupted turns are not approval.
- Image-generation retries are sequential, not parallel: wait for each request to return, time out, or fail; record the result; apply bounded backoff; then start the next attempt. Stop on the first usable asset and preserve the final error if all attempts fail.
- In `auto` mode, the opening is a title card, not a cover or a text-free background: reuse the approved background unchanged and add a deterministic exact-text layer in the right safe area. Never use a `No text`/`no letters` prompt for `opening.png`; that prompt is valid only for `background.png`. Use a small kicker, dominant Chinese title, English subline, and small byline; do not add the cover's mechanism sequence, random copy, or source-quotation claims. Inspect both `assets/opening.png` and a frame from the first three seconds of the sample; reject if the exact title strings are absent. The renderer must not assume an image-only opening contains text. Deterministic text is allowed for opening/title cards but remains prohibited for covers. Verify the actual 1920x1080 raster for clipping, spacing, and face/gesture clearance.
- For bilingual narration, preserve stable paragraph IDs across translation, TTS, subtitle timing, concatenation, and rendering. Validate numeric ordering naturally (`para11` after `para10`, never lexical misordering).
- After full render, audit every TTS event against subtitle coverage, check audio energy at start/middle/end checkpoints, validate final duration, and write a machine-readable manifest with `ok: true`. Final preflight fails closed if the manifest is missing, invalid, or false.

### Completion definition

The production workflow is complete only when the source remains auditable, the source/translation paragraph counts and order match, the cover independently passes identity/topic/typography QA and explicit approval, every derivative is synchronized, the final render passes the machine-readable sync audit, and final preflight passes.

### Default hook layer

New projects use the bilingual hook layer by default. Keep the source transcript unchanged and persist the selected opening hook in `work/hooks.json`. Render hooks with the same subtitle styles and right-side safe area as source captions: Chinese wraps at 13 characters, English at 8 words, and real TTS events provide the timing. The ending is one fixed combined hook, not separate action and CTA segments:

`一键三连，关注我的账号，持续更新。行动起来，成为更好的自己。`

The portable runner executes `manifest -> tts -> hooks-tts -> timeline -> audio -> sample/full`. The audio order is `3s opening -> intro hook -> 0.35s gap -> source -> 0.35s gap -> combined ending hook -> 4s music tail`. Verify the merged ending appears once in the ASS file, no `hook_cta` event remains, and final duration equals opening plus the rebuilt master audio.

## Runtime files

The scripts write temporary downloads, extracted audio, subtitles, and frames under a temporary working directory unless `--out-dir` is supplied. Delete the working directory after follow-up questions are finished.

See `references/` for Chinese ASR cleanup, subtitle ingestion, YouTube formatting, and content-library patterns.
