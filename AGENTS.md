# Working on PuzzlePress

PuzzlePress is a deterministic Python engine for themed puzzle books. The CLI
and local Web Studio share the same core. Read `CONTEXT.md` for current scope.

## Rules

- Audit existing code, tests, CI, and `git status` before changing behavior.
- Keep core APIs independent of terminal/web state. No printing or hidden writes.
- Use small modules, frozen value models, strict types, and structured expected
  errors. Let unexpected programming failures remain visible.
- Use explicit seeds and local random generators. Keep input and direction
  ordering deterministic. Bound generation work; never silently omit targets,
  resize grids, alter words, or enable extra directions.
- Keep worst-case batch work within the whole-batch attempt budget; raise a
  content cap only after measuring generation through package at the new size.
- Solutions come from authoritative placements. Verify them independently.
- Keep quality findings separate from generation failures. Report incomplete
  screening explicitly. Never silently regenerate or change authored policy.
- Preflight observes: it never mutates the plan, layout, PDF, manifest or source
  to make a check pass. Reuse inspected facts only for byte-identical bytes. Keep structural validity separate from KDP readiness;
  unevaluated rules never count as passing. KDP values need official provenance.
- Preserve per-puzzle seed derivation across batch reordering. Serialize 64-bit
  report seeds as decimal strings so web clients retain exact values.
- Publication plans stay renderer-independent. Layout consumes a verified plan
  and must reject, never silently regroup, repaginate or reorder, its pages.
- Physical values live in print specifications, in points, with KDP limits in
  one place. Rebind puzzle digests before drawing; reopen and inspect every PDF.
  Use bundled, digest-pinned fonts only. Keep PDF bytes deterministic.
- Cover geometry derives only from a current, verified interior build (page count
  read from the PDF, profile paper); never accept an authored page count or spine
  width. Paper is a print-profile fact, never inferred.
- Cover photographs are authored source: import copies original bytes, never
  overwrites, and crops are configuration. Studio previews and the final PDF use
  the same Python crop, layout and renderer; the browser never lays out a cover.
  Rendered covers carry only pixels, never source EXIF/GPS/XMP metadata.
- Cover text layers change only the cover: hiding or restyling text never edits
  book metadata, and displayed text must still match the book details. Offsets
  are authored points that Python lays out; the browser never draws cover type.
  Imported fonts are validated in Python from memory (static TrueType outlines,
  embedding and subsetting permitted), digest-pinned, never system fonts; their
  license is what the author records, never inferred.
- Publishing metadata is authored source with its own identity, outside build
  identity. Never declare AI use, rights or other attestations for the author or
  invent an ISBN; undecided values block. A confirmation stores the Python-computed
  review identity of what it covers and applies only while that matches; a legacy
  boolean never counts. Readiness reruns interior and cover
  preflight and never trusts saved reports. Packages use the inspected bytes only,
  are verified before replacement, and nothing contacts or submits to Amazon.
- Cover design elements and interior styles are laid out and rendered by Python
  only; translucency is flattened by Python or reported, never emitted as PDF
  transparency. Conversion between cover versions is explicit, never implicit.
- Assets are removed only by moving an unreferenced file to the project trash;
  purging is a second explicit step. Never delete a referenced asset.
- Editorial reviews (`reviews.yaml`) and proof records (`proofs.yaml`) are authored
  source outside every production identity. Never infer, default or date them;
  they bind to the identities they cover and go stale when those change.
- Rebuilds run only the assessed steps through the single writers, stop before
  writing if the saved source changed, and never export the publishing package.
- Book plans are authored source in `planning.yaml`, outside every production
  identity; no build reads them and planning never writes `book.yaml`. Keep
  research evidence kinds distinct; never fabricate sources, comparables, prices
  or approvals, or treat an author note as verified. A plan describes targets
  beyond current caps and reports them unsupported; it never raises a cap or
  generates content. Approval stores the reviewed planning identity.
- Real books live in the separate book repository; the engine, its tests and CI
  never read or require them. Engine fixtures are small and synthetic.
- Keep authored source and disposable generated directories disjoint. Recheck
  filesystem boundaries before any future write or recursive cleanup.
- Preserve versioned schema and identity contracts. Include output-affecting
  inputs in any future build fingerprint. Engine version is part of identity.
- Test changed behavior, failure bounds, corruption, and determinism. Preserve
  regressions. Run pytest, Ruff lint/format, strict mypy, and `pip check`.
- Avoid new dependencies unless they materially improve the implementation.
- Preserve unrelated work. Do not commit, push, merge, publish, release, or deploy
  without explicit authorization.
- Finish the requested interval only. No speculative frameworks or placeholder
  features for later intervals.
- Keep public documentation concise and factual. Update `CONTEXT.md` after
  material changes with actual checks and limitations. Keep history out of here.

## Commands

After activating `.venv` (Python 3.11+):

```text
python -m pip install -e ".[dev,studio,web-test]"
python -m pytest --basetemp=.pytest_cache/tmp
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pip check
puzzlepress validate tests/fixtures/legacy-automotive
puzzlepress book build books/composition-demo --output .pytest_cache/interior
puzzlepress book build books/cover-demo --output .pytest_cache/cover
puzzlepress cover build books/cover-demo --output .pytest_cache/cover
puzzlepress cover preflight books/cover-demo --output .pytest_cache/cover --no-write
puzzlepress publish validate books/publishing-demo
puzzlepress publish inspect books/publishing-demo --output .pytest_cache/publishing
python tests/production_book.py .pytest_cache/synthetic/books/production
puzzlepress plan validate .pytest_cache/synthetic/books/production
puzzlepress plan production .pytest_cache/synthetic/books/production
puzzlepress puzzle generate --width 10 --height 8 --seed 2026 --word ENGINE --word PISTON --solution
git diff --check
git status --short
```

Studio checks (from `studio/`): `npm ci`, `npm run check`, `npm test`,
`npm run build`, and `npm run test:browser` with Playwright Chromium installed.
Keep Python authoritative; frontend transport types must not become a second
project validator, generator, solver, or quality implementation.

Without activation on Windows, use `.\.venv\Scripts\python.exe` and
`.\.venv\Scripts\puzzlepress.exe`. On Linux/macOS, use `.venv/bin/`.
