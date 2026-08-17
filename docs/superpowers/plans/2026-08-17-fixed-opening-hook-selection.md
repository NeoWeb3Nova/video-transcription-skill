# Fixed Opening Hook Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add seven immutable opening hooks selected once by `current_second % 7`, persisted per project, and rendered as bilingual hook audio/subtitles before the source speech.

**Architecture:** Keep source `scripts/en.md` and `scripts/zh.md` unchanged. Extend the repository's canonical `scripts/produce.py` pipeline with a fixed catalog, a persisted `work/hooks.json` selection, three hook TTS segments (intro hook, ending hook, CTA), dynamic timeline offsets, and hook-aware audio/render/audit checks. The selected opening catalog item is chosen only when hooks are initialized; all later steps read the persisted value.

**Tech Stack:** Python 3.12 standard library, existing `edge_tts`, existing ffmpeg/ffprobe binaries, ASS subtitles, JSON manifests.

---

## Baseline and invariants

- Repository root: `/home/neo/projects/video-transcription-skill`.
- Canonical reusable pipeline: `scripts/produce.py`.
- Project selection remains controlled by `PROJECT_SLUG`.
- Source paragraph IDs remain `para01...paraNN`; hooks never enter source paragraph counts.
- Existing completed projects without `work/hooks.json` retain the legacy path only when explicitly enabled; new hook-enabled runs require the hook file.

## Task 1: Add the fixed catalog and persisted hook manifest

**Files:**
- Modify: `scripts/produce.py` near constants and project initialization.
- Create: `references/fixed-opening-hooks.json`.
- Modify: `README.md` pipeline documentation.
- Modify: `SKILL.md` hook workflow and gate documentation.
- Test: `scripts/produce.py` self-check command or a small `scripts/test_hooks.py`.

- [ ] **Step 1: Add the exact immutable catalog.**

Create `references/fixed-opening-hooks.json` with exactly these seven Chinese strings in order:

```json
[
  "睡前30分钟，听完这段话，明天开始改变自己。",
  "每天睡前30分钟，悄悄改变你的人生。",
  "睡前30分钟，听进去，人生就会开始转向。",
  "睡前30分钟，给自己一次改变人生的机会。",
  "睡前30分钟，别让今天的你，毁掉明天的人生。",
  "睡前30分钟，听懂了，你就不会再是原来的自己。",
  "每天睡前30分钟，让自己一步一步变得不一样。"
]
```

The catalog is data, not generated copy. No topic substitution is allowed.

- [ ] **Step 2: Add deterministic selection and persistence helpers.**

Add functions in `scripts/produce.py` with these contracts:

```python
def select_hook_index(second: int) -> int:
    if not 0 <= second <= 59:
        raise ValueError("second must be in [0, 59]")
    return second % 7


def ensure_hooks() -> dict:
    # Read P/work/hooks.json if it exists and validate it.
    # Otherwise read the seven-item catalog, use datetime.now().second,
    # create the manifest, and return it.
```

The manifest must contain `version`, `source: "editorial_hook"`, `hook_index`, `selection_second`, `selection_method: "current_second_mod_7"`, `catalog_zh`, and bilingual `intro`, `outro`, and `cta` text. `ensure_hooks()` must never overwrite an existing valid manifest.

- [ ] **Step 3: Add a self-check.**

The self-check must assert all seven mappings:

```python
assert [select_hook_index(s) for s in range(7)] == list(range(7))
assert select_hook_index(59) == 3
```

It must also create a temporary manifest path or use an isolated temp project and prove a second call returns the original selection instead of selecting again.

- [ ] **Step 4: Run the self-check and JSON validation.**

Run:

```bash
.venv/bin/python scripts/test_hooks.py
python3 -m json.tool references/fixed-opening-hooks.json >/dev/null
```

Expected: exit code 0 and seven catalog entries.

- [ ] **Step 5: Update docs.**

Document the exact seven strings, `current_second % 7`, zero-based mapping, and persistence rule. State that opening hooks are editorial framing, not source quotations.

- [ ] **Step 6: Commit.**

```bash
git add references/fixed-opening-hooks.json scripts/produce.py scripts/test_hooks.py README.md SKILL.md
git commit -m "feat: add persisted random opening hooks"
```

## Task 2: Generate bilingual hook TTS and events

**Files:**
- Modify: `scripts/produce.py` TTS section.
- Modify: `scripts/test_hooks.py`.

- [ ] **Step 1: Add hook segment definitions.**

Use the manifest's selected opening hook and fixed bilingual ending copy. Keep files separate:

```text
work/tts/hooks/intro.mp3
work/tts/hooks/intro.events.json
work/tts/hooks/outro.mp3
work/tts/hooks/outro.events.json
work/tts/hooks/cta.mp3
work/tts/hooks/cta.events.json
```

Narration is Chinese only, matching the existing voice-over. English is subtitle-only.

- [ ] **Step 2: Add resumable hook synthesis.**

Reuse the existing `edge_tts.Communicate` voice and event conversion. Skip a hook only when both its MP3 and event JSON exist. Retry each hook at most three times. A missing hook after retries exits non-zero.

- [ ] **Step 3: Run TTS self-check with a mocked synthesizer boundary.**

Prove the three hook output names are distinct and an existing pair is skipped. Do not call the network in the test.

- [ ] **Step 4: Run the hook TTS command.**

```bash
PROJECT_SLUG=<slug> .venv/bin/python scripts/produce.py hooks-tts
```

Expected: three MP3 files and three event JSON files.

- [ ] **Step 5: Commit.**

```bash
git add scripts/produce.py scripts/test_hooks.py
 git commit -m "feat: synthesize opening and closing hook segments"
```

## Task 3: Add hook timing, subtitles, and audio assembly

**Files:**
- Modify: `scripts/produce.py` timeline and audio functions.
- Modify: `scripts/test_hooks.py`.

- [ ] **Step 1: Compute dynamic offsets from probed durations.**

Use actual hook and source durations:

```text
source_start = 3.0 + intro_duration + 0.35
outro_start = source_start + source_narration_duration + 0.35
cta_start = outro_start + outro_duration + 0.35
```

Do not estimate hook duration or use a fixed source offset.

- [ ] **Step 2: Add ASS hook events.**

Use existing ZH/EN styles and karaoke styles. Add role metadata in the event-generation code for `HOOK_INTRO`, `SOURCE`, `HOOK_OUTRO`, and `CTA`; role metadata need not be visible. Source subtitle timestamps are shifted by `source_start` only.

- [ ] **Step 3: Assemble audio in exact order.**

Build the narration stream as:

```text
intro.wav → 0.35s silence → source paragraph wavs with existing gaps
→ 0.35s silence → outro.wav → 0.35s silence → cta.wav
```

Then mix the existing music bed and append the existing four-second tail. Preserve numeric sorting for source paragraphs.

- [ ] **Step 4: Test timing invariants with synthetic durations.**

Use simple numeric fixtures to assert the formulas and assert strict ordering with non-overlapping intervals. Test that source paragraph count is unchanged.

- [ ] **Step 5: Run the pipeline steps.**

```bash
PROJECT_SLUG=<slug> .venv/bin/python scripts/produce.py manifest
PROJECT_SLUG=<slug> .venv/bin/python scripts/produce.py hooks-tts
PROJECT_SLUG=<slug> .venv/bin/python scripts/produce.py timeline
PROJECT_SLUG=<slug> .venv/bin/python scripts/produce.py audio
```

Expected: hook subtitles exist, `audio/master.wav` includes all hook segments, and source subtitle starts at the computed offset.

- [ ] **Step 6: Commit.**

```bash
git add scripts/produce.py scripts/test_hooks.py
 git commit -m "feat: place hooks in bilingual timeline and master audio"
```

## Task 4: Render, audit, and fail closed

**Files:**
- Modify: `scripts/produce.py` sample/full render, spotcheck, and preflight.
- Modify: `scripts/test_hooks.py`.
- Modify: `README.md` and `SKILL.md` if command names change.

- [ ] **Step 1: Render the sample and full video using expanded master duration.**

Keep the existing 3-second opening card and background. The 15-second sample must contain the opening card, the selected hook, and no clipped hook subtitle. The full render duration must equal `master_duration + 3.0`.

```bash
PROJECT_SLUG=<slug> .venv/bin/python scripts/produce.py sample
PROJECT_SLUG=<slug> .venv/bin/python scripts/produce.py full
```

- [ ] **Step 2: Audit hook and source coverage.**

`spotcheck` must verify intro, source, outro, and CTA events separately. It must write `work/spotcheck.json` with `hook_events`, `source_offset_s`, `source_events`, `hook_events_total`, and `ok: true`.

- [ ] **Step 3: Add fail-closed preflight checks.**

Preflight fails when the manifest is malformed, any hook file/event is missing, hook order overlaps source, the first source subtitle misses `source_start`, CTA subtitle coverage is incomplete, final duration is wrong, or any start/middle/end audio checkpoint is silent.

- [ ] **Step 4: Run verification.**

```bash
PROJECT_SLUG=<slug> .venv/bin/python scripts/produce.py spotcheck
PROJECT_SLUG=<slug> .venv/bin/python scripts/produce.py preflight
python3 -m py_compile scripts/produce.py scripts/test_hooks.py
```

Expected: `spotcheck.json` contains `ok: true`; preflight exits 0; video has 1920x1080 H.264 video and AAC audio.

- [ ] **Step 5: Commit.**

```bash
git add scripts/produce.py scripts/test_hooks.py README.md SKILL.md
 git commit -m "feat: audit and gate bilingual video hooks"
```

## Task 5: Final repository verification

**Files:**
- No new files.

- [ ] **Step 1: Run the focused self-check.**

```bash
.venv/bin/python scripts/test_hooks.py
```

Expected: PASS.

- [ ] **Step 2: Run repository diff and status checks.**

```bash
git diff --check
 git status --short --branch
```

Expected: no whitespace errors; only intentional changes remain.

- [ ] **Step 3: Commit any documentation-only correction.**

Only if the previous commands identify an intentional uncommitted correction:

```bash
git add README.md SKILL.md references/fixed-opening-hooks.json scripts/produce.py scripts/test_hooks.py
git commit -m "docs: finalize fixed opening hook workflow"
```
