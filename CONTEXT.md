# PuzzlePress current state

## Completed scope

Interval 5 complete: local visual word-search authoring with Python validation,
unsaved deterministic previews, real quality review and revision-checked source
saves. No Interval 6 work, commits, pushes or deployment. Engine/package 0.1.0;
schema, identity, generation and pipeline contracts remain version 1.

## Architecture and launch

- Python core remains pure and authoritative. Runtime dependency remains PyYAML.
  Studio extras remain FastAPI >=0.135,<0.136 and uvicorn; web tests use httpx.
- React/strict TypeScript/Vite frontend, locally bundled Newsreader/Public Sans.
  No dependencies added; existing lockfile unchanged. Node 22+, Python 3.11+.
- `src/puzzlepress/studio/service.py`: scoped snapshots/revisions and core report
  presentation; `editing.py`: draft validation and explicit file transactions;
  `server.py`: thin HTTP/static boundary and installed loopback launcher.
- `studio/src/Editor.tsx`: saved/draft/preview lifecycle; `ContentEditor.tsx`:
  targets, bank entries, profiles and policy; `editor-fields.tsx`: input helpers.
  Existing Overview/Puzzles/Quality remain views of saved source.
- Build: `cd studio; npm ci; npm run build`. Launch from root:
  `.\.venv\Scripts\puzzlepress-studio.exe` at http://127.0.0.1:8000/books.
  Flags: --books, --frontend, --port. Checkout required; wheel lacks UI assets.
  `npm run dev` proxies API/logo to port 8000 for hot reload.

## Editing and API

- `/books/{key}/edit` edits puzzle ID/title/theme, bank/profile references, ordered
  targets; add/remove/reorder definitions; edit/add/remove bank entries; shared
  profile dimensions/directions/limits; book title/seed; reuse/screening policy.
  Legacy projects can explicitly initialize word-search content. No folder creation
  or extra bank/profile creation in existing content. Unexposed fields survive.
- GET `/api/projects`, GET `/api/projects/{key}` (normalized source, string seed,
  build identity, validation, engine version and exact-byte revision).
- POST `/api/projects/{key}/generation` with `{identity}` still generates source.
- POST `/api/projects/{key}/draft/validate` and `/draft/preview` with `{source}`.
  Validation returns normalized model/identity, null persisted revision. Preview
  uses the same batch engine, quality, verification and authoritative cells as CLI.
- POST `/api/projects/{key}/draft/save` with `{source, revision}` returns reloaded
  authoritative state. All mutations validate through Python, including output
  separation. Quality findings/generation failure do not prohibit valid saves.
- Explicit validation avoids keystroke traffic. Pending requests disable editing;
  edits clear old findings/previews and abandoned responses are ignored. Drafts
  stay mounted across project tabs; leaving with edits requires confirmation.
  Beforeunload warns where supported. Delete/revert/reload are deliberate.
- Expected errors have `{error:{code,message,issues}}`; invalid draft/source 422,
  missing 404, conflict/busy 409, save I/O 503. Unexpected failures log diagnostics
  and return generic 500. Host/Origin/JSON/CSP boundaries retained; no CORS.

## Persistence contract

- Only existing immediate-child `book.yaml` under configured root can be replaced.
  Keys are ASCII 1..128, letters/digits/_/-, alphanumeric first, independent of IDs.
  Resolved directory/file boundaries reject escapes/symlinks. No arbitrary writes.
- Revision `sha256-<exact source bytes>` is separate from semantic build identity:
  comments, line endings and output-only edits also conflict. Repeated canonical
  bytes have identical revision. Saves serialize within one process.
- Validate, stage UTF-8 canonical YAML in sibling temp, flush/fsync, reload/check
  staged model, recheck boundaries and revision, `os.replace`, reload/validate,
  return persisted state. Failed staging/replacement preserves old source.
  Failed post-replacement confirmation reports `save_unconfirmed`; reload/review.
- PyYAML sorts mapping keys and emits normalized defaults/null optional fields,
  decimal integer YAML seeds and its own scalar quoting/whitespace. Sequence order
  remains authored except existing direction/screening normalization. Comments
  and original formatting are deliberately lost; UI warns before save.
- Use one Studio process/library. No portable atomic compare-and-swap with an
  uncooperative external editor: last-check/replacement race remains small but
  real. Trusted local authors, not hostile concurrent filesystem swaps. No network
  filesystem/power-loss durability guarantee. Forced termination can leave ignored
  sibling `.puzzlepress-*.tmp` files; no recursive cleanup or automatic merge.

## Core contracts retained

Frozen values, explicit seeds/local RNG, bounded search, authoritative placements
and independent verification. Banks/profiles/puzzles stay schema-v1 inline content;
legacy content.items is not targets. Per-puzzle SHA-256 seed derivation uses book
seed, puzzle ID and pipeline version, independent of batch order. All HTTP seeds
are decimal strings. Identity includes engine and output-affecting normalized
inputs, excludes output paths/timestamps. Core source/API algorithms unchanged.
Quality is separate: no automatic retry/content repair; empty policy is disabled,
1,000-occurrence cap reports truncation. Existing ASCII, 20 definitions/banks/
profiles, 100 entries/targets, 1..50 dimensions and work caps apply.

## Actual local verification

Windows Python 3.13.15: **386 passed, 4 skipped, 1 warning** (390 collected).
API suite included: **69 passed, 3 skipped**; new write tests **37 passed, 1 skipped**.
Skips require symlink permission; portable simulated-boundary checks also pass.
Ruff lint and format (45 files), strict mypy (24 sources), pip check passed.
Eight installed CLI regressions passed, including parsed two-puzzle clean batch.
Installed Studio served real garden-demo/profile and legacy empty states with
zero axe violations/browser errors and no saves.

Frontend: clean npm ci; **21 Vitest tests**, strict TS/ESLint/Prettier, npm ls and
production build passed (JS 267.02 kB, gzip 81.63 kB). **5 Playwright tests passed**
using installed Chrome: temporary edit/validate/preview/save/reload, repeated
preview, competing save, simulated HTTP failure, structured field error, keyboard,
1440/1024/768/390 and zero axe violations in checked states. All browser sources
are temporary copies on port 8015, never a reused authoring server. Repository
fixtures' SHA-256 hashes unchanged. git diff --check passed. CI matrix unchanged;
remote CI not verified. Windows/Linux 3.11/3.13/3.14 remain configured.

npm audit exits 1: two moderate existing dev-tool entries (Vitest/@vitest/mocker,
GHSA-82fw-gwwq-j7x9); fixing requires a major tooling upgrade, deferred explicitly.
No dependency changes. Starlette's existing httpx deprecation warning remains.
Sandbox blocked esbuild's parent traversal; frontend checks passed outside it.

## Design, docs and next interval

Existing paper/green identity/logo preserved, forms and keyboard reorder controls,
field associations, live status and non-color solutions. Editor stacks below
1200px with preview jump; grids scroll internally. Ten new real captures plus
refreshed existing captures in docs/images/studio. Impeccable written guidance and
independent screenshot review: ship visually; documenter verified narrow draft
status clarification in DESIGN.md/sidecar. Engine/detector unavailable; no automated
Impeccable verdict claimed. Playwright used because agent-browser unavailable.

README, PRODUCT, docs/studio.md, docs/batch-quality.md and interval-5-report.md
updated. AGENTS and CI unchanged. Drafts/previews are memory-only, no autosave,
undo, merge, invalid-YAML repair UI, Firefox/WebKit or screen-reader certification.
No PDF/book composition/cover/KDP/cloud/account functionality. Next is Interval 6,
only on request. Review canonical YAML acceptance, single-process/external-editor
limitations and the existing Vitest tooling advisory before extending scope.
