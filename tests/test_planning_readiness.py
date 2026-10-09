"""Readiness states, identity-bound approval, staleness and the production handoff."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from planning_helpers import ROOT, codes, complete_plan, document, evaluate, project, variant

from puzzlepress.planning import (
    ApprovalError,
    HandoffUnavailable,
    State,
    approve_plan,
    evaluate_plan,
    handoff_bytes,
    handoff_document,
    report_bytes,
    withdraw_approval,
)

LADDER = [
    (variant(concept__summary=None), State.DRAFT),
    (variant(questions__0__resolution=None), State.NEEDS_RESEARCH),
    (variant(themes__1__puzzles=5), State.NEEDS_CONTENT),
    (variant(vocabulary__0__entries__0={"word": "O-RING"}), State.NEEDS_CONTENT),
    (variant(structure__puzzle_type="crossword"), State.STRUCTURALLY_VALID),
    (variant(structure__print_profile=None), State.PRODUCTION_FEASIBLE),
    (complete_plan(), State.READY_FOR_APPROVAL),
]


@pytest.mark.parametrize(("data", "state"), LADDER)
def test_each_state_is_reachable_and_the_first_blocking_gate_decides(
    data: dict[str, object], state: State
) -> None:
    report = evaluate(data)
    assert report.state is state
    failing = [g.gate.value for g in report.gates if not g.passed]
    assert report.ready is (state is State.READY_FOR_APPROVAL)
    if failing:
        assert all(code for g in report.gates if not g.passed for code in g.blocking)


def test_gates_are_reported_separately_never_as_one_boolean() -> None:
    data = variant(concept__summary=None, structure__print_profile=None)
    report = evaluate(data).to_dict()
    gates = {g["gate"]: g["passed"] for g in report["gates"]}  # type: ignore[union-attr, index]
    assert gates == {
        "definition": False,
        "research": True,
        "content": True,
        "structure": True,
        "feasibility": True,
        "decisions": False,
    }
    assert report["state"] == "draft"


def approved(data: dict[str, object] | None = None) -> dict[str, object]:
    data = data or complete_plan()
    report = evaluate(data)
    doc = approve_plan(project(), document(data), report.identity)
    return {**data, "approval": doc.approval}


def test_approval_binds_to_the_reviewed_identity() -> None:
    data = complete_plan()
    report = evaluate(data)
    assert report.approval.status == "none"
    doc = approve_plan(project(), document(data), report.identity)
    assert doc.approval == report.identity
    approved_report = evaluate_plan(project(), doc)
    assert approved_report.state is State.APPROVED
    assert approved_report.identity == report.identity  # Approval is outside the identity.
    assert approved_report.approval.to_dict() == {
        "status": "current",
        "approved_identity": report.identity,
        "counts": True,
    }


def test_approval_is_never_automatic_or_for_unseen_content() -> None:
    data = complete_plan()
    with pytest.raises(ApprovalError) as caught:
        approve_plan(project(), document(data), "pp1-planning-sha256-" + "0" * 64)
    assert caught.value.code == "identity_mismatch"
    blocked = variant(structure__print_profile=None)
    with pytest.raises(ApprovalError) as caught:
        approve_plan(project(), document(blocked), evaluate(blocked).identity)
    assert caught.value.code == "not_ready"
    assert evaluate(data).document.approval is None


def test_edits_make_approval_stale_and_restoring_content_restores_it() -> None:
    data = approved()
    for change in (
        {"concept": {**data["concept"], "summary": "A different concept."}},  # type: ignore[dict-item]
        {"research": []},
        {"themes": [*data["themes"][:1], {**data["themes"][1], "label": "Workshop"}]},  # type: ignore[index]
    ):
        edited = {**data, **change}
        report = evaluate(edited)
        assert report.approval.status == "stale"
        assert report.state is not State.APPROVED
        f = next(f for f in report.findings if f.rule.code == "approval_stale")
        assert (f.actual, f.expected) == (report.identity, data["approval"])
    assert evaluate(data).state is State.APPROVED  # The original content: approved again.


def test_non_semantic_edits_keep_approval() -> None:
    data = approved()
    explicit = {**data, "constraints": {**data["constraints"], "notes": []}}  # type: ignore[dict-item]
    assert evaluate(explicit).state is State.APPROVED


def test_a_recorded_approval_on_a_blocked_plan_does_not_count() -> None:
    blocked = variant(structure__print_profile=None)
    blocked["approval"] = evaluate(blocked).identity  # Hand-edited, bypassing approve_plan.
    report = evaluate(blocked)
    assert report.state is State.PRODUCTION_FEASIBLE
    assert report.approval.status == "current" and not report.approval.counts
    assert "approval_not_ready" in codes(report)


def test_withdrawal_removes_only_the_approval() -> None:
    data = approved()
    doc = withdraw_approval(document(data))
    assert doc.approval is None and doc.content() == document(data).content()
    assert evaluate_plan(project(), doc).state is State.READY_FOR_APPROVAL


def test_planning_approval_is_not_publishing_approval() -> None:
    report = evaluate(approved()).to_dict()
    assert "not publishing approval" in str(report["boundary"])
    assert "will sell" in str(report["boundary"])


# ----------------------------------------------------------------- handoff


def test_handoff_requires_a_current_approval() -> None:
    for data in (complete_plan(), {**approved(), "concept": {"summary": "Changed"}}):
        with pytest.raises(HandoffUnavailable):
            handoff_document(evaluate(data))


def test_handoff_describes_the_approved_plan_without_inventing_content() -> None:
    data = approved()
    report = evaluate(data)
    handoff = handoff_document(report)
    assert handoff["handoff_version"] == 1
    assert handoff["book"] == {"id": "automotive-word-search", "title": "Automotive Word Search"}
    assert handoff["planning_identity"] == handoff["approved_identity"] == report.identity
    puzzles = handoff["puzzles"]
    assert isinstance(puzzles, list) and len(puzzles) == 12
    first = puzzles[0]
    assert first["order"] == 1 and first["id"] == "engines-1"
    assert first["settings"]["width"] == 10
    assert first["words"][0] == {"word": "PISTON", "search": "PISTON", "source": "human"}
    assert handoff["provenance"]["words_by_source"]["human"] == 48  # type: ignore[index]
    assert handoff["required_human_decisions"] and handoff["not_verified"]
    assert "word_search" not in json.dumps(handoff["puzzles"])  # No book.yaml fragment.


def test_handoff_bytes_are_deterministic_across_processes(tmp_path: Path) -> None:
    data = approved()
    expected = handoff_bytes(evaluate(data))
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    script = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(ROOT / 'tests')!r})\n"
        "from planning_helpers import evaluate\n"
        "from puzzlepress.planning import handoff_bytes, report_bytes\n"
        f"data = json.load(open({str(source)!r}))\n"
        "r = evaluate(data)\n"
        "sys.stdout.buffer.write(handoff_bytes(r) + report_bytes(r))\n"
    )
    outputs = set()
    for seed, cwd in (("0", ROOT), ("99", tmp_path)):
        out = subprocess.run(
            [sys.executable, "-c", script],
            cwd=cwd,
            capture_output=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        outputs.add(out.stdout)
    assert outputs == {expected + report_bytes(evaluate(data))}
    assert str(tmp_path).encode() not in expected and b"\\\\" not in expected


def test_report_contains_no_paths_or_times() -> None:
    raw = report_bytes(evaluate(complete_plan())).decode("ascii")
    assert str(ROOT) not in raw and str(ROOT).replace("\\", "/") not in raw
    data = json.loads(raw)
    assert set(data) >= {
        "planning_identity",
        "state",
        "gates",
        "approval",
        "feasibility",
        "page_estimate",
        "findings",
        "rules",
        "allocation",
        "progression",
    }
    assert "generated_at" not in raw and "timestamp" not in raw


def test_identity_changes_only_with_meaningful_content() -> None:
    base = evaluate(complete_plan()).identity
    assert evaluate(complete_plan()).identity == base
    assert evaluate(variant(themes__0__notes="A note")).identity != base
    doc = replace(document(complete_plan()), approval=base)
    assert evaluate_plan(project(), doc).identity == base
