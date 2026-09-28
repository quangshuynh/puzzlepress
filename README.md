# PuzzlePress

PuzzlePress is an early-stage Python publishing engine for themed puzzle books.
Interval 1 provides project loading, validation, serialization, and deterministic
build identities. Puzzle generation and print artifacts are future work.

## Install and run

Requires Python 3.11 or newer. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\puzzlepress.exe --version
.\.venv\Scripts\puzzlepress.exe validate books/automotive
.\.venv\Scripts\puzzlepress.exe inspect books/automotive/book.yaml
```

On macOS/Linux, use `.venv/bin/python` and `.venv/bin/puzzlepress` instead.
After activating the environment, the commands are simply:

```text
puzzlepress --version
puzzlepress validate books/automotive
puzzlepress inspect books/automotive
python -m puzzlepress inspect books/automotive
```

`validate` and `inspect` are read-only. Exit codes: **0** success, **1** expected
project/configuration error, **2** command-line usage error. Errors go to stderr;
successful output goes to stdout. There are no build or generation commands yet.

## Source convention and schema v1

The example at [`books/automotive/book.yaml`](books/automotive/book.yaml) contains
three authored items, not generated puzzles:

```yaml
schema_version: 1
book:
  id: automotive-word-search
  title: Automotive Word Search
  language: en-US
build:
  seed: 2026
content:
  items:
    - ENGINE
    - CLUTCH
    - PISTON
output:
  directory: ../../build/automotive-word-search
```

| Field | Contract |
| --- | --- |
| `schema_version` | Required integer `1`; unsupported versions fail before interpreting version-specific fields. |
| `book.id` | Required stable identifier: lowercase ASCII letters/digits separated by hyphens; Windows device names are rejected. |
| `book.title` | Required nonempty string. |
| `book.language` | Required language tag such as `en` or `en-US`; basic syntax check, not a language registry lookup. |
| `book.subtitle`, `description`, `author`, `imprint` | Optional nonempty strings or null, under `book`. |
| `build.seed` | Required unsigned 64-bit integer (`0` through `18446744073709551615`) or decimal digit string. |
| `content.items` | Ordered nonempty strings; omitted content/items defaults to an empty list. Duplicates and order are preserved. No puzzle-specific rules apply. |
| `output.directory` | Relative path from the resolved YAML file's directory; defaults to `../build/<book.id>`. |

Unknown fields are errors, including nested typos. Text is trimmed at its edges;
internal whitespace, case, and Unicode normalization form are preserved. Omitted
optional book fields normalize to null. Quote numeric-looking titles/items.

Seeds such as `42`, `"42"`, and `" 00042 "` normalize to the same integer.
Booleans, floats, negative values, signs in strings, hex strings, arbitrary text,
and out-of-range values are rejected. No random or clock-derived default exists.

Source is one UTF-8 YAML document (an optional BOM is accepted). Duplicate keys,
aliases, merge keys, and explicit tags are rejected. Date-like values and
`yes`/`no`/`on`/`off` stay strings; lowercase `true`/`false` are booleans. Decimal
integers have no implicit octal/hex conversion. Serialization emits normalized
YAML; comments and source formatting are not preserved.

### Filesystem boundaries

Pass either a source file or a directory containing exactly `book.yaml`. Loading
does not search parent directories, enumerate content, or depend on filesystem
ordering. Input paths may be absolute or relative to the caller's working directory.

Each book directory is authoritative source. Generated artifacts belong in a
separate tree, normally repository-root `build/<book.id>/` as in the example.
Output paths use forward slashes, including on Windows. Absolute paths, drive
paths, backslashes, and invalid path characters are rejected. Relative `..`
components are intentional: they allow output outside the book source tree.

Loading resolves symlinks and rejects output that is inside, equal to, or an
ancestor of the source directory. Existing output files are rejected. Nothing
creates or deletes output directories in this interval. Future writers must
recheck separation when writing, prevent collisions with other projects, and
never place authoritative data in build directories. `build/`, environments,
test caches, and packaging artifacts are ignored by Git.

## Core API and architecture

```python
from puzzlepress import (
    build_identity,
    canonical_build_inputs,
    dump_project,
    load_project,
    parse_project,
    validate_project,
)

loaded = load_project("books/automotive")
project = loaded.project
identity = build_identity(project)
canonical_bytes = canonical_build_inputs(project)
normalized_yaml = dump_project(project)
assert parse_project(normalized_yaml) == project

result = validate_project({"schema_version": 7})
assert not result.valid
assert result.issues[0].path == "schema_version"
```

| Module | Responsibility |
| --- | --- |
| `models.py` | Frozen, typed normalized values and independent dictionary serialization. |
| `validation.py` | Pure schema validation, normalization, structured results/errors, version dispatch seam. |
| `yaml_io.py` | Restricted safe YAML parsing and normalized YAML serialization. |
| `identity.py` | Canonical semantic inputs and SHA-256 identity. |
| `project.py` | Read-only file discovery/loading and output/source separation checks. |
| `cli.py` | Argument parsing, human-readable presentation, and exit codes. |

The CLI calls the same public APIs a future web adapter can call. Core APIs do not
print, prompt, modify random state, or write files. Use `parse_project`,
`validate_project(...).require_project()`, or `load_project` to obtain validated
models. Direct dataclass constructors are typed value objects, not validation
entry points. Pure parsing/validation does not perform filesystem checks;
`load_project` additionally checks resolved output separation.

`validate_project` returns a `ValidationResult` with multiple independent issues.
Each `ValidationIssue` has `path`, stable `code`, human-readable `message`, and
optional one-based `line`/`column` for YAML errors. `require_project`, parsing, and
loading raise `ProjectError` for expected failures. Unexpected programming errors
are not converted into misleading configuration errors.

## Deterministic identity contract

`canonical_build_inputs` returns UTF-8 JSON with sorted keys, compact separators,
and an envelope containing identity format version `1`, engine version `0.1.0`,
and the normalized schema/book/build/content values. SHA-256 produces an identity
formatted as `pp1-sha256-<64 hex characters>`.

- Book metadata, seed, content order, and content values affect identity.
- YAML comments, mapping order, formatting, equivalent seeds, and omitted versus
  explicit defaults do not affect identity.
- Source paths, output location, timestamps, environment variables, and process
  hash randomization are excluded.
- Engine version changes intentionally invalidate identities. Identity-format
  changes require a new identity version; schema changes require explicit dispatch.

Only inline source content is supported. Future external content/assets must be
included by content digest before they influence generation. The current identity
is a fingerprint of declared inputs, not a guarantee of reproducible PDF bytes
or a complete release-environment manifest.

## Development and verification

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
```

In a sandbox that cannot access the shared OS temporary directory, run tests with
`--basetemp=.pytest_cache/tmp` (pytest owns and clears that dedicated directory).
Symlink tests skip only when the OS does not permit creating symlinks. CI runs
tests, lint, formatting, types, and the example CLI on Windows/Linux with Python
3.11, 3.13, and 3.14. Configuring CI does not imply those remote jobs have run.

PyYAML is the only runtime dependency because the standard library has no YAML
parser. The CLI, models, hashing, and path handling use the standard library.
Development dependencies are pytest, Ruff, mypy, and PyYAML type stubs; setuptools
is the packaging backend. Dependency ranges are not a release lockfile.

## Later intervals

Puzzle algorithms, solutions, difficulty, print/PDF rendering, KDP preflight and
economics, photography/covers, research, marketing, release artifacts, series
management, and the web publishing studio are intentionally deferred. There are
no placeholder implementations for them. Before extending the engine, decide how
typed puzzle content and external-file digests evolve the schema and identity
contract; do not hide new output-affecting inputs from the fingerprint.
