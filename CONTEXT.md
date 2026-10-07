# PuzzlePress current state

## Completed scope

Interval 8 complete: print preview and KDP preflight. `book preflight` and Studio's
Print tab inspect a built interior and report structural validity separately from
modeled KDP readiness; Studio proofs the real PDF. No Interval 9 work (covers, KDP
package, metadata), commits, pushes or deployment. Engine/package 0.1.0; schema,
identity, pipeline, composition, plan, manifest and renderer versions unchanged;
preflight report v1, ruleset `puzzlepress-kdp-paperback` v1. Contracts:
docs/book-composition.md, docs/print-interior.md, docs/preflight.md.

## Architecture and launch

- Python core is pure and authoritative. Runtime deps: PyYAML, ReportLab 5.0.x
  (BSD; pulls Pillow, charset-normalizer), pypdf 6.x (BSD-3). Dev adds
  types-reportlab. Studio extras FastAPI/uvicorn; web tests httpx. React/strict
  TypeScript/Vite, locally bundled fonts.
- Pipeline: project -> batch -> quality -> composition -> plan -> verification ->
  digest binding -> layout -> layout validation -> PDF -> pypdf inspection -> write.
- Core: `composition.py`, `composition_validation.py`, `publication.py`,
  `publication_verification.py`, `book_cli.py` (plan, build). Print engine in
  `interior/`: `spec` (profiles, points, `KdpConstraints`), `fonts` (bundled Vera
  Sans, pinned SHA-256), `text` (wrap), `geometry`, `engine` (layout),
  `validation`, `render` (ReportLab), `inspection` (pypdf), `build` (pipeline,
  manifest, only writer), `issues`, `model`. CLI imports it lazily.
- Preflight in `preflight/`: `model` (Rule, Finding, Measure, RuleResult,
  PreflightReport, versions), `context` (artifact reading, manifest parsing,
  Context), `rules` (catalogue, 39 rules), `engine` (`preflight_interior`).
  `interior.inspection.read_pdf_facts` is the single pypdf fact layer shared by
  the post-build check and preflight. `interior.build` stays the only writer
  (adds `write_preflight_report`, `interior_identity`, `toolchain`).
- Studio: `printing.py` (status/build/page adapter), `preview.py` (PDFium raster,
  LRU); `Print.tsx` plus existing `service.py`, `editing.py`, `draft.tsx` etc.
- Build `cd studio; npm ci; npm run build`; launch from root
  `.\.venv\Scripts\puzzlepress-studio.exe` (http://127.0.0.1:8000/books).

## Print interior

- Profile `paperback-8.5x11` v1 (only one): 612x792 pt, no bleed (rejected), margins
  inside 0.75 / outside 0.5 / top+bottom 0.625 in, gray ink, centered folios
  (`outside` supported). Spec is renderer-facing, not authored YAML; `--profile`.
- KDP rules centralized (verified on KDP help 2026-10): gutter table to 828 pages,
  0.25 in outer margins, 7 pt text, 0.75 pt lines, 24-page minimum (warning only;
  renderer never pads). Physical pages = plan pages. Gutter fixed, validated
  against count, never enlarged.
- Layout: one PhysicalPage per plan entry; elements TextLine/Rule/LetterGrid
  (with SolutionMark capsules); 24 pt folio band. Solution template from plan's
  largest group: 1, 2 stacked, 2x2, 2x3. Puzzle letters 9-20 pt, solutions 7-14.
- Failures are `InteriorError(stage, LayoutIssue...)` with page, physical page,
  kind, subject, region, actual/required. Overflow, tiny grids, unbreakable words,
  missing glyphs, digest mismatch, incomplete plan, foreign report, unknown kind,
  bad order, density >6, bad spec: fail, never repaginate/regroup/shrink.
- Determinism: ReportLab invariant mode, empty metadata, subset fonts. Same source,
  profile, versions, fonts and ReportLab version give byte-identical PDF and
  manifest (tested across process, cwd, PYTHONHASHSEED).
- Output: `output.directory` or `--output`: `interior.pdf`, `interior.json` (interior
  identity, plan digest, profile, versions, fonts, PDF SHA-256, warnings; no time).
  Rechecks source disjointness at write; replaces only same-book manifests; staged,
  fsynced, read back, `os.replace`; failed builds write nothing.

## Preflight (docs/preflight.md)

- Observational: reads `interior.pdf`/`interior.json` (fixed names, no symlinks),
  rebuilds the expected interior in memory via `build_interior`, compares. Never
  mutates plan, layout, PDF, manifest or source. Writes only `preflight.json`.
- Structural valid = no structural error rule failed or unevaluated. KDP ready =
  structurally valid and no KDP error rule failed or unevaluated. Warnings never
  block. Layout rules run only if PDF bytes equal a fresh render
  (`pdf_matches_layout`), else `not_evaluated`. Stale = source/plan/profile/
  toolchain rule failed; mismatched PDF/manifest = invalid.
- KDP rules (values in `spec.KdpConstraints`, read on official KDP help
  2026-10-07): min 24 pages, max 550 (8.5x11; official table omits the row,
  indexed copy 590 white/550 cream: ambiguous), trim range, single trim pages,
  no bleed, gutter table, 0.25 in outside, 7 pt, 0.75 pt, embedded fonts, full
  embedding (warning, ambiguous), no annotations/bookmarks/forms, not encrypted,
  flattened, no printer marks, 300 DPI images (n/a without images), blank runs
  4/10, even folios on verso, descriptive metadata (warning). Margins measured
  from element ink bounds. Ruleset bump on any verdict change; identities unchanged.
- composition-demo: structurally valid, NOT KDP ready (only error
  `kdp_minimum_page_count`, warning `kdp_full_font_embedding`). 16-puzzle
  variant (29 pages) is ready (tested).
- CLI `book preflight PROJECT [--output DIR] [--json] [--no-write]`: exit 0 valid
  and ready, 1 otherwise, 2 usage; `--json` bytes equal `preflight.json`.
- Studio Print tab (`/books/{key}/print`): Build interior (saved revision only;
  dirty draft disables it), verdict line, thumbnails (lazy), single/spread view
  (page 1 alone right), zoom fit/50-300%, keyboard on canvas, overlays (live area,
  KDP minimum margins, element bounds, finding regions; Python boxes, SVG only),
  findings linked to pages, passed/n.a./not-evaluated disclosures, stale/invalid
  notes. API: GET `/interior`, POST `/interior/build {revision}`, GET
  `/interior/pages/{n}?size=thumb|page|detail&pdf=<sha256>` (409 `preview_stale`).
  Print reads wait up to 60 s for the generation lock; drafts still 409.
- Preview: pypdfium2 rasters of the exact PDF bytes, scales 0.5/2/4 (306x396,
  1224x1584, 2448x3168), lossless PNG, in-memory LRU 96 MB keyed by PDF digest,
  page, size; one PDFium lock; digest URLs cached `private, immutable`.

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

- `puzzlepress book plan PROJECT [--json]`: read-only; exit 0 complete, 1
  invalid/missing composition/generation failure, 2 usage.
- `puzzlepress book build PROJECT [--output DIR] [--profile ID] [--json]`: exit 0
  written (warnings on stderr), 1 expected failure with diagnostics (JSON `{success:
  false, stage, diagnostics}`), 2 usage.
- POST `/api/projects/{key}/draft/plan` `{source}` (409 `generation_busy`, 422
  `no_composition`). Print endpoints: see Preflight.

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

- Baseline before edits matched Interval 7 (559 passed, 4 skipped; 29 Vitest).
- Python: **646 passed, 4 skipped** (symlink permission), 1 Starlette httpx
  warning. Preflight 59; print API 23; book CLI incl. 5 preflight. Ruff lint and
  format (81 files), strict mypy (48), pip check.
- Boundaries tested: 23/24 and 550/551 pages; gutter at 24/150/151/300/301/500/
  501/700/701/828 on recto and verso (exact pass, 0.05 pt below fails), 829 not
  evaluated; outside/top/bottom 0.25 in; 7 vs 6.99 pt; 0.75 vs 0.74 pt; blank runs.
  Corruption: tampered/foreign PDF, forged manifest, unknown profile, old renderer,
  malformed manifests, missing files, annotations, bookmarks, encryption, metadata,
  spreads, raster image, transparency, verso arabic 1.
- Frontend: npm ci, check (tsc, ESLint, Prettier), 39 Vitest (10 Print), npm ls,
  build (JS 302.81 kB, CSS 30.24 kB). Playwright 9/9 three consecutive runs (2
  new: real build, statuses, 24-page finding, keyboard, puzzle/blank/solution,
  overlays vs layout boxes, spread pairing, detail raster, axe; 1440/1024/768/390).
  Playwright rewrites existing captures; unrelated ones restored. New captures:
  docs/images/studio/print*.png.
- Installed CLI: 18 regressions as expected; two builds byte-identical;
  `build/composition-demo` (11 pages, PDF 19d5bd5a..., unchanged from Interval 7)
  plus preflight.json. CI print-job steps simulated in Git Bash (exit 1, cmp,
  unchanged digests, deterministic rerun).
- Visual: real Studio at 1440/390; title, copyright (verso overlays), blank,
  recto puzzle, verso puzzle, 2-up spread; 4-up, 6-up and about pages rasterized
  from variant builds. Pixel test: puzzle ink inside the live area.
- Fixture SHA-256 (LF-normalized) unchanged: garden-demo ffd7f7eb..., automotive
  209f3fd6..., composition-demo b15651cd.... Remote CI not verified.

## Limits and decisions for review

One puzzle per page; all definitions included; solutions end or omitted; no TOC.
One profile, no bleed, Vera Sans only (Latin-1), subset embedding, no PDF/X.
Studio builds the default profile only. Preview images are visual only. Review
before Interval 9: the unverified 8.5x11 maximum (550), whether subset embedding
should stay a warning, preflight.json written by default (`--no-write` opts
out), Studio preflight recomputed live (cached) rather than read from
preflight.json, and two-file (three with report) non-atomic artifact replacement.
