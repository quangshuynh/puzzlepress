# PuzzlePress Studio

Studio is a local, read-only application for inspecting real PuzzlePress projects,
generated word searches, authoritative solutions, and descriptive quality reports.

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

Open <http://127.0.0.1:8000/books>. Stop with Ctrl+C. After the initial frontend
build, only the last command is needed. No Node process runs in this mode.
Linux/macOS equivalents use `.venv/bin/python`, `.venv/bin/puzzlepress-studio`,
and `npm`. Node is only needed for frontend development and builds.

The CLI accepts `--books books`, `--frontend studio/dist`, and `--port 8000`.
Paths are relative to the launch directory. Binding is deliberately loopback-only.
The Studio is supported from a repository checkout; frontend files are not bundled
into the Python wheel. `python -m puzzlepress.studio.server` is also supported.

For frontend hot reload, keep the Python server running and use `npm run dev`
from `studio/`. Open Vite's printed local URL. Vite proxies API and logo requests
to port 8000; no cross-origin API policy is needed. Rebuild before using the Python
server's UI again. The original CLI installation still needs only PyYAML.

## Architecture decision

FastAPI and uvicorn provide a thin HTTP adapter around the existing Python core.
React, strict TypeScript, and Vite provide reusable application views without an
additional full-stack framework, database, router package, or server process in
normal use. Native links and History API navigation keep URLs shareable and
refreshable. This leaves room for an editor without implementing one now.

`studio/service.py` handles scoped reads, identity checks and report presentation.
`studio/server.py` handles HTTP errors and static assets. Handlers contain no
publishing rules. Existing `load_project`, `build_identity`, `generate_batch`, and
`verify_word_search` remain authoritative and unchanged. HTTP generation retains
the exact JSON report used by the CLI, plus verification results and solution cells.

`studio/src/types.ts` describes transport shapes only. It contains no schema
validation, normalization, seed derivation, solver, or quality algorithm. Tests
compare its real-data JSON fixtures to fresh Python output. JavaScript seeds are
strings. No inputs, dimensions, words, directions, or quality policies are changed
by the browser. Rendering and numeric formatting are presentation concerns.

FastAPI is constrained to `>=0.135,<0.136`, before native telemetry hooks became
defaults. There is no analytics, telemetry exporter, account system, external font
request, or cloud service. Dependency upgrades should review that constraint.

References: [FastAPI responses](https://fastapi.tiangolo.com/advanced/custom-response/)
and [Vite backend integration](https://vite.dev/guide/backend-integration.html).

## Discovery and filesystem boundary

The configured root defaults to `books/`. Discovery is sorted by immediate folder
name and opens only `book.yaml`. Folder keys contain 1..128 ASCII letters, digits,
hyphens or underscores and start with a letter or digit. They are route keys,
independent of authored `book.id`; two folders cannot collide through book IDs.

Resolved folders must remain immediate children of the root and resolved YAML
files must remain inside their folder. Symlink sources and directory links that
escape are rejected. Invalid YAML projects remain visible with their validation
issues; directories without a supported source are ignored. A missing root is a
configuration error, while an empty existing root is an empty library.

The app never writes book YAML or generated book artifacts. Frontend build output
is disposable `studio/dist/`, separate from authored `books/`. There is no arbitrary
filesystem browser. The boundary assumes a trusted local author, not an attacker
concurrently replacing filesystem entries between checks and reads.

## HTTP surface

| Method and path | Result |
| --- | --- |
| `GET /api/projects` | Discovered valid and invalid projects, metadata and source validation |
| `GET /api/projects/{key}` | Normalized source, decimal-string seed, schema/engine version, identity and validation |
| `POST /api/projects/{key}/generation` | Complete core batch report, verification per puzzle, authoritative cell coordinates |

Generation body: `{"identity":"pp1-sha256-…"}`. It accepts no generation overrides.
Only one batch runs per process. A concurrent request returns `409 generation_busy`.
An identity mismatch returns `409 source_changed`. Reloading/retrying fetches fresh
source. Invalid projects return `422 invalid_project` with original structured
issues. Missing projects return `404 project_not_found`; a legacy source without
puzzles returns `422 no_puzzles`. Expected per-puzzle search exhaustion remains
inside an HTTP 200 batch report, preserving partial successes.

Errors have `{"error":{"code":"…","message":"…","issues":[]}}`. Unexpected
exceptions remain visible in server logs and become a generic HTTP 500 message.
Filesystem I/O diagnostics are sanitized. JSON POSTs require a matching Origin
when supplied; Host is limited to local names. Static files use a restrictive CSP.

## Routes and interaction

| Route | View |
| --- | --- |
| `/`, `/books` | Searchable library, real metadata and validation |
| `/books/{key}` | Authored metadata, definitions, banks, profiles, limits, quality configuration and identity |
| `/books/{key}/puzzles` | Generated list with verification, failures and review findings |
| `/books/{key}/puzzles/{id}` | Read-only grid, targets, seed, profile, solutions and quality |
| `/books/{key}/quality` | Batch findings, policy status, reuse and pairwise comparisons |

Entering Puzzles, an inspector, or Quality generates the authored batch. Tabs
reuse that report while the project remains open. A reload or reopening a project
repeats deterministic generation. Results are not persisted or automatically
regenerated to remove findings. A displayed report is a snapshot; external source
edits are picked up on reload, not watched continuously. Generation is bounded by
the core; closing a page does not interrupt Python work already in progress.

Source validation, successful generation, verification and quality are separate
states. Green means a specific check passed. Amber means review. Red indicates
validation/generation failure. Screening disabled and screening incomplete remain
explicit; no finding does not mean publication readiness. The fixture book-shaped
labels in the library are source labels, not authored cover designs.

The solution view uses Python-supplied cell membership. Underlines, heavier text
and a textual register accompany color. The register uses one-based coordinates
for readers and says so; API coordinates stay zero-based. Semantic tables provide
row/column labels, and large grids have a focusable horizontal scroll region.

## Design and accessibility

Impeccable's written guidance informed the editorial system: locally hosted
Newsreader headings, Public Sans controls, warm paper, restrained green accents,
flat ruled lists, and sparse status markers. The existing logo is copied into the
build without alteration. The user selected direct implementation; the Impeccable
launcher was unavailable because its binary/cache setup required external access.
`PRODUCT.md`, `DESIGN.md` and `.impeccable/` record the resulting system.

At narrower widths the sidebar becomes a compact header and inspector columns
stack. Grid letters retain their size; large grids scroll within their own region.
Links and buttons retain native keyboard behavior, route changes focus main,
there is a skip link, and reduced-motion preferences disable the loading animation.
There are explicit loading, empty-library, missing-project, invalid-source,
generation-failure, offline/server-failure and unexpected-render states.

## Checks

From the repository root with the environment activated:

```text
python -m pytest --basetemp=.pytest_cache/tmp
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pip check
```

Backend/API tests are in `tests/web/`. Core-only tests can use
`python -m pytest --ignore=tests/web`. From `studio/`:

```text
npm ci
npm run check
npm test
npm run build
npx playwright install chromium
npm run test:browser
npm ls --depth=0
```

`check` runs strict TypeScript, ESLint and Prettier. Browser tests start the local
server when needed, exercise real Python data, compare both solutions to API
coordinates, check keyboard/focus behavior and axe accessibility, and capture real
screenshots. They cover desktop 1440, laptop 1024, tablet 768 and phone 390 pixels.
To use installed Chrome instead of Playwright Chromium on Windows:
`$env:STUDIO_BROWSER_CHANNEL='chrome'` before the browser command.

The Python CI matrix retains Windows/Linux on Python 3.11/3.13/3.14. A separate
Linux job builds and tests the frontend and runs the browser checks. Remote CI
must still run; local completion is not a claim about hosted jobs.

## Screenshots

Actual garden-demo sessions, captured by `studio/e2e/studio.spec.ts`:

- [Library](images/studio/library.png)
- [Project overview](images/studio/project.png)
- [Puzzle inspector](images/studio/puzzle.png)
- [Authoritative solution](images/studio/solution.png)
- Responsive inspectors: [desktop](images/studio/desktop.png),
  [laptop](images/studio/laptop.png), [tablet](images/studio/tablet.png),
  [mobile](images/studio/mobile.png)

## Limits and next decisions

This is a local inspection foundation, with no browser editing or persistence.
There is no PDF, cover editor, KDP workflow, authentication, deployment or cloud
storage. Core limits remain ASCII words, 20 definitions and bounded greedy search.
Only Chrome/Chromium has been exercised locally; automated checks do not replace
screen-reader user testing. The local Windows run also emitted a connection-reset
diagnostic during browser navigation, without failing requests or assertions.
Starlette currently warns that its httpx-based test client is deprecated; API
tests pass and a test-client dependency migration is deferred.

Before Interval 5, review source-edit/save transactions, stale-source conflict
handling, route-key stability if project folders move, and whether persisted
generation sessions are needed. Those decisions are not implemented here.
