# Bilingual Video Hook Layer Design

## Status

Approved design for review before implementation.

## Goal

Add a reusable editorial hook layer to the bilingual video-production workflow:

1. an opening hook before the source speech;
2. an ending reflection/action hook after the source speech;
3. a light channel CTA after the ending hook.

The hooks must increase viewer retention and create a listen-to-action loop without pretending to be quotations from the source speaker or making unverifiable promises.

## Approved copy templates

### Opening hook

Chinese:

> 这30分钟，不是让你听得更多，而是帮你在【主题】上，做出一个更好的选择。现在，安静下来，我们开始。

English:

> These 30 minutes are not about listening to more. They are about helping you make a better choice about 【topic】. Now, settle in. Let us begin.

`【主题】` is an editorial action object, not necessarily the literal video title. Examples:

- `相信自己` → `相信自己这件事`
- `如何成为一个高效的人` → `真正高效这件事`
- `默默强大自己` → `持续成长这件事`

### Ending hook

Chinese:

> 听完这段演讲，不算改变。真正的改变，发生在你接下来的那个选择里。今天，只选一个原则，把它变成一个具体行动。等下一次你再次分心、怀疑，或者想要放弃时，回来再听一遍。

English:

> Listening to this speech is not change. Real change happens in the choice you make next. Choose one principle today and turn it into one specific action. When you feel distracted, doubtful, or ready to quit again, come back and listen once more.

### CTA

Chinese:

> 如果这段内容对你有帮助，欢迎订阅。下一次，用30分钟，继续把一个重要的原则，变成你生活中的行动。

English:

> If this helped you, consider subscribing. Next time, spend 30 minutes turning another important principle into action in your life.

The templates are defaults. A project may use topic-specific wording, but it must preserve the same promise boundary: no guaranteed life transformation, instant success, magic, or passive results.

## Project data contract

Each new project contains `work/hooks.json`:

```json
{
  "version": 1,
  "source": "editorial_hook",
  "topic": "相信自己",
  "intro": {"zh": "...", "en": "..."},
  "outro": {"zh": "...", "en": "..."},
  "cta": {"zh": "...", "en": "..."}
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
→ outro hook TTS
→ 0.35s gap
→ CTA TTS
→ 4s music tail
```

The source transcript remains unchanged. The source start offset is computed from actual intro audio duration:

```text
source_start = 3.0 + intro_duration + 0.35
outro_start = source_start + source_narration_duration + 0.35
cta_start = outro_start + outro_duration + 0.35
```

No hook duration is estimated or hard-coded.

## Files and components

Hook TTS is kept separate from source paragraph TTS:

```text
work/tts/zh/hook_intro.mp3
work/tts/zh/hook_intro.events.json
work/tts/zh/hook_outro.mp3
work/tts/zh/hook_outro.events.json
work/tts/zh/hook_cta.mp3
work/tts/zh/hook_cta.events.json
```

Planned shared-script changes:

- `build_paras.py`: validate `hooks.json` without counting hooks as source paragraphs;
- `tts_generate.py`: synthesize the three hook segments with bounded retries;
- `build_timeline.py`: add hook events and apply the dynamic source offset;
- `assemble_audio.py`: concatenate intro, source, outro, CTA, and music tail in that order;
- `render_full.py` and `render_sample15.py`: render using the expanded master audio;
- `spotcheck.py`: audit hook and source segments separately;
- `preflight_project.py`: fail closed when hook data, audio, events, or timing are missing;
- project initialization: create a `hooks.json` template and checkpoint.

The existing 3-second opening card, background, cover, subtitle styles, and source script files remain unchanged.

## Compatibility

Completed legacy projects remain valid and are not rewritten. New initialized projects require hooks by default. An explicit `--no-hooks` escape hatch may preserve the old flow for legacy maintenance, but it cannot be the default for new projects.

## Subtitle roles

ASS events carry a semantic role:

- `HOOK_INTRO`
- `SOURCE`
- `HOOK_OUTRO`
- `CTA`

All use the existing bilingual karaoke visual styles. Roles are used for machine auditing and do not need visible labels in the video.

## Failure handling

Fail closed when:

- `hooks.json` is missing, malformed, or missing any language field;
- a hook contains non-speech caption labels;
- any hook TTS or event file is missing;
- hook audio order or timing overlaps the source;
- source paragraph count/order changes;
- the first source subtitle does not align to the computed source offset;
- the last CTA subtitle does not cover CTA audio;
- final duration does not equal opening plus master audio;
- any start/middle/end audio checkpoint is silent;
- `spotcheck.ok` is not true.

Bounded TTS retries and resumable per-segment outputs follow the existing paragraph workflow.

## Acceptance criteria

A new project is complete only when:

1. `work/hooks.json` exists and passes schema/content validation;
2. source paragraph count and 1:1 bilingual alignment remain unchanged;
3. all three hook TTS files and event files exist;
4. the timeline contains intro, source, outro, and CTA roles in that order;
5. the computed source offset matches the first source subtitle;
6. the 15-second sample includes the opening card and opening hook without clipping;
7. full render has 1920x1080 video and AAC audio;
8. spotcheck audits hook events and source events with `ok: true`;
9. final preflight passes;
10. hook copy is disclosed as editorial packaging, not source quotation.

## Scope exclusions

This change does not add dynamic hook visuals, a new TTS engine, automatic hype generation, new cover assets, or retroactive rebuilds of completed projects.
