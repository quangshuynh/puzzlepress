# PuzzlePress current state

## Completed scope

Interval 10 complete: KDP metadata and publishing package on branch
`feat/kdp-publishing-package` (from main `9ef8901`, which merged Interval 9 via
PR #1; pushed, not merged; no PR, tag, release or deployment). Authors write KDP
paperback metadata, declare AI content, confirm rights, and export a verified,
deterministic package for manual KDP upload via CLI (`puzzlepress publish ...`) or
Studio's Publishing tab. Nothing contacts Amazon. No Interval 11 work. Engine
0.1.0; identity, pipeline, composition, plan, interior, cover and preflight
versions unchanged. Contracts: docs/publishing.md plus cover, preflight, others.

## Architecture and launch

- Python core is pure and authoritative. Runtime deps: PyYAML, ReportLab 5.0.x
  (BSD), pypdf 6.x (BSD-3), Pillow 12.x (MIT-CMU; now declared, `>=12,<13`). Dev adds
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
- Cover: `cover_config.py`/`cover_validation.py` (schema) and `cover/` (`assets`,
  `crop`, `geometry`, `fonts`, `layout`, `model`, `validation`, `render`,
  `inspection`, `build` = only writer, `preflight`); `cover_cli.py`.
- Publishing: `publishing_config.py`/`publishing_validation.py` (schema) and
  `publishing/` (`model`, `rules` = catalogue and the one home of KDP metadata
  values, `isbn`, `text`, `identity`, `metadata`, `readiness`, `provenance`,
  `submission`, `package` = only writer); `publish_cli.py`; `studio/publishing.py`;
  `Publishing.tsx`.
- Studio: `printing.py` (status/build/page adapter, profile choice), `preview.py`
  (PDFium raster, one process-wide lock), `covering.py` (cover adapter); `Print.tsx`,
  `Cover.tsx` plus `service.py`, `editing.py`, `draft.tsx` etc.
- Build `cd studio; npm ci; npm run build`; launch from root
  `.\.venv\Scripts\puzzlepress-studio.exe` (http://127.0.0.1:8000/books).

## Print interior

- Profiles `paperback-8.5x11` v2 (white, default) and `paperback-8.5x11-cream` v1,
  both black ink, paper stated explicitly (v1 interiors now report stale; page
  geometry and PDF bytes identical, identity differs). Shared geometry: 612x792 pt, no bleed (rejected), margins
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

## Cover (docs/cover.md)

- Config: optional `cover` (version 1) in book.yaml, requires composition,
  excluded from build identity. layout full_wrap|front_photo; image {path
  `cover-assets/<name>.jpg|png`, sha256}; crop {x, y 0..1, zoom 1..4, 4 dp};
  type {style editorial|bold|minimal, position top|middle|bottom, align
  center|left, tone light|dark}; legibility shade|panel|none; background #rrggbb;
  spine_text auto|none; back_text <=1,200. Copy = book title/subtitle/author/imprint.
- Photos: import copies original bytes, content-addressed, never overwrites, reuses
  identical bytes. JPEG/PNG <=64 MB, <=80 MP. Decode once: EXIF orientation,
  ICC->sRGB (LittleCMS), 8-bit RGB, opaque only. PDF gets a bare-pixel baseline
  JPEG q95 4:4:4 (JFIF only), DCTDecode unchanged (no ASCII85). No EXIF/GPS/XMP/ICC.
- Crop: cover-fit uniform scale x zoom, focal clamped; whole source pixels drawn,
  clipped, no resampling. Effective DPI = used pixels / printed inches;
  ok | image_low_effective_dpi | image_too_small.
- Geometry from a current interior only (manifest digest, identity, source,
  profile, toolchain; pages counted in the PDF). Wrap = 0.125 + W + spine + W +
  0.125; spine = pages x 0.002252 (white) / 0.0025 (cream). KDP safe 0.125 in;
  spine 0.0625 in; type area 0.5 in; barcode 2x1.2 in at 0.25 in from bottom/fold
  (offsets assumed) with keep-clear corner. Spine text from 80 pages (stricter of
  KDP's contradictory wording) and only if 7 pt fits; else omitted with reason.
- Fonts: Vera Sans + Newsreader 72pt Regular, 16pt Regular/Italic (OFL 1.1,
  upstream commit cfcb4f7, pinned SHA-256). Titles step 2 pt within preset, <=3 lines.
- Identity `pp1-cover-sha256-` over book ID, semantic config (photo by digest),
  copy, interior physical facts, cover profile v1, toolchain (renderer v1, engine,
  ReportLab, Pillow, fonts). Provenance (interior identity, PDF digest, photo path)
  is recorded, not identity: a rebuilt interior with equal facts only warns.
- Output beside the interior: cover.pdf (1 page, MediaBox=BleedBox=wrap,
  TrimBox=trim, DeviceRGB, no strokes/marks/annotations/metadata), cover.json,
  cover-preflight.json. Byte-identical across process, cwd, PYTHONHASHSEED.
- Cover preflight ruleset `puzzlepress-kdp-cover` v1, 25 rules (10 structural,
  15 KDP; warnings: provenance, 40 MB, RGB vs CMYK). States no_config, missing,
  current, stale, invalid. Never writes except cover-preflight.json.
- CLI `cover inspect|import|build|preflight` (`--output`, `--json`, `--no-write`);
  exit 0/1/2 as book commands; preflight 0 only when valid and ready.
- Studio Cover tab: shared draft; debounced POST /draft/cover renders the real PDF
  in memory (stale interior labeled, damaged refused); PDFium raster views
  (wrap/front/spine/back); Python-geometry overlays; drag, sliders, keyboard crop
  (arrows, Shift, +/-, 0; key-code fallback); readiness column; build saved
  revision only. API: GET /cover, POST /draft/cover, GET /cover/preview,
  GET/POST /cover/assets (raw image/jpeg|png upload, route-scoped), POST
  /cover/build. Print: paper choice, keeps the built profile.
- Fixtures: `books/cover-demo` (20 puzzles, 35 pages, synthetic stand-in photo from
  tests/cover_demo_photo.py): cover valid and KDP ready (interior is not; see
  verification), spine text omitted. 20-puzzle
  limit keeps every book below 80 pages; spine text tested with synthetic facts.

## Publishing (docs/publishing.md)

- Optional `publishing` (version 1) in book.yaml, requires composition, excluded
  from build identity; `pp1-publishing-sha256-` over the section, referenced book
  details (title, subtitle, author, imprint, language), schema and engine versions.
  Title/subtitle/author/imprint/language stay in `book`; `book.description` is not
  the KDP description. Undecided values are explicit (null, `undecided`, `unknown`).
  Schema bounds are generous; KDP limits are findings, so drafts over them save.
- KDP values read on official help pages 2026-10-08 (URLs in `publishing/rules.py`):
  title+subtitle <200 (two wordings; stricter), description 4,000 and prohibited
  content, 7 keywords, 3 categories, 100-char imprint, 39 paperback languages,
  explicit-content answer, low-content (puzzle books "not generally low-content";
  no free ISBN or series when low-content), free ISBN KDP-only, AI-generated vs
  AI-assisted disclosure, cover must match details. 50-char keyword length is an
  assumption (warning). Plain-text descriptions are a PuzzlePress rule.
- 36 metadata/disclosure/attestation rules plus 12 artifact/consistency rules
  (`puzzlepress-kdp-publishing` v1); findings carry code, severity, scope, basis,
  source URL, field, actual/required, action, Studio area, related preflight rule.
  Heuristic detectors (testimonials, promotion, stuffing, keyword variants) warn;
  unambiguous patterns block. Description puzzle counts are checked against content.
- Readiness reruns interior and cover preflight (never trusts saved reports; a
  missing/outdated/forged one is a warning), keeps verdicts separate (metadata,
  disclosure, attestations, interior and cover state/structural/KDP, artifacts,
  package), carries preflight warnings unchanged, treats unevaluated error rules as
  blocking, and explains staleness ("Cover is out of date because the interior
  paper changed (white -> cream).").
- Package (only when ready, from inspected bytes): interior.pdf, cover.pdf,
  metadata.json, kdp-checklist.md, readiness.json, interior-/cover-preflight.json,
  provenance.json, package.json; `pp1-package-sha256-` over identities, print
  configuration, three ruleset versions and file digests. Staged directory,
  verified, swapped; refuses foreign/other-book directories; export state none,
  current, stale, damaged. Optional stored ZIP with fixed order, date, attributes.
- CLI `publish validate|inspect|package` (`--output`, `--json`, `--zip`): exit 0/1/2;
  inspect `--json` equals readiness bytes. Studio: GET /publishing, POST
  /draft/publishing, POST /publishing/export {revision, archive}; Publishing tab.
- `books/publishing-demo`: cover-demo puzzles with 13 x 13 varied grids, metadata
  valid, interior and cover KDP ready, AI disclosure unknown and no confirmations,
  so packaging is blocked until a person decides. Tests/CI decide on temp copies.

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

- Baseline before edits matched Interval 9 (954 passed, 4 skipped).
  `.pytest_cache` is unreadable in this sandbox; runs used a scratch `--basetemp`.
- Python: **1114 passed, 4 skipped** (symlink permission), 1 Starlette httpx
  warning; publishing tests 160 (schema and metadata 104, readiness 19, provenance
  and package 21, CLI and API 16). Ruff lint and format (133 files), strict mypy
  (80), pip check.
- Frontend: npm ci, check (tsc, ESLint, Prettier), 55 Vitest (7 Publishing), build
  (JS 357.62 kB, CSS 38.04 kB), npm ls, npm audit --omit=dev 0. Playwright 15/15
  twice (3 new: blocked review, field findings, keyboard confirmations, save,
  export with ZIP, reload; paper-change stale cover with link; 1440/1024/768/390
  without overflow; axe on key states); captures reproduced byte-identically.
- Installed CLI: 27 regressions with expected exits (0/1/2). Scratch end to end:
  positive package hashes verified, PDFs identical to the build, inspect JSON
  stable, ZIP and every package file byte-identical across process, cwd and
  PYTHONHASHSEED; keyword change gives a new identity and a stale export; source
  change stales interior and cover; cream rebuild gives the paper message; an
  unconfirmed attestation blocks. No publishing code imports network modules; a
  test runs all commands with sockets disabled. CI publishing job simulated in
  Git Bash (all steps pass). Real Studio checked in the built-in browser and via
  Playwright captures; fixed text inputs shrunk by the radio-group rule.
- Pre-existing, unchanged: the cover-demo interior (PDF 9f907be3...) is
  structurally valid but NOT KDP ready under the existing preflight: ten verso
  puzzle pages fail `kdp_no_printer_marks` because 14 x 14 grid frames sized to the
  live width overhang it by half the 1 pt stroke (0.007 in; KDP minimum margins are
  still met). Interval 9's CI checked only the cover preflight. Its cover is ready.
  composition-demo PDF 19d5bd5a... unchanged since Interval 7.
- Fixture SHA-256 (LF) unchanged: automotive 209f3fd6, composition-demo b15651cd,
  cover-demo b906bbda, garden-demo ffd7f7eb; new publishing-demo e49110ea (photo
  34b4d3b9..., same blob as cover-demo). Remote CI not verified.

## Limits and decisions for review

Paperback only; plain-text descriptions; categories are unverified preferences;
the keyword 50-character warning is an assumption; contributor roles beyond
author/editor/illustrator/translator come from KDP's form, not its help pages;
confirmations are booleans that do not reset when metadata changes; heuristic
detectors can over- or under-report. Not modeled: pricing, territories,
marketplace, cover finish, publishing-rights options, public domain. Review
before Interval 11: whether to fix the grid-frame overhang (layout engine, a
renderer version bump) or treat sub-point overhangs within KDP margins as a
warning in preflight; whether `saved_reports` should be a note; whether
confirmations should bind to the publishing identity; and the Interval 9 items
(80-page spine reading, barcode offsets, RGB warning, 550-page maximum, two-file
cover write). History: Interval 9 commits 9c6d290 and 446252b (on main) lack their
source modules (an unanchored `cover/` ignore rule); 7ea89b2 adds them. The
branch was already merged and deleted, so it was not rewritten.