import os
import random
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace

import pytest

from puzzlepress.wordsearch import (
    ALPHABET,
    Coordinate,
    Direction,
    GenerationConfig,
    Grid,
    GridSize,
    Placement,
    Solution,
    TargetEntry,
    WordSearchError,
    generate_word_search,
    normalize_targets,
    verify_word_search,
)
from puzzlepress.wordsearch.generation import _can_place


def entries(*words):
    return tuple(TargetEntry(f"t{i}", word) for i, word in enumerate(words))


def generate(words=("ENGINE", "CLUTCH", "PISTON"), seed=2026, config=None):
    return generate_word_search(entries(*words), config or GenerationConfig(GridSize(10, 8)), seed)


@pytest.mark.parametrize(
    "text,display,search",
    [("engine", "engine", "ENGINE"), (" FUEL  Pump ", "FUEL  Pump", "FUELPUMP"), ("A", "A", "A")],
)
def test_normalization(text, display, search):
    target = normalize_targets(entries(text))[0]
    assert (target.id, target.display, target.search) == ("t0", display, search)


@pytest.mark.parametrize(
    "word",
    [
        "",
        "   ",
        "A-B",
        "A'B",
        "A1",
        "café",
        "ß",
        "A\tB",
        "A\n",
        "A\u00a0B",
        "A" * 51,
        " " * 201,
        None,
    ],
)
def test_invalid_words(word):
    with pytest.raises(WordSearchError) as error:
        normalize_targets(entries(word))
    assert error.value.issues[0].path == "targets.0.display"


@pytest.mark.parametrize("words", [("FUEL PUMP", "FUELPUMP"), ("abc", "ABC"), ("A", "A")])
def test_duplicate_search(words):
    with pytest.raises(WordSearchError) as error:
        normalize_targets(entries(*words))
    assert error.value.issues[0].code == "duplicate_search"


def test_identity_and_independent_input_errors():
    with pytest.raises(WordSearchError) as error:
        normalize_targets(
            (TargetEntry("same", "A"), TargetEntry("same", "B"), TargetEntry("", "!"))
        )
    assert {issue.code for issue in error.value.issues} == {"duplicate_id", "id", "characters"}
    for targets in ((), entries(*("A" for _ in range(101)))):
        with pytest.raises(WordSearchError, match="1..100"):
            normalize_targets(targets)


# Explicit expected vectors catch swapped axes and incorrect direction definitions.
DIRECTIONS = [
    (Direction.RIGHT, (1, 0)),
    (Direction.LEFT, (-1, 0)),
    (Direction.DOWN, (0, 1)),
    (Direction.UP, (0, -1)),
    (Direction.DOWN_RIGHT, (1, 1)),
    (Direction.DOWN_LEFT, (-1, 1)),
    (Direction.UP_RIGHT, (1, -1)),
    (Direction.UP_LEFT, (-1, -1)),
]


@pytest.mark.parametrize("direction,vector", DIRECTIONS)
def test_coordinate_math_boundaries_and_exact_fit(direction, vector):
    dx, dy = vector
    start = Coordinate(2 if dx < 0 else 0, 2 if dy < 0 else 0)
    placement = Placement("t", "ABC", start, direction)
    expected = tuple(Coordinate(start.x + i * dx, start.y + i * dy) for i in range(3))
    assert (direction.dx, direction.dy) == vector
    assert placement.coordinates == expected
    assert placement.end == expected[-1]
    cells = [[""] * 3 for _ in range(3)]
    assert _can_place(cells, placement)
    assert not _can_place(cells, replace(placement, search="ABCD"))
    assert not _can_place(cells, replace(placement, start=Coordinate(-1, 0)))
    assert not _can_place(cells, replace(placement, start=Coordinate(0, 3)))
    for c, letter in zip(expected, "ABC", strict=True):
        cells[c.y][c.x] = letter
    assert _can_place(cells, placement)
    cells[expected[1].y][expected[1].x] = "Z"
    assert not _can_place(cells, placement)


@pytest.mark.parametrize("direction,vector", DIRECTIONS)
def test_generation_in_each_direction(direction, vector):
    config = GenerationConfig(GridSize(3, 3), (direction,))
    puzzle = generate(("ABC",), config=config)
    assert puzzle.solution.placements[0].direction is direction
    assert verify_word_search(puzzle).valid
    with pytest.raises(WordSearchError) as error:
        generate(("ABCD",), config=config)
    assert error.value.issues[0].code == "cannot_fit"


def test_compatible_and_conflicting_intersections():
    cells = [["", "A", ""], ["", "B", ""], ["", "C", ""]]
    assert _can_place(cells, Placement("x", "DBE", Coordinate(0, 1), Direction.RIGHT))
    assert not _can_place(cells, Placement("x", "DZE", Coordinate(0, 1), Direction.RIGHT))


@pytest.mark.parametrize(
    "width,height", [(0, 5), (-1, 5), (51, 5), (5, 0), (5, 51), (True, 5), (5, 1.5)]
)
def test_invalid_dimensions(width, height):
    with pytest.raises(WordSearchError):
        generate(config=GenerationConfig(GridSize(width, height)))


@pytest.mark.parametrize(
    "changes",
    [
        {"directions": ()},
        {"directions": (Direction.RIGHT, Direction.RIGHT)},
        {"directions": ("right",)},
        {"max_restarts": -1},
        {"max_restarts": 101},
        {"max_restarts": True},
        {"max_attempts": 0},
        {"max_attempts": 1_000_001},
        {"max_attempts": 2.5},
    ],
)
def test_invalid_configuration(changes):
    with pytest.raises(WordSearchError):
        generate(config=replace(GenerationConfig(GridSize(10, 8)), **changes))


@pytest.mark.parametrize("seed", [-1, 2**64, True, None, 1.0, "", "+2", "-1", "0x2", "9" * 5000])
def test_invalid_seed(seed):
    with pytest.raises(WordSearchError) as error:
        generate(seed=seed)
    assert error.value.issues[0].code == "seed"


def test_determinism_filler_metadata_and_immutability(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = random.getstate()
    puzzle = generate()
    assert random.getstate() == state
    random.seed(99)
    try:
        assert generate() == puzzle == generate(seed=" 002026 ")
    finally:
        random.setstate(state)
    assert generate(seed=2027).grid != puzzle.grid
    assert verify_word_search(puzzle).valid
    assert len(puzzle.grid.rows) == 8
    assert all(len(row) == 10 and set(row) <= set(ALPHABET) for row in puzzle.grid.rows)
    assert tuple(p.target_id for p in puzzle.solution.placements) == tuple(
        t.id for t in puzzle.targets
    )
    for target, placement in zip(puzzle.targets, puzzle.solution.placements, strict=True):
        assert placement.search == target.search
        assert "".join(puzzle.grid.rows[c.y][c.x] for c in placement.coordinates) == target.search
    with pytest.raises(FrozenInstanceError):
        puzzle.seed = 3
    assert not list(tmp_path.iterdir())
    assert capsys.readouterr() == ("", "")


def test_directions_order_is_canonical():
    config = GenerationConfig(GridSize(10, 8), (Direction.UP, Direction.RIGHT))
    a = generate(config=config)
    b = generate(config=replace(config, directions=tuple(reversed(config.directions))))
    assert a == b
    assert {p.direction for p in a.solution.placements} <= set(config.directions)


def test_rectangular_fit_respects_direction():
    with pytest.raises(WordSearchError, match="cannot fit"):
        generate(("ABCDE",), config=GenerationConfig(GridSize(5, 2), (Direction.DOWN,)))
    assert verify_word_search(
        generate(("ABCDE",), config=GenerationConfig(GridSize(5, 2), (Direction.LEFT,)))
    ).valid


def test_impossible_puzzle_and_exact_restart_bound():
    config = GenerationConfig(GridSize(1, 1), (Direction.RIGHT,), max_restarts=2)
    with pytest.raises(WordSearchError) as error:
        generate(("A", "B"), config=config)
    assert error.value.issues[0].code == "search_exhausted"
    assert error.value.stats.attempts == 6
    assert error.value.stats.restarts == 2


def test_total_attempt_budget_across_restarts():
    config = GenerationConfig(GridSize(1, 1), (Direction.RIGHT,), max_attempts=3)
    with pytest.raises(WordSearchError) as error:
        generate(("A", "B"), config=config)
    assert error.value.stats.attempts == 3
    assert error.value.stats.restarts == 1


def test_exact_budget_success_and_single_letter():
    puzzle = generate(("A",), config=GenerationConfig(GridSize(1, 1), (Direction.RIGHT,), 0, 1))
    assert puzzle.grid.rows == ("A",)
    assert puzzle.stats.attempts == 1
    assert verify_word_search(puzzle).valid


def test_success_after_restart_clears_old_placements():
    config = GenerationConfig(GridSize(4, 4), (Direction.RIGHT, Direction.DOWN))
    puzzle = generate(("ABCD", "DEFG", "GHIJ", "JKLM"), seed=34, config=config)
    assert puzzle.stats.restarts == 1
    assert puzzle.stats.attempts == 62
    assert verify_word_search(puzzle).valid
    with pytest.raises(WordSearchError):
        generate(("ABCD", "DEFG", "GHIJ", "JKLM"), seed=34, config=replace(config, max_restarts=0))


def test_generation_v1_known_result():
    puzzle = generate(("FUEL PUMP", "AXLE"), config=GenerationConfig(GridSize(8, 6)))
    assert puzzle.generation_version == 1
    assert puzzle.grid.rows == (
        "VKLFCRZF",
        "FUELPUMP",
        "YIQQMUDE",
        "TGAOHGNL",
        "QQEQGZIX",
        "YWPERVKA",
    )
    assert puzzle.solution.placements == (
        Placement("t0", "FUELPUMP", Coordinate(0, 1), Direction.RIGHT),
        Placement("t1", "AXLE", Coordinate(7, 5), Direction.UP),
    )
    assert verify_word_search(puzzle).valid


@pytest.mark.parametrize("direction,vector", DIRECTIONS)
def test_exhaustive_small_rectangle_boundaries(direction, vector):
    # Exhaustive small-domain checks give coordinate coverage without Hypothesis.
    dx, dy = vector
    for width in range(1, 5):
        for height in range(1, 5):
            cells = [[""] * width for _ in range(height)]
            for x in range(-1, width + 1):
                for y in range(-1, height + 1):
                    for length in range(1, 6):
                        expected = all(
                            0 <= x + i * dx < width and 0 <= y + i * dy < height
                            for i in range(length)
                        )
                        placement = Placement("t", "A" * length, Coordinate(x, y), direction)
                        assert _can_place(cells, placement) == expected


def test_required_overlap_is_preserved():
    puzzle = generate(("ABC", "BC"), config=GenerationConfig(GridSize(3, 1), (Direction.RIGHT,)))
    assert puzzle.grid.rows == ("ABC",)
    a, b = puzzle.solution.placements
    assert set(b.coordinates) < set(a.coordinates)
    assert verify_word_search(puzzle).valid


def corrupt_placement(puzzle, **changes):
    placements = puzzle.solution.placements
    return replace(puzzle, solution=Solution((replace(placements[0], **changes), *placements[1:])))


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"start": Coordinate(-1, 0)}, "bounds"),
        ({"start": Coordinate(1.5, 0)}, "coordinate"),
        ({"direction": Direction.LEFT}, "direction"),
        ({"search": "XYZ"}, "metadata"),
        ({"target_id": "unknown"}, "unknown_target"),
    ],
)
def test_verifier_rejects_placement_corruption(changes, code):
    puzzle = generate(("ABC",), config=GenerationConfig(GridSize(3, 1), (Direction.RIGHT,)))
    result = verify_word_search(corrupt_placement(puzzle, **changes))
    assert not result.valid
    assert code in {issue.code for issue in result.issues}


def test_verifier_rejects_enabled_but_wrong_direction():
    puzzle = generate(("ABC",), config=GenerationConfig(GridSize(3, 3)))
    placement = puzzle.solution.placements[0]
    opposite = next(
        d for d in Direction if d.value == (-placement.direction.dx, -placement.direction.dy)
    )
    assert not verify_word_search(corrupt_placement(puzzle, direction=opposite)).valid


def test_verifier_rejects_grid_manifest_and_solution_corruption():
    puzzle = generate(("ABC", "BC"), config=GenerationConfig(GridSize(3, 1), (Direction.RIGHT,)))
    corruptions = [
        replace(puzzle, grid=Grid(("ZBC",))),
        replace(puzzle, grid=Grid(("AB",))),
        replace(puzzle, grid=Grid(())),
        replace(puzzle, grid=Grid(("AB!",))),
        replace(puzzle, solution=Solution(puzzle.solution.placements[1:])),
        replace(puzzle, solution=Solution(puzzle.solution.placements * 2)),
        replace(puzzle, targets=(replace(puzzle.targets[0], search="ZZZ"), *puzzle.targets[1:])),
        replace(puzzle, generation_version=999),
        replace(puzzle, config=replace(puzzle.config, max_attempts=0)),
        corrupt_placement(puzzle, search="AXC"),
    ]
    for corrupted in corruptions:
        assert not verify_word_search(corrupted).valid


def test_verifier_is_independent_of_generator_geometry(monkeypatch):
    puzzle = generate()

    def broken(*args):
        raise AssertionError("Verifier used generation geometry")

    monkeypatch.setattr(Placement, "coordinates", property(broken))
    monkeypatch.setattr(Placement, "end", property(broken))
    monkeypatch.setattr("puzzlepress.wordsearch.generation._can_place", broken)
    assert verify_word_search(puzzle).valid


def test_process_hash_seed_independence(tmp_path):
    code = (
        "from puzzlepress.wordsearch import *; "
        "print(generate_word_search((TargetEntry('a','ENGINE'), TargetEntry('b','PISTON')), "
        "GenerationConfig(GridSize(10,8)),2026))"
    )
    outputs = [
        subprocess.run(
            [sys.executable, "-c", code],
            cwd=tmp_path,
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in ("1", "98765")
    ]
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("seed", range(10))
def test_moderate_synthetic_generation(seed):
    # 25 distinct eight-letter targets on a normal book-sized logical grid.
    # Check work units rather than fragile wall-clock timing.
    words = tuple("TEST" + letter + "XYZ" for letter in ALPHABET[:25])
    puzzle = generate(words, seed=seed, config=GenerationConfig(GridSize(20, 20)))
    assert len(puzzle.solution.placements) == 25
    assert puzzle.stats.attempts < 10_000
    assert verify_word_search(puzzle).valid
