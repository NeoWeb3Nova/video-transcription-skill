# Video production repository instructions

Read `SKILL.md` before producing video work.

## End-to-end entrypoints

1. Bootstrap a project:
   YouTube URLs automatically use `projects/youtube-<video-id>`; local videos require `--slug <slug>`.
   `python3 scripts/bootstrap_project.py <youtube-url-or-local-video> [--slug <slug>]`
2. Complete `scripts/zh.md`, `work/visual_brief.md`, and obtain user approval for `work/image_mode.txt`, `work/cover_approval.txt`, and `work/sample_approval.txt`.
3. Provide approved `assets/cover.png`, `assets/background.png`, and `assets/opening.png` (1920x1080); keep `work/cover_typography_mode.txt` as `model-typeset` and do not invent approval markers.
4. Render the gated preparation sample:
   `python3 scripts/run_pipeline.py --project projects/<slug> --step prepare`
5. After sample approval, render and audit:
   `python3 scripts/run_pipeline.py --project projects/<slug> --step all`

Never replace the approved ASS style with a new font/layout to make OCR easier. New projects use the default hook layer (`manifest → tts → hooks-tts → timeline → audio`). The final gate requires `work/caption_qa.json` with `status: pass`. PaddleOCR is isolated outside the repository; use `PADDLEOCR_PYTHON` and `PADDLEOCR_DEVICE` when needed.

If image generation is unavailable, stop at the asset gate and give the user exact prompts/required upload paths; do not create fake assets or approval files.
