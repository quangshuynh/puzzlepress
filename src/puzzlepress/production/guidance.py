"""The final-mile overview: every production check and human step, kept apart.

Each item states what it checks, why it matters, what kind of rule it is and
where to act. Kinds never blur:

- `internal`: a PuzzlePress contract or workflow rule (artifact currency, the
  optional rule that every puzzle is reviewed);
- `kdp_modeled`: a KDP requirement PuzzlePress models from Amazon's help pages;
  passing it is not Amazon's acceptance;
- `author_judgment`: a decision only the author can make (AI disclosure,
  rights, ISBN, classifications, content review, plan approval);
- `external`: work done outside PuzzlePress (KDP's Print Previewer, a printed
  proof) that the author records.

Statuses: completed, needs_attention, blocking, not_applicable,
awaiting_review (a person has not decided yet) and external_pending (an outside
step has not been recorded). `blocks_export` says whether an item stops the
publishing package. Nothing here selects an answer, approves anything, or
contacts Amazon; everything is recomputed from current source and artifacts.
"""

from dataclasses import dataclass
from pathlib import Path

from ..batch import generate_batch
from ..editorial import ReviewReport, evaluate_reviews, read_reviews
from ..errors import ProjectError
from ..models import Project
from ..planning import evaluate_plan, read_planning
from ..preflight.model import Outcome
from ..proofing import ProofKind, current_artifacts, evaluate_proofs, read_proofs
from ..publishing import PublishingReadinessReport, evaluate_readiness
from .artifacts import Assessment, assess


@dataclass(frozen=True)
class Item:
    code: str
    title: str
    status: str
    basis: str
    blocks_export: bool
    what: str
    why: str
    action: str | None
    area: str  # Studio section: plan, puzzles, quality, book, print, cover, publishing.
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "title": self.title,
            "status": self.status,
            "basis": self.basis,
            "blocks_export": self.blocks_export,
            "what": self.what,
            "why": self.why,
            "action": self.action,
            "area": self.area,
            "detail": self.detail,
        }


PROOFING_STEPS = (
    ("build", "Build current interior and cover PDFs", "print"),
    ("validate", "Validate the publishing package and export it", "publishing"),
    ("upload", "Upload the interior and cover to KDP yourself", "external"),
    ("previewer", "Review the book in KDP's Print Previewer", "external"),
    ("check", "Check trim, margins, bleed, text, images and the barcode area", "external"),
    ("order", "Order a printed proof copy", "external"),
    ("record", "Record what you observed in the proof", "publishing"),
    ("correct", "Correct the source files for any issue", "book"),
    ("rebuild", "Rebuild and export a new review release", "print"),
    ("approve", "Record approval only after you have reviewed the proof", "publishing"),
)


def _outcome(report: PublishingReadinessReport, code: str) -> Outcome | None:
    return next((r.outcome for r in report.results if r.rule.code == code), None)


def _messages(report: PublishingReadinessReport, *codes: str) -> str:
    return " ".join(f.message for f in report.findings if f.rule.code in codes)


def _decided(report: PublishingReadinessReport, code: str) -> str:
    outcome = _outcome(report, code)
    if outcome is Outcome.PASSED:
        return "completed"
    if outcome is Outcome.NOT_APPLICABLE:
        return "not_applicable"
    return "awaiting_review"


def _planning(project: Project, source: Path) -> Item:
    what = "Whether the saved book plan is approved for the current planning identity."
    why = "Approval records that you reviewed the plan; it is not publishing approval."
    try:
        loaded = read_planning(source)
    except ProjectError:
        return Item(
            "planning_approval",
            "Book plan approval",
            "needs_attention",
            "author_judgment",
            False,
            what,
            why,
            "Fix planning.yaml so it validates.",
            "plan",
            "planning.yaml does not validate.",
        )
    if loaded.document is None:
        return Item(
            "planning_approval",
            "Book plan approval",
            "not_applicable",
            "author_judgment",
            False,
            what,
            why,
            None,
            "plan",
            "This book has no planning.yaml.",
        )
    report = evaluate_plan(project, loaded.document)
    approval = report.to_dict()["approval"]
    assert isinstance(approval, dict)
    status = approval.get("status")
    state = {"current": "completed", "stale": "needs_attention"}.get(str(status), "awaiting_review")
    detail = {
        "current": "Approved for the current plan.",
        "stale": "The plan changed after approval; review and approve it again if intended.",
    }.get(str(status), f"Not approved (plan state: {report.state}).")
    return Item(
        "planning_approval",
        "Book plan approval",
        state,
        "author_judgment",
        False,
        what,
        why,
        None if state == "completed" else "Review the plan and approve it in Plan.",
        "plan",
        detail,
    )


def _quality(project: Project) -> Item:
    what = "Generation succeeded for every puzzle and automated quality screening found nothing."
    why = "Automated screening finds accidental or prohibited words; it is not a human review."
    if project.word_search is None:
        return Item(
            "generation_quality",
            "Puzzle generation and quality",
            "not_applicable",
            "internal",
            False,
            what,
            why,
            None,
            "quality",
            "No puzzles.",
        )
    batch = generate_batch(project)
    if not batch.success:
        status, detail = "blocking", "Some puzzles did not generate."
    elif batch.findings:
        status, detail = "needs_attention", f"{len(batch.findings)} quality finding(s) to review."
    else:
        status, detail = "completed", f"{len(batch.puzzles)} puzzles generated and screened clean."
    return Item(
        "generation_quality",
        "Puzzle generation and quality",
        status,
        "internal",
        status == "blocking",
        what,
        why,
        None if status == "completed" else "Open Quality to review the findings.",
        "quality",
        detail,
    )


def _review(report: ReviewReport) -> Item:
    s = report.summary()
    gate = bool(s["require_all"])
    done = bool(s["complete"])
    detail = (
        f"{s['reviewed']} of {s['total']} reviewed, {s['needs_changes']} need changes, "
        f"{s['not_reviewed']} not reviewed, {s['stale']} stale."
    )
    status = "completed" if done else "blocking" if gate else "awaiting_review"
    return Item(
        "human_review",
        "Human content review",
        status,
        "author_judgment",
        False,
        "Your own judgment of every puzzle's words, title and theme, bound to that content.",
        "Engine checks cannot tell whether terms are accurate or appropriate. Reviews are "
        "an internal record; KDP does not require them."
        + (" Your review policy requires every puzzle before production approval." if gate else ""),
        None if done else "Review the remaining puzzles in Puzzles.",
        "puzzles",
        detail,
    )


def _artifact_item(
    code: str, title: str, state: str, reasons: tuple[str, ...], area: str, what: str
) -> Item:
    status = {"current": "completed", "not_applicable": "not_applicable"}.get(state, "blocking")
    detail = {
        "current": "Built from the current source.",
        "missing": "Not built yet.",
        "no_config": "Not configured.",
        "stale": "Out of date: " + " ".join(reasons),
        "invalid": "The files do not verify: " + " ".join(reasons),
        "unavailable": "The build directory is unavailable.",
    }.get(state, state)
    return Item(
        code,
        title,
        status,
        "internal",
        status == "blocking",
        what,
        "Previews, preflight and the package must describe the files you upload.",
        None
        if status != "blocking"
        else f"Rebuild in {area.capitalize()} (or rebuild outdated artifacts).",
        area,
        detail.strip(),
    )


def _preflight_item(
    code: str, title: str, structural: str, kdp: str, area: str, warnings: str
) -> Item:
    if structural == "missing":
        status, detail = "blocking", "No artifact to check."
    elif structural != "valid":
        status, detail = "blocking", "Structurally invalid."
    elif kdp != "ready":
        status, detail = "blocking", "Not ready for the KDP requirements PuzzlePress models."
    elif warnings:
        status, detail = "needs_attention", warnings
    else:
        status, detail = "completed", "Valid and ready for the modeled KDP requirements."
    return Item(
        code,
        title,
        status,
        "kdp_modeled",
        status == "blocking",
        "The KDP rules PuzzlePress models, measured on the built PDF.",
        "Passing is necessary, not sufficient: Amazon reviews and decides.",
        None if status == "completed" else f"Open {area.capitalize()} to see each finding.",
        area,
        detail,
    )


def overview(project: Project, source: Path, directory: Path) -> dict[str, object]:
    """The consolidated publishing overview. Reads only; writes nothing."""
    readiness = evaluate_readiness(project, source, directory)
    verdicts = readiness.verdicts()
    assessment: Assessment = assess(project, readiness, source, directory)
    reviews = evaluate_reviews(project, read_reviews(source).document)
    artifacts = current_artifacts(directory)
    proofs = evaluate_proofs(read_proofs(source).document, artifacts)
    interior_v = verdicts["interior"]
    cover_v = verdicts["cover"]
    assert isinstance(interior_v, dict) and isinstance(cover_v, dict)
    items: list[Item] = [
        Item(
            "source_valid",
            "Source validity",
            "completed",
            "internal",
            False,
            "book.yaml validates against the PuzzlePress schema.",
            "Everything else is computed from the saved source.",
            None,
            "book",
            "The saved book.yaml is valid.",
        ),
        _planning(project, source),
        _quality(project),
        _review(reviews),
        _artifact_item(
            "interior_current",
            "Interior is current",
            assessment.state("interior").state,
            assessment.state("interior").reasons,
            "print",
            "interior.pdf was built from the current source, style, profile and toolchain.",
        ),
        _preflight_item(
            "interior_preflight",
            "Interior preflight",
            str(interior_v["structural"]),
            str(interior_v["kdp"]),
            "print",
            _messages(readiness, "interior_warnings"),
        ),
    ]
    cover_state = assessment.state("cover").state
    items.append(
        _artifact_item(
            "cover_current",
            "Cover is current",
            "missing" if cover_state == "not_applicable" else cover_state,
            assessment.state("cover").reasons,
            "cover",
            "cover.pdf matches the current cover design and the built interior's page count "
            "and paper.",
        )
    )
    items.append(
        _preflight_item(
            "cover_preflight",
            "Cover preflight",
            str(cover_v["structural"]),
            str(cover_v["kdp"]),
            "cover",
            _messages(readiness, "cover_warnings"),
        )
    )
    resolution = None
    if readiness.cover is not None:
        resolution = next(
            (
                r.outcome
                for r in readiness.cover.results
                if r.rule.code == "kdp_cover_image_resolution"
            ),
            None,
        )
    photo_status = (
        "not_applicable"
        if resolution is None
        else {
            Outcome.PASSED: "completed",
            Outcome.NOT_APPLICABLE: "not_applicable",
        }.get(resolution, "blocking")
    )
    items.append(
        Item(
            "photo_quality",
            "Photo print quality",
            photo_status,
            "kdp_modeled",
            photo_status == "blocking",
            "Every cover photograph prints at 300 DPI or more after cropping.",
            "Low-resolution photographs print soft or pixelated.",
            None if photo_status != "blocking" else "Use a larger photograph or zoom out in Cover.",
            "cover",
            {
                "completed": "Every photograph reaches 300 DPI.",
                "not_applicable": "No photograph to measure (or no built cover).",
                "blocking": "A photograph is below 300 DPI.",
            }[photo_status],
        )
    )
    metadata = str(verdicts.get("metadata"))
    items.append(
        Item(
            "metadata",
            "KDP metadata",
            "completed" if metadata == "valid" else "blocking",
            "kdp_modeled",
            metadata != "valid",
            "Title, contributors, description, keywords, categories and language follow KDP's "
            "published limits.",
            "KDP rejects or edits listings that break its metadata guidelines.",
            None if metadata == "valid" else "Complete the metadata in Publishing.",
            "publishing",
            f"Metadata: {metadata}.",
        )
    )
    disclosure = _decided(readiness, "ai_disclosure_complete")
    items.append(
        Item(
            "ai_disclosure",
            "AI disclosure",
            disclosure,
            "author_judgment",
            disclosure != "completed",
            "Your declaration of AI-generated text, images and translations.",
            "KDP asks every publisher to disclose AI-generated content. Only you can declare it.",
            None if disclosure == "completed" else "Declare it yourself in Publishing.",
            "publishing",
            "Declared."
            if disclosure == "completed"
            else "Not declared yet: nothing is selected for you.",
        )
    )
    attest = _outcome(readiness, "attestations")
    confirmations = [c.to_dict() for c in readiness.metadata.confirmations]
    stale = [c for c in confirmations if c.get("state") == "stale"]
    rights_status = (
        "completed"
        if attest is Outcome.PASSED
        else "needs_attention"
        if stale
        else "awaiting_review"
    )
    items.append(
        Item(
            "rights",
            "Rights and confirmations",
            rights_status,
            "author_judgment",
            rights_status != "completed",
            "Your confirmations that you hold the rights and that metadata and disclosure are "
            "accurate, bound to the content you reviewed.",
            "These are your attestations to KDP; PuzzlePress cannot make them.",
            None if rights_status == "completed" else "Review and confirm in Publishing.",
            "publishing",
            f"{sum(c.get('state') == 'confirmed' for c in confirmations)} of {len(confirmations)} "
            "confirmed" + (f", {len(stale)} stale" if stale else "") + ".",
        )
    )
    isbn = _decided(readiness, "isbn_decided")
    items.append(
        Item(
            "isbn",
            "ISBN",
            isbn,
            "author_judgment",
            isbn != "completed",
            "Whether you use a free KDP ISBN or your own; PuzzlePress never invents one.",
            "The ISBN identifies this edition; the imprint must match it.",
            None if isbn == "completed" else "Decide in Publishing.",
            "publishing",
            "Decided." if isbn == "completed" else "Undecided.",
        )
    )
    classified = [
        _decided(readiness, code) for code in ("low_content_decided", "audience_explicit")
    ]
    class_status = "completed" if all(s == "completed" for s in classified) else "awaiting_review"
    items.append(
        Item(
            "classification",
            "Content classifications",
            class_status,
            "author_judgment",
            class_status != "completed",
            "Low-content, explicit content and reading age, as you answer them.",
            "KDP uses these answers for eligibility and placement.",
            None if class_status == "completed" else "Answer them in Publishing.",
            "publishing",
            "Answered." if class_status == "completed" else "Some answers are undecided.",
        )
    )
    package = assessment.state("package").state
    ready = readiness.package_ready
    export_status = (
        "completed"
        if package == "current"
        else "blocking"
        if not ready or package == "damaged"
        else "needs_attention"
    )
    items.append(
        Item(
            "export",
            "Publishing package",
            export_status,
            "internal",
            False,
            "The verified folder of exactly the inspected files, metadata and checklist.",
            "Upload exactly what was verified; the package is never sent anywhere.",
            {
                "completed": None,
                "needs_attention": "Export the package in Publishing.",
                "blocking": "Resolve the blocking items first.",
            }[export_status],
            "publishing",
            {
                "current": "Exported and current.",
                "stale": "The exported package is out of date.",
                "damaged": "The exported package does not verify.",
            }.get(package, "Not exported." if ready else "Not ready to export."),
        )
    )
    for _kind, code, title, what in (
        (
            ProofKind.PRINT_PREVIEWER,
            "print_previewer",
            "KDP Print Previewer",
            "Your review of the uploaded files in Amazon's online previewer.",
        ),
        (
            ProofKind.PHYSICAL_PROOF,
            "physical_proof",
            "Physical proof",
            "Your review of a printed proof copy.",
        ),
    ):
        latest = proofs[code]
        if latest is None:
            status, detail = "external_pending", "Nothing recorded yet."
        else:
            assert isinstance(latest, dict)
            record = latest["record"]
            assert isinstance(record, dict)
            if not latest["current"]:
                status, detail = "needs_attention", "Recorded for earlier artifacts; review again."
            elif record["decision"] == "approved":
                status, detail = "completed", "Reviewed and approved by you for these artifacts."
            elif record["decision"] == "changes_needed":
                status, detail = "needs_attention", "You recorded changes needed."
            elif record["status"] == "reviewed":
                status, detail = "awaiting_review", "Reviewed; no decision recorded."
            else:
                status, detail = "external_pending", f"Proof {record['status']}."
        items.append(
            Item(
                code,
                title,
                status,
                "external",
                False,
                what,
                "Only Amazon's previewer and a printed copy show how KDP prints this book; "
                "PuzzlePress cannot certify acceptance.",
                None if status == "completed" else "Record it in Publishing after you review.",
                "publishing",
                detail,
            )
        )
    statuses = {item.code: item.status for item in items}
    built = statuses["interior_current"] == "completed" and statuses["cover_current"] == "completed"
    preflighted = statuses["interior_preflight"] in ("completed", "needs_attention") and statuses[
        "cover_preflight"
    ] in ("completed", "needs_attention")
    stages = [
        ("draft", "Draft source", True, "book.yaml is saved and valid."),
        ("built", "Built artifacts", built, "Interior and cover are built from current source."),
        (
            "internally_reviewed",
            "Internally reviewed",
            built and preflighted and statuses["human_review"] == "completed",
            "Preflight passes and every puzzle has your current review.",
        ),
        (
            "exported",
            "Exported package",
            statuses["export"] == "completed",
            "The package is current.",
        ),
        (
            "previewer_checked",
            "Print Previewer checked",
            statuses["print_previewer"] == "completed",
            "You recorded a Print Previewer review of these artifacts.",
        ),
        (
            "proof_reviewed",
            "Physical proof reviewed",
            statuses["physical_proof"] == "completed",
            "You recorded an approved printed proof of these artifacts.",
        ),
    ]
    blocking = sum(i.status == "blocking" for i in items)
    awaiting = sum(i.status in ("awaiting_review", "external_pending") for i in items)
    return {
        "statement": (
            f"{blocking} blocking item(s) and {awaiting} decision(s) or outside step(s) remain. "
            "PuzzlePress checks what it models; Amazon KDP reviews and decides."
        ),
        "items": [i.to_dict() for i in items],
        "stages": [{"code": c, "title": t, "reached": r, "detail": d} for c, t, r, d in stages]
        + [
            {
                "code": "published",
                "title": "Published",
                "reached": None,
                "detail": "PuzzlePress never publishes or contacts Amazon; it does not track "
                "publication.",
            }
        ],
        "proofing": [{"code": c, "title": t, "area": a} for c, t, a in PROOFING_STEPS],
        "assessment": assessment.to_dict(),
        "reviews": reviews.summary(),
        "proofs": proofs,
    }
