# Automotive Word Search: production

The first production book: [`books/automotive`](../books/automotive/book.yaml), 60
word searches about vehicles, built from its plan
([`planning.yaml`](../books/automotive/planning.yaml)) through PuzzlePress's
existing pipeline. This page records what was built, how it was verified, what
was measured and what only the author can still decide. The per-puzzle review aid
is the [content audit](automotive-content-audit.md).

**State (Interval 12):** interior complete, verified, deterministic and
structurally valid and KDP ready under the modeled rules (95 pages). Content is
AI-drafted and not yet reviewed by a person. The plan is not approved. There is
no cover, because no photograph has been supplied. Publishing is blocked on the
author's decisions. Nothing has been proofed physically, uploaded or submitted.

## Positioning and audience

Working positioning from the Interval 12 brief, recorded in the plan as the
author's preference (`r-positioning-default`), not as research:

- Primary audience: adult car enthusiasts and automotive hobbyists.
- Secondary audience: automotive students and aspiring mechanics.
- Reader experience: entertaining, approachable and educational; not a repair,
  maintenance or training manual (the copyright page says so).
- Format: 8.5 x 11 in paperback word-search book, 60 puzzles, gradual difficulty.

No customer research, sales potential or comparable books are claimed. The plan's
audience text still reads "working assumption, not validated".

## Planning state and handoff

`puzzlepress plan report books/automotive`: **needs_research**. The only blocking
finding is the open question about comparable books (`q-comparables`): none has
been read and cited, and PuzzlePress never invents one. Every other gate passes
(definition, content, structure, feasibility, decisions). Approval: none.
Resolutions recorded this interval, each from the author's brief: audience
(working default), paper (white), puzzle cap (raised to 100). A new non-blocking
question asks for a person's review of the AI-drafted content (`q-vocabulary-review`).

The plan was deliberately extended through the normal planning file, not
rewritten: positioning, themes, allocations, levels, strategy, research notes and
the opening seven puzzles' IDs and titles are unchanged; word order in those seven
is now alphabetical (noted on each). `plan handoff` stays unavailable because the
plan is not approved.

`puzzlepress plan production books/automotive` is the auditable handoff in the
other direction (new, [book-planning](book-planning.md#production-comparison)):
planning identity `pp1-planning-sha256-2c0ae76c...`, production build identity
`pp1-sha256-fa7c150b...`, 60 target / 60 planned / 60 produced, every theme
allocation met, level settings equal to the production profiles, every puzzle's
title, level and words equal to the plan, **0 deviations**, all 793 placed words
recorded as `ai_generated`, and the open questions. It states that the book does
not follow an approved plan.

## Themes, levels and progression

| Theme | Puzzles | Warm-up | Standard | Challenge |
| --- | ---: | ---: | ---: | ---: |
| Engines & Powertrains | 10 | 3 | 3 | 4 |
| Maintenance & Repair | 10 | 4 | 3 | 3 |
| Tools & Workshop | 8 | 3 | 3 | 2 |
| Vehicle Systems | 10 | 3 | 4 | 3 |
| Motorsport | 8 | 3 | 2 | 3 |
| Automotive History | 6 | 2 | 2 | 2 |
| Driving & Road Culture | 8 | 2 | 3 | 3 |
| **Total** | **60** | **20** | **20** | **20** |

| Level (profile) | Pages | Grid | Directions | Words |
| --- | --- | --- | --- | --- |
| Warm-up (`warm-up`) | 1-20 | 13 x 13 | right, down, down-right | 10-11 |
| Standard (`standard`) | 21-40 | 15 x 15 | adds up-right | 13-14 |
| Challenge (`challenge`) | 41-60 | 17 x 17 | all eight, including backwards | 16 |

Levels are the plan's settings as existing generator profiles; there is no second
difficulty engine and no difficulty score. "Harder" means larger grids, more words
and more directions, which are only some influences on difficulty. Themes rotate
within each level so no theme runs in a block.

Puzzle IDs are `<theme>-NN` (for example `engines-07`), stable and descriptive;
seeds derive from the book seed (2026) and the ID, so adding, removing or
reordering other puzzles never changes a grid (tested at 20, 60 and 100).

## Vocabulary and provenance

787 distinct words over 793 placements; six words appear twice, none more. Every
word, title and matter text was drafted with an AI model: the 184 Interval 11
candidates (168 distinct forms used) and 623 words added in this interval, each
marked in `planning.yaml`. Provenance stays `ai_generated`; nothing was relabeled
human or AI-assisted. No external reference was consulted for vocabulary and none
is cited; nothing was copied from other puzzle books. Generic terms only (no
brand, model, team or driver names), American English spelling. Ten Interval 11
candidates are unused, each with its reason in the plan (too long for any grid,
contained in another target, a 3-letter acronym, replaced after screening).

Word lists print alphabetically. Banks split each theme's vocabulary into a
warm-up/standard bank and a challenge bank (14 banks, at most 84 entries) because
six theme pools exceed the 100-entry bank cap; the plan anticipated this
(`bank_size_exceeds`: select or split before production).

## Quality

`puzzlepress puzzle batch books/automotive --strict-quality` exits 0: every puzzle
generated, every placement independently verified, **no findings** (no accidental
extra targets, no screened words, no reuse above 2, no identical or similar word
sets; 1,770 pairs compared). A 23-word screening list of offensive words was added
for the author's review. The first generation flagged ten grids where filler and
placed letters spelled a screened word; each was revised deliberately in its word
list and noted (see the [audit](automotive-content-audit.md#quality-screening-and-revisions)).
No quality rule was weakened and no word was silently dropped.

## Composition and print

- Front matter: title page (title and working subtitle "60 Themed Puzzles with
  Solutions"; no author or imprint yet), a factual copyright/credits page (no
  ownership claim, ISBN, publisher or date), "How to Use This Book" (rules, levels,
  page ranges, where solutions are). A test checks every number it states against
  the built plan.
- Puzzles start on a recto after one justified blank; one puzzle per page.
- Solutions at the end, two per page, starting on a recto, captioned with title
  and page number. Back matter: "About the Words".
- Numbering `roman_front_matter`, front matter unnumbered: **puzzle N is printed on
  page N**, solutions on 61-90, the closing page 91.
- Print profile `paperback-8.5x11` v2: 8.5 x 11 in, black ink, **white paper**, no
  bleed, puzzle grid letters 15-20 pt and solution letters 9.8-12.7 pt (measured
  from the layout), inside margin 0.75 in (meets KDP's gutter up to 700 pages), outside 0.5 in,
  top and bottom 0.625 in. Renderer unchanged; the book revealed no layout defect.

KDP check (help pages read 2026-10-09): 8.5 x 11 in lies within KDP's custom
paperback trim range and black ink on white paper is offered; the official table
still lists no 8.5 x 11 row or page range, so the existing 550-page modeled
maximum (ambiguous) stands. Cream paper was not chosen; changing paper changes the
print profile, so the interior reports stale and the cover must be rebuilt.

## Interior: actual page count and preflight

`puzzlepress book build books/automotive`: **95 pages** (3 front matter, 1 blank,
60 puzzles, 30 solution pages, 1 back matter), interior identity
`pp1-interior-sha256-5aaa6019...`, PDF SHA-256 `00da6391...`, byte-identical across
processes, working directories and hash seeds (tested; CI on Ubuntu and Windows).

`puzzlepress book preflight books/automotive`: **structurally valid, KDP ready**
(modeled rules), 38 rules passed, one warning `kdp_full_font_embedding` (fonts are
subset-embedded; KDP's wording is ambiguous), 1 not applicable (images). Preflight
models a documented subset of KDP rules; KDP decides acceptance. KDP's handling of
an odd page count is not modeled; check it in Print Previewer.

Pages reviewed visually (rasterized from the real PDF): title page, copyright,
instructions, first puzzle, a middle standard puzzle, the hardest puzzle (page
60), first and last solution pages and the closing page. Grids, word lists, folios
and captions were aligned and legible with no clipping.

## Cover and spine

No authorized photograph has been supplied, so there is **no cover section**: no
image was invented, generated or borrowed, and `cover build` fails with
`cover_missing`. Readiness reports the cover as `no_config`.

Spine facts from the real interior: 95 pages x 0.002252 in (white) = **0.2139 in**;
full wrap **17.464 x 11.25 in**. The book reaches KDP's 80-page spine-text rule,
but its spine leaves 6.4 pt inside the 0.0625 in clearances, so spine text is
**omitted** (`spine_too_narrow`; verified with a synthetic stand-in photo in a
temporary copy). Cream paper (0.2375 in) would allow it with the editorial preset
(from about 89 pages); that is the author's paper decision, not a reason to change.

Photograph needed (300 DPI effective): for `full_wrap`, at least about **5,300 x
3,400 px** landscape (wider than 3:2 works best; the wrap is 1.55:1); for
`front_photo`, at least about **2,600 x 3,400 px** portrait. Zooming or cropping
raises the need. Import with `puzzlepress cover import books/automotive PHOTO`;
the original bytes are copied, never altered, and no EXIF/GPS reaches cover.pdf.

## Publishing state

`book.yaml` has a `publishing` section with a drafted plain-text description and
five descriptive keywords (both AI-drafted, for review; no category chosen, no
marketplace research). `puzzlepress publish inspect books/automotive`: interior
current, valid and KDP ready; cover `no_config`; package **not ready**. Blocking:

| Decision | Finding |
| --- | --- |
| Author name (on the cover and title page) | `author_present` |
| ISBN: KDP free or your own (none invented) | `isbn_decided` |
| Low-content classification | `low_content_decided` |
| Sexually explicit content answer | `audience_explicit` |
| AI disclosure for text, images, translations | `ai_disclosure_complete` |
| Rights, AI disclosure and metadata confirmations | `attestations` |
| Cover photograph and design | `cover_present` |

**AI disclosure.** KDP's content guidelines (read 2026-10-09) define AI-generated
content as text, images or translations created by an AI-based tool, "even if you
applied substantial edits afterwards", and require disclosing it; AI-assisted
content (yours, refined with AI) need not be disclosed. This book's word lists,
titles, matter text and description were created with an AI model, so a truthful
text declaration is likely `ai_generated`; PuzzlePress leaves it `unknown` because
the declaration is yours. Images depend on the photograph you supply; the book is
not a translation.

`publish package` writes nothing until every decision is made. Nothing contacts
Amazon.

## Generator scaling

The project cap rose from 20 to **100 puzzles**, with a new batch work budget
(`content.MAX_BATCH_ATTEMPTS`, 20,000,000 candidate checks summed over every
puzzle's profile) equal to the former worst case (20 x 1,000,000), so worst-case
generation work did not grow (about 6.7 us per check: roughly two minutes). Default
profiles fit 100 puzzles (10,000,000). Measured on a synthetic book drawn from the
plan's vocabulary (13/15/17 grids, 2 solutions a page; Windows, Python 3.13):

| Puzzles | Generation + quality | Plan | Interior | Preflight | Pages |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 0.16 s | 0.18 s | 1.15 s | 1.13 s | 32 |
| 60 | 0.49 s | 0.51 s | 3.32 s | 3.35 s | 92 |
| 100 | 0.82 s | 0.84 s | 5.51 s | 5.93 s | 152 |

At 100 puzzles: peak traced memory 3.6 MB for generation and 14.4 MB for the
interior; the 152-page interior is valid and KDP ready; with a synthetic photo
the cover printed spine text at 14 pt (0.342 in spine), cover preflight took 1.4 s,
readiness 7.0 s, and with synthetic test decisions a package exported in 7.2 s.
Pairwise quality grows quadratically (4,950 pairs at 100) but stays under a second.

## Performance (the real book)

In-process, best of three, Windows 11, Python 3.13 (one development machine):

| Workload | Before | After |
| --- | ---: | ---: |
| Generation + quality (60 puzzles) | 0.63 s | 0.60 s |
| Publication plan | 0.65 s | 0.63 s |
| Interior build (render + inspection) | 5.09 s | 3.59 s |
| Interior preflight | 8.72 s | 3.59 s |
| Publishing readiness (interior and cover preflight) | - | 3.67 s |
| Cover build (synthetic photo, temporary copy) | - | 0.52 s |

Profiling showed about three quarters of a build in pypdf re-parsing each page.
Two exact changes: the image count skips pypdf's second content-stream parse when
a page has no `/XObject` and no `BI` bytes, and preflight reuses the facts a build
read from byte-identical PDF bytes. PDF bytes are unchanged. No cache can mistake
stale output for current: reuse is keyed by the exact bytes.

Studio (browser, Playwright, Chromium, local server): open project 0.5 s; generate
and review 60 puzzles 0.9-1.0 s; quality view 1.6 s (1,770 comparison rows; render
about 40 ms after the response); composition plan 1.0-1.6 s; build interior and
preflight 4.1-4.2 s; first publishing readiness 4.6 s, then about 0.16 s from
Studio's report cache (keyed by source revision and artifact digests); planning
view 0.9 s. No background workers or database were added.

## Production workflow

```text
puzzlepress plan report books/automotive          # needs_research (comparables open)
puzzlepress plan production books/automotive      # 0 deviations; not approved
puzzlepress puzzle batch books/automotive --strict-quality
puzzlepress book plan books/automotive
puzzlepress book build books/automotive           # build/automotive-word-search/
puzzlepress book preflight books/automotive
puzzlepress cover import books/automotive PHOTO   # once you supply a photograph
puzzlepress cover build books/automotive          # fails: no cover section yet
puzzlepress cover preflight books/automotive
puzzlepress publish validate books/automotive     # lists your open decisions
puzzlepress publish inspect books/automotive
puzzlepress publish package books/automotive      # refuses until ready
```

## Human review checklist

- [ ] Read every word list, title and the matter text ([audit](automotive-content-audit.md)).
- [ ] Review the screening list and the ten screening revisions.
- [ ] Record comparable books you have actually read, or resolve `q-comparables`.
- [ ] Approve the plan if it is what you intend (`plan approve --identity`).
- [ ] Enter the author name; decide imprint, subtitle, copyright notice and edition.
- [ ] Supply and import your own photograph; design the cover in Cover Studio.
- [ ] Decide ISBN, low-content, the explicit-content answer and categories.
- [ ] Declare AI use truthfully; confirm rights, disclosure and metadata.
- [ ] Rebuild and preflight interior and cover; `publish inspect` must be ready.
- [ ] Export the package and upload it yourself in KDP.

## Physical proof workflow

1. Export the package once readiness passes; keep its package identity.
2. Upload `interior.pdf` and `cover.pdf` to KDP yourself and inspect every page in
   KDP Print Previewer (margins, gutter, folios, blank page 4, the final page).
3. Order a printed proof. Check legibility of the grids (puzzle letters 20 pt at
   13 x 13, 17.6-18.3 pt at 15 x 15, 15.0-16.2 pt at 17 x 17; solution letters
   9.8-12.7 pt), binding, spine, cover color (RGB is converted by KDP)
   and barcode area.
4. Record what you found. Only after reviewing a physical proof is the book
   proof-approved; no part of PuzzlePress records or claims that.

## Known limitations

- Content is AI-generated and unreviewed; no external terminology source is cited.
- The description-claims heuristic reads "13 by 13 grids" as a count of 13 puzzles,
  so the drafted description avoids grid dimensions (a heuristic over-report).
- Generation v1's random sequence depends on the word count, not the words, so a
  screening revision must change a length or the count to move a grid.
- KDP behavior for an odd page count (95) and the 8.5 x 11 page maximum are not
  confirmed from KDP's tables; check in Print Previewer.
- Spine text is omitted at 95 white pages; Studio performance figures are from one
  Windows machine.
