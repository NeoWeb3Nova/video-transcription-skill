# Bilingual Video Hook Layer Design

## Status

Implemented in the canonical `scripts/produce.py` pipeline and enabled by default for new projects.

## Goal

Add a reusable editorial hook layer to the bilingual video-production workflow:

1. an opening hook before the source speech;
2. one fixed ending hook after the source speech, combining action and account-follow CTA.

The opening hook must use one fixed catalog entry, selected at production time by the current clock second. It must create an immediate emotional trigger without pretending to be a source quotation. The catalog is intentionally topic-independent so the channel develops a recognizable recurring ritual.

## Approved copy templates

### Fixed opening-hook catalog

The exact seven Chinese strings are immutable and must not be rewritten per topic:

1. `睡前30分钟，听完这段话，明天开始改变自己。`
2. `每天睡前30分钟，悄悄改变你的人生。`
3. `睡前30分钟，听进去，人生就会开始转向。`
4. `睡前30分钟，给自己一次改变人生的机会。`
5. `睡前30分钟，别让今天的你，毁掉明天的人生。`
6. `睡前30分钟，听懂了，你就不会再是原来的自己。`
7. `每天睡前30分钟，让自己一步一步变得不一样。`

The English subtitle is generated from the selected fixed Chinese string and is stored with the project selection. It is not used to select a different hook.

Selection algorithm:

```text
hook_index = current_second % 7
0 → catalog item 1
1 → catalog item 2
...
6 → catalog item 7
```

The selected index, source second, algorithm name, and exact Chinese/English strings are persisted in `work/hooks.json`. Retries, sample rendering, full rendering, and final audits reuse that persisted selection; they never reselect based on a later clock second.

### Opening hook timing

The selected opening hook is spoken after the 3-second opening card and before the source speech.

### Fixed ending hook

The action prompt and account-follow CTA are one fixed ending hook:

Chinese:

> 一键三连，关注我的账号，持续更新。行动起来，成为更好的自己。

English subtitle:

> Like, share, and follow my account for continuous updates. Take action and become a better version of yourself.

The seven strings are fixed by editorial decision. They are promotional framing, not quotations from Jim Rohn or claims made by the source speech. No additional topic-specific opening rewrite is allowed in the default workflow.

## Project data contract

The first hook-aware `manifest` step creates and persists `work/hooks.json` for the project:

```json
{
  "version": 1,
  "source": "editorial_hook",
  "hook_index": 2,
  "selection_second": 16,
  "selection_method": "current_second_mod_7",
  "topic": "相信自己",
  "catalog_zh": "睡前30分钟，听进去，人生就会开始转向。",
  "catalog_en": "Spend 30 minutes before bed listening closely, and your life will begin to turn.",
  "intro": {"zh": "...", "en": "..."},
  "ending": {"zh": "...", "en": "..."}
}
```

Required fields are non-empty. Hook copy is explicitly editorial and must never be represented as source transcript or a Jim Rohn quotation.

## Audio and timing

The rendered sequence is:

```text
3s opening card
→ intro hook TTS
→ 0.35s gap
→ source narration
→ 0.35s gap
→ ending hook TTS
→ 4s music tail
```

The source transcript remains unchanged. The source start offset is computed from actual intro audio duration:

```text
source_start = 3.0 + intro_duration + 0.35
ending_start = source_start + source_narration_duration + 0.35
```

No hook duration is estimated or hard-coded.

## Files and components

Hook TTS is kept separate from source paragraph TTS:

```text
work/tts/hooks/intro.mp3
work/tts/hooks/intro.events.json
work/tts/hooks/ending.mp3
work/tts/hooks/ending.events.json
```

Implemented components:

- `scripts/produce.py`: render using the expanded master audio, audit hook/source timing, and fail closed on missing event data;
- `scripts/run_pipeline.py`: run hooks by default and enforce the approval gates;
- first hook-aware `manifest`: create and persist the project `hooks.json` checkpoint.

The existing 3-second opening card, background, subtitle styles, and source script files remain unchanged; the independent cover remains a required approved asset.

## Compatibility

Completed legacy projects remain valid and are not rewritten. New initialized projects require hooks by default. The portable runner does not expose a hook-free compatibility path; legacy completed artifacts remain readable but new runs are hook-aware by default.

## Subtitle roles

ASS events carry a semantic role:

- `HOOK_INTRO`
- `SOURCE`
- `HOOK_ENDING`

All use the existing bilingual karaoke visual styles. Roles are used for machine auditing and do not need visible labels in the video.

## Failure handling

Fail closed when:

- `hooks.json` is missing, malformed, or missing any language field;
- a hook contains non-speech caption labels;
- any hook TTS or event file is missing;
- hook audio order or timing overlaps the source;
- source paragraph count/order changes;
- the first source subtitle does not align to the computed source offset;
- the ending-hook subtitle does not cover ending-hook audio;
- final duration does not equal opening plus master audio;
- any start/middle/end audio checkpoint is silent;
- `spotcheck.ok` is not true.

Bounded TTS retries and resumable per-segment outputs follow the existing paragraph workflow.

## Acceptance criteria

A new project is complete only when:

1. `work/hooks.json` exists and passes schema/content validation;
2. source paragraph count and 1:1 bilingual alignment remain unchanged;
3. both hook TTS files and event files exist;
4. the timeline contains intro, source, and ending-hook roles in that order;
5. the computed source offset matches the first source subtitle;
6. the 15-second sample includes the opening card and opening hook without clipping;
7. full render has 1920x1080 video and AAC audio;
8. spotcheck audits hook events and source events with `ok: true`;
9. final preflight passes;
10. hook copy is disclosed as editorial packaging, not source quotation.

## Scope exclusions

This change does not add dynamic hook visuals, a new TTS engine, automatic hype generation, or retroactive rebuilds of completed projects. It also does not force every topic into identical wording: the emotional trigger is selected per topic within the short/direct/agitating style.
