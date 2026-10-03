# PuzzlePress current state

## Completed scope

Interval 4 complete: local, read-only Web Studio with real project discovery,
source overview, deterministic batches, puzzle/solution inspectors and quality
review. Existing core/CLI source and regression tests unchanged. Interval 5
browser editing has not started. No commits, pushes or deployment.

Python 3.11+, engine/package `0.1.0`, schema/identity/generation/pipeline versions
all remain `1`. Core runtime still only PyYAML. Studio extras: FastAPI
`>=0.135,<0.136` (before native telemetry defaults), uvicorn; API tests: httpx.
Frontend: React, strict TypeScript, Vite, locally bundled Newsreader/Public Sans.
Dev: Vitest/Testing Library/jsdom, ESLint, Prettier, Playwright and axe.
Frontend lockfile: `studio/package-lock.json`; use Node 22+.

## Architecture and entry points

- `src/puzzlepress/studio/service.py`: scoped read-only project store, original
  core reports plus independent verification and authoritative solution cells.
- `studio/server.py`: FastAPI handlers, static bundle, structured expected errors,
  logged unexpected exceptions, loopback-only uvicorn launcher.
- `studio/src/`: App navigation/loading/error boundary, Library, Overview,
  Puzzles/Inspector/Quality, presentation primitives, CSS and transport types.
  No frontend validator, generator, solver, seed or quality algorithms.
- `puzzlepress-studio` from repo root serves `studio/dist` and `/api` at
  `http://127.0.0.1:8000`. Flags: `--books`, `--frontend`, `--port`. Missing build
  returns 503. Wheel does not include frontend assets; checkout is required.
- Build once with `cd studio; npm ci; npm run build`. For hot reload run
  `npm run dev` alongside Python; Vite proxies API/logo to port 8000.
- API: GET `/api/projects`, GET `/api/projects/{key}`, POST
  `/api/projects/{key}/generation` with `{identity: <current build identity>}`.
  Routes: `/`, `/books`, `/books/{key}`, plus `/puzzles`, `/quality`, and
  `/puzzles/{id}` under each project. Deep links serve the shell.
- Discovery sorts immediate root folders. Keys: 1..128 ASCII letters/digits,
  hyphens/underscores, starting alphanumeric; separate from authored book IDs.
  Resolved folder/YAML boundaries reject escapes and source symlinks. Invalid
  projects remain listed. No arbitrary filesystem browser or source writes.
- Generation requires viewed identity (409 if stale); one batch per process
  (409 if busy). Expected placement failures remain HTTP 200 partial reports;
  invalid source is 422, missing project 404. Unexpected failures log diagnostics,
  return generic 500. Local Host/Origin constraints and CSP apply; no CORS.
- Puzzle/quality views generate once per mounted project. Tabs reuse results;
  refresh/reopen deterministically recomputes. No persistent cache/source watching.
  A page close does not interrupt Python generation already running.

## Core contracts to preserve

- Frozen models, explicit seeds/local RNG, canonical direction/input ordering,
  bounded generation, independent placement verification, no core printing/writes.
- `content`, `content_validation`: optional schema-v1 inline banks, explicit
  profiles and themed definitions. Legacy `content.items` is not puzzle targets.
- `batch.generate_batch` derives per-puzzle 64-bit seeds from project seed, puzzle
  ID and pipeline version with SHA-256; reordering preserves individual grids.
  JSON seeds, including Studio source seeds, are decimal strings.
- `quality` scans all eight directions with authoritative target-path exclusion,
  palindrome deduplication, 1,000-hit cap and explicit truncation. Empty policy
  means prohibited screening disabled. Findings never change generation.
- Reuse, exact duplicates, Jaccard/containment and same-position grid agreement
  remain descriptive. Success means all generated; clean also needs no findings.
- Identity covers engine and all output-affecting normalized authored inputs;
  paths/timestamps excluded. Missing word_search keeps legacy hashes. No version
  contract changed. Source/output trees stay disjoint; no generated book writes.
- Limits: ASCII words, 20 banks/profiles/puzzles, 100 entries/targets, dimensions
  1..50; default 20 restarts/100,000 attempts, caps 100/1,000,000 per puzzle.

## Design, tests and documentation

Editorial paper/green system, original logo, semantic controls, local fonts,
compact phone navigation, scrollable large grids, labeled cells, underlined
solutions and textual register. UI register is labeled one-based; API zero-based.
Validation, generation, verification and review findings are separate.
`PRODUCT.md`, `DESIGN.md`, `.impeccable/design.json` record the system. User selected
code-first. Impeccable written guidance applied; engine launcher unavailable.

Windows Python 3.13.15: **349 passed, 3 skipped** (352 collected); skips require
symlink permission. New API suite: 32 passed, 2 skipped, included in total.
Ruff lint/format (40 files), strict mypy (23 source files), pip check, eight
installed CLI regressions and git diff --check passed. Frontend: 12 Vitest tests,
strict TS/ESLint/Prettier, npm ls and production build passed. Three Playwright
tests passed with installed Chrome; zero axe violations on library and both
solution views, no browser errors in the main flow. Widths: 1440/1024/768/390;
both grids/solution cell sets match HTTP output. Eight actual screenshots in
`docs/images/studio/`. CI adds API checks and Linux frontend/Chromium job;
remote CI not run here.

Limits: Starlette warns about its httpx test-client deprecation. Windows emitted
one connection-reset diagnostic during browser navigation; requests/tests passed.
No Firefox/WebKit or manual screen-reader certification. No editing, persistence,
PDF, covers, KDP, authentication, cloud or telemetry. Source boundary assumes
trusted authors, not hostile concurrent filesystem replacement.

README has quick start; `docs/studio.md` has architecture/API/commands;
`docs/interval-4-report.md` has completion details. Before Interval 5, review save
transactions, stale-source conflicts, folder-route stability and whether
generation needs persistence. Do not implement those implicitly.
