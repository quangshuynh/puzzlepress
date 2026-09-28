from dataclasses import replace

import pytest

from puzzlepress.quality import (
    MAX_SCAN_HITS,
    analyze_word_search,
    compare_target_sets,
    screen_words,
)
from puzzlepress.wordsearch import (
    Coordinate,
    Direction,
    GenerationConfig,
    GenerationStats,
    Grid,
    GridSize,
    Placement,
    Solution,
    Target,
    WordSearch,
    WordSearchError,
)


def puzzle(rows, words):
    """Independent hand-authored grids and placements, avoiding generator coupling."""
    return WordSearch(
        tuple(Target(str(i), word, word) for i, (word, _, _) in enumerate(words)),
        GenerationConfig(GridSize(len(rows[0]), len(rows))),
        0,
        Grid(tuple(rows)),
        Solution(
            tuple(
                Placement(str(i), word, start, direction)
                for i, (word, start, direction) in enumerate(words)
            )
        ),
        GenerationStats(1, 0),
    )


@pytest.mark.parametrize("direction", list(Direction))
def test_scan_all_eight_directions(direction):
    start = Coordinate(2 if direction.dx < 0 else 0, 2 if direction.dy < 0 else 0)
    rows = [["X"] * 3 for _ in range(3)]
    expected = []
    for i, letter in enumerate("ABC"):
        x, y = start.x + i * direction.dx, start.y + i * direction.dy
        rows[y][x] = letter
        expected.append(Coordinate(x, y))
    grid = Grid(tuple("".join(row) for row in rows))
    result = screen_words(grid, ("a b c",))
    assert not result.truncated
    assert len(result.occurrences) == 1
    assert result.occurrences[0].word == "ABC"
    assert result.occurrences[0].coordinates == tuple(expected)


def test_accidental_excludes_authoritative_only_and_scans_disabled_directions():
    p = puzzle(("CAT", "XXX", "TAC"), [("CAT", Coordinate(0, 0), Direction.RIGHT)])
    p = replace(p, config=replace(p.config, directions=(Direction.RIGHT,)))
    report = analyze_word_search(p)
    assert len(report.accidental_targets.occurrences) == 1
    assert report.accidental_targets.occurrences[0].coordinates == (
        Coordinate(2, 2),
        Coordinate(1, 2),
        Coordinate(0, 2),
    )
    assert not report.prohibited.occurrences
    assert not report.prohibited_screening_enabled


def test_palindromes_single_letters_and_authoritative_reverse_are_deduplicated():
    p = puzzle(("LEVEL",), [("LEVEL", Coordinate(4, 0), Direction.LEFT)])
    assert not analyze_word_search(p).accidental_targets.occurrences
    assert len(screen_words(p.grid, ("LEVEL",)).occurrences) == 1
    assert len(screen_words(Grid(("AA",)), ("A",)).occurrences) == 2
    assert len(screen_words(Grid(("AAA",)), ("AA",)).occurrences) == 2


def test_substrings_overlaps_and_no_row_wrap():
    p = puzzle(
        ("SCAT", "CATX"),
        [("SCAT", Coordinate(0, 0), Direction.RIGHT), ("CAT", Coordinate(0, 1), Direction.RIGHT)],
    )
    result = analyze_word_search(p, ("SCAT", "CAT"))
    assert len(result.accidental_targets.occurrences) == 1
    assert result.accidental_targets.occurrences[0].coordinates[0] == Coordinate(1, 0)
    assert len(result.prohibited.occurrences) == 3
    assert result.prohibited_screening_enabled
    assert not screen_words(Grid(("XXA", "BCX")), ("ABC",)).occurrences


def test_scan_limit_is_explicit_and_invalid_grids_fail():
    result = screen_words(Grid(tuple("A" * 50 for _ in range(50))), ("A",))
    assert len(result.occurrences) == MAX_SCAN_HITS
    assert result.truncated
    for rows in ((), ("",), ("AB", "A"), ("a",), ("A" * 51,)):
        with pytest.raises(WordSearchError):
            screen_words(Grid(rows), ())


def test_scan_exact_limit_is_complete():
    result = screen_words(Grid(tuple("A" * 50 for _ in range(20))), ("A",))
    assert len(result.occurrences) == MAX_SCAN_HITS
    assert not result.truncated


@pytest.mark.parametrize("words", [("!",), ("A B", "AB"), ("",), ("A",) * 101, "ABC"])
def test_policy_list_uses_explicit_normalization_and_bounds(words):
    with pytest.raises(WordSearchError):
        screen_words(Grid(("ABC",)), words)


def test_quality_rejects_invalid_solution():
    p = puzzle(("ABC",), [("ABC", Coordinate(0, 0), Direction.RIGHT)])
    with pytest.raises(WordSearchError):
        analyze_word_search(replace(p, grid=Grid(("AXC",))))


def test_similarity_metrics_and_unavailable_grid_comparisons():
    result = compare_target_sets(
        "a", "b", frozenset(("A", "B")), frozenset(("B", "C")), Grid(("ABC",)), Grid(("AXC",))
    )
    assert result.shared_words == ("B",)
    assert result.target_jaccard == pytest.approx(1 / 3)
    assert result.target_overlap == 0.5
    assert result.grid_agreement == pytest.approx(2 / 3)
    assert not result.identical_targets
    reverse = compare_target_sets("b", "a", frozenset(("B", "C")), frozenset(("A", "B")))
    assert reverse.target_jaccard == result.target_jaccard
    assert reverse.grid_agreement is None
    assert (
        compare_target_sets(
            "a", "b", frozenset(("A",)), frozenset(("A",)), Grid(("AA",)), Grid(("A",))
        ).grid_agreement
        is None
    )
    contained = compare_target_sets("a", "b", frozenset(("A",)), frozenset(("A", "B")))
    assert contained.target_overlap == 1
    assert contained.target_jaccard == 0.5
