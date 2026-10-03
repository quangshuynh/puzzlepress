# Interval 4 completion report

## 1. Starting state

Clean Git working tree. Interval 3 claims checked against package, CLI, schema,
tests, fixtures, CI and documentation. Baseline: 317 passed, 1 permission skip;
Ruff lint/format, strict mypy and pip check passed. Existing core/CLI source and
regression tests remain unchanged.

## 2–6. Architecture, boundary, components, API and routes

FastAPI/uvicorn adapts the Python core; React/TypeScript/Vite provides application
views. The built frontend and API use one local server. No second project
validator, generator, solver or quality implementation.

- `src/puzzlepress/studio/service.py`: scoped project access and report adapter.
- `src/puzzlepress/studio/server.py`: HTTP errors, static serving, local launcher.
- `studio/src/{App,Library,Overview,Puzzles,ui}.tsx`: shell and implemented views.
- `studio/src/{api,types}.ts`, `style.css`: transport, types and visual primitives.
- `tests/web/`, frontend fixtures/unit tests, three real-browser acceptance tests.
- Build/lint/type/format configuration, dependency lockfile and CI job.

API: GET `/api/projects`, GET `/api/projects/{key}`, POST
`/api/projects/{key}/generation` with current source identity. Generation returns
the unchanged core batch report, independent verification and authoritative cell
coordinates. All 64-bit seeds are strings; expected errors are structured.

Routes: `/`, `/books`, `/books/{key}`, `/books/{key}/puzzles`,
`/books/{key}/puzzles/{id}`, `/books/{key}/quality`. Refresh tested.

## 7–10. Library, overview, inspector and quality

Library discovery sorts immediate folders under the books root, showing actual
titles, IDs, language, definition counts, profiles and validation. Garden-demo is
discovered; automotive is explicitly a source fixture. Resolved folder/YAML
boundaries reject escapes. Invalid projects remain visible. No source writes.

Overview exposes metadata, schema/engine version, seed, identity, ordered
definitions, bank entries, profiles/limits and quality settings. Developer JSON
is behind native disclosure controls.

Both garden-demo puzzles use `generate_batch`. The inspector shows exact grids,
targets, seeds, dimensions, profiles, verification and quality. Highlighted cells
come directly from Python placements; a textual solution register uses clearly
labeled one-based coordinates while API coordinates remain zero-based.

Validation/generation failures, successful verification, review findings, no
findings, disabled screening and incomplete screening have distinct wording.
Quality never changes the puzzle. Similarity and reuse remain descriptive.

## 11–14. Design, accessibility, responsive and application states

Impeccable's written guidance informed the editorial system recorded in
`DESIGN.md`, `PRODUCT.md` and `.impeccable/`. The user chose direct implementation.
The launcher could not initialize its engine in the restricted cache environment;
its automated engine did not run.

Locally bundled Newsreader/Public Sans, warm paper, restrained green, ruled lists,
and the unchanged logo establish the Studio. No fabricated metrics or fake pages.

Semantic controls, skip link, focus outlines, main focus after navigation, heading
hierarchy, labeled grid cells, textual solutions, reduced motion and non-color
cues are implemented. Axe found zero violations on library and both solution
views. Keyboard Enter activation and focus behavior passed.

Widths tested: 1440, 1024, 768 and 390 pixels. No page overflow. Sidebar becomes
a compact header; inspector columns stack; grid letters retain readable sizing.

Loading, empty/search-empty library, missing/invalid project, generation failure,
offline/server failure and unexpected-render states include useful messages and
recovery. Python diagnostics stay in server logs, not ordinary UI traceback text.

## 15. Real screenshots

`docs/images/studio/`: `library.png`, `project.png`, `puzzle.png`, `solution.png`,
`desktop.png`, `laptop.png`, `tablet.png`, `mobile.png`. All are actual browser
captures from real repository data. README shows two linked thumbnails.

## 16. Dependencies

- Optional Python Studio: FastAPI 0.135.x and uvicorn. The FastAPI constraint
  avoids native telemetry defaults; this release line needs no telemetry package.
- API tests: httpx. Core still uses only PyYAML.
- Frontend runtime: React/React DOM and two Fontsource font packages.
- Tooling: TypeScript, Vite/React plugin, ESLint/hooks/types, Prettier, Vitest,
  jsdom, Testing Library, Playwright and axe.
- No database, auth, queues, orchestration, cloud or analytics infrastructure.

## 17–18. Exact final checks and CLI regression results

| Check | Local result |
| --- | --- |
| Full pytest | 349 passed, 3 skipped, 1 warning; 352 collected |
| New API tests (included above) | 32 passed, 2 skipped |
| Ruff lint | Passed |
| Ruff formatting | Passed, 40 files |
| Strict mypy | Passed, 23 source files |
| pip check | No broken requirements |
| Vitest | 12 passed |
| TypeScript + ESLint + Prettier | Passed |
| Production Vite build | Passed; JS 250.75 kB, 77.06 kB gzip |
| npm ls --depth=0 | Passed |
| Playwright | 3 passed, including real-data, solution, keyboard, responsive and axe checks |
| git diff --check | Passed |

All skips are Windows symlink permissions. Starlette warns about its deprecated
httpx test client. Browser navigation emitted a Windows connection-reset diagnostic
without failing requests/assertions. Remote CI configured, not run here.

Installed executable exit 0 for all eight commands:

```text
puzzlepress --version
puzzlepress validate books/automotive
puzzlepress inspect books/automotive
puzzlepress validate books/garden-demo
puzzlepress inspect books/garden-demo
puzzlepress puzzle generate --width 10 --height 8 --seed 2026 --word ENGINE --word PISTON --solution
puzzlepress puzzle batch books/garden-demo --json
puzzlepress puzzle batch books/garden-demo --strict-quality
```

Batch JSON was parsed and checked for two puzzles, success and clean status.
API tests compare repeated HTTP output to the core report and solution coordinates
to placements. They cover 64-bit precision, stale identity, bounded partial failure,
prohibited findings, path escapes, invalid sources, generation concurrency,
unexpected failures and no filesystem writes. Existing regressions remain intact.

## 19. Documentation and durable instructions

README covers actual scope, setup, screenshots and limitations. AGENTS updates
architecture, developer extras/checks and the rule keeping domain behavior in
Python. CONTEXT records contracts and actual results for Interval 5. `docs/studio.md`
details the HTTP and filesystem boundary. Batch docs now link to the Studio.

## 20. Git state

No commit, push, PR, merge, tag, release, publishing or deployment.
Exact final `git status --short`:

```text
 M .github/workflows/ci.yml
 M .gitignore
 M AGENTS.md
 M CONTEXT.md
 M README.md
 M docs/batch-quality.md
 M pyproject.toml
?? .impeccable/
?? DESIGN.md
?? PRODUCT.md
?? docs/images/studio/
?? docs/interval-4-report.md
?? docs/studio.md
?? src/puzzlepress/studio/
?? studio/
?? tests/web/
```

## 21–22. Limits and decisions before Interval 5

Local, read-only, checkout-based app. No editing, save transactions, persisted
generation, PDFs, covers, KDP, accounts or cloud workflow. Source snapshots update
on reload. Already-running Python generation continues after browser cancellation;
one batch per process. Filesystem safety assumes a trusted local author rather
than hostile concurrent replacement. Core ASCII, batch and search limits remain.

Review edit/save transactions, stale-source conflicts, folder-key stability and
generation persistence before Interval 5. Review the FastAPI constraint on upgrades.
Firefox/WebKit and manual screen-reader testing remain future validation work;
automated accessibility checks are not certification. No Interval 5 scope added.

## 23. Exact local commands

The environment and built frontend in this workspace are ready:

```powershell
.\.venv\Scripts\puzzlepress-studio.exe
```

Open <http://127.0.0.1:8000/books>. Full installation and verification commands:
[Studio documentation](studio.md#start-locally) and README.
