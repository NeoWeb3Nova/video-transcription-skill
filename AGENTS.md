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

Unattended mode is available when the agent is responsible for asset and
sample review: bootstrap with `--overview <file>`, then run `--step all --auto`.
It uses explicit `auto-approved` markers and still fails closed on missing
assets, translation, OCR, timing, or preflight checks.

Never replace the approved ASS style with a new font/layout to make OCR easier. New projects use the default hook layer (`manifest → tts → hooks-tts → timeline → audio`). The final gate requires `work/caption_qa.json` with `status: pass`. PaddleOCR is isolated outside the repository; use `PADDLEOCR_PYTHON` and default `PADDLEOCR_DEVICE=gpu:0`. Use CPU only after a verified GPU preflight failure.

Opening-card guard: `assets/opening.png` is text-bearing. In auto mode, never use a text-free image-generation prompt for it; reuse the approved background and add the exact deterministic kicker/title/English line/byline. Inspect the opening asset and a first-three-second sample frame before approval. A valid background or cover does not prove the opening title exists.

Image-generation retry guard: retries are strictly sequential. Issue one request, wait for success, timeout, or failure, record the result, apply bounded backoff, then issue the next attempt. Stop immediately after a usable success; never fan out retry attempts concurrently.

If image generation is unavailable, stop at the asset gate and give the user exact prompts/required upload paths; do not create fake assets or approval files.
