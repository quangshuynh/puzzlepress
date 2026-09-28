# PuzzlePress

PuzzlePress is a deterministic Python publishing engine for themed puzzle books.
It provides project validation and a reusable word-search engine. A CLI exposes
the same core APIs intended for a future web publishing studio.

**Status: Interval 2 complete.** Word searches can be generated and independently
verified. Print/PDF output, book builds, and the web studio are planned.

## Install

Requires Python 3.11 or newer. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\Activate.ps1
```

On Linux/macOS, activate with `source .venv/bin/activate`.

## CLI

```text
puzzlepress --version
puzzlepress validate books/automotive
puzzlepress inspect books/automotive/book.yaml
puzzlepress puzzle generate --width 8 --height 6 --seed 2026 --word "FUEL PUMP" --word AXLE --solution
```

Generation prints the seed, text grid, target list, and verification status.
`--solution` adds authoritative placements using zero-based `(column, row)`
coordinates. Repeat `--direction` to enable a subset of `right`, `left`, `down`,
`up`, `down-right`, `down-left`, `up-right`, and `up-left`. All eight are enabled
by default. `--max-attempts` and `--max-restarts` bound the search.

Commands are read-only. Exit codes: **0** success, **1** expected configuration
or generation failure, **2** CLI usage error. Errors go to stderr.
`python -m puzzlepress` is also supported.

## Word-search API

```python
from puzzlepress.wordsearch import (
    GenerationConfig,
    GridSize,
    TargetEntry,
    generate_word_search,
    verify_word_search,
)

puzzle = generate_word_search(
    (TargetEntry("fuel-pump", "FUEL PUMP"), TargetEntry("axle", "AXLE")),
    GenerationConfig(GridSize(width=8, height=6)),
    seed=2026,
)
assert verify_word_search(puzzle).valid
print(puzzle.grid.rows)
print(puzzle.solution.placements)
```

The engine preserves display text separately from uppercase search forms.
Only ASCII letters and literal spaces are accepted; normalized duplicates are
rejected. Matching letters may overlap. Filler uses A-Z and cannot overwrite
targets. The same normalized inputs and seed produce the same result under the
same generation semantics, without using global random state.

Generation returns every target or raises a structured `WordSearchError`.
Bounded search can fail even when an arrangement exists. The independent verifier
checks the saved placements against the grid and target manifest.
See the [engine contract](docs/word-search.md) for limits and policies.

## Example project

[`books/automotive/book.yaml`](books/automotive/book.yaml) is a small three-item
source fixture. It is not a finished book. Schema v1 stores book metadata, an
explicit unsigned 64-bit seed, ordered authored content, and an output location.

Loading rejects malformed/ambiguous YAML, unknown fields, unsupported schemas,
and overlapping source/output directories. Generated directories are disposable.
The [project format](docs/project-format.md) documents these rules and the
versioned SHA-256 build identity, which includes the engine version and excludes
paths, timestamps, comments, and YAML key order.

Puzzle generation is currently separate from project YAML because schema v1 has
no puzzle settings. No book build or publish command exists.

## Development

With the development environment activated:

```text
python -m pytest --basetemp=.pytest_cache/tmp
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pip check
git diff --check
```

The dedicated pytest temporary directory supports restricted sandboxes.
Symlink tests skip when OS permissions prevent creating symlinks. CI is configured
for Windows/Linux on Python 3.11, 3.13, and 3.14.

PyYAML is the only runtime dependency. Development tools are pytest, Ruff, mypy,
and PyYAML type stubs.

## Architecture

- `models`, `validation`, `yaml_io`: immutable project values and schema handling.
- `project`, `identity`: read-only loading, filesystem boundaries, build fingerprints.
- `wordsearch`: puzzle values, normalization, bounded generation, independent verification.
- `cli`, `puzzle_cli`: argument parsing and terminal presentation.

Core generation has no terminal or filesystem side effects. See
[AGENTS.md](AGENTS.md) for contribution rules and [CONTEXT.md](CONTEXT.md) for the
current engineering handoff.

## Limitations and roadmap

Current puzzles use ASCII A-Z. Accidental extra word occurrences and offensive
filler are not suppressed. Quality checks, difficulty, real book content,
batch generation, print/PDF layout, publishing workflows, and the web studio
remain future work.

## License

[MIT](LICENSE).
