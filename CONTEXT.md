# PuzzlePress current state

## Completed scope

Interval 9 complete: photography-first Cover Studio on branch `feat/cover-studio`
(from main `b3e8c13`, pushed, not merged; no PR, tag, release or deployment).
Authors build a deterministic full-wrap paperback cover from their own photo,
sized from the built interior, via CLI (`puzzlepress cover ...`) or Studio's Cover
tab, with cover preflight. No Interval 10 work (KDP metadata, package,
publishing). Engine/package 0.1.0; identity, pipeline, composition, plan,
interior manifest and renderer versions unchanged; `paperback-8.5x11` profile v2.
Contracts: docs/cover.md plus book-composition, print-interior, preflight.

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
  tests/cover_demo_photo.py): valid and KDP ready, spine text omitted. 20-puzzle
  limit keeps every book below 80 pages; spine text tested with synthetic facts.

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

- Baseline before edits matched Interval 8 (646 passed, 4 skipped; 39 Vitest;
  Playwright 9/9). `.pytest_cache` is unreadable in this sandbox; runs used a
  scratch `--basetemp`.
- Python: **954 passed, 4 skipped** (symlink permission), 1 Starlette httpx
  warning; cover and cover API tests alone 306. Ruff lint and format (109 files),
  strict mypy (65), pip check.
- Boundaries: spine at 1/11/24/79/80/300/550 pages, white and cream; 79/80 spine
  eligibility; exact safe, barcode and region insets; every EXIF orientation;
  crop clamps, zoom, DPI; 144 preset/position/align/treatment combinations meet
  the layout contract; tampered layouts, PDFs, manifests, interiors and photos.
- Frontend: npm ci, check, 48 Vitest (9 Cover), build (JS 329.99 kB, CSS
  34.20 kB), npm ls, npm audit --omit=dev 0. Playwright 12/12 twice (3 new: import,
  keyboard crop, overlays, save/reload, build verdicts; drag; cover demo ready at
  1440/1024/768/390; axe). Captures reproduced byte-identically.
- Installed CLI: 34 regressions as expected. Independent check with an EXIF-6
  photo carrying camera/GPS/comment data: none in cover.pdf, JFIF only, boxes
  exact, spine 29 x 0.002252 in, upright raster, identical rebuild from another
  cwd/PYTHONHASHSEED, stale after source/interior/photo changes, preflight
  read-only. CI cover job simulated in Git Bash (all steps pass).
- Real Studio inspected in the built-in browser at 1440 and 375; fixed: pale pressed
  toggles, file input sizing, lost import notice, label/output pairing, cramped
  three columns (now only >=1600px). Cover visually checked (type, shade, back,
  barcode corner, bleed).
- build/: composition-demo interior PDF 19d5bd5a... (unchanged since Interval 7),
  valid, not KDP ready; cover-demo interior 9f907be3..., cover 5dcaf42d...
  (identity pp1-cover-sha256-01167bf7...), valid and ready.
- Fixture SHA-256 (LF) unchanged: automotive 209f3fd6, composition-demo b15651cd,
  garden-demo ffd7f7eb; new cover-demo b906bbda (+ photo 34b4d3b9...). Remote CI
  not verified.

## Limits and decisions for review

One trim; black ink white/cream; RGB output without CMYK or output intent; two
layouts, three presets; Latin-1 sans; no barcode/ISBN, hardcover or ebook covers;
unreferenced imported photos are kept. Review before Interval 10: the 80-page
spine reading, the assumed barcode offsets, RGB-as-warning, the 20-puzzle cap
versus spine text, cover excluded from build identity, the profile v2 bump
(staling v1 interiors), keeping the 550-page maximum for white paper, and the
two-file non-atomic cover write. History note: commits 6850538 and fc4477d lack
their source modules (an unanchored `cover/` ignore rule); 21819fa adds them.
Interior notes from Interval 8 still apply (550 max ambiguity, subset embedding
warning, preflight.json default write).
