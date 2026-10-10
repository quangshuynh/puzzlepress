# Production scale and book repositories

PuzzlePress is the engine: CLI, Studio, schemas, validators, renderers, preflight,
publishing checks, tests and documentation. Real books, their plans, vocabulary,
photographs, reviews and release artifacts live in a separate book repository
(for this project, the private `quangshuynh/puzzlepress-books`). The engine never
reads, tests against or requires that repository; its tests and CI use synthetic
books only.

## Working with a book repository

Every command takes an explicit project path, so a book can live anywhere:

```text
puzzlepress validate ../puzzlepress-books/books/automotive
puzzlepress puzzle batch ../puzzlepress-books/books/automotive --strict-quality
puzzlepress plan production ../puzzlepress-books/books/automotive
puzzlepress book build ../puzzlepress-books/books/automotive
puzzlepress book preflight ../puzzlepress-books/books/automotive
puzzlepress publish inspect ../puzzlepress-books/books/automotive
```

Paths in `book.yaml` resolve from the `book.yaml` file, never from the working
directory: `output.directory: ../../build/<id>` writes to the book repository's own
`build/`, which it ignores. Source/output disjointness, symlink refusal and atomic
writes apply wherever the book is (tested with an external library).

Studio serves one library folder, whose subfolders each hold a `book.yaml`:

```text
puzzlepress-studio --books ../puzzlepress-books/books
```

With an editable install, Studio finds this checkout's built frontend
(`studio/dist`) from any working directory, so it can also be started inside the
book repository (`puzzlepress-studio --books books`). Saves stay revision-checked
and limited to `book.yaml` and `planning.yaml` inside that library.

## Synthetic production book

[`tests/production_book.py`](../tests/production_book.py) writes a SYNTHETIC
60-puzzle book with a real book's production shape: seven themes allocated
10/10/8/10/8/6/8, warm-up/standard/challenge levels on 13/15/17 grids with 10-11,
13-14 and 16 words, banks split by section, title/copyright/instructions front
matter, recto starts, two solutions a page, a closing page, roman front-matter
numbering (95 pages), undecided publishing metadata and an unapproved plan with
one open blocking question. Its words are invented pseudo-words generated
deterministically; nothing is authored book content. Tests use it through the
`production_book` fixture; CI and the browser tests write it with
`python tests/production_book.py DIRECTORY`.

It builds a valid, modeled-KDP-ready interior, its batch is clean with screening
enabled, `plan production` reports no deviation, and publishing stays blocked on
exactly the author's decisions and the missing cover.

## Generator scaling

The project cap is 100 puzzles (`content.MAX_PUZZLES`) within a batch work budget
(`content.MAX_BATCH_ATTEMPTS`, 20,000,000 candidate checks summed over every
puzzle's profile), the worst case before the cap rose from 20 (about 6.7 us per
check: roughly two minutes). Default profiles fit 100 puzzles. Measured on a
synthetic book (13/15/17 grids, two solutions a page; Windows 11, Python 3.13, one
development machine, 2026-10-09):

| Puzzles | Generation + quality | Plan | Interior | Preflight | Pages |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 0.16 s | 0.18 s | 1.15 s | 1.13 s | 32 |
| 60 | 0.49 s | 0.51 s | 3.32 s | 3.35 s | 92 |
| 100 | 0.82 s | 0.84 s | 5.51 s | 5.93 s | 152 |

At 100 puzzles peak traced memory was 3.6 MB for generation and 14.4 MB for the
interior; the 152-page interior was valid and KDP ready; with a synthetic photo the
cover printed spine text at 14 pt (0.342 in spine), cover preflight took 1.4 s,
readiness 7.0 s, and with synthetic test decisions a package exported in 7.2 s.
Pairwise quality grows quadratically (4,950 pairs at 100) but stays under a second.

## Performance of a 95-page interior

Measured on a real 95-page production book (in-process, best of three, same
machine). Profiling showed about three quarters of a build in pypdf re-parsing each
page; two exact changes removed the repetition (image counts skip a second parse
when a page has no `/XObject` and no `BI` bytes; preflight reuses the facts a build
read from byte-identical bytes). PDF bytes were unchanged.

| Workload | Before | After |
| --- | ---: | ---: |
| Generation + quality (60 puzzles) | 0.63 s | 0.60 s |
| Publication plan | 0.65 s | 0.63 s |
| Interior build (render + inspection) | 5.09 s | 3.59 s |
| Interior preflight | 8.72 s | 3.59 s |
| Publishing readiness | - | 3.67 s |

Studio with the synthetic 60-puzzle book (Playwright, Chromium, local server):
open 0.4-0.5 s, generate and review 60 puzzles 0.9-1.0 s, quality view 1.6 s,
composition plan 1.0-1.6 s, build and preflight 3.9-4.2 s, first publishing
readiness 4.0-4.6 s (then about 0.16 s from the cache keyed by source revision and
artifact digests), planning view 0.9 s.
