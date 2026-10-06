# PuzzlePress current state

## Completed scope

Interval 6 complete: renderer-independent book composition, a deterministic and
independently verified logical publication plan, `book plan` CLI and Studio Book
composer. No Interval 7 work (layout/PDF), commits, pushes or deployment.
Engine/package 0.1.0; schema, identity and word-search pipeline remain version 1.
Composition and plan versions are 1. Full contract: docs/book-composition.md.

## Architecture and launch

- Python core is pure and authoritative. Runtime dependency remains PyYAML; Studio
  extras FastAPI >=0.135,<0.136 and uvicorn; web tests use httpx. React/strict
  TypeScript/Vite, locally bundled fonts. No dependencies added in Intervals 5-6.
- Pipeline: project -> batch generation -> quality -> composition -> plan. Layout
  is the Interval 7 boundary and must consume, never regroup or repaginate, plans.
- Core: `composition.py` (frozen models/enums), `composition_validation.py`,
  `publication.py` (planner, `build_publication`, `plan_publication`),
  `publication_verification.py` (verifier, shared JSON payload), `book_cli.py`.
  `batch.puzzle_digest` binds plan entries to generated puzzles.
- Studio: `service.py`, `editing.py`, `server.py` as before plus `plan_project`.
  Frontend `draft.tsx` holds the single whole-project draft shared by `Editor.tsx`
  (Edit tab) and `Composer.tsx` (Book tab); `editor-fields.tsx` field helpers.
- Build `cd studio; npm ci; npm run build`; launch from root
  `.\.venv\Scripts\puzzlepress-studio.exe` (http://127.0.0.1:8000/books).

## Composition model

- Optional top-level `composition` (requires `word_search`): `front_matter`
  (title_page, copyright_page{text}, instructions{title,text}; each once; title
  page first), `puzzles.start` any|recto, required `solutions` {placement end|omit;
  with end: title, per_page 1|2|4|6, start any|recto}, `back_matter` (about{title,
  text}, notes{title}), `page_numbers` {scheme continuous|roman_front_matter,
  show_front_matter false, show_solutions true, show_back_matter true}.
- Titles 1..200 single-line; body 1..2,000 plain text with line breaks. No default
  legal text anywhere. Errors collected with structured paths; nothing repaired.
- Backward compatibility: absent composition is not reinterpreted; legacy identities
  byte-identical (garden-demo/automotive pinned). Planning requires explicit
  composition (`composition [required]`); Studio offers a visible starter.
- Identity: present composition is in canonical inputs plus envelope
  `composition_version: 1`; omitted/explicit defaults hash equally.
- Publication order is `word_search.puzzles` order: no second reference list,
  every definition once. Seeds follow IDs, so reordering never changes grids.

## Plan semantics

- Each plan page is one logical page; index 1 recto, odd recto/even verso. One
  page per matter item and per puzzle; solutions grouped per_page in puzzle order
  (grouping semantic, arrangement is layout). Back matter follows directly.
- recto start inserts one explicit blank (`section_recto_start`, `before_section`)
  attributed to the preceding section, only when needed.
- Numbers: value/style/label/displayed; blanks counted, never displayed; puzzle
  pages always displayed. roman_front_matter: front (incl. trailing blank) roman,
  arabic restarts at 1. Cross-refs by logical index: `solution_page`, `puzzle_page`.
- Puzzle refs: id, ordinal, title, theme, seed (JSON string), `sha256-` digest of
  generated puzzle JSON. Failed generation keeps entries with null digest plus a
  `generation_failed` diagnostic; `complete` false. Quality stays separate.
- Statistics are logical counts, not final printed/KDP page counts.
- Verifier checks invariants vs source/report (order, sections, matter text, seeds,
  digests, coverage, grouping, cross-refs, justified blanks, recto starts,
  numbering/display, statistics, diagnostics). Fresh-plan failure raises.

## CLI and API

- `puzzlepress book plan PROJECT [--json]`: table or JSON `{plan, verification,
  generation{success,clean,quality_findings}}`. Exit 0 complete, 1 invalid/missing
  composition/generation failure, 2 usage. Writes nothing.
- New POST `/api/projects/{key}/draft/plan` `{source}`; shares generation lock
  (409 `generation_busy`), 422 `no_composition`. Shell route `/books/{key}/book`.
  Composition saves reuse `/draft/validate` and `/draft/save` unchanged.

## Studio composer

Outline sections (front matter, puzzles, solutions, back matter, page numbers)
beside a plan table grouped by section with side, number (parenthesized when not
printed), content, blanks and reasons, statistics, verification and quality count.
Up/Down/Remove buttons (no drag dependency); focus follows moved puzzles. Saved plan
auto-requests once per revision; edits clear it until Preview plan; save/reload
announce then refresh. Plan sticky above 1200px; stacks below with Jump to plan.
Same revision/atomic save/stale rejection/draft retention as Interval 5.

## Persistence contract (unchanged)

Only existing root-scoped `book.yaml`; key/symlink/output boundary checks; byte
revision `sha256-<bytes>`; validate, stage, fsync, reload, recheck, `os.replace`,
reload. Canonical YAML loses comments/formatting. One Studio process per library;
small external-editor race remains. Drafts memory-only; no autosave/undo/merge.

## Actual local verification (Windows, Python 3.13.15, Node 24.18.0)

- Python: **472 passed, 4 skipped** (symlink permission), 1 Starlette httpx
  deprecation warning. Composition/CLI/API-composition subset 85 passed; API suite
  84 passed, 3 skipped. Ruff lint/format (55 files), strict mypy (29), pip check.
- Frontend: npm ci, check (tsc/ESLint/Prettier), **29 Vitest**, npm ls, build
  (JS 284.49 kB, 86.37 kB gzip). **7 Playwright** (installed Chrome) incl. 2
  composer specs: real edit/preview/save/reload, deterministic repeat preview,
  validation, stale conflict, keyboard reorder, starter, 1440/1024/768/390 without
  overflow, zero axe violations in checked states.
- Installed CLI: 9 regressions exit 0; legacy `book plan` exit 1 structured; plan
  JSON byte-identical across runs/cwd/hash seed; no build output written.
- Fixture SHA-256 (LF-normalized) unchanged: garden-demo ffd7f7eb..., automotive
  209f3fd6..., composition-demo b15651cd... All writes use temp copies.
- pytest needs a writable basetemp; sandbox blocked `.pytest_cache`, so runs used
  a scratch basetemp. esbuild/Playwright ran outside the sandbox. Remote CI not
  verified; CI adds `validate`/`book plan` for composition-demo.

## Limits and decisions for review

One puzzle per page; all definitions included; solutions end or omitted; no TOC,
half-title, dividers, per-puzzle recto, rich text or images; no overflow detection
(renderer must report). Book title edited only in Edit. Existing npm audit Vitest
advisory not re-examined. Review before Interval 7: per_page set {1,2,4,6},
copyright/instructions text model, `notes` semantics, plan JSON plus report as the
renderer input, and whether exclusion of puzzles or a TOC is needed.
