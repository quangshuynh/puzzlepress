# PuzzlePress current state

## Completed scope

Interval 2: deterministic standalone word-search generation and independent
verification. Interval 1 project behavior is preserved. No Interval 3 work started.

Python 3.11+, package/engine version `0.1.0`, schema version `1`, identity version
`1`, standalone word-search generation version `1`. No dependencies added:
PyYAML remains the only runtime dependency. pytest, Ruff, strict mypy, and
PyYAML stubs provide development checks.

## Architecture and contracts

- `src/puzzlepress/`: immutable project models, structured validation, restricted
  YAML, read-only loading, canonical SHA-256 identity, thin CLI adapters.
- `wordsearch/`: immutable targets/config/grid/placements/solution/results,
  normalization, bounded greedy generation, and an independent verifier.
  Public APIs: `generate_word_search`, `verify_word_search`, `normalize_targets`.
- Targets have explicit unique IDs. Display retains case and internal spaces;
  search uses uppercase ASCII letters with literal spaces removed. Other
  characters and normalized duplicates are rejected.
- Logical grids are rectangular, 1..50 per axis; 1..100 targets, 1..50 letters
  each. All eight directions work; subsets are canonicalized in enum order.
- Local `Random(seed)` drives longest-first tie ordering, candidate ordering,
  and A-Z filler. Defaults: 20 restarts and 100,000 total candidate checks.
  Hard caps: 100 restarts, 1,000,000 checks. No silent partial puzzles or resizing.
- Solutions retain authoritative placements; coordinates/end are derived.
  Verification computes geometry independently and checks the embedded requested
  manifest. Search exhaustion is a structured failure, not proof of impossibility.
- Core generation has no I/O or global random-state mutation. Source and
  generated directories remain disjoint; generated directories are disposable.
- Book identity includes engine version, so it describes build inputs rather
  than source alone. Paths/timestamps/formatting are excluded. Schema and engine
  version are unchanged; the Interval 1 identity regression still passes.
  Standalone puzzle inputs are not included in that project fingerprint.

## CLI and examples

`puzzlepress --version`, `validate <project>`, `inspect <project>` and
`puzzle generate --width N --height N --seed N --word TEXT [--word TEXT ...]`.
Optional repeated `--direction`, `--max-attempts`, `--max-restarts`, `--solution`.
Generation always verifies before printing. Exit codes: 0 success, 1 expected
input/search failure, 2 usage error. No commands write artifacts.

Book YAML and the small automotive fixture are unchanged. Puzzle CLI inputs are
isolated because schema v1 has no puzzle configuration. Details live in
`docs/project-format.md` and `docs/word-search.md`.

## Verified locally

Windows, Python 3.13.15: **208 passed, 1 skipped** (209 collected; the skip requires
symlink permission). Ruff lint passed; format check passed (22 files); strict mypy
passed (14 source files); `pip check` passed; `git diff --check` passed.
Installed CLI validation/inspection/generation passed. Same-seed outputs match;
2026 and 2027 yield different valid puzzles. Impossible inputs exit 1 cleanly.

Tests include all directions, exhaustive small-grid bounds, matching/conflicting
overlaps, bounded failure, successful restart, corruption, fixed generation-v1
output, process hash-seed independence, and 25-target 20x20 puzzles across ten
seeds. Hypothesis was not needed for the exhaustive coordinate domain and these
seeded invariants. CI is configured for Windows/Linux, Python 3.11/3.13/3.14;
remote CI was not run here. Nothing committed, pushed, or published.

## Limits and next interval

ASCII only; greedy search can exhaust on feasible puzzles. No accidental-word
suppression, offensive filler filtering, difficulty scoring, batch books, real
automotive content, PDFs/layout, publishing automation, or web application.
Verifier checks internal consistency, not seed replay or external authenticity.

Next is Interval 3; its scope has not been supplied. Before book generation,
define puzzle schema inputs and their identity coverage. Review normalization,
search limits, and generation-version expectations before extending semantics.
