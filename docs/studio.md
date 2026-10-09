# PuzzlePress Studio

Studio is a local visual editor for word-search projects, their book composition,
a print proof of the built interior, a photography-first cover studio and a
publishing workspace that exports a package for manual KDP upload. Python remains the
single authority for schema validation, normalization, generation, identity and
quality. The browser keeps drafts and displays authoritative results.

## Start locally

Python 3.11+ and Node.js 22+ are required. From the repository root on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,studio,web-test]"
cd studio
npm.cmd ci
npm.cmd run build
cd ..
.\.venv\Scripts\puzzlepress-studio.exe
```

Open <http://127.0.0.1:8000/books>. After building, only the last command is needed.
Linux/macOS use `.venv/bin/python`, `.venv/bin/puzzlepress-studio` and `npm`.
The launcher is loopback-only; flags are `--books books`, `--frontend studio/dist`
and `--port 8000`. Paths are relative to the launch directory. A checkout is
required: the Python wheel does not bundle the frontend. For frontend development,
run `npm run dev` in `studio/` alongside the Python server; Vite proxies API calls.

## Authoring workflow

1. Open a valid project and choose **Edit**. The initial draft is a copy of the
   normalized persisted source. Overview, Puzzles and Quality show saved source;
   the Edit tab retains its draft when you visit those tabs.
2. Edit a puzzle title, ID or theme. Select its bank and difficulty profile. Add
   or remove target references and reorder them with the Up/Down controls.
3. In **Word banks**, choose any existing bank and edit entry IDs/display text,
   add entries or deliberately remove them. Bank changes affect all referencing
   puzzles. Renaming/removing entry IDs does not silently repair references;
   validation identifies references that need attention.
4. Add, remove or reorder puzzle definitions. New IDs are the first unused
   `puzzle-N`; entries use `word-N`. No randomness or clock data is introduced.
   The project seed is shared. Changing a puzzle ID changes its derived seed;
   reordering puzzles preserves their individual seeds and grids.
5. Expand **Profile settings** to edit the selected shared profile's dimensions,
   directions and work limits. Names are authored settings, not calibrated scores.
   Quality policy exposes maximum reuse and the prohibited-word list. Similarity
   thresholds and other unexposed schema values are retained in the draft.
6. **Validate draft** explicitly asks Python to validate the entire project.
   Issues retain original paths/codes; safely mapped input errors also appear
   beside their fields. Editing clears outdated issues and preview results.
7. **Preview draft** validates and generates the whole unsaved batch. Inspect the
   selected grid, targets, decimal-string seed, profile, independent verification,
   authoritative solutions and whole-book quality. Findings never rewrite content.
   Generation failures, review findings, disabled screening and incomplete scans
   remain distinct. Neither validation nor preview writes any source or output.
8. **Save changes** validates again, checks the revision, persists and reloads.
   The editor adopts the server's reloaded state, including normalization. Saving
   requires schema/filesystem validity, not a clean quality report or successful
   generation. Publishers may save valid content that still needs review.

**Revert draft** returns to the snapshot originally opened or last saved, after
confirmation. It does not fetch external edits. Leaving the project with edits
requires confirmation; browser close/refresh uses the native warning where
supported. Drafts stay in memory only. No autosave, undo history or recovery after
closing the browser is provided. Requests disable draft controls while pending;
responses from abandoned components are ignored.

A legacy project can explicitly add initial word-search content, with visible
10×10/right/down custom settings. The first word and theme need author input.
Invalid saved YAML remains visible as an invalid project; repair it on disk before
opening the visual editor. The editor does not create project folders, rename
banks/profiles or add additional banks/profiles to existing content.

## Book composer

Choose **Book** in a project. The composer edits the same in-memory draft as
**Edit**: one revision, one unsaved state, one validation and one save. Changes
made in either tab are visible in the other. Composition rules are in
[book composition](book-composition.md).

1. A project without `composition` shows an explicit **Start book composition**
   action: a title page, editable instructions and solutions at the end. Nothing is
   saved until **Save changes**. No copyright text is supplied.
2. **Front matter** and **Back matter** list one logical page per item. Add, remove
   and reorder items with buttons. The title page edits the book's subtitle, author
   and imprint; the book title stays in Edit.
3. **Puzzles** sets whether the section starts on a recto page and reorders the
   project's single puzzle order with Up/Down. Focus follows the moved puzzle.
   Reordering also reorders Edit and reports, never a grid.
4. **Solutions** chooses end or omit, the section heading, solutions per logical
   page and the section start. **Page numbers** chooses the scheme and which
   sections print numbers.
5. On opening, the saved plan is requested once. After edits, **Preview plan**
   validates, generates and plans the unsaved draft. The plan lists every logical
   page grouped by section, with side, number (parenthesized when counted but not
   printed), content, cross-references and explicit blanks with their reason, plus
   statistics, verification, completeness and a separate quality-finding count.
   It is not a print preview. After a save or reload the plan refreshes.

Validation errors attach to their composer fields. Failed and stale saves keep the
draft, exactly as in Edit. Drag-and-drop is not used: buttons work for pointer and
keyboard and avoid accidental moves.

## Print proof

Choose **Print** to build the saved source's interior, run preflight and proof the
real PDF page by page: thumbnails, single pages, facing spreads, zoom, geometry
overlays and findings linked to their pages. Builds use the saved revision only;
unsaved drafts disable **Build interior**. Stale and mismatched interiors are
labeled. Details, caching and endpoints: [preflight](preflight.md#studio-print-proof).

## Cover Studio

Choose **Cover** to design the paperback cover around your own photograph
([cover](cover.md)). The Cover tab edits the project's `cover` section in the same
draft as Edit and Book: one revision, one validation, one save.

1. Build the interior in **Print** first: the wrap is sized from its real page
   count, trim and paper (Print offers white or cream paper). Without one, the
   preview explains that the interior is missing.
2. A book without a cover starts by choosing a photo already in `cover-assets` or
   importing a JPEG or PNG. Import copies the original bytes into the project
   immediately, never overwriting; choosing it only changes the draft.
3. Edit the layout (full wrap or front photo), crop (focal point and zoom),
   type preset, title position, alignment, tone, legibility treatment, fill
   color, spine-text policy and back text. Title, subtitle, author and imprint
   come from the book details (Edit and Book tabs).
4. Each change renders the draft's real cover PDF in Python (debounced) and shows
   a PDFium raster of it. Views: full wrap, front, spine and back crop the same
   raster. Overlays drawn from Python geometry: trim and folds, bleed, KDP safe
   areas, PuzzlePress type area, barcode corner, text bounds. None are in the PDF.
5. Crop by dragging the photo, with the sliders, or with the keyboard on the
   focused preview: arrows move the focal point (Shift for larger steps), `+`/`-`
   zoom, `0` resets. All map to normalized values; Python clamps and reports the
   applied focal point.
6. The readiness column shows interior pages and paper, the calculated spine width
   and wrap size, spine-text eligibility, effective DPI with its source pixels and
   printed size, a stale-interior warning, and the built cover's separate
   structural and KDP verdicts, stale reasons and findings.
7. **Save changes**, then **Build cover** (saved revision only; disabled while the
   draft is dirty). Switch between **Draft preview** and **Built cover.pdf**.

A draft previews against the last built interior even when that interior is out
of date for the draft, and says so; an interior whose files do not agree is
refused. Decoded photos (two) and draft PDFs (160 MB) are cached in memory.

## Publishing

Choose **Publishing** to turn the built book into a package for manual KDP upload
([publishing](publishing.md)). It edits the project's `publishing` section in the
same draft as Edit, Book and Cover.

1. A book without metadata shows **Start publishing metadata**: every decision
   starts undecided and nothing is confirmed for you.
2. The summary shows the front panel cropped from the built `cover.pdf` raster,
   title, subtitle, author, format, paper, pages, spine width and separate
   metadata, interior, cover and package verdicts.
3. Edit series, edition, contributors, the plain-text description (with a
   character count), keywords, category preferences, the explicit-content and
   reading-age answers, low-content classification, the ISBN option, AI content
   per kind and your confirmations. Title, subtitle, author, imprint and language
   are shown read-only, linking to Edit and Book.
4. As you type, Python checks the draft (`POST /draft/publishing`); blocking and
   review findings appear beside their fields as text.
5. Confirmations come from that check. Each shows **Confirmed**, **Review
   again** (with what it covers and that it changed) or **Not confirmed**; a box
   is checked only when Python reports the current draft confirmed, and shows
   nothing while a newer draft is being checked. Ticking one records the review
   identity Python reported; editing covered content unticks it, and nothing is
   reconfirmed for you. A version 1 section shows **Upgrade publishing section**
   and its old answers never count. Native checkboxes; Space toggles.
6. The readiness column (saved source) lists what is done and what is left with
   links to Print or Cover, the readiness statement, grouped findings with their
   KDP sources, and every check. It moves above the form below 1000px.
7. **Save changes**, then **Export package** (saved revision only; disabled while
   the draft is dirty or anything blocks). Optionally write `publishing.zip`. The
   summary lists the files, digests, location relative to the project and the
   package identity, and the checklist is shown in full. Nothing is uploaded.

## Conflict and failure recovery

A save includes the revision loaded with the authoritative source. A competing
save or external byte change, including comments or output settings, returns
`409 source_changed`. The draft remains available. Review/copy the edits you want
to keep, then choose **Reload saved source** and confirm discarding the draft.
Reload is read-only and the draft is replaced only after the response succeeds.
There is no automatic merge or force-overwrite button.

Invalid drafts return structured issues without writing. Failed saves retain the
draft and never show a success state. `save_unconfirmed` means replacement occurred
but reload could not confirm the result; reload to review before retrying. A lost
network response can likewise leave the client uncertain whether a save completed.
Missing projects, unavailable server, malformed response and unexpected failures
have recovery messages. Python tracebacks stay in server logs.

## Persistence and YAML behavior

Only `book.yaml` in an immediate project folder under the configured books root
can be replaced. Route keys are 1..128 ASCII letters/digits/hyphens/underscores,
starting alphanumeric. Keys are independent of book IDs. Resolved directory/file
boundaries and symlinks are checked; output must remain disjoint from source.
No caller-supplied destination or arbitrary filesystem write is accepted.

`studio/editing.py` validates the complete proposed object through `validate_project`
and `resolve_output_directory`. It stages `dump_project` UTF-8 bytes in a unique
sibling temporary file, flushes and fsyncs it, then reloads and verifies that staged
model. It rechecks route/output boundaries and the exact original revision before
`os.replace`. Same-directory replacement is atomic on supported local Windows and
POSIX filesystems: readers see the old or new complete file. Successful saves reload
and validate the authoritative file and return that state. Saves within a process
serialize through a lock. Failures before replacement preserve the old source and
attempt to remove the staged file; cleanup failures are logged.

Use one Studio process per books root. Portable file APIs do not provide an atomic
compare-and-swap against an uncooperative external editor: a very small interval
remains between the last revision check and replacement. This is trusted local
authoring software, not protection against hostile concurrent filesystem swaps.
Network filesystem semantics and sudden-power-loss durability are not guaranteed.
A forcibly killed process may leave a `.puzzlepress-*.tmp` sibling; it is never
loaded as project source, and Studio does not recursively clean directories.

The existing PyYAML serializer is deliberately canonical, not a formatting
round-tripper. It sorts mapping keys, emits normalized defaults and null optional
book fields, preserves authored sequence order, and uses its own scalar quoting,
whitespace and formatting. Comments, original quotes and blank lines are lost.
Seeds become decimal YAML integers; HTTP seeds remain decimal strings. Directions
and prohibited search forms follow existing core normalization. Equivalent models
produce identical YAML bytes. No YAML dependency or schema change was added.

## Architecture and HTTP surface

- `studio/service.py`: scoped snapshots, byte revisions, core report presentation.
- `studio/editing.py`: explicit adapter-level persistence, keeping core APIs pure.
- `studio/printing.py`, `studio/preview.py`: interior build/preflight adapter and the
  PDFium page rasterizer with its digest-keyed cache (one process-wide PDFium lock).
- `studio/covering.py`: cover status, draft render, photo import, build and rasters.
- `studio/publishing.py`: publishing readiness, draft metadata checks and export.
- `studio/server.py`: thin HTTP handlers, expected errors, static assets and launcher.
- `studio/src/draft.tsx`: shared draft lifecycle and toolbar; `Editor.tsx`,
  `ContentEditor.tsx`, `Composer.tsx`, `editor-fields.tsx`: visual inputs and
  transport presentation. No second domain implementation or planner.

| Method and path | Request / result |
| --- | --- |
| `GET /api/projects` | Sorted library, including invalid projects |
| `GET /api/projects/{key}` | Normalized source, validation, identity, engine version, byte revision |
| `POST /api/projects/{key}/generation` | `{identity}`; saved-source batch report |
| `POST /api/projects/{key}/draft/validate` | `{source}`; normalized valid project and semantic identity |
| `POST /api/projects/{key}/draft/preview` | `{source}`; core batch, verification and authoritative solution cells |
| `POST /api/projects/{key}/draft/plan` | `{source}`; verified publication plan, verification and generation summary |
| `POST /api/projects/{key}/draft/save` | `{source, revision}`; reloaded authoritative state and new revision |
| `GET /api/projects/{key}/interior` | Saved interior state (`missing`, `current`, `stale`, `invalid`), preflight report, preview pages and overlay geometry |
| `POST /api/projects/{key}/interior/build` | `{revision}`; builds saved source, writes interior and `preflight.json`, returns state or `{build: {success: false, stage, diagnostics}}` |
| `GET /api/projects/{key}/interior/pages/{n}` | `?size=thumb\|page\|detail&pdf=<sha256>`; PNG raster of page `n` of that exact PDF |
| `GET /api/projects/{key}/cover` | Saved cover state (`no_config`, `missing`, `current`, `stale`, `invalid`), cover preflight report, layout geometry |
| `POST /api/projects/{key}/draft/cover` | `{source}`; renders the draft's cover in memory; layout geometry, interior facts, checks, preview digest |
| `GET /api/projects/{key}/cover/preview` | `?size=preview\|detail&pdf=<sha256>`; PNG of a draft PDF or `cover.pdf` (409 when gone) |
| `GET /api/projects/{key}/cover/assets` | Photos in `cover-assets` with pixels, orientation and problems |
| `POST /api/projects/{key}/cover/assets` | `?name=`; raw `image/jpeg` or `image/png` body (the only non-JSON POST); imports and returns the asset |
| `POST /api/projects/{key}/cover/build` | `{revision}`; builds saved source, writes `cover.pdf`, `cover.json`, `cover-preflight.json` |
| `GET /api/projects/{key}/publishing` | Readiness report, KDP metadata record, checklist, package identity, export state (`none`, `current`, `stale`, `damaged`), location, built cover digest |
| `POST /api/projects/{key}/draft/publishing` | `{source}`; `{metadata, upgrade}`: findings and confirmation states with current review identities for the draft, and the version 2 form of a version 1 section; writes nothing |
| `POST /api/projects/{key}/publishing/export` | `{revision, archive}`; exports the saved revision's package (409 `source_changed`), or returns why not and writes nothing |

Revision is `sha256-<digest of exact source bytes>`. It detects cosmetic changes
and output edits that semantic identity intentionally excludes. Identical bytes
have the same revision, including repeated canonical saves. Draft validation has
no persisted revision (`null`). Build identity/version and per-puzzle seed
contracts are unchanged. Reports retain the CLI structure and string seeds.

Errors use `{"error":{"code":"...","message":"...","issues":[]}}`.
Invalid project/draft: 422; missing project: 404; stale source: 409; save I/O failure:
503; unexpected programming failure: generic 500 with logged diagnostics.
One generation or plan runs per service at a time; competing requests receive
`409 generation_busy`. Planning a draft without composition returns `422 no_composition`. Expected per-puzzle generation failures are in the
HTTP 200 batch report. Closing a page does not interrupt already-running Python.
JSON POSTs require same-origin Origin when supplied, local Host and JSON content
type. CSP and no-store response headers remain enabled; no CORS, auth or telemetry.

Routes: `/books`, `/books/{key}`, `/books/{key}/edit`, `/books/{key}/book`, `/books/{key}/print`, `/books/{key}/cover`, `/books/{key}/publishing`, `/books/{key}/puzzles`,
`/books/{key}/puzzles/{id}`, `/books/{key}/quality`. Deep links serve the shell.

## Design, accessibility and screenshots

The established paper/green design, supplied logo, locally bundled Newsreader and
Public Sans remain. Desktop editing sits alongside preview; narrower views stack
and include a preview jump. Labels, fieldsets, explicit buttons, focus outlines,
keyboard reorder controls, native discard/delete confirmations and polite status
messages support keyboard operation. Solutions also use underlines and a textual
one-based coordinate register; the API remains zero-based. Large grids scroll
inside their region. Reduced-motion behavior remains.

Actual captures from disposable projects:
[editor](images/studio/editor.png), [word editing](images/studio/word-editing.png),
[draft solution](images/studio/draft-preview.png), [quality](images/studio/editor-quality.png),
[validation](images/studio/editor-validation.png), [conflict](images/studio/editor-conflict.png),
and [1440](images/studio/editor-1440.png), [1024](images/studio/editor-1024.png),
[768](images/studio/editor-768.png), [390](images/studio/editor-390.png) widths.
Composer: [overview](images/studio/composer.png), [front matter](images/studio/composer-front-matter.png),
[ordering](images/studio/composer-order.png), [plan](images/studio/composer-plan.png),
[validation](images/studio/composer-validation.png), and [1440](images/studio/composer-1440.png),
[1024](images/studio/composer-1024.png), [768](images/studio/composer-768.png),
[390](images/studio/composer-390.png) widths. Above 1200px the plan stays in view while
editing; narrower layouts stack it below the outline with a **Jump to plan** link.

## Checks

From the repository root, with the environment activated:

```text
python -m pytest --basetemp=.pytest_cache/tmp
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pip check
```

From `studio/`:

```text
npm ci
npm run check
npm test
npm run build
npm ls --depth=0
npx playwright install chromium
npm run test:browser
```

`check` runs strict TypeScript, ESLint and Prettier. Browser tests start
`e2e/server.py` on port 8015 with disposable temporary copies, never reuse a running
server, and verify the repository fixtures' bytes remain unchanged. API writes
also use pytest temporary projects. Browser checks cover real edit/preview/save/
reload, deterministic preview, conflict, simulated HTTP save failure, field errors,
keyboard operation, responsive layouts and axe, for Edit, the Book composer and the
Print proof (real build, preflight, rasterized pages, overlays, spreads). For installed Chrome on Windows,
set `$env:STUDIO_BROWSER_CHANNEL='chrome'` before running browser tests.
The Python Windows/Linux 3.11/3.13/3.14 CI matrix and separate Linux browser job
remain unchanged; local results do not establish remote CI status.

## Limits

Existing ASCII/size/search limits apply. No extra schema fields, calibrated
scores, automatic content repair, persisted previews, collaboration or cloud.
Only Chrome/Chromium is exercised; axe is not screen-reader certification.
Starlette warns about its deprecated httpx test client. Page previews need
`pypdfium2` (in the `studio` extra). Publishing exports a local package only; it never
logs in to, uploads to or submits anything in KDP.
Publishing captures: [overview](images/studio/publishing.png),
[metadata](images/studio/publishing-metadata.png),
[AI disclosure](images/studio/publishing-disclosure.png),
[readiness](images/studio/publishing-readiness.png),
[blocking findings](images/studio/publishing-blocking.png),
[ready package](images/studio/publishing-ready.png),
[export](images/studio/publishing-export.png), [390](images/studio/publishing-390.png).
Cover captures: [overview](images/studio/cover.png), [start](images/studio/cover-start.png),
[front crop](images/studio/cover-crop.png), [full wrap](images/studio/cover-wrap.png),
[overlays](images/studio/cover-overlays.png), [spine](images/studio/cover-spine.png),
[readiness](images/studio/cover-readiness.png), [1440](images/studio/cover-1440.png),
[390](images/studio/cover-390.png).
Print captures: [overview](images/studio/print.png), [puzzle](images/studio/print-puzzle.png),
[spread](images/studio/print-spread.png), [overlays](images/studio/print-overlays.png),
[findings](images/studio/print-findings.png), [status](images/studio/print-kdp-not-ready.png),
[390](images/studio/print-390.png).
