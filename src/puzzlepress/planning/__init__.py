"""Book research and planning: a versioned blueprint beside book.yaml (docs/book-planning.md).

Pure analysis lives in `analysis`, `feasibility` and `readiness`; `store` is the
only writer of planning.yaml. Nothing here generates puzzles, writes book.yaml
or any build directory, or contacts the network.
"""

from .handoff import HandoffUnavailable, handoff_bytes, handoff_document
from .identity import planning_identity
from .model import PLANNING_FILE, PLANNING_VERSION, PlanningDocument
from .readiness import (
    ApprovalError,
    PlanningReadinessReport,
    State,
    approve_plan,
    evaluate_plan,
    report_bytes,
    withdraw_approval,
)
from .rules import RULES, RULESET_ID, RULESET_VERSION
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
    "RULES",
    "RULESET_ID",
    "RULESET_VERSION",
    "ApprovalError",
    "HandoffUnavailable",
    "LoadedPlan",
    "PlanningDocument",
    "PlanningReadinessReport",
    "PlanningWriteError",
    "State",
    "approve_plan",
    "dump_planning",
    "evaluate_plan",
    "handoff_bytes",
    "handoff_document",
    "parse_planning",
    "planning_identity",
    "read_planning",
    "report_bytes",
    "validate_planning",
    "withdraw_approval",
    "write_planning",
]
