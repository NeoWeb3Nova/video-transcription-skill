# Cover Typography Policy

This repository uses one canonical rule for video covers:

## Cover rule

Every video cover is a complete model-directed advertising poster. The image model must design and render the typography as part of the composition. This is called `model-typeset`.

Do not create a cover by generating a text-free background and adding a fixed-font Pillow, SVG, ImageMagick, or FFmpeg text overlay. That pipeline is rejected even when the characters are exact and readable.

The model prompt must provide every approved visible string, forbid extra/random text, preserve the source mechanism and identity, and specify poster-level hierarchy: kicker, dominant title, supporting hook, attribution, grid/framing, deliberate line breaks, contrast, and thumbnail-scale legibility.

## Allowed deterministic text

Deterministic text overlays are allowed only for:

- the persistent subtitle-safe video background, when it remains text-free in the final video;
- an opening/title card derived from an approved background;
- repair of a non-cover title layer when exact wording is required.

They are never allowed for the cover itself.

## Required project state

Before generating a cover, persist:

- `work/image_mode.txt` = `auto` or `prompt`;
- `work/cover_typography_mode.txt` = `model-typeset`;
- `work/visual_brief.md` containing the source mechanism, identity anchors, exact approved strings, forbidden interpretations, and the model-typeset requirement.

The cover gate must fail closed when the typography mode is missing, not `model-typeset`, or when the cover was produced from a text-free artwork through a post-processing text overlay.

## QA

Inspect both the full raster and a 320×180 preview. Reject the cover for malformed/extra text, weak title hierarchy, a generic font-overlay appearance, identity drift, semantic drift, clipped text, or a composition that leaves the art and title as disconnected panels. User approval is required before TTS or rendering.
