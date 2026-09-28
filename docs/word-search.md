# Word-search engine contract

The public API is `puzzlepress.wordsearch`. It performs no filesystem I/O and
does not print. Dataclass constructors are typed value objects; generation and
`normalize_targets` are validation boundaries. The verifier accepts typed models,
including corrupted values, rather than arbitrary deserialized objects.

## Inputs and normalization

- `TargetEntry(id, display)` supplies an explicit stable identity and display text.
  IDs use 1..64 ASCII letters, digits, underscores, or hyphens and must be unique.
- Accept 1..100 entries, each with 1..200 ASCII letters or literal spaces.
  Trim edge spaces for display; preserve casing and internal spaces.
- Search forms remove spaces and uppercase letters. Require 1..50 letters.
  Reject normalized duplicates, including `FUEL PUMP` and `FUELPUMP`.
- Tabs, newlines, punctuation, digits, accented letters, and other Unicode
  characters are errors. There is no implicit transliteration or punctuation removal.
- Seeds follow the project convention: unsigned 64-bit integers or decimal strings.
  Equivalent forms such as `42` and `" 00042 "` normalize identically.

`GenerationConfig` contains a `GridSize(width, height)`, a nonempty tuple of distinct
`Direction` values, `max_restarts`, and `max_attempts`. Dimensions are independently
bounded to 1..50. Directions are canonicalized in declaration order: right, left,
down, up, down-right, down-left, up-right, up-left. Caller direction order is ignored.

## Placement and limits

Generation v1 uses a local `random.Random(seed)`. Each pass shuffles target order,
then stably sorts by descending search length. For each target it shuffles all
start-cell/direction candidates and accepts the first compatible placement.
Candidate cells are enumerated row first, then column, then canonical direction.
Matching occupied letters may overlap; conflicting letters cannot be overwritten.

If a target has no compatible candidate, restart with an empty grid and the same
advancing generator. There is no backtracking. Completed placements are returned
in the original requested target order. Fill only empty cells, in row order, with
uniform choices from uppercase A-Z using that same local generator.

- `max_restarts`: default 20, allowed 0..100, excluding the initial pass.
- `max_attempts`: default 100,000, allowed 1..1,000,000, shared across all passes.
  Each tested candidate counts, including out-of-bounds candidates. Candidate
  lists contain at most 20,000 integers; dimensions, target count, and restarts
  also bound enumeration/shuffling work.
- Geometrically oversized targets fail before searching (`cannot_fit`).
- Budget or restart exhaustion raises `WordSearchError` with `search_exhausted`
  and `GenerationStats`. This does **not** prove mathematical impossibility.
- Errors carry the existing `ValidationIssue` shape: path, code, message.

Repeated normalized inputs give equal immutable results for generation v1 and
the supported runtime semantics. Tests pin a known result and compare processes
with different hash seeds. Changes to RNG behavior, enumeration, or normalization
require deliberate generation-version review; no cross-version promise is made
for arbitrary future Python random implementations.

## Solutions and verification

Coordinates are zero-based `(column, row)`, with `(0, 0)` at the upper left.
`Placement` stores target ID, search form, start, and direction. Its coordinates
and end are derived. `Solution` groups authoritative placements. `WordSearch`
retains the requested normalized targets, effective configuration, seed, grid,
solution, work statistics, and generation version.

`verify_word_search` returns immutable `VerificationResult` issues. It checks
the target manifest, grid dimensions/alphabet, identity coverage, unique
placements, enabled directions, bounds, spelling, and metadata agreement. It
computes coordinates independently of the generator and placement properties.
It checks internal consistency against the embedded manifest, not authenticity
against an external project, and does not replay the seed or discover solutions.

Accidental extra target occurrences, reversed equivalents, palindrome ambiguity,
and offensive filler are not suppressed. Authoritative placements remain clear
by ID even if the grid happens to contain other occurrences.

## Project boundary

The standalone CLI uses repeated `--word` values and assigns ordered IDs
`word-1`, `word-2`, etc. It always verifies before printing; `--solution` shows
placements. It writes no files. Book schema v1 remains general authored content:
it has no puzzle dimensions or direction fields, so generation does not load
book YAML. A later schema interval must include all puzzle settings in build
identity before generating book artifacts.
