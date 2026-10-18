# Book composition and publication plans

Composition answers one question: what belongs in this book, and in what logical
order? It produces a deterministic, verified **publication plan**. It does not
lay out pages, choose fonts, trim, margins or coordinates, or produce PDF bytes.
The [print interior engine](print-interior.md) consumes the plan and decides
physical layout.

```text
project -> generation -> quality -> composition -> publication plan | layout -> PDF
```

See [`composition-demo`](../books/composition-demo/book.yaml) for a complete example.

## Schema

Schema v1 gains an optional top-level `composition` section, added like
`word_search`. It requires `word_search` puzzle definitions.

```yaml
composition:
  front_matter:            # 0..3 pages, in this order
    - kind: title_page
    - kind: copyright_page
      text: Your own notice.
    - kind: instructions
      title: How to Play
      text: |-
        Find each listed word hidden in the grid.
  puzzles:
    start: recto           # any (default) | recto
    layout: single         # single (default) | spread: word list facing its grid
  solutions:               # required
    placement: end         # end | omit
    title: Solutions       # required with end
    per_page: 2            # 1 | 2 | 4 (default) | 6 | 8 per printed page, only with end
    start: recto           # any (default) | recto, only with end
  back_matter:             # 0..2 pages, in this order
    - kind: notes
      title: Notes
  page_numbers:
    scheme: roman_front_matter   # continuous (default) | roman_front_matter
    show_front_matter: false     # default false
    show_solutions: true         # default true
    show_back_matter: true       # default true
```

| Kind | Section | Fields |
| --- | --- | --- |
| `title_page` | front | none; uses `book.title`, `subtitle`, `author`, `imprint` |
| `copyright_page` | front | `text` |
| `instructions` | front | `title`, `text` |
| `about` | back | `title`, `text` |
| `notes` | back | `title` (a page reserved for reader notes) |

Each kind appears at most once and only in its section. A title page must be
first. Titles are single-line text of 1..200 characters. Body text is 1..2,000
characters of plain text; line breaks are kept, other control characters are
rejected, edges are trimmed. There is no rich text or markup.

PuzzlePress never invents legal text. The schema has no default copyright notice,
and Studio adds a copyright page with an empty field the author must complete.
Studio's starter instructions are visible, editable text.

Validation collects independent issues with structured paths, for example
`composition.solutions.per_page [choice]`. Unknown fields and kinds, duplicate
kinds, title-page order, malformed text, invalid choices, non-boolean flags,
settings that do not apply to omitted solutions, and roman numbering without
front matter are rejected. Nothing is repaired.

## Existing projects and identity

Projects without `composition` are unchanged. They keep their exact build
identity, and `composition` is omitted from canonical inputs. Planning such a
project fails with `composition [required]`; it is never silently given an
implied book. Studio offers an explicit, visible starter that is only saved
when the author saves. This mirrors how legacy projects add word-search content.

When present, the normalized composition is part of the project and its build
identity, with envelope field `composition_version: 1`. Omitted and explicit
defaults produce the same identity. Engine version (0.1.0), identity version and
word-search pipeline version are unchanged. Older engines reject the new section
as an unknown field.

## Puzzle order

Publication order is the authored `word_search.puzzles` order. That sequence
already existed, is identity-bearing and is reorderable in Studio, so composition
does not add a second, redundant list of references that could drift. Every
definition appears exactly once; missing or duplicate references cannot occur.
Puzzle seeds derive from the book seed and puzzle ID, so reordering never
changes a grid. Excluding a puzzle from a book is not supported.

## Pages, sides and blanks

Every plan entry is one **logical page** in reading order. Page 1 is a recto
(right-hand) page; odd pages are recto, even pages verso.

- Each matter item is one page. Each puzzle is one page (a grid and its word
  list), or with `puzzles.layout: spread` two: a `puzzle_words` page on a verso
  facing its `puzzle` grid page on the recto. A word list that would fall on a
  recto is preceded by one blank with reason `spread_verso_start`. Cross-references
  name the grid page. `puzzles.start: recto` with a spread needs theme dividers
  (`spread_starts_verso`). `single` is never written, so existing identities hold.
- Solutions are grouped `per_page` to a printed page, in puzzle order (four when
  omitted; it was one before interior design version 2, so a book that omitted it
  repaginates). Grouping is semantic: which solutions share a page. Their
  arrangement, scale and position on paper belong to the renderer, which must
  reject a density it cannot fit rather than regroup it
  ([interior design](interior-design.md#solutions-per-page)).
- `start: recto` makes a section begin on a recto page. If the next page would be
  verso, one explicit blank page is inserted with reason `section_recto_start`
  and the section it precedes. It belongs to the preceding section. Blanks are
  inserted only for this reason, at most one per section start.

`puzzles.dividers` (optional) inserts a `divider` page before each theme group:
`start` any or recto, and `themes` with each theme's own `title` (default: the
theme name), `text`, `quote` and `attribution` (the author's words; nothing is
supplied). Each theme's puzzles must be consecutive in publication order
(`themes_not_contiguous`); a listed theme no puzzle uses is `unknown_theme`. With
`start: recto`, one blank with reason `divider_recto_start` precedes a divider
that would fall on a verso. Dividers belong to the puzzles section and are
counted but never print a page number; they change
the page count, so the cover must be rebuilt. Without `dividers`, plans and
identities are unchanged. Divider styling (layout, tint, photograph) is the
interior style's ([production design](production-design-polish.md#theme-dividers)).

Back matter follows directly after solutions (or puzzles when solutions are
omitted). Signatures, imposition and final even-page padding are print concerns
and are not modelled.

## Page numbers

Every page has an abstract number: a value, a style (`arabic` or `roman`), a
label (`7`, `iv`) and `displayed`. Numbering never skips: blanks are counted.

- `continuous`: arabic numbers equal to the logical page index.
- `roman_front_matter`: front-matter pages (including a blank after them) are
  `i, ii, iii...`; arabic restarts at 1 on the first following page.
- Display: puzzle pages always display numbers, so solutions can refer to them.
  Blank pages never display. Front matter, solutions and back matter follow the
  `show_*` settings.

Cross-references use logical indexes: a puzzle page carries `solution_page`, and
each grouped solution carries `puzzle_page`. A renderer prints them using the
referenced page's label. Placement, fonts and styling of numbers are not decided.

## Publication plan

`puzzlepress.publication.build_publication(project)` validates the project,
runs the existing batch generator and returns `(BatchReport, PublicationPlan)`.
`plan_publication(project, report)` plans from a report generated from the same
source and rejects an unrelated report. Neither writes files or prints.

A plan has `plan_version` (1), the source build `identity`, `book_id`,
`language`, ordered `pages`, `statistics` and `diagnostics`. Each page has its
`index`, `side`, `section`, `kind`, `number`, and as applicable `heading` (the
first solution page's section heading), `matter` content, a `puzzle` reference,
`solution_page`, grouped `solutions` and a `blank` reason.

Puzzle references contain ID, ordinal, title, theme, the derived seed (a decimal
string in JSON) and `digest`: `sha256-` over the canonical JSON of the generated
puzzle's grid, targets, configuration and placements. A solution reference
carries the same puzzle reference, so it is bound to exactly the generated
puzzle on its puzzle page. A renderer receives the plan and the batch report and
should recheck digests before drawing.

Plan structure depends only on validated source. Generation supplies digests and
completeness. If a puzzle fails to generate, its puzzle and solution entries
remain, with `digest: null`, and a `generation_failed` diagnostic is added;
`complete` is false and the CLI exits 1. Nothing is omitted or regenerated.
Quality findings are reported separately and never change a plan.

### Statistics

`logical_pages`, `front_matter_pages`, `puzzle_pages`, `solution_pages`,
`back_matter_pages`, `blank_pages`, `puzzles`, `solutions`, `first_puzzle_page`
and `first_solution_page` (logical indexes), plus `divider_pages` only when
dividers exist. These are logical counts. The current
renderer prints exactly one physical page per logical page; they are not a KDP
page count, cost or royalty estimate.

### Verification

`puzzlepress.publication_verification.verify_publication_plan(plan, project,
report)` checks invariants against the source and report, not by re-running
the planner: contiguous indexes and reading order, page kinds in their sections,
matter text against source, every definition exactly once in authored order with
source-derived seeds and digests matching generation, complete solution coverage
bound to the same puzzle references, grouping, heading and cross-references,
justified blanks only, recto section starts, numbering sequences and display
policy, statistics and diagnostics. Tests corrupt plans in each of these ways.
A freshly planned plan that fails verification is a programming error and raises.

## CLI

```text
puzzlepress book plan books/composition-demo
puzzlepress book plan books/composition-demo --json
```

Text output lists each page with side, number (parenthesized when counted but not
displayed), section and content, followed by statistics. JSON contains `plan`,
`verification` and a separate `generation` summary (`success`, `clean`,
`quality_findings`). Exit 0 for a complete verified plan, 1 for invalid source,
missing composition or a generation failure (diagnostics on stderr), 2 for usage
errors. No files are written.

## Studio

The **Book** tab is the composer. It edits the same whole-project draft as **Edit**,
so both views share one revision, one validation call and one save. Edits are
memory-only until **Save changes**; the existing revision check, atomic save,
reload and stale-write rejection apply unchanged. See [Studio](studio.md).

## Determinism

Identical normalized inputs produce identical plans and JSON bytes: no clocks,
random identifiers, filesystem enumeration or hash-order dependence. Tests compare
plans across calls and CLI JSON across processes with different hash seeds and
working directories.

## Limitations

One puzzle per page; all definitions are always included. Solutions only at the
end or omitted. No table of contents, half-title, dedication, section dividers,
per-puzzle recto rules, rich text or images. Instructions are not checked against
each puzzle's enabled directions. Logical pages do not detect text overflow; the
renderer reports content that cannot fit a page rather than paginating it. Plans
contain no layout, trim, bleed or fonts; see [print interior](print-interior.md).
