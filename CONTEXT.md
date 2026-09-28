# PuzzlePress current state

## Completed scope

Interval 3: project-defined word searches, reusable word banks, themed puzzle
definitions, explicit difficulty profiles, deterministic batches, and quality
reports. Intervals 1 and 2 remain covered by unchanged regression tests.

Python 3.11+, package/engine version `0.1.0`, schema version `1`, identity version
`1`, standalone generation version `1`, project word-search pipeline version `1`.
No new dependencies. PyYAML is the sole runtime dependency; pytest, Ruff, strict
mypy, and PyYAML stubs support development.

## Architecture and decisions

- Existing project models/validation/YAML/loading/identity and `wordsearch/`
  remain. Shared errors moved to `errors.py` to avoid model import cycles;
  existing public error imports still work.
- `content.py` defines immutable word banks, difficulty profiles, themed puzzle
  definitions, quality settings, and their collection. `content_validation.py`
  validates the optional schema-v1 `word_search` section and all references.
- Profiles explicitly specify dimensions and directions; names are authored
  labels, not calibrated difficulty scores. Each puzzle selects ordered IDs
  from one bank. Unknown fields and normalized duplicates within a bank fail.
- A project supports 1..20 banks/profiles/puzzles, 1..100 entries per bank and
  targets per puzzle. Existing ASCII normalization and generation bounds remain:
  dimensions 1..50, at most 50 letters per target, defaults 20 restarts/100,000
  attempts, hard caps 100 restarts/1,000,000 attempts per puzzle.
- `batch.generate_batch` revalidates source, derives each seed from SHA-256 of
  project seed plus puzzle ID and pipeline version, then generates sequentially.
  Reordering/inserting definitions preserves existing grids. Expected placement
  failures remain in the report and do not prevent later definitions running.
- `quality.py` scans all eight directions for accidental target paths and
  optional prohibited words. Authoritative paths are excluded only from target
  scans. Palindrome reverse traversals are deduplicated. Scans cap at 1,000 hits;
  incomplete scans explicitly warn. Disabled screening is reported separately.
- `batch.analyze_content` reports normalized word reuse, equal target sets,
  Jaccard similarity and containment overlap. Batch reports add same-position
  grid agreement. Thresholds are configurable; no hidden automatic repair.
- Reports are immutable, with independent JSON-compatible dictionaries. JSON
  seeds are decimal strings for lossless JavaScript use. Core seeds are integers.
- Full normalized `word_search` content/settings and pipeline version enter
  project build identity. Missing sections are omitted, retaining legacy hashes.
  Engine version still participates; output paths and timestamps remain excluded.
- Core APIs do not print/write or mutate global randomness. Source and generated
  trees remain disjoint. No commands write generated artifacts.

## CLI and examples

Existing `--version`, `validate`, `inspect`, and standalone `puzzle generate`
remain. New: `puzzlepress puzzle batch <project> [--json] [--strict-quality]`.
Exit 1 for validation or generation failure; quality findings warn unless strict
mode requests exit 1. Usage errors exit 2. JSON partial-failure reports go to
stdout; invalid-project errors go to stderr. `success` means all definitions
were generated; `clean` also requires no quality findings.

`books/automotive` remains the original fixture. `books/garden-demo` contains two
small themed puzzles and produces a clean batch with seed 2026. Detailed contracts
and API examples are in `docs/batch-quality.md`, `docs/project-format.md`, and
`docs/word-search.md`. README gives installation and usage.

## Final local verification

Windows Python 3.13.15: **317 passed, 1 skipped** (318 collected). The skipped
symlink test requires unavailable OS permission. Ruff lint/format, strict mypy
(20 source files), `pip check`, installed CLI, and `git diff --check` passed.
Documentation Python examples executed successfully. Same-seed batch JSON is
identical across runs and process hash seeds; different project seeds change grids.
Tests include schema failures, identity coverage, partial failures, exact retry
bounds, policy/accidental scans, palindrome deduplication, truncation, threshold
boundaries, reuse across banks, and five 25-target 20x20 puzzles.

CI includes the new fixture/batch commands on Windows/Linux Python 3.11/3.13/3.14;
remote jobs were not run here. Nothing committed, pushed, published, or deployed.

## Limits and next interval

ASCII A-Z word content; inline banks only; 20-puzzle batch cap. Greedy search can
fail on feasible inputs. Similarity metrics flag review candidates, without
rotation/translation comparison or an originality guarantee. Screening is literal
matching against an explicit list, without contextual moderation or a built-in
policy. There is no automatic suppression or repair.

PDFs, covers, KDP layout, web UI, measured difficulty, external content files,
and production book publishing remain deferred. Interval 4 has not started;
its scope has not been supplied. Review schema and pipeline-version compatibility
before changing generation, seed derivation, or quality semantics.
