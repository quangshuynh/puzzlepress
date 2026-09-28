# Working on PuzzlePress

PuzzlePress is a deterministic Python engine for themed puzzle books. The CLI
and a future web studio share the same core. Read `CONTEXT.md` for current scope.

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
- Preserve per-puzzle seed derivation across batch reordering. Serialize 64-bit
  report seeds as decimal strings so web clients retain exact values.
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
python -m pip install -e ".[dev]"
python -m pytest --basetemp=.pytest_cache/tmp
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pip check
puzzlepress validate books/automotive
puzzlepress puzzle generate --width 10 --height 8 --seed 2026 --word ENGINE --word PISTON --solution
git diff --check
git status --short
```

Without activation on Windows, use `.\.venv\Scripts\python.exe` and
`.\.venv\Scripts\puzzlepress.exe`. On Linux/macOS, use `.venv/bin/`.
