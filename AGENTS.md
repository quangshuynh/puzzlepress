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
- Solutions come from authoritative placements. Verify them independently.
- Keep quality findings separate from generation failures. Report incomplete
  screening explicitly. Never silently regenerate or change authored policy.
- Preflight observes: it never mutates the plan, layout, PDF, manifest or source
  to make a check pass. Keep structural validity separate from KDP readiness;
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
puzzlepress validate books/automotive
puzzlepress book build books/composition-demo --output .pytest_cache/interior
puzzlepress book build books/cover-demo --output .pytest_cache/cover
puzzlepress cover build books/cover-demo --output .pytest_cache/cover
puzzlepress cover preflight books/cover-demo --output .pytest_cache/cover --no-write
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
