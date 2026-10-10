# Research and book planning

Planning is the deliberate stage before production. A plan records what the
author intends to make and why: concept, audience and positioning, structure,
themes, candidate vocabulary, planned puzzles, difficulty, constraints, open
questions, research notes and comparable books. PuzzlePress checks it against
itself, the generator's rules, the current production caps and the print
constants, reports how ready it is, and records the author's approval of an
exact plan. It never generates puzzles from a plan, edits `book.yaml`, looks
anything up online, or judges a market.

Example: [`books/automotive/planning.yaml`](../books/automotive/planning.yaml), a
demonstration plan for the upcoming automotive book (see [Demo](#automotive-demo)).

## Storage

A plan is a separate, versioned document, `planning.yaml`, beside `book.yaml` in
the project folder. Chosen over a `planning` section of `book.yaml` because:

- Planning edits never touch `book.yaml` bytes, its revision, a book draft in
  Studio, or any identity derived from it. Build, interior, cover, publishing,
  review and package identities cannot change, by construction.
- Research notes, which may quote sources and record hypotheses, stay out of the
  production source file.
- A plan can exist, and stay incomplete, for a project whose production content
  has not been written yet; legacy projects need no change.
- A standalone versioned document can later be referenced by series planning
  without reshaping `book.yaml` (not implemented).

Tradeoffs: two files per project; a plan needs a valid `book.yaml` (its book ID);
Studio keeps a separate draft and revision for the plan. Title, subtitle and
author are not duplicated: the working title is `book.title`. The book is
identified by `book.id`.

`planning.yaml` follows the project source rules: one UTF-8 YAML document, no
aliases, tags or duplicate keys, unknown fields rejected, text trimmed at its
edges and otherwise kept exactly. Saving writes normalized YAML in document order;
comments and formatting are not preserved. Symlinks and directories named
`planning.yaml` are refused. `planning.store.write_planning` is the only writer:
it checks the byte revision the author opened (`null` means the file must still
not exist), stages beside the target, fsyncs, parses back and compares, rechecks
the revision and replaces atomically.

## Schema (planning version 1)

```yaml
planning_version: 1
concept: {summary, subject, reader_experience, scope}          # text or null
positioning:
  primary_audience: null          # chosen by the author
  secondary_audience: null
  candidate_audiences: []         # considered, not validated
  familiarity: undecided          # newcomer | casual | enthusiast | professional | mixed
  tone, use_case, main_benefit, differentiation: null
  evidence: []                    # research note IDs this positioning relies on
  claims: [{text, evidence: [note IDs]}]
structure:
  puzzle_type: null               # word_search is the only supported type
  target_puzzles: null
  print_profile: null             # paperback-8.5x11 | paperback-8.5x11-cream
  solutions: undecided            # end | omit
  solutions_per_page: null        # 1 | 2 | 4 | 6
  front_matter_pages: null
  back_matter_pages: null
difficulty:
  strategy: undecided             # consistent | gradual | sections | mixed
  levels:                         # easiest to hardest, by the author's judgment
    - {id, label, width, height, directions, words: {min, max}, notes}
    - {id, label, profile: an-existing-word_search-profile, words: {min, max}}
themes: [{id, label, parent, required, puzzles, notes}]
vocabulary:                       # one pool per theme
  - theme: engines
    source: unknown               # human | public_reference | licensed | ai_assisted | ai_generated
    reference: null
    entries: [{word, source, reference, note}]   # entry source null: the pool's
puzzles:                          # planned puzzles in book order
  - {id, theme, level, title, words: [entries of the theme's pool], notes}
constraints: {min_letters, max_letters, max_word_reuse, prohibited_words, notes}
questions: [{id, question, blocking, resolution}]
research: [{id, question, observation, evidence, confidence, source: {citation, url, type},
            observed, relevance, notes, decision}]
comparables: [{id, title, contributor, url, citation, format, trim, pages, puzzles,
               price: {amount: "12.99", currency: USD}, audience, strengths, weaknesses,
               positioning, observed, evidence}]
approval: null                    # the planning identity the author approved
```

Every field except `planning_version` is optional; omitted values mean undecided
or unknown and are reported, never filled in. Schema bounds are generous (up to
2,000 planned puzzles, 1,000 words a pool, grids up to 999) so a plan can
describe what production cannot do yet. The schema only decides whether values
are interpretable: types, enumerations, identifiers (1..64 ASCII letters, digits,
`_`, `-`), unique IDs per list, one pool per theme, dates as `YYYY-MM-DD`, prices
as quoted decimal text with an ISO currency code, and approvals as planning
identities. Anything a plan can get wrong while still being a plan is a finding,
so drafts save. Prohibited words follow the word-search quality normalization.

## Research and evidence

Each research note says what kind of statement it is (`evidence`):

| Value | Meaning |
| --- | --- |
| `verified_source` | The author states they checked the cited source. |
| `unverified_source` | A cited source the author has not checked. |
| `author_observation` | Something the author noticed; not a study. |
| `hypothesis` | An idea still to be tested. |
| `preference` | The author's choice, not a finding. |
| `unknown` | Not classified. |

PuzzlePress never fetches a URL, verifies a source, infers permission from a URL,
or treats a note as market research. Sourced kinds must cite a citation or URL.
A decision or positioning that rests on a hypothesis or unknown note is flagged;
a preference is a legitimate basis for the author's own decisions but never
evidence for a claim. Claims about the book need a `verified_source`. Observation
dates are authored data; no runtime clock is ever read.

Comparable books are manual records of books the author has looked at, with where
they were seen. Unknown pages, puzzles and prices stay null, never zero. There are
no ratings, sales estimates, rankings or revenue fields. An unsourced comparable
blocks research; a price without an observation date is flagged. Nothing is
scraped, copied or looked up.

## Audience and positioning

Candidate audiences are possibilities; only `primary_audience` is a choice, and
only the author makes it. Familiarity, tone, use, main benefit and
differentiation are the author's statements. Promotional or superlative wording
in the concept, benefit, differentiation or claims is flagged (the publishing
promotional detector plus a short superlative list); this is a heuristic.

## Themes and allocation

Themes form a hierarchy through `parent`. Each theme's `puzzles` is its own
allocation; a parent may hold none of its own. Allocations of leaf themes must be
stated and all allocations must add up to `target_puzzles`. Required themes must
receive puzzles (in their subtree). Planned puzzles must not exceed their theme's
allocation; unspecified puzzles are reported, never invented.

Theme labels that are equal after case, spacing and `&`/`and` folding are an
objective duplicate (error). Labels sharing half or more of their meaningful words
are an editorial note, skipped for a theme and its ancestors, since related
themes may share terminology. Pools sharing 30% or more of their words (Jaccard)
are noted as possibly overlapping. A theme with more than twice an even share of
the allocated puzzles is flagged as dominant, less than half as thin. These
thresholds are conventions for review, not measurements of quality.

## Vocabulary

Every candidate word passes through the generator's own normalization (ASCII
letters and spaces, 1..50 letters once spaces are removed) exactly as a word-bank
entry would. Invalid words, and words in one pool that normalize to the same
search form (`FUEL PUMP`, `fuelpump`), are errors that stay in the plan as
authored; nothing is transliterated or replaced. A word appearing in several
pools is a note, not an error. Exact matches of the plan's prohibited list (and
the project's `word_search.quality.prohibited_words`, if any) block; containing a
prohibited form is a warning, since it may be an innocent overlap. Authored
`min_letters`/`max_letters` give editorial warnings; whether a word fits a grid is
decided by the generator's fit rule (feasibility).

Pools must hold at least as many usable words as one puzzle needs. Reuse and
similarity across planned puzzles use the batch quality measures and defaults:
reuse limit `max_word_reuse` (default 2), identical word sets, and target Jaccard
at or above 0.8. A pool that cannot fill its allocation even reusing each word up
to the limit is flagged (`needed` in the report).

### Provenance

`source` records origin only: `human`, `public_reference`, `licensed`,
`ai_assisted`, `ai_generated` or `unknown` (the default; never assumed human).
Words assigned to planned puzzles must have a known source before approval.
Licensed words should record a licence reference. AI-generated vocabulary is
counted, and the report reminds the author that the book text's AI involvement is
declared in Publishing ([AI disclosure](publishing.md#ai-disclosure)); planning
never sets that declaration. A generic term is not proprietary because a
commercial source uses it.

## Difficulty

Levels use the generator's settings: grid width and height, enabled directions,
and the expected word count, or an existing `word_search` profile of the project.
There is no second difficulty engine and no difficulty score. Level order is the
author's declaration from easiest to hardest. Strategy checks follow book order:
`consistent` uses one level, `gradual` never steps back (skipping a level is
flagged), `sections` keeps each level contiguous (out-of-order sections are
flagged), `mixed` is free. A later level whose grid is no larger, with no new
direction and no more words, is flagged with the caveat that these are only some
influences on difficulty.

## Feasibility

Each feasibility item states how it is known: `verified` (decided by the engine's
own rules or a current cap), `estimate` (computed from the plan, not a built
book), `unknown` (only production can tell), or `unsupported`.

- Puzzle type, puzzle count against the project cap, word banks (one per pool),
  difficulty profiles (one per level), generator limits per level, and whether
  every assigned word fits its level's grid (`validate_fit`) are verified.
- Print fit reuses the interior's `fit_grid`, `page_frame` and `solution_slots`
  with a region larger than any real one (the whole live area, no title or word
  list). A grid that cannot keep the profile's minimum letter size there cannot
  print at all (unsupported); one that can is only an estimate.
- Pages are estimated as one per puzzle, grouped solution pages, planned matter
  and at most two recto blanks, against KDP's 24-page minimum, the modeled
  maximum and the 80-page spine-text threshold, all read from `interior.spec`.
  The publication plan is authoritative; nothing here duplicates preflight.
- Generation success and cover geometry are always unknown before production.

## Readiness

`PlanningReadinessReport` evaluates gates in order. The state is the first gate
with an error finding; every gate is reported separately.

| Gate | Blocked state | Question |
| --- | --- | --- |
| definition | `draft` | Concept, subject, audience, differentiation, type, target, strategy, themes, levels. |
| research | `needs_research` | Blocking questions resolved; evidence attributable. |
| content | `needs_content` | Allocation, planned puzzles, words and progression complete. |
| structure | `needs_content` | References, labels and vocabulary valid. |
| feasibility | `structurally_valid` | Producible with the current PuzzlePress. |
| decisions | `production_feasible` | Print profile, solutions and word provenance decided. |
| (none) | `ready_for_approval` | |
| + approval | `approved` | The recorded approval equals the current identity. |

Warnings and notes never block. Editorial findings are prompts for judgment.

### Rules

Severity in brackets: E error (blocks its gate), W warning, N note.

- Definition: `concept_missing`, `subject_missing`, `audience_missing`,
  `differentiation_missing`, `puzzle_type_missing`, `target_missing`,
  `strategy_undecided`, `themes_missing`, `levels_missing` (E).
- Research: `question_blocking_open`, `evidence_source_missing`,
  `comparable_unsourced`, `claim_unsupported` (E); `evidence_undated`,
  `comparable_price_undated`, `source_url_format`, `claim_weak_evidence`,
  `assumption_unresolved` (W); `question_open` (N).
- Content: `allocation_missing`, `allocation_total_mismatch`,
  `required_theme_empty`, `puzzles_unspecified`, `puzzles_exceed_target`,
  `theme_overspecified`, `puzzle_level_missing`, `puzzle_words_missing`,
  `puzzle_word_count`, `pool_missing`, `pool_insufficient`,
  `level_settings_missing`, `progression_contradicts_strategy` (E).
- Structure: `reference_unknown`, `theme_cycle`, `theme_label_duplicate`,
  `level_profile_unknown`, `word_invalid`, `word_duplicate`, `word_prohibited`,
  `puzzle_word_not_in_pool`, `puzzle_word_repeated` (E).
- Feasibility: `puzzle_type_unsupported`, `puzzle_count_unsupported`,
  `bank_count_unsupported`, `profile_count_unsupported`, `grid_unsupported`,
  `grid_print_unsupported`, `solution_print_unsupported`,
  `words_per_puzzle_unsupported`, `word_cannot_fit`,
  `print_profile_unsupported`, `page_estimate_below_minimum`,
  `page_estimate_above_maximum` (E); `page_estimate_uncertain`,
  `bank_size_exceeds` (W).
- Decisions: `print_profile_undecided`, `solutions_undecided`,
  `provenance_unknown` (E).
- Editorial (never blocks): `theme_labels_similar`, `theme_vocabulary_overlap`,
  `theme_overrepresented`, `theme_without_puzzles`, `pool_thin`, `word_reuse`,
  `duplicate_word_sets`, `similar_word_sets`, `puzzle_titles_duplicate`,
  `word_short`, `word_long`, `word_contains_prohibited`, `difficulty_jump`,
  `sections_out_of_order`, `level_order_inverted`, `familiarity_undecided`,
  `audience_repeated`, `promotional_language`, `licensed_unreferenced` (W);
  `theme_thin`, `word_cross_theme`, `level_unused`, `vocabulary_ai_generated`,
  `pool_unused` (N).
- Approval: `approval_stale`, `approval_not_ready` (W).

Each finding carries its code, gate, severity, basis (`plan_consistency`,
`evidence_integrity`, `engine_rule`, `production_cap`, `print_constant`,
`quality_measure`, `author_decision`, `editorial_heuristic`), message,
`planning.yaml` path, actual and expected values where meaningful, action and
subjects. Ruleset `puzzlepress-planning` version 1.

## Identity and approval

`pp1-planning-sha256-` is SHA-256 over canonical JSON (sorted keys, ASCII) of the
normalized document without `approval`, the book ID and the planning identity
version. Comments, key order, formatting, omitted versus explicit defaults and
direction order do not change it; authored list order does (it is the book
order). It contains no paths, times, engine or toolchain versions: approval binds
to the authored plan, while findings are always recomputed by the running engine.
It is stable across processes, working directories and hash seeds (tested). No
production identity includes it.

Approval follows the confirmation principle of [publishing](publishing.md#author-confirmations):
`approval` stores the planning identity the author reviewed. PuzzlePress records
it only when the author passes the current identity of a plan that is ready
(`plan approve --identity`, or Studio's Approve on the saved revision); it never
approves by itself. Any material edit makes it stale; restoring exactly the
approved content makes it apply again. No person, time or history is recorded.
A recorded approval on a blocked plan does not count. Planning approval is not
publishing approval, KDP acceptance or evidence that a book will sell.

## Production handoff

`puzzlepress plan handoff PROJECT --json` prints a deterministic, versioned
document (`handoff_version` 1) for an approved plan only: book ID and title,
planning and approved identities, concept and positioning, structure, levels
with their settings, theme allocations, planned puzzles in order with their words,
search forms and sources, vocabulary with validity and provenance, constraints,
the page estimate, feasibility items, open editorial findings and questions, what
production must still verify, and the decisions only a person can make (word and
puzzle IDs, composition text, the puzzle cap, AI disclosure, metadata and cover).
It is printed, never written, and is not a `book.yaml` fragment: it creates or
overwrites no puzzle definitions and generates nothing.

## Generator limits

A project holds at most 100 puzzle definitions, 20 word banks of 100 entries and
20 difficulty profiles (`content.MAX_*`); a plan beyond them is reported as
`unsupported` and its target is kept. Interval 12 raised the puzzle cap from 20
to 100 after measuring 20, 60 and 100-puzzle books through generation, interior,
preflight, cover and publishing (see
[automotive production](automotive-production.md#generator-scaling)):

- Schema: a literal bound in `content_validation`; the generator and batch code
  have no other dependency on it.
- Work: a batch work budget (`content.MAX_BATCH_ATTEMPTS`, 20,000,000 candidate
  checks summed over every puzzle's profile) keeps the worst case where it was
  with 20 puzzles. Default profiles (100,000 attempts) fit 100 puzzles.
- Composition and print: no puzzle cap; plans, layout and the KDP gutter table
  handle long books (up to 828 pages; 550 modeled maximum at 8.5 x 11).
- Studio: generation, plan preview and publishing readiness are synchronous
  requests under one lock; long books make them proportionally slower, and
  reports are cached by the exact bytes they depend on.

Planning never changes the cap.

## CLI

```text
puzzlepress plan inspect PROJECT [--json]    # summary, identity, gates; exit 0 if loaded
puzzlepress plan validate PROJECT [--json]   # schema, references, vocabulary; exit 0 if valid
puzzlepress plan report PROJECT [--json]     # full report; exit 0 only when ready or approved
puzzlepress plan approve PROJECT --identity ID | --withdraw
puzzlepress plan handoff PROJECT [--json]    # approved plans only
```

Exit codes: 0 success, 1 missing, invalid or not ready, 2 usage. `report --json`
prints the canonical report bytes. Only `approve` writes, and only
`planning.yaml`. Nothing reads or writes a build directory or `book.yaml`, or opens
a network connection.

## Studio

The Planning tab (`/books/{key}/planning`) is one editor: a section list
(overview, audience, research, comparable books, themes, puzzle allocation,
vocabulary, difficulty, coverage) that deep-links by `#planning-<section>`, the
section's fields, and a readiness column with each gate, approval and production
feasibility. Python checks each draft change (`POST /draft/planning`); findings
appear beside their fields and schema problems keep the draft. Saving uses the
plan's own revision (`POST /planning/save`, 409 on conflict, never overwriting a
plan created meanwhile). Approval is a deliberate action on the saved, unedited
plan (`POST /planning/approval`); unsaved edits to an approved plan are announced
as making it stale. Charts are tables of Python's numbers: allocation by theme,
usable versus needed words, and level progression in book order. See
[studio.md](studio.md#planning).

## Automotive demo

`books/automotive/planning.yaml` plans 60 puzzles in seven themes under one parent,
three levels with a gradual strategy, 184 candidate words and the opening
warm-up section (7 puzzles). It is honest about what it is: audiences are
labelled working assumptions; there are no comparable books, because none has
been read and cited; KDP facts are cited from PuzzlePress's recorded provenance
and marked unverified for this book; the vocabulary was drafted with an AI model
and is recorded as `ai_generated`; nothing is approved. Its report: needs
research (three blocking questions), 53 puzzles unspecified, the 20-puzzle cap
unsupported, the print profile undecided, and thin pools for 60 puzzles. Its
`book.yaml` and build identity are unchanged.

## Limitations

- Heuristics (label similarity, pool overlap, balance, promotional wording, level
  order) can over- or under-report; thresholds are conventions.
- Feasibility does not trial-generate grids; placement success is unknown.
- Page counts are estimates; the publication plan is authoritative.
- No series or catalogue planning, market data, keyword research, pricing or
  forecasting. Research is entered by a person and verified by none.
- Approval binds to content, not to a person or time, and keeps no history.
