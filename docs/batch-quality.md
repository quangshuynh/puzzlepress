# Project batches and quality

Interval 3 adds an optional `word_search` section to schema v1. Legacy
`content.items` remains uninterpreted authored content. It is not implicitly
selected as puzzle targets. Use [garden-demo](../books/garden-demo/book.yaml)
for a complete two-puzzle project.

## Schema

```yaml
word_search:
  banks:
    - id: parts
      entries:
        - {id: pump, display: FUEL PUMP}
        - {id: axle, display: AXLE}
  profiles:
    - id: gentle
      width: 10
      height: 8
      directions: [right, down]
      max_restarts: 20
      max_attempts: 100000
  puzzles:
    - id: garage
      title: In the Garage
      theme: Vehicle parts
      bank: parts
      target_ids: [pump, axle]
      difficulty: gentle
  quality:
    max_word_reuse: 2
    target_similarity_threshold: 0.8
    grid_similarity_threshold: 0.9
    prohibited_words: []
```

`banks`, `profiles`, and `puzzles` are required lists with 1..20 entries each.
Their IDs are unique within each list. IDs use 1..64 ASCII letters, digits,
underscores, or hyphens. References are case-sensitive; text edges are trimmed.
Puzzle `title` and `theme` are required nonempty Unicode text up to 200 characters.

A bank contains 1..100 `{id, display}` entries. Each puzzle explicitly selects
1..100 unique `target_ids` from one bank, in generation order. IDs and normalized
search forms must be unique within a bank. Different banks may reuse a search
form; cross-puzzle analysis compares the normalized form, not the ID.
Word normalization follows the [engine contract](word-search.md).

Profiles require `id`, `width`, `height`, and `directions`. They are explicit
named configurations, with no hidden easy/medium/hard presets. Names do not imply
an empirically calibrated difficulty. Dimensions and generation limits follow
the engine contract. Only `max_restarts` (20) and `max_attempts` (100,000) default.
Directions are distinct names from the eight supported values and are normalized
to enum order. Selected words must physically fit an enabled direction.

All quality fields are optional and default as shown. `max_word_reuse` is an
integer 1..20. Similarity thresholds are finite numbers in `(0, 1]`.
`prohibited_words` accepts 0..100 display strings, normalizes them to search forms,
rejects duplicates, and sorts them. Empty means screening is disabled. There is
no embedded policy list, network lookup, regex policy, or arbitrary code in YAML.
Unknown fields, invalid references, duplicate IDs, and malformed values produce
structured validation issues before any generation.

## Core APIs

```python
from puzzlepress import load_project
from puzzlepress.batch import analyze_content, generate_batch
from puzzlepress.quality import analyze_word_search, screen_words

project = load_project("books/garden-demo").project
assert project.word_search is not None
authored_quality = analyze_content(project.word_search)
report = generate_batch(project)
assert report.success
first = report.puzzles[0].puzzle
assert first is not None
quality = analyze_word_search(first, prohibited_words=("EXAMPLE",))
matches = screen_words(first.grid, ("EXAMPLE",))
payload = report.to_dict()
```

`content.py` defines immutable `WordBank`, `DifficultyProfile`, `PuzzleDefinition`,
`QualityConfig`, and `WordSearchContent` values. Project validation and batch
entry points normalize and validate these models. Content resolver methods and
similarity helpers expect validated typed inputs. No core API prints or writes.
`screen_words` is a reusable hook for application-supplied policy lists; ad hoc
screening outside the project does not change that project's identity.

## Determinism and failures

Each puzzle seed is the first eight bytes (big-endian) of SHA-256 over compact
ASCII JSON `["puzzlepress-word-search", 1, normalized_project_seed, puzzle_id]`.
It is independent of batch position, themes, and other puzzles. IDs are therefore
stable generation identities. Changing target selection or a profile still changes
the puzzle inputs. Batch order remains meaningful to reports and project identity.

Generation is sequential and bounded by 20 definitions and each profile's search
limits (at most 20 million candidate checks in a batch). Every generated puzzle
is independently verified. Expected placement exhaustion produces a per-puzzle
error with attempt/restart counts, while later definitions continue. Invalid
projects fail before starting; unexpected implementation failures remain visible.

Quality findings never change grids or trigger retries. `BatchReport.success`
means every definition generated successfully. `clean` additionally requires no
quality findings. A clean report only describes the configured checks and word list.
All normalized project settings, including screening and reporting thresholds,
are covered by [build identity](project-format.md#build-identity).

## Quality measures

Occurrence scans examine contiguous straight paths in all eight directions,
including directions disabled for placement. The authoritative path for each
target is excluded from accidental-target findings. Other occurrences count,
including a target embedded inside a longer word. A palindrome's two traversals
of the same cells count once; single letters count once per cell. Prohibited
screening includes every match, even an intentionally placed target.

The scanner follows word prefixes, stopping when a prefix cannot match. Grid
dimensions, word lengths/counts, and a 1,000-occurrence cap per scan bound work
and report size. A cap reached with more matches sets `truncated` and yields a
`scan_truncated` warning. Authoritative exclusions happen before applying this
cap. Results contain exact zero-based coordinates; no suppression or repair occurs.

Cross-puzzle analysis includes every definition, even when generation fails:

| Measure | Definition and flag behavior |
| --- | --- |
| Word reuse | Normalized words occurring in multiple puzzle definitions, with puzzle IDs. Warn when usage exceeds `max_word_reuse`. |
| Exact duplicates | Equal normalized target sets, ignoring selection order and IDs. Always warn. |
| Target Jaccard | Shared word count divided by union word count. Warn at or above `target_similarity_threshold`. |
| Target overlap | Shared word count divided by the smaller target count. Report containment; no separate automatic flag. |
| Grid agreement | Fraction of equal letters at the same coordinates. Warn at or above `grid_similarity_threshold`. Unavailable for failed puzzles or different dimensions. |

Grid comparison does not account for rotations, translations, or difficulty.
These metrics flag candidates for review; they are not an originality guarantee.
Screening is literal ASCII matching, not linguistic or contextual moderation.

## CLI and report contract

```text
puzzlepress validate books/garden-demo
puzzlepress inspect books/garden-demo
puzzlepress puzzle batch books/garden-demo
puzzlepress puzzle batch books/garden-demo --json --strict-quality
```

Text mode shows grids, seeds, targets, findings, and a generation summary.
JSON mode includes source identity, pipeline version, effective quality settings,
per-puzzle configurations/grids/solutions/work counts, errors, occurrence
coordinates, reuse, and all pairwise metrics. Per-puzzle seeds are decimal strings
to preserve unsigned 64-bit values in JavaScript clients. The core retains integers.
`prohibited_screening_enabled` distinguishes an empty policy from no matches.

Exit codes: 0 when all puzzles generate, 1 for invalid input or any generation
failure, 2 for CLI usage errors. Warnings keep exit 0 unless `--strict-quality`
is requested. JSON reports, including partial failures, go to stdout. Source
validation errors go to stderr without a report. No output files are written.

PDFs, covers, KDP layout, web UI, difficulty calibration, automatic repair,
external word-bank files, and large book production remain deferred.
