<p align="center">
  <img src="docs/images/puzzlepress-logo.png" alt="PuzzlePress icon" width="256">
</p>

# PuzzlePress

[![CI](https://github.com/quangshuynh/puzzlepress/actions/workflows/ci.yml/badge.svg)](https://github.com/quangshuynh/puzzlepress/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Ruff](https://img.shields.io/badge/lint-Ruff-261230.svg)](https://docs.astral.sh/ruff/)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-blue.svg)](https://mypy-lang.org/)

PuzzlePress is a deterministic Python engine and local publishing studio for
themed puzzle books. Validate authored projects, generate verified word searches,
compose them into an ordered book, build a deterministic print interior PDF, preflight
it, and proof every real page in a local browser studio.

**Interval 8 complete:** `book preflight` reports two separate verdicts for a built
interior: structural validity (the files match their authoritative inputs) and
readiness against the Amazon KDP paperback rules PuzzlePress models. Studio's Print
tab previews the actual PDF. Preflight is not a guarantee of KDP acceptance; Amazon
decides. Covers and publishing remain future work.

## Quick start

Requires Python 3.11+. The Studio build also requires Node.js 22+.
From the repository root on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,studio,web-test]"
cd studio
npm.cmd ci
npm.cmd run build
cd ..
.\.venv\Scripts\puzzlepress-studio.exe
```

Open **http://127.0.0.1:8000/books** and choose **Garden Word Searches**.
After setup, start the Studio with the last command alone. One local Python
process serves the UI and API. On Linux/macOS use `.venv/bin/python`,
`.venv/bin/puzzlepress-studio` and `npm`.

For CLI-only use, install with `python -m pip install -e .` and activate the
virtual environment. Runtime dependencies are PyYAML, ReportLab (PDF output) and
pypdf (independent PDF inspection). The `studio` extra adds FastAPI, uvicorn and
pypdfium2 (page previews).

## CLI

```text
puzzlepress --version
puzzlepress validate books/automotive
puzzlepress inspect books/garden-demo
puzzlepress puzzle generate --width 10 --height 8 --seed 2026 --word ENGINE --word PISTON --solution
puzzlepress puzzle batch books/garden-demo --json
puzzlepress puzzle batch books/garden-demo --strict-quality
puzzlepress book plan books/composition-demo
puzzlepress book plan books/composition-demo --json
puzzlepress book build books/composition-demo
puzzlepress book build books/composition-demo --output /tmp/demo-interior --json
puzzlepress book preflight books/composition-demo
puzzlepress book preflight books/composition-demo --json --no-write
```

Commands are read-only except `book build`, which writes `interior.pdf` and an
`interior.json` manifest to the project's output directory (here
`build/composition-demo/`) or `--output`, and `book preflight`, which writes only
`preflight.json` beside them (unless `--no-write`). `book preflight` exits 0 only
when the interior is structurally valid and KDP ready. `composition-demo` has 11
pages: structurally valid, not KDP ready (the paperback minimum is 24 pages). Exit codes: **0** success, **1** expected configuration
or generation failure, **2** usage error. Batch quality findings are warnings
unless `--strict-quality` is used. `book plan` exits 1 when a puzzle fails to
generate, still printing the plan. `book build` exits 1 with structured
diagnostics (overflow, digest mismatch, invalid profile) and writes nothing. `python -m puzzlepress` is also supported.

## Web Studio

- Discover local projects and inspect metadata, validation and build identity.
- Edit puzzle titles, themes, IDs, ordered targets and reusable word-bank entries.
- Add, remove and reorder puzzles; select and configure shared difficulty profiles.
- Validate unsaved drafts, preview them, then save with stale-source protection.
- Generate and inspect real grids, exact seeds and independent verification.
- Toggle authoritative solutions with highlighted paths and a coordinate register.
- Review quality findings, screening completeness, reuse and similarity reports.
- Compose the book: front matter, puzzle order, solutions, back matter and page numbers.
- Preview the verified publication plan: every logical page, its side and its number.
- Build the interior, then proof real rendered pages: thumbnails, spreads, zoom,
  margin overlays, and preflight findings linked to the pages they concern.

[`composition-demo`](books/composition-demo/book.yaml) is a small composed book:
front matter, four puzzles, grouped solutions and a notes page.
[`garden-demo`](books/garden-demo/book.yaml) has two themed puzzles without a
composition. [`automotive`](books/automotive/book.yaml) is a small source fixture
without word-search definitions. None is presented as a finished publishing product.

Open a book and choose **Edit**. Make changes, **Validate draft**, then **Preview
draft** to inspect the grid and quality. **Save changes** validates again and
reloads the persisted source. Drafts survive project tabs; **Revert draft** discards
unsaved work deliberately. Saves canonicalize YAML, including removal of comments
and original formatting. See the [editing workflow](docs/studio.md#authoring-workflow).

Choose **Book** to compose. Reorder puzzles, edit matter and set solution and
numbering policy, then **Preview plan**. The plan is not a print preview: it states
what belongs in the book and in what order, not how pages are laid out. Composition
edits share the same draft, validation and save. See [book composition](docs/book-composition.md).

### A look inside

<p>
  <a href="docs/images/studio/draft-preview.png"><img src="docs/images/studio/draft-preview.png" alt="Visual editor beside an unsaved generated puzzle and authoritative solution" width="48%"></a>
  <a href="docs/images/studio/composer-plan.png"><img src="docs/images/studio/composer-plan.png" alt="Book composer beside an unsaved publication plan with sections, sides and page numbers" width="48%"></a>
</p>
<p>
  <a href="docs/images/studio/print.png"><img src="docs/images/studio/print.png" alt="Print proof: structural valid, KDP not ready, the rendered title page and preflight findings" width="48%"></a>
  <a href="docs/images/studio/print-spread.png"><img src="docs/images/studio/print-spread.png" alt="Facing-page spread of a puzzle and a solution page with live-area and KDP margin overlays" width="48%"></a>
</p>

Actual application captures from disposable demo projects. See the
[quality review](docs/images/studio/editor-quality.png),
[validation](docs/images/studio/editor-validation.png),
[puzzle ordering](docs/images/studio/composer-order.png),
[narrow composer](docs/images/studio/composer-390.png),
[preflight findings](docs/images/studio/print-findings.png) and
[narrow print proof](docs/images/studio/print-390.png).

## Development

Install the development extras shown above. With the Python environment activated:

```text
python -m pytest --basetemp=.pytest_cache/tmp
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pip check
git diff --check
```

From `studio/`:

```text
npm ci
npm run check
npm test
npm run build
npx playwright install chromium
npm run test:browser
```

`npm run check` runs strict TypeScript, ESLint and formatting checks. Browser tests
use real engine output and include accessibility, keyboard, responsive and solution
checks. For hot reload, run `npm run dev` alongside the Python server. Detailed
startup options, API contracts and test commands are in [Studio documentation](docs/studio.md).

CI covers Windows/Linux on Python 3.11, 3.13 and 3.14, plus a separate frontend and
Chromium job. Symlink tests skip when OS permission is unavailable.

## Architecture

```text
                 PuzzlePress Python core
                 /                     \
               CLI                Studio service
                                       |
                                FastAPI / uvicorn
                                       |
                                React / TypeScript
```

Project -> generation -> quality -> composition -> publication plan -> layout -> PDF
-> preflight.
The print engine consumes the plan and the generated puzzles, verifies their
digests, lays out pages without repaginating and rejects content that does not fit.

Immutable Python models own validation, deterministic generation, identity,
quality and publication planning. The web adapter exposes existing reports; the browser renders them.
There is no JavaScript generator, solver, planner or second project validator. Build
identities include engine version and output-affecting inputs. Seeds travel over
HTTP as decimal strings. Source and disposable build directories stay disjoint.

Contracts: [project format](docs/project-format.md), [word-search engine](docs/word-search.md),
[batch and quality](docs/batch-quality.md), [book composition](docs/book-composition.md),
[print interior](docs/print-interior.md), [preflight and preview](docs/preflight.md),
[Studio architecture](docs/studio.md).
Contribution rules: [AGENTS.md](AGENTS.md). Current handoff: [CONTEXT.md](CONTEXT.md).

## Current limitations

ASCII A-Z targets, at most 20 definitions per batch, and bounded greedy generation
that can fail on feasible inputs. Quality is descriptive, with explicit scan
limits and no built-in prohibited-word list or automatic repair. Profile names
are authored settings, not calibrated difficulty scores.

Studio edits only existing `book.yaml` projects within its configured books root.
It has no arbitrary filesystem browser, accounts, cloud services or telemetry.
Drafts are in memory, without autosave or merge; conflicts require review and reload.
Use one Studio process per library. YAML comments and formatting are not preserved.
Frontend assets are built from this checkout. Interiors use one profile (8.5 x 11
in, no bleed, black ink) and one bundled sans family; books under 24 pages build
with a KDP warning and fail KDP readiness. Preflight models a documented subset of
KDP rules; some official values are ambiguous (see [preflight](docs/preflight.md)).
Covers, KDP packaging and publishing automation are not implemented.

## License

[MIT](LICENSE).
