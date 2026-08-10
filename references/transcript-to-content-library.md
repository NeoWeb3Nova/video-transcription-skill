# Transcript → Reusable Content Library

Use this when the user wants a transcript reorganized into a durable source bank for later articles, newsletters, social posts, decks, or visual explainers—not merely summarized into one document.

## Deliverable shape

Create a separate `docs/<topic>-content-library.md` beside the transcript and ordinary notes. Treat it as a source library, not a finished article.

Recommended sections:

1. Usage guide and provenance
2. Confidence labels: source meaning / edited synthesis / extension / verify
3. Core thesis and reusable claims
4. Scope and boundaries (what the source does and does not cover)
5. End-to-end workflow stages
6. For each stage: questions, actions, deliverables, metrics, mistakes, article-ready angle
7. User journey / funnel / lifecycle
8. Channel or stakeholder matrices
9. Metrics and review framework
10. AI-assisted workflow and human judgment boundaries
11. Before / during / after checklist
12. Topic bank
13. Title formulas and opening hooks
14. Article outline templates
15. Diagram and illustration briefs
16. Analogies and edited quote candidates
17. FAQ bank
18. Fact-check and ASR-risk list
19. Fields to enrich later
20. Suggested content series

## Evidence discipline

- Add stable transcript line ranges or paragraph identifiers to important claims.
- Never present edited synthesis as a verbatim quote.
- Label extrapolations explicitly; do not imply the speaker used a method merely because it is a reasonable extension.
- Isolate uncertain names, acronyms, figures, and ASR artifacts in a verification section.
- Preserve the distinction between the source’s specific operating context and universal claims. For example, a Builder-focused hackathon workflow is not automatically the same as exchange or consumer-product operations.

## Writing for future reuse

- Prefer modular sections, tables, checklists, formulas, and reusable blocks over a continuous essay.
- Include multiple content angles: cognition, workflow, growth, AI, career, case study, and diagnosis.
- Produce article-ready components without pretending the library itself is publication-ready.
- If the user writes in Chinese, apply normal Chinese/English spacing and full-width punctuation to synthesized material; do not aggressively autocorrect raw transcript excerpts.

## Large-file construction pattern

Long Chinese libraries can exceed a single tool-call argument budget. Use this safe pattern:

1. Write 2–4 bounded Markdown chunks under `/tmp/`.
2. Combine the chunks deterministically with Python.
3. Write the final artifact through the file-writing tool.
4. Re-read the beginning and end, then run structural verification.

Important pitfall: Hermes `read_file` output includes `LINE_NUM|CONTENT` display prefixes. Do not concatenate that rendered output into the final document. When combining files programmatically, read the temporary files directly with `Path.read_text(encoding="utf-8")`, then write the joined string.

## Verification

Check at minimum:

- one H1;
- every required H2 section exists;
- all workflow stages are present exactly once;
- source links resolve;
- source line references fall within the transcript;
- no Unicode replacement characters;
- no accidental `123|` line prefixes;
- no unsupported verbatim-quote claims;
- `git diff --check` passes;
- only requested paths are staged when the worktree contains unrelated changes.
