# Interval 5 completion report

## Starting-state assessment

The working tree was clean. AGENTS, CONTEXT, PRODUCT, DESIGN, Interval 4 report,
Studio/core/schema docs, serialization, backend/frontend, tests and CI were audited.
The Windows installed-console helper uses sysconfig's scripts path and `.exe` on
Windows. It was Ruff-formatted; console regression coverage was preserved.
Baseline: 349 Python passed, 3 permission skips; Ruff, strict mypy, pip check,
12 frontend tests, frontend check/build/npm ls, 3 browser tests and installed CLI
checks passed. esbuild required execution outside the sandbox. Remote CI was not
verified. No previous interval was reimplemented and no Interval 6 work was added.

## Editing architecture and authoritative state

Python remains authoritative. The browser holds a whole-project draft copied from
a normalized source snapshot. Validation and preview pass that object to Python;
no TypeScript schema/word/difficulty/identity/quality algorithms were added.
`service.py` supplies snapshots and reports; new `editing.py` contains explicit
adapter-level persistence. Existing core algorithms and serializer are unchanged.

Source, draft, preview and saved state are separate. Changes invalidate preview
and validation. A successful save adopts the reloaded server model, including
normalization. Project tabs retain the draft; Overview/Puzzles/Quality continue to
represent source. In-memory drafts are not written on keystrokes or preview.

## Mutation API, revisions and persistence

Added POST `/api/projects/{key}/draft/validate`, `/draft/preview` with `{source}`,
and `/draft/save` with `{source,revision}`. GET detail now includes a source byte
revision. Existing generation endpoint remains available. HTTP handlers delegate
to adapters/core. Expected errors preserve structured paths/codes; unexpected
failures are logged and produce a generic response.

Revision is SHA-256 of exact source bytes, independent of semantic identity.
Comment, line-ending and output-only changes also reject stale saves. Same-process
saves serialize; a competing save against an old revision gets 409. Drafts remain
intact on validation, conflict, network or save errors. Reload requires explicit
discard confirmation and only replaces a draft after a successful source response.

Only existing root-scoped `book.yaml` can be replaced. Save validates schema and
output separation, stages a sibling file, flushes/fsyncs, reloads/verifies it,
rechecks boundaries and revision, atomically replaces, then reloads/validates and
returns authoritative state. Pre-replacement failures preserve the original file.
Post-replacement uncertainty is explicit (`save_unconfirmed`). Tests exercise
failed fsync/replacement, corrupted staging, concurrent saves and rechecks.

The existing serializer emits sorted keys, normalized defaults/null optional
fields, canonical decimal YAML seeds and PyYAML scalar quoting/whitespace.
Comments, original quoting, blank lines and formatting are not preserved.
Sequences retain authored order except existing core normalization. The UI and
docs state this before saving; repeated normalized saves yield identical bytes.

## Implemented authoring workflows

- Puzzle title, ID, theme, bank and profile selection; ordered target add/remove/
  reorder; new definitions, deliberate removal and keyboard Up/Down management.
- Existing bank selection, entry ID/display editing, add/remove entries. Referenced
  deletions/renames are not silently repaired; Python identifies broken references.
- Shared profile width/height/directions/restarts/attempts. Shared effects are
  labeled; no invented calibrated difficulty score or per-puzzle overrides.
- Book title and shared seed; reuse and prohibited-word policy. Existing unexposed
  fields and thresholds are retained. Legacy content can explicitly initialize
  its first word-search section, requiring authored word/theme input.
- Explicit Python validation, project-level structured issues and mapped field
  associations. Pending requests disable changes; abandoned responses are ignored.
- Whole-draft deterministic batch preview with grids, targets, exact string seeds,
  dimensions/profile, independent verification and authoritative solution cells.
- Selected-puzzle and whole-book quality views preserve failure/review distinctions,
  reuse/similarity/accidental/prohibited findings and screening completeness.
  Findings never regenerate or rewrite content. Schema-valid projects can be saved
  even with generation failures or quality findings.
- Visible unsaved state, deliberate Save/Revert, project-tab retention, leave warning,
  native browser unload protection where supported, and safe failed-save retention.

## Design, accessibility and responsive evidence

Preserved the supplied logo and existing Newsreader/Public Sans, paper/green,
flat ruled publishing-desk design. Desktop uses editor beside preview; narrow
views stack, with a preview jump. No new visual world or design dependencies.
Impeccable written guidance was applied; its engine/context/detector could not run
in the restricted installation. An independent screenshot reviewer returned ship
visually. The documenter verified PRODUCT and the narrow Evidence Rule update for
truthful local unsaved status. Other existing design drift was not changed.
The Vercel React checklist informed component review. agent-browser was unavailable;
real browser work used the repository's Playwright toolchain.

Semantic labeled forms, fieldsets, visible focus, explicit buttons, keyboard reorder,
native keyboard confirmations and status announcements are present. Solutions
use underlines/weight and a textual register as well as color. Automated axe checks
found zero violations in the tested preview/solution, validation, conflict, narrow,
expanded profile and legacy-empty states. No screen-reader certification claimed.
1440/1024/768/390 browser checks found no page overflow; critical controls remain.

Ten new actual screenshots in `docs/images/studio/`: `editor.png`,
`word-editing.png`, `draft-preview.png`, `editor-quality.png`,
`editor-validation.png`, `editor-conflict.png`, `editor-1440.png`,
`editor-1024.png`, `editor-768.png`, `editor-390.png`. Existing eight captures were
refreshed for current navigation. README shows two linked editor captures.

## Exact final checks

| Check | Result |
| --- | --- |
| Full Python | 386 passed, 4 skipped, 1 warning; 390 collected |
| API suite (included above) | 69 passed, 3 skipped, 1 warning; 72 collected |
| New write suite (included above) | 37 passed, 1 skipped |
| Ruff lint / format | Passed / 45 files already formatted |
| Strict mypy | Passed, 24 source files |
| pip check | No broken requirements |
| npm ci | Passed, 273 packages installed; existing deprecation/advisory notices |
| Vitest | 21 passed, 2 files |
| TypeScript / ESLint / Prettier | Passed |
| npm ls --depth=0 | Passed |
| Production build | Passed; JS 267.02 kB, 81.63 kB gzip |
| Playwright / installed Chrome | 5 passed in 16.0s |
| Installed Studio real-source smoke | Passed; editor/profile/legacy empty state; no saves |
| Installed CLI | Eight commands exit 0; batch JSON parsed and checked |
| git diff --check | Passed |
| npm audit (additional inspection) | Exit 1; 2 moderate existing dev-tool entries |

All four Python skips are Windows symlink permission. Simulated resolved-boundary
and path-traversal tests also ran. The warning is Starlette's pre-existing httpx
TestClient deprecation. npm audit identifies Vitest/@vitest/mocker under
GHSA-82fw-gwwq-j7x9; remediation requires a major tooling upgrade, left for separate
review. No dependencies or lockfile changes. No remote CI claim. Python matrix and
installed-console coverage remain; browser checks stay in the existing separate job.

The browser acceptance suite performs real temporary edit/validate/repeated-preview/
quality/save/reload and competing-write conflict. HTTP save failure is simulated
in the browser; actual filesystem failure behavior is tested in Python. Tests also
cover field validation, draft retention/revert, malformed/offline responses,
request cancellation, profile selection and keyboard management. Initial test
failures exposed one button contrast issue (fixed) and test fixture/selector
mistakes (corrected); the final results above are the completed reruns.

## Fixture safety

All write tests use pytest temporary projects or the browser runner's OS temporary
copies. The runner binds port 8015 and refuses to reuse a running server, so browser
writes cannot target a normal authoring server. Actual repository source was only
read by the installed-launcher smoke. Byte checks confirm unchanged SHA-256:

- garden-demo: `ffd7f7eb02c5d88f1f3e4880a505e140d60562cb113973fc448aeaabcffac540`
- automotive: `209f3fd646b2bf5cfd97f646c2c7868ba376edf9e11bf262bb09a02a5f3759e0`

## Documentation, limitations and decisions before Interval 6

README is concise authoring/setup/screenshot/limits guidance; docs/studio.md details
workflow/API/persistence/recovery. PRODUCT, batch-quality link, CONTEXT and this
report reflect Interval 5. DESIGN and its sidecar only clarify draft status semantics.
AGENTS and CI were unchanged. No commit, push, PR, merge, release or deployment.

Review these deliberate limits before expanding scope:

1. Canonical YAML saves remove comments/formatting. No alternate round-trip library.
2. One Studio process per library. Portable check-then-replace is not atomic CAS
   against uncooperative external tools; hostile filesystem swapping and network
   filesystems are outside the boundary. No sudden-power-loss durability guarantee.
3. A forcibly killed process may leave an ignored sibling temp file. No automatic
   recursive cleanup. Post-save uncertainty requires source reload/review.
4. Drafts/previews are memory-only, with no autosave, undo history, merge or force save.
   Invalid saved YAML requires disk repair. Existing banks/profiles can be edited
   but additional banks/profiles or project folders are not created by this UI.
5. Core ASCII and bounded-generation limits persist. No Firefox/WebKit or manual
   screen-reader verification. Existing Vitest tooling advisory needs separate review.
6. No book composition, PDF/print layout, covers, KDP, cloud, accounts, AI generation
   or publishing automation. Interval 6 has not begun.

## Exact local commands

From repository root on Windows, after the existing installation:

```powershell
.\.venv\Scripts\puzzlepress-studio.exe
.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest_cache/tmp
.\.venv\Scripts\python.exe -m pytest tests/web --basetemp=.pytest_cache/tmp-api
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\puzzlepress.exe --version
.\.venv\Scripts\puzzlepress.exe validate books/automotive
.\.venv\Scripts\puzzlepress.exe inspect books/automotive
.\.venv\Scripts\puzzlepress.exe validate books/garden-demo
.\.venv\Scripts\puzzlepress.exe inspect books/garden-demo
.\.venv\Scripts\puzzlepress.exe puzzle generate --width 10 --height 8 --seed 2026 --word ENGINE --word PISTON --solution
.\.venv\Scripts\puzzlepress.exe puzzle batch books/garden-demo --json
.\.venv\Scripts\puzzlepress.exe puzzle batch books/garden-demo --strict-quality
cd studio
npm.cmd ci
npm.cmd run check
npm.cmd test
npm.cmd run build
npm.cmd ls --depth=0
$env:STUDIO_BROWSER_CHANNEL='chrome'
npm.cmd run test:browser
cd ..
git diff --check
git status --short
```

Use `npx playwright install chromium` and omit the Chrome environment setting when
using Playwright's bundled browser. Full first-time setup is in README/docs/studio.

## Exact final Git status

```text
 M .impeccable/design.json
 M CONTEXT.md
 M DESIGN.md
 M PRODUCT.md
 M README.md
 M docs/batch-quality.md
 M docs/images/studio/desktop.png
 M docs/images/studio/laptop.png
 M docs/images/studio/library.png
 M docs/images/studio/mobile.png
 M docs/images/studio/project.png
 M docs/images/studio/puzzle.png
 M docs/images/studio/solution.png
 M docs/images/studio/tablet.png
 M docs/studio.md
 M src/puzzlepress/studio/server.py
 M src/puzzlepress/studio/service.py
 M studio/playwright.config.ts
 M studio/src/App.tsx
 M studio/src/api.ts
 M studio/src/fixtures/library.json
 M studio/src/fixtures/project.json
 M studio/src/style.css
 M studio/src/types.ts
 M tests/web/test_studio.py
?? docs/images/studio/draft-preview.png
?? docs/images/studio/editor-1024.png
?? docs/images/studio/editor-1440.png
?? docs/images/studio/editor-390.png
?? docs/images/studio/editor-768.png
?? docs/images/studio/editor-conflict.png
?? docs/images/studio/editor-quality.png
?? docs/images/studio/editor-validation.png
?? docs/images/studio/editor.png
?? docs/images/studio/word-editing.png
?? docs/interval-5-report.md
?? src/puzzlepress/studio/editing.py
?? studio/e2e/editor.spec.ts
?? studio/e2e/server.py
?? studio/src/ContentEditor.tsx
?? studio/src/Editor.test.tsx
?? studio/src/Editor.tsx
?? studio/src/editor-fields.tsx
?? tests/web/test_editing.py
```
