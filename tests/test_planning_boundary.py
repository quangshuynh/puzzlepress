"""The planning/production boundary: planning never stales or changes a built book.

A disposable, publishable book (interior, cover and package built) gets a plan,
an approval, edits and a withdrawal. Build, interior, cover, publishing and
package identities, every built byte, the readiness report and the package's
export state stay exactly as they were. Planning approval confirms nothing in
Publishing. All declarations here are synthetic test decisions.
"""

from pathlib import Path

from planning_helpers import complete_plan, document, variant

from puzzlepress import build_identity, load_project
from puzzlepress.planning import (
    State,
    approve_plan,
    evaluate_plan,
    handoff_document,
    read_planning,
    withdraw_approval,
    write_planning,
)
from puzzlepress.publishing import (
    assemble_package,
    evaluate_readiness,
    readiness_bytes,
    validate_metadata,
)
from puzzlepress.publishing.identity import publishing_identity
from puzzlepress.publishing.package import export_state, write_package
from tests.publishing_helpers import publishing_project


def snapshot(source: Path, output: Path) -> dict[str, object]:
    project = load_project(source).project
    report = evaluate_readiness(project, source, output)
    package = assemble_package(report)
    return {
        "book.yaml": (source / "book.yaml").read_bytes(),
        "build_identity": build_identity(project),
        "publishing_identity": publishing_identity(project),
        "metadata": validate_metadata(project).to_dict(),
        "readiness": readiness_bytes(report),
        "package_identity": package.identity,
        "export": export_state(output, source, project.book.id, package.identity).to_dict(),
        "output": {
            p.relative_to(output).as_posix(): p.read_bytes()
            for p in sorted(output.rglob("*"))
            if p.is_file()
        },
    }


def test_planning_edits_and_approval_never_touch_production(tmp_path: Path) -> None:
    source, output = publishing_project(tmp_path)
    project = load_project(source).project
    report = evaluate_readiness(project, source, output)
    assert report.package_ready
    write_package(assemble_package(report), output, source)
    before = snapshot(source, output)
    assert before["export"]["state"] == "current"  # type: ignore[index]

    # Add a plan, approve it, edit it (stale), restore and withdraw.
    plan = document(complete_plan())
    saved = write_planning(source, plan, None)
    planning = evaluate_plan(project, plan)
    assert planning.state is State.READY_FOR_APPROVAL
    approved = approve_plan(project, plan, planning.identity)
    saved = write_planning(source, approved, saved.revision)
    assert evaluate_plan(project, approved).state is State.APPROVED
    handoff_document(evaluate_plan(project, approved))  # Prints nothing, writes nothing.
    assert snapshot(source, output) == before
    edited = document({**variant(themes__1__puzzles=5), "approval": approved.approval})
    saved = write_planning(source, edited, saved.revision)
    assert evaluate_plan(project, edited).approval.status == "stale"
    assert snapshot(source, output) == before
    saved = write_planning(source, withdraw_approval(approved), saved.revision)
    assert read_planning(source).document == withdraw_approval(approved)
    assert snapshot(source, output) == before


def test_planning_approval_is_not_a_publishing_confirmation(tmp_path: Path) -> None:
    source, _ = publishing_project(tmp_path, attestations={"rights": False, "metadata": False})
    project = load_project(source).project
    states = {c.name: c.state for c in validate_metadata(project).confirmations}
    plan = document(complete_plan())
    identity = evaluate_plan(project, plan).identity
    write_planning(source, approve_plan(project, plan, identity), None)
    after = load_project(source).project
    assert {c.name: c.state for c in validate_metadata(after).confirmations} == states
    assert states["rights"] == "unconfirmed" and states["metadata"] == "unconfirmed"
    assert after == project  # The project model has no planning in it at all.
