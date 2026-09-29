<p align="center">
  <img src="docs/images/puzzlepress-logo.png" alt="PuzzlePress icon" width="256">
</p>

# PuzzlePress

[![CI](https://github.com/quangshuynh/puzzlepress/actions/workflows/ci.yml/badge.svg)](https://github.com/quangshuynh/puzzlepress/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Ruff](https://img.shields.io/badge/lint-Ruff-261230.svg)](https://docs.astral.sh/ruff/)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-blue.svg)](https://mypy-lang.org/)

PuzzlePress is a deterministic Python publishing engine for themed puzzle books.
It provides project validation and a reusable word-search engine. A CLI exposes
the same core APIs intended for a future web publishing studio.

**Status: Interval 3 complete.** Projects can define themed puzzles, reusable
word banks, and explicit difficulty profiles. Batch generation produces verified
grids and structured quality reports. Print/PDF output and the web studio are planned.

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
puzzlepress puzzle batch books/garden-demo
puzzlepress puzzle batch books/garden-demo --json --strict-quality
```

Generation prints the seed, text grid, target list, and verification status.
`--solution` adds authoritative placements using zero-based `(column, row)`
coordinates. Repeat `--direction` to enable a subset of `right`, `left`, `down`,
`up`, `down-right`, `down-left`, `up-right`, and `up-left`. All eight are enabled
by default. `--max-attempts` and `--max-restarts` bound the search.

Commands are read-only. Exit codes: **0** success, **1** expected configuration
or generation failure, **2** CLI usage error. Batch quality findings are warnings;
`--strict-quality` makes them exit 1. JSON mode prints a complete report, including
per-puzzle generation failures, to stdout. Invalid project errors go to stderr.
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

[`books/garden-demo/book.yaml`](books/garden-demo/book.yaml) demonstrates the
optional schema-v1 `word_search` section with two themed puzzles. Its word banks,
profiles, puzzle definitions, and quality settings all participate in identity.
Older projects keep their existing identities.

```python
from puzzlepress import load_project
from puzzlepress.batch import generate_batch

report = generate_batch(load_project("books/garden-demo").project)
assert report.success
payload = report.to_dict()
```

Reports include accidental target occurrences, optional caller-supplied prohibited
word matches, cross-puzzle reuse, duplicate target sets, and similarity metrics.
Difficulty profiles are named settings, not measured difficulty scores. See
[batch and quality contracts](docs/batch-quality.md) for schema, API, and report details.

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
- `content`, `content_validation`: word banks, difficulty profiles, themed definitions.
- `batch`, `quality`: deterministic batches, occurrence screening, reuse and similarity reports.
- CLI modules: argument parsing and terminal/JSON presentation.

Core generation has no terminal or filesystem side effects. See
[AGENTS.md](AGENTS.md) for contribution rules and [CONTEXT.md](CONTEXT.md) for the
current engineering handoff.

## Limitations and roadmap

Current puzzles use ASCII A-Z. Batches are limited to 20 definitions. Quality
checks flag findings without changing grids; there is no built-in prohibited-word
list. Screening is literal and capped with an explicit incomplete-scan flag.
Difficulty calibration, automatic quality repair, real book content, print/PDF
layout, publishing workflows, and the web studio remain future work.

## License

[MIT](LICENSE).
