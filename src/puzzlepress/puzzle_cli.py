"""Argument and terminal adapter for standalone puzzle generation."""

from __future__ import annotations

import argparse

from .wordsearch import (
    Direction,
    GenerationConfig,
    GridSize,
    TargetEntry,
    generate_word_search,
    verify_word_search,
)


def add_puzzle_command(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    puzzle = commands.add_parser("puzzle", help="Standalone puzzle tools")
    actions = puzzle.add_subparsers(dest="puzzle_command", required=True)
    generate = actions.add_parser("generate", help="Generate and verify a text word search")
    generate.add_argument("--word", action="append", required=True, help="Target (repeat for each)")
    generate.add_argument("--width", type=int, required=True)
    generate.add_argument("--height", type=int, required=True)
    generate.add_argument("--seed", required=True, help="Unsigned 64-bit decimal seed")
    generate.add_argument(
        "--direction",
        action="append",
        choices=[d.name.lower().replace("_", "-") for d in Direction],
        help="Enabled direction (repeat); defaults to all eight",
    )
    generate.add_argument("--max-restarts", type=int, default=20)
    generate.add_argument("--max-attempts", type=int, default=100_000)
    generate.add_argument("--solution", action="store_true", help="Show zero-based placements")


def run_puzzle_command(args: argparse.Namespace) -> int:
    directions = (
        tuple(Direction[name.upper().replace("-", "_")] for name in args.direction)
        if args.direction
        else tuple(Direction)
    )
    puzzle = generate_word_search(
        tuple(TargetEntry(f"word-{i + 1}", word) for i, word in enumerate(args.word)),
        GenerationConfig(
            GridSize(args.width, args.height), directions, args.max_restarts, args.max_attempts
        ),
        args.seed,
    )
    verification = verify_word_search(puzzle)
    if not verification.valid:
        raise RuntimeError(f"Generated puzzle failed verification: {verification.issues!r}")
    print(f"Seed: {puzzle.seed}")
    print(f"Grid: {puzzle.config.size.width} x {puzzle.config.size.height}")
    print("\n".join(" ".join(row) for row in puzzle.grid.rows))
    print("Targets: " + "; ".join(target.display for target in puzzle.targets))
    print("Verified: all targets have valid authoritative placements")
    if args.solution:
        print("Solution (zero-based column, row):")
        for placement in puzzle.solution.placements:
            start, end = placement.start, placement.end
            direction = placement.direction.name.lower().replace("_", "-")
            print(
                f"  {placement.target_id}: {placement.search} "
                f"({start.x}, {start.y}) -> ({end.x}, {end.y}) {direction}"
            )
    return 0
