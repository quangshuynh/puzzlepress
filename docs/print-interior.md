# Print interior engine

`puzzlepress book build` turns a composed project into a print interior PDF. It
consumes the verified [publication plan](book-composition.md) and never changes
it: one physical page per plan entry, in plan order.

```text
project -> generation -> plan -> plan verification -> digest binding
        -> print specification -> layout -> layout validation
        -> PDF -> PDF inspection -> interior.pdf + interior.json
```

```text
puzzlepress book build books/composition-demo
puzzlepress book build books/composition-demo --output /tmp/demo --json
```

## Renderer contract

The plan decides what is on each page; the renderer decides where. Layout may
choose coordinates, grid scale and the arrangement of an already-planned
solution group. It never reorders, omits, inserts, merges or splits entries,
regroups solutions, changes numbering, regenerates puzzles or shrinks content
below profile minimums. Content that does not fit fails with a diagnostic.

Code lives in `puzzlepress.interior`: `spec` (profiles, units, KDP constraints),
`fonts`, `text` (wrapping), `geometry`, `engine` (layout), `validation`,
`render` (ReportLab), `inspection` (pypdf) and `build` (pipeline and writer).
`build_interior(project, spec)` is pure; `write_interior` is the only writer.

## Print specification

A `PrintSpecification` is renderer-facing and separate from composition; nothing
physical enters the plan or `book.yaml`. Profiles are built in and selected by
`--profile`. Adding a trim means adding a profile and its supported trim, not
changing page templates. Specs are validated before layout.

| Profile | `paperback-8.5x11` v1 |
| --- | --- |
| Trim | 8.5 x 11 in (612 x 792 pt); media box = trim box |
| Bleed | none (bleed specs are rejected) |
| Margins | inside 0.75 in, outside 0.5 in, top 0.625 in, bottom 0.625 in |
| Live area | 7.25 x 9.75 in, mirrored between recto and verso |
| Ink | DeviceGray only, no transparency |
| Folios | centered at the foot of the live area (`outside` also supported) |

Units: PDF points (1 in = 72 pt), converted once in `spec.inches`. Every
profile dimension is exact in binary floating point. Geometry comparisons use
1e-6 pt; layout validation and PDF box checks use 0.01 pt.

Recto pages are odd physical pages with the inside (binding) margin on the left;
verso pages are even with it on the right. Tests use asymmetric margins to catch
mirroring mistakes.

### KDP constraints

Centralized in `spec.KdpConstraints`, checked against KDP help pages ("Set Trim
Size, Bleed, and Margins"; "Paperback Manuscript File Requirements"):

- Gutter by page count: 24-150 0.375 in; 151-300 0.5; 301-500 0.625; 501-700
  0.75; 701-828 0.875. Above 828 pages the build fails.
- Outside/top/bottom at least 0.25 in without bleed (0.375 in with bleed).
- Text at least 7 pt; lines at least 0.75 pt; fonts embedded; no annotations,
  bookmarks or printer's marks.
- At least 24 pages. A shorter book still builds with warning
  `kdp_minimum_page_count`: the plan owns page count and the renderer never pads.

Physical page count equals the plan's logical page count. The gutter is fixed by
the profile and validated against that count; it is never enlarged automatically.

Bleed is not supported: puzzle pages have no element that prints to the trim
edge, so a bleed page box would add risk without content. KDP's bleed sizes
(0.125 in outside, top and bottom) are documented here for a future profile.

## Typography

Bitstream Vera Sans Regular, Bold and Italic are bundled in
`src/puzzlepress/interior/fonts/` with their license (copied from ReportLab's
distribution; redistributable, embeddable, may not be sold alone). Each file's
SHA-256 is pinned and checked before registration; system fonts are never
consulted. Vera has clear, distinct capitals for grids and covers Latin-1 plus
common punctuation. Text containing a character the font cannot draw fails
with `unsupported_character` and its code point.

| Role | Size (pt) |
| --- | --- |
| Title / subtitle / author / imprint | 30 bold / 16 / 14 / 11 |
| Heading, puzzle title | 22 bold |
| Body, copyright | 11.5, 9.5 |
| Theme | 12 italic |
| Word list | 13 |
| Puzzle grid letters | 9 to 20, scaled with cells |
| Solution grid letters | 7 to 14, scaled with cells |
| Captions, folios | 9.5, 10 |

## Layout model

`layout_interior(plan, report, spec)` returns an immutable `InteriorLayout`:
the spec, plan digest and identity, warnings, and `PhysicalPage`s, each with
its plan index and kind, media/trim/live boxes, displayed folio and elements.
Elements are `TextLine` (measured, with bounds), `Rule` and `LetterGrid`
(authoritative rows, square cells, frame, emphasized cells and `SolutionMark`
capsules). Origin is the bottom-left of the trim box. The renderer draws exactly
these elements, so layout is tested without parsing PDFs.

A 24 pt folio band is reserved at the foot of every live area.

- **Title page:** title, a short rule, subtitle and author from book metadata;
  imprint at the foot if authored. Nothing is invented.
- **Copyright:** authored text at the foot, in a 5.5 in measure, line breaks kept.
- **Instructions / about:** heading, then text wrapped in a 5.5 in measure.
- **Notes:** heading, then ruled writing lines (0.75 pt, gray).
- **Puzzle:** title, theme, framed grid and word list centered together below
  the header. Cells are square, largest that fit, capped at 20 pt letters.
  Words keep their display text and authored order, column-major in up to five
  equal columns.
- **Solutions:** the first page carries the plan's heading. Template by the
  plan's largest group: 1 (1x1), 2 (stacked), 4 (2x2), 6 (2 columns x 3 rows),
  filled in reading order. Each slot has the puzzle title and the puzzle page's
  plan label above its grid. Target letters are bold black inside 1 pt capsule
  outlines from first to last cell; other letters are 55% gray. Shape carries
  the meaning, so it reads in grayscale and crossings remain legible.
- **Blank:** a real, empty PDF page with no folio.

Wrapping is greedy, keeps authored line breaks and collapses runs of spaces. It
never hyphenates, truncates or shrinks; an unbreakable word fails.

## Diagnostics

`InteriorError(stage, issues)`; stages `print_spec`, `integrity`, `layout`,
`layout_validation`, `pdf_verification`, `output`. Each `LayoutIssue` has a
`code`, `message`, logical `page`, `physical_page`, plan `kind`, `subject`
(puzzle ID), `region`, and measured `actual`/`required` values where relevant.

Codes include `unsupported_profile`, `unsupported_trim_size`,
`unsupported_bleed_configuration`, `margin_too_small`, `gutter_too_small`,
`invalid_page_geometry`, `font_too_small`, `line_weight_too_small`,
`incomplete_plan`, `missing_puzzle`, `identity_mismatch`, `digest_mismatch`,
`solution_invalid`, `plan_order`, `unsupported_page_type`,
`unsupported_solution_density`, `text_overflow`, `word_list_overflow`,
`grid_too_small`, `unsupported_character`, `page_count_unsupported`, `font_invalid`,
PDF inspection codes (`pdf_*`, `font_not_embedded`) and output codes.

## Integrity and verification

1. The plan is verified by `verify_publication_plan`.
2. Every puzzle and solution entry is bound to the batch report by recomputing
   `puzzle_digest`; IDs alone are not trusted. Incomplete plans, foreign reports
   and mismatches fail; nothing regenerates. Solutions are independently verified.
3. `validate_layout` restates the contract: page order and kind, mirrored margins,
   folios equal to plan labels, empty blanks, grids equal to generated rows, word
   lists, exact solution groups and marks, minimum sizes and strokes, containment
   in the live area and no overlapping elements.
4. After rendering, pypdf reopens the bytes and checks page count, media and trim
   boxes, rotation, annotations, outline, forms, embedded font programs
   (`FontFile2`), empty blank pages and printed folios.

## PDF and determinism

ReportLab draws the layout with invariant mode (fixed 2000-01-01 dates, fixed
document ID), page compression and empty title/author/subject/keywords. Fonts
are embedded as TrueType subsets with deterministic subset names. No
annotations, outlines, links, crop or trim marks.

Guarantee: identical project source, profile, engine/renderer version, bundled
fonts and ReportLab version produce byte-identical `interior.pdf` and
`interior.json`. Tests compare bytes within a process and across processes with
different working directories and `PYTHONHASHSEED`. A different ReportLab
release may change bytes; its version is part of the interior identity.

## Output

Files go to the project's `output.directory` (for example
`build/composition-demo/`) or `--output DIR`:

- `interior.pdf`
- `interior.json`: manifest version, book ID, `interior_identity`
  (`pp1-interior-sha256-...` over project identity, plan digest, profile,
  renderer and engine versions, PDF library and font digests), page count, trim,
  PDF SHA-256 and byte size, and warnings. No timestamps or paths.

The writer resolves the directory again at write time and rejects any overlap
with the source directory. It only replaces an interior whose manifest names
the same book; an unowned `interior.pdf` or a foreign manifest is never touched.
Both files are staged beside their targets, fsynced, read back, then moved with
`os.replace`. A failed build writes nothing; a failed write leaves the previous
interior in place and removes staged files. The two replacements are not one
atomic transaction: an interruption between them can pair a new PDF with the
previous manifest, which the manifest's PDF SHA-256 reveals.

## CLI

`puzzlepress book build PROJECT [--output DIR] [--profile ID] [--json]`. Text
output gives paths, page count, trim, profile, interior identity and PDF
SHA-256; warnings go to stderr. JSON: `{success, output{pdf, manifest},
manifest}` or `{success: false, stage, diagnostics}`. Exit 0 success, 1 expected
failure (nothing written), 2 usage. Studio does not build interiors yet.

## Limitations

One profile (8.5 x 11 in, no bleed, black ink). Fonts are subset-embedded (KDP
recommends, but does not require, full embedding). One sans family with Latin-1
coverage. No PDF/X conformance, color management, images, hyphenation, running
heads, table of contents or per-book typography settings. The KDP page minimum
is a warning. Layout never repaginates, so overflow must be fixed in source or
composition. Print preview and full KDP preflight are Interval 8 work.
