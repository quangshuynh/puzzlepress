"""Book research and planning: a versioned blueprint beside book.yaml (docs/book-planning.md).

`store` is the only writer of planning.yaml. Nothing here generates puzzles,
writes book.yaml or any build directory, or contacts the network.
"""

from .identity import planning_identity
from .model import PLANNING_FILE, PLANNING_VERSION, PlanningDocument
from .schema import validate_planning
from .store import (
    LoadedPlan,
    PlanningWriteError,
    dump_planning,
    parse_planning,
    read_planning,
    write_planning,
)

__all__ = [
    "PLANNING_FILE",
    "PLANNING_VERSION",
    "LoadedPlan",
    "PlanningDocument",
    "PlanningWriteError",
    "dump_planning",
    "parse_planning",
    "planning_identity",
    "read_planning",
    "validate_planning",
    "write_planning",
]
