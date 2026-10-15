# Production design and publishing polish

This guide covers cover regions and design elements, the asset library, interior
styles and theme dividers, dependency-aware rebuilding, editorial review and
human proof records. Python lays out and renders everything. Studio shows Python's
rasters and boxes and never lays out a cover or a page itself.

Related references: [cover.md](cover.md), [print-interior.md](print-interior.md),
[book-composition.md](book-composition.md), [preflight.md](preflight.md),
[publishing.md](publishing.md), [studio.md](studio.md).

## Cover regions (cover version 3)

A version 3 cover replaces the single `layout`, `image` and `background` of
versions 1 and 2 with three regions and a stack of elements:

```yaml
cover:
  version: 3
  type: {style: editorial, position: top, align: center, tone: light}
  legibility: shade
  spine_text: auto
  regions:
    back:  {color: "#1d2a44"}
    spine: {color: "#1d2a44"}
    front: {color: "#1d2a44", gradient: {to: "#0b1220", direction: vertical}}
  elements:
    - {id: photo, type: photo, region: wrap,
       image: {path: cover-assets/harbour-dusk-34b4d3b99667.jpg, sha256: 34b4…},
       crop: {x: 0.5, y: 0.5, zoom: 1}}
    - {id: band, type: rect, region: front,
       box: {x: 0, y: 500, width: 612, height: 120}, fill: "#f4efe4", opacity: 0.6}
```

- Each region has a solid `color` and an optional two-stop `gradient`
  (`vertical` runs top to bottom, `horizontal` left to right). When all three
  regions share one solid color, the background is drawn as a single fill.
- Region boxes are never authored. They come from the cover geometry of the
  current built interior: page count read from the PDF, and paper from the print
  profile.
- Book-detail text (title, subtitle, author, back text, imprint and spine text)
  keeps the version 2 preset layout and overrides. It is always drawn above the
  elements.
- Nothing converts a cover implicitly. **Convert to regions**
  (`convert_to_regions`) maps a full-wrap or front-photo cover onto regions plus
  one photograph element. The converted cover renders byte-identical PDF bytes,
  which is tested. Its cover identity still changes, because the authored
  configuration changed. The built cover therefore reports as stale until it is
  rebuilt, and the rebuild writes the same bytes.
- Design presets (`front-photo-solid-back`, `full-wrap-photo`, `framed-photo` and
  `solid-with-rules`) return authored values that use the cover's own photograph
  and colors. Python lays them out like any other cover.

### Coordinate system

An element's `box` (`x`, `y`, `width`, `height`) or its line points (`from`,
`to`) are PDF points, measured from the bottom-left corner of the element's
region trim box (x to the right, y up).

- A front element stays in place when the spine width changes.
- `wrap` is the full trim width (back, spine and front) and accepts photographs
  only.
- Coordinates are bounded to ±1,500 pt.

### Layer model

Elements draw in list order: the first is at the bottom and the last on top. The
stack holds at most 24 elements, of which at most 4 may be photographs.

| Type | Fields | Regions |
| --- | --- | --- |
| `photo` | `image`, `crop`, optional `box` | wrap, back, front |
| `rect`, `ellipse` | `box`, `fill`, `stroke`, `stroke_width`, `opacity`, `rotation` | back, spine, front |
| `line` | `from`, `to`, `color`, `width` | back, spine, front |
| `text` | `box`, `text`, `font`, `size`, `color`, `align`, `line_spacing`, `letter_spacing`, `case` | back, front |

Fields shared by every element:

- `id` and `type`.
- `visible`: hidden elements are not drawn.
- `locked` and `name`: editing aids only. They are excluded from the cover
  identity and never affect output.

Field rules:

- `stroke_width` and line `width` must be between 0.75 and 72 pt. The lower bound
  is KDP's minimum line weight.
- `opacity` must be between 0.05 and 1.
- A shape must have a fill or a stroke.
- `rotation` needs a `box`.
- A translucent shape cannot have a stroke.

How elements are drawn:

- Strokes are drawn as filled even-odd rings. The PDF never uses stroke operators.
- KDP covers may not use PDF transparency, so Python flattens opacity in one of
  two ways:
  - blending the shape with the single solid region color beneath it; or
  - baking it into the pixels of the single photograph beneath it.

  Anything else is reported as `opacity_not_flattenable` instead of being
  approximated.

Text boxes wrap inside their box. A word wider than the box, or text taller than
the box, is reported as `text_overflow`.

### Spine and barcode rules

These are layout issues. They block a build:

- `spine_element_outside`: a spine element must stay between the two folds.
- `element_outside_media`: an element extends past the bleed edge.

These are warnings. They never block:

- `spine_color_at_fold`: the spine and a neighboring panel have different
  backgrounds. Binding can shift a fold, so a little of either color may show on
  the other side.
- `spine_element_at_fold`: a spine element comes within KDP's fold variance.
- `element_under_barcode`: an element lies under the barcode keep-clear area.

Cover preflight ruleset `puzzlepress-kdp-cover` version 3 reports these warnings
as `kdp_spine_design` and `kdp_barcode_design`. Spine text still prints only from
80 pages, and only when 7 pt fits.

## Asset library

Photographs live in `cover-assets/` and imported fonts in `cover-assets/fonts/`,
under content-addressed names. Importing identical bytes reuses the existing
file.

The library lists each asset with:

- kind, format, pixel size, file size and SHA-256;
- every place it is used, in the saved source and in the unsaved Studio draft.

Uses are read from authored source only: the cover (any version) and the
interior style.

**Removal contract.**

- An asset the saved source or the draft uses cannot be removed (`asset_in_use`).
- Removing an unused asset moves it, with one atomic rename, to
  `cover-assets/.trash/` (fonts go to `.trash/fonts/`). Listings and imports
  never enumerate the trash.
- A trashed asset can be restored under its original name, or purged as a
  second, explicit step.
- The digest the author saw must still match. A file replaced in the meantime is
  refused (`asset_changed`).
- A name that is taken again on restore is refused (`asset_collision`).
- Paths are derived only from validated references and rechecked against the
  resolved project folder. Symlinks, other folders and bundled fonts are never
  touched (`asset_unsafe`).
- Studio holds the save lock while it moves a file, so a save cannot race a
  removal.
- Asset operations never change `book.yaml`, the build identity or any PDF.

## Interior styles

The optional `interior` section is version 1 and is presentation only. Like the
cover, it is outside the build identity, so restyling never changes plans,
seeds or grids. The resolved renderer settings (`interior.design`, version 1)
enter the interior identity as the manifest's `style` input. A book without a
style section renders byte-identically to before.

```yaml
interior:
  version: 1
  preset: editorial          # classic | editorial | modern | high_contrast
  folio: outside             # center | outside
  title_page: {layout: color_block, tint: 12, title_size: 36, align: left, rule: true}
  puzzle_pages: {header_align: left, title_size: 22, title_bold: true, theme_label: true,
                 theme_size: 11, header_rule: true, grid_frame: 1.5, word_size: 12,
                 word_columns: 4, word_rule: false}
  solution_pages: {caption_size: 9, mark_width: 1.25, muted_ink: 50}
  dividers: {layout: band, tint: 15, photos: []}
```

**Presets.** A preset names a coherent set of settings, and each field overrides
one of them.

- `classic`: exactly the original interior.
- `editorial`: left-aligned headers, fine rules, folios on the outside edge.
- `modern`: regular-weight titles, a framed title page, heavier grid frames.
- `high_contrast`: larger words, bold frames and solution marks.

**Bounds.** All sizes are in points:

| Field | Range |
| --- | --- |
| Title | 18–48 |
| Puzzle title | 16–30 |
| Theme | 9–14 |
| Words | 10–16 |
| Word columns | 2–5 |
| Grid frame | 0.75–3 |
| Caption | 8–12 |
| Mark width | 0.75–2 |
| Muted ink | 35–65 % black |
| Tint | 0–100 % black |

KDP's 7 pt text and 0.75 pt line minimums always hold.

### Title pages and backgrounds

The interior is black ink on white or cream paper, with no bleed. Title-page
layouts:

- `minimal`: the original centered layout.
- `editorial`: left-aligned under a full-measure rule.
- `color_block`: the title in a DeviceGray tinted block.
- `framed`: a ruled frame.
- `photo_feature`: a grayscale photograph above the title.

Panels and frames stay inside the live area. Nothing prints to the trimmed edge.

Photographs used by `photo_feature` and by divider `photos`:

- Python converts them to grayscale (ITU-R 601 luma of the sRGB-normalized
  pixels).
- They are embedded as DeviceGray baseline JPEGs without metadata, using the
  cover's crop window: whole source pixels, never stretched or upscaled.
- Effective DPI is measured from the layout. Interior preflight ruleset 3
  (`raster_images`, `kdp_image_resolution`) reports a photograph below 300 DPI
  as a finding, not as a build failure.

### Theme dividers

Dividers are pagination, so they are composition rather than style. They appear
in the publication plan as `divider` pages.

```yaml
composition:
  puzzles:
    dividers:
      start: recto        # any | recto
      themes:
        - {theme: Harbour, title: The Harbour, text: Boats, quays and the tide.,
           quote: Your own words only, attribution: You}
```

- One divider page precedes each theme group. Each theme's puzzles must be
  consecutive in publication order; otherwise validation reports
  `themes_not_contiguous`. A theme no puzzle uses is reported as
  `unknown_theme`.
- `title` defaults to the theme name. `text`, `quote` and `attribution` are the
  author's own optional words. PuzzlePress never supplies a quotation.
- `start: recto` puts every divider on a right-hand page, inserting an explicit
  blank (`divider_recto_start`) only when needed.
- The plan statistic `divider_pages` appears only when it is non-zero, so earlier
  plans and identities are unchanged.
- Dividers change the page count, so the cover must be rebuilt afterwards. Studio
  says so before saving.

## Dependency-aware rebuilding

```text
source + composition -> plan -> interior.pdf/.json -> preflight.json
interior page count and paper -> cover geometry -> cover.pdf/.json -> cover-preflight.json
artifacts + metadata + confirmations -> publishing package
```

**Assessment** (`production.artifacts.assess`) observes and never writes. It
reuses the publishing readiness report, which reruns both preflights and never
trusts a saved report. Each artifact is `current`, `stale`, `missing`, `invalid`
or `not_applicable`, with the reasons Python found.

**The rebuild plan** lists only steps whose inputs changed:

| Change | Plan |
| --- | --- |
| Cover typography | The cover alone |
| Keyword or other metadata | Nothing |
| Editorial review | Nothing |
| Interior | The interior, then a conditional cover check |

The conditional cover check rebuilds the cover only if the page count, paper or
profile changed. Otherwise it reports `unchanged` and refreshes the cover
preflight report.

**Running a rebuild** (`production.rebuild`) goes through the same single writers
as the CLI:

- A failed step writes nothing, so the previous artifact stays in place. Later
  steps are skipped with a reason.
- Studio passes a `before_write` check: if the saved source changes during the
  run, it stops before the next write (`source_changed`) and reports the steps
  already completed.
- The result is always the state recomputed afterwards.
- Exporting the publishing package is never part of a rebuild.

## Editorial review

`reviews.yaml` sits beside `book.yaml`. It is authored source outside every
production identity, revision-checked and written atomically.

```yaml
review_version: 1
policy: {require_all: false}
puzzles:
  - {puzzle: harbour-1, status: reviewed, content: pp1-puzzle-review-sha256-…,
     note: Checked spellings., reviewer: Your name, reviewed_on: 2026-10-15}
```

- **Identity.** `pp1-puzzle-review-sha256-` is computed over canonical JSON of:
  the book ID, puzzle ID, title, theme, difficulty profile (grid size and
  directions), and the ordered words (ID and display text). It excludes seeds,
  publication order and other puzzles.
- **States.** A puzzle is `not_reviewed`, `reviewed`, `needs_changes` or
  `stale`. A review goes stale when the content changes; restoring the content
  restores it. Reviews for puzzles that no longer exist are listed as orphaned.
- **What it is not.** A review is never inferred from quality checks, never
  defaulted and never dated by PuzzlePress. The reviewer and date are words the
  author types.
- **Policy.** `require_all` is an internal workflow gate, not a KDP rule.

## Publishing readiness and human proofing

The production overview (`production.guidance.overview`) lists every check and
human step.

Each item has a kind, which never blurs:

- `internal`: a PuzzlePress rule;
- `kdp_modeled`: a KDP requirement PuzzlePress models (passing it is not Amazon's
  acceptance);
- `author_judgment`: AI disclosure, rights, ISBN, classifications, content
  review or plan approval;
- `external`: the Print Previewer or a printed proof.

Each item has a status: `completed`, `needs_attention`, `blocking`,
`not_applicable`, `awaiting_review` or `external_pending`. Each item also states
whether it blocks export.

Stages run from draft source to Published. PuzzlePress never tracks publication:
it never publishes and never contacts Amazon.

**Proof records** live in `proofs.yaml` beside `book.yaml`, outside every
production identity.

```yaml
proof_version: 1
proofs:
  - id: proof-1
    kind: physical_proof          # print_previewer | physical_proof
    status: received              # ordered | received (physical only) | reviewed
    decision: undecided           # undecided | changes_needed | approved
    artifacts: {interior: pp1-interior-…, interior_pdf: <sha256>, cover: pp1-cover-…, cover_pdf: <sha256>}
    received_on: 2026-10-20
    issues: [Gutter text is tight on page 12.]
```

A record names the interior and cover identities and PDF digests that Python
reported for the build directory when the author recorded it. It goes stale once
either artifact changes. Studio offers ten proofing steps. The decision is
always the author's: nothing is approved, dated or submitted for them.

## Backward compatibility and determinism

- Version 1 and 2 covers, books without `interior`, and books without dividers
  render byte-identical PDFs with unchanged identities. This was compared
  against `main` for every demo book and the synthetic production book.
- Reviews, proof records and unused assets never change PDF bytes. Restyling
  changes only the interior identity. A cover change never changes the interior.
- Rebuilds call the same build functions and single writers as the CLI.

## Performance

Measured with the Studio API on the synthetic 60-puzzle book with the cover
demo's cover. Times are medians on Windows with Python 3.13; operations that
exist in both trees match `main` within 1 %:

| Operation | Time |
| --- | --- |
| Studio Cover opening | 0.33 s |
| Cover preview, plain | 0.47 s |
| Cover preview, 24-element region design | 0.48 s |
| Interior style draft preview | 0.25 s |
| 60-puzzle interior build | 3.5 s |
| Interior preflight | 0.16 s |
| Cover build | 0.68 s |
| Cover preflight | 0.28 s |
| Publishing readiness | 4.1 s |
| Asset library listing | 0.15 s |
| Review navigator (60 puzzles) | 0.15 s |
| Production overview (cached) | 0.16 s |
| Smart rebuild, nothing outdated | 4.3 s |
| Smart rebuild after a puzzle edit | 15.2 s |

Small field edits never render the whole book. The interior style preview
renders one sample page of each kind. A no-op rebuild costs one readiness
evaluation, because currency is never assumed.

## Limitations

- Interior photographs print in grayscale only. Studio places them with a
  centered crop; another focal point or zoom is authored in YAML.
- Divider and title-page photographs belong to the interior style, so they need
  an `interior` section.
- Elements cannot be grouped or aligned to each other.
- Rotation applies only to rectangles and ellipses.
- Gradients have two stops.
- Text boxes take one font and one style.
- Rebuild, review and proof records have no CLI. They are available through the
  Python API and Studio.
- Proof records and reviews keep no history beyond the current file.
