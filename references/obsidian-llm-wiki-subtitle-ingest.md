# Obsidian LLM-Wiki subtitle ingest pattern

Use this when the user gives a local subtitle file (JSON/SRT/VTT/ASS) and asks to “整理成文章 / 放入 Obsidian”.

## Target output

For LLM-Wiki, prefer a two-layer output when the transcript contains reusable knowledge:

1. Raw cleaned transcript
   - Path: `LLM-Wiki/raw/articles/<topic>-transcript-<YYYY-MM-DD>.md` or `raw/transcripts/` if it is explicitly a meeting/interview transcript.
   - Purpose: preserve cleaned source material.
   - Include YAML frontmatter, original source path, cleanup notes, and the cleaned article-like transcript.

2. Compiled wiki article
   - Path: usually `LLM-Wiki/queries/<topic>-<YYYY>.md` for a source-specific analytical note, or `concepts/` / `entities/` only when the page is the durable canonical page.
   - Purpose: turn the raw transcript into structured knowledge with sections, tables, conclusions, and wikilinks.
   - Include `sources:` pointing to the raw cleaned transcript, not just the external/local file.

## Workflow

1. Resolve Windows paths to WSL paths (`D:\...` → `/mnt/d/...`) and verify the source file exists.
2. Parse subtitle JSON/SRT/VTT/ASS, strip timestamps/sequence fields, and extract text.
3. Fix obvious ASR/字幕 errors using local context (project names, protocol names, common English terms). Document major fixes in the raw transcript note.
4. Create the raw cleaned transcript note first.
5. Create the compiled article as a separate wiki page when there is enough conceptual value.
6. If the transcript introduces a durable project/company/person, create or update the corresponding entity page instead of leaving the compiled note as the only entry point.
7. Add at least 2 meaningful wikilinks in the compiled article.
8. Check `SCHEMA.md` before finalizing frontmatter: if you introduce a new `type` or tag (e.g. `raw`, project-specific tags such as `kite-ai`, or domain tags such as `fintech`), update the schema/taxonomy in the same pass.
9. Update the relevant hub/canonical concept page with a short backlink section if one exists.
10. Update `index.md` with the new compiled page and any new entity page, and bump date/page count according to local convention.
11. Append an entry to `log.md` describing created/updated pages, including schema changes when made.
12. Verify files exist, line counts are plausible, and key wikilinks resolve.

## Pitfalls

- Do not only dump the cleaned transcript if the user asked for “文章”; produce a readable compiled article too when the content has thesis/case-study value.
- Do not put source-specific analysis directly into the canonical concept page as a long section; keep the canonical page as a hub and link to the compiled article.
- Do not cite the local subtitle file as the only source of the compiled article; cite the cleaned raw transcript note so Obsidian has a stable internal source chain.
- Do not skip `SCHEMA.md` when adding new tags or raw/frontmatter types; unresolved tags make the page look valid locally but fail later wiki hygiene checks.
- If the transcript is about a project/company/person that will recur, do not bury it only inside a query note; add/update an entity page and index entry.
