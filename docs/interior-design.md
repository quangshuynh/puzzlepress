# Interior design

Interior design controls how puzzle pages, answer pages and dividers look and how
answers are paginated. Everything is authored source in `book.yaml`; Python
resolves it, lays out the whole book, validates every page and renders the PDF.
Studio presents choices and Python's previews; it never draws a page.

Two sections hold the settings, by what they change:

| Setting | Section | Changes |
| --- | --- | --- |
| Solutions per printed page (1, 2, **4**, 6, 8) | `composition.solutions.per_page` | pagination: answer pages, page count, spine |
| One page or a two-page spread per puzzle | `composition.puzzles.layout` | pagination: puzzle pages, page count, spine |
| Theme, page layout, accents, banners, frames, decoration, spacing, captions | `interior` (version 2) | presentation only: the PDF, not the plan |

Composition is part of the build identity; the `interior` style is not, but it is
recorded in the interior manifest and identity. Either change makes a built
interior stale (see [Effects on artifacts](#effects-on-artifacts)).

## Solutions per page

`composition.solutions.per_page` is the number of solution grids on each printed
page (never a two-page total). Omitted, it is **4**, arranged 2 x 2. Choices:

| Per page | Arrangement | Largest square grid at 7 pt (classic) | Without the 7.5 pt advisory |
| --- | --- | --- | --- |
| 1 | one large grid | 39 x 39 | 38 x 38 |
| 2 | two stacked | 22 x 22 | 20 x 20 |
| 4 (default) | 2 x 2 | 19 x 19 | 17 x 17 |
| 6 | 2 x 3 | 13 x 13 | 12 x 12 |
| 8 | 2 x 4, compact cells | 11 x 11 | 10 x 10 |

Measured by `answer_fits` on 8.5 x 11 in with the solutions heading. Themes with a
page frame or decoration leave a little less room (Classic Garage: four a page up
to 17 x 17). Studio shows the measure for the book's own grids and theme.

Solutions continue onto further pages in puzzle order; the last page may hold
fewer. Each grid is captioned with its puzzle's title and the page that puzzle is
printed on (from the plan's cross-references, so captions follow any
repagination), and every word is outlined from its first to its last cell. One
arrangement serves the whole book, chosen by the plan's largest group.

Letters never go below the print profile's 7 pt solution minimum. When a choice
cannot reach it for the book's largest grid, the build stops with one
`solution_layout_unreadable` issue that names the densest choice that fits, for
example "4 solutions a page print 26 x 26 grids with 5.9 pt letters, below the 7
pt minimum. Choose 1 solutions a page or fewer." The count is never changed for
you. Between 7 and 7.5 pt the page builds with the advisory
`dense_solution_page` (preflight rule `design_legibility`). Eight a page uses
compact cells (letters 68% of the cell instead of 56%) so small grids keep 7 pt.

Older books stating `per_page: 2` keep two a page until you change it. A book
that omitted `per_page` (which meant 1 before this release) now gets four a page:
its plan, page count and identity change, and its built interior reports stale.

## Puzzle page layouts

`composition.puzzles.layout: spread` puts each puzzle's title and word list on a
left-hand page facing its grid on the right. A right-hand page that would carry a
word list is preceded by a blank with reason `spread_verso_start`. Spreads double
the puzzle pages; solution captions and answer references name the grid page.
`puzzles.start: recto` needs theme dividers with a spread (otherwise
`spread_starts_verso`). Omitted, `single` keeps title, grid and word list on one
page, as before.

`interior.layout` arranges the header, grid and word list:

| Layout | What it does |
| --- | --- |
| `classic` | Centred title and theme label, the grid, then the word list (the original). |
| `bold_header` | The title in a banner of the theme's style (solid when the theme has none), a rule between grid and word list. |
| `clean_minimal` | Left-aligned regular-weight title over a hairline, up to four columns, spacious spacing. |
| `large_readability` | 15 pt bold words in up to three columns, 26 pt titles, letters 64% of each cell, 11 pt captions. |

`puzzle_pages` overrides any value: `header_align`, `title_size`, `title_bold`,
`theme_label` (the category label), `theme_size`, `header_rule`, `grid_frame`,
`word_size`, `word_columns` (1..5), `word_rule`, and in version 2
`word_position` (below | above), `word_align` (center | left), `word_weight`
(regular | bold), `letter_scale` (standard | large), `grid_width` (60..100% of
the measure), `puzzle_number` and `answer_reference`. Grid letters stay at least
9 pt; a word list that does not fit is `word_list_overflow`, never cut or shrunk.

`answer_reference` and `solution_pages.page_label` are your own words with
`{page}` once where the number goes ("Solution on page {page}", "page {page}"),
up to 60 characters. PuzzlePress adds no words of its own, so these work in the
book's language. Python fills in the plan's page label.

## Themes

`interior.theme` sets tones and treatments; each can be overridden at the top of
the section.

| Theme | Banners | Corners | Background | Decoration | Page numbers |
| --- | --- | --- | --- | --- | --- |
| `classic` | none | square | none | none | plain |
| `racing_orange` | solid #141414 | rounded | none | stripes, accent #e8590c | rule |
| `classic_garage` | outline #3b3b3b | rounded | page frame | subtle chevrons, accent #8c5a2b | outline |
| `editorial_minimal` | heavy rule | square | none | none | plain, outside |
| `high_contrast` | solid black | square | none | none | plain |
| `ink_saver` | outline #4d4d4d | rounded | none | none | plain |

Overrides: `colors` {`accent`, `secondary` as #rrggbb}, `banner` (none | rule |
outline | solid), `corners` (square | rounded), `background` (none |
header_band | frame), `motif` (none | stripes | chevrons), `motif_intensity`
(subtle | medium | bold), `density` (compact | balanced | spacious: 0.75, 1 or
1.3 times the template gaps) and `folio_style` (plain | rule | outline). Themes
also set grid frame, path outline weight, letter gray on answer pages and the
divider layout; `title_page`, `solution_pages` and `dividers` keep their
version 1 fields.

```yaml
interior:
  version: 2
  theme: racing_orange
  layout: bold_header
  colors: {accent: "#cc3300"}
  motif_intensity: subtle
  puzzle_pages:
    puzzle_number: true
    answer_reference: Solution on page {page}
  solution_pages:
    page_label: page {page}
```

Section headings (the solutions title, instructions and notes headings) use the
theme's banner. Decoration and frames appear on puzzle, word-list, answer and
divider pages only, never on the title page or matter pages.

### Printing in black ink

Both interior profiles print black ink. Every colour prints as the gray of its
Rec. 601 luminance (Racing Orange's accent prints as 52% black), the PDF
contains DeviceGray only, and Studio's preview is that print simulation. A solid
banner takes paper-white type when it is dark and is checked for contrast
(`low_contrast_text`); accent labels lighter than 50% black warn (`light_text`).
Fills are small: banners, a 7% header band, thin stripes. Ink Saver uses
outlines only, with no fills or decoration.

Decoration is vector polygons in a band reserved at the top of the content area,
on the page's outer side (mirrored across a spread), clear of the gutter. Layout
validation refuses decoration that touches text, a grid or a photograph
(`decoration_overlap`), a frame or banner outline that crosses content
(`frame_crosses_content`), and any panel over a grid. Grid corners are rounded
by at most 30% of a cell, inside the frame padding, so solution outlines never
leave their frame.

Version 1 styles (`preset`) render exactly as before. Version 2 refuses
`preset`; version 1 refuses version 2 fields (`requires_version_2`). Studio
converts version 1 to 2 only when you ask, choosing the closest theme.

## Design files

A design can be saved as a named JSON file and imported into another book
(`format: puzzlepress-interior-design`, `format_version` 1, at most 64 KB). It
holds the `interior` section only: no book details, puzzles, composition or
photographs. Importing validates it with the same schema, keeps the receiving
draft's photographs, and changes only the draft until you save. Nothing in a file
is executed.

## Studio

Open a book and choose **Interior**. Tabs:

- **Page layout**: one page or a spread, the layout preset, header, word list,
  grid and footer (page numbers, answer reference). **Reset page layout**.
- **Answer layout**: solutions per printed page with Python's letter size and a
  Fits / Cramped / Too small status for this book's largest grids, the number of
  answer pages and how many the last holds, caption label and path weights.
  **Reset answer layout** returns to four a page.
- **Theme**: themes with their swatches, accents with what each prints as,
  treatments, **Reset to the theme**, and design file export and import.
- **Title & dividers**: the title page and theme divider pages.

The preview renders the whole draft book in Python and shows a puzzle spread, a
puzzle page, a full answer page, the last answer page (when it holds fewer),
a divider, the instructions and the title page. A draft that does not lay out
shows Python's issues instead. **Reset the whole design to defaults** removes the
`interior` section from the draft. Save writes `book.yaml` through the usual
revision-checked save; book details, puzzles, planning and publishing are not
touched.

## Effects on artifacts

| Change | Interior | Cover | Package |
| --- | --- | --- | --- |
| Theme, layout or any `interior` value | stale ("The interior style changed after this interior was built.") | stale only if the page count changes | stale |
| Solutions per page, spread, dividers | stale (source identity) | spine changes with the page count | stale |

Rebuild the interior in **Print proof** (or the rebuild panel), then the cover if
the page count changed, then export the package again. Proof records bound to the
old interior become stale. Preflight reruns on every rebuild and never trusts a
saved report; `design_legibility` warnings never block.

## Limits

One trim (8.5 x 11 in) and the bundled Vera Sans faces: there is no font family
choice. No free positioning or drag-and-drop page editing; layouts are tested
presets. Themes print in gray on the supported black-ink profiles. Answer
arrangements are fixed per count (two is always stacked). Section dividers exist
for themes only, not for instructions, difficulty levels or the answers section.
Difficulty labels are not printed on puzzle pages. Planning's
`solutions_per_page` accepts 8 but planning does not model spreads.
