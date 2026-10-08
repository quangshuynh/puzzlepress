"""Immutable publishing vocabulary: rules with provenance, findings and outcomes.

Severities and rule outcomes are the preflight's: an error rule that failed or
could not be evaluated blocks; warnings and notes never block. A finding states
what was observed, where (a metadata field or an artifact), measured against
what, on whose authority, and what a person must do about it.
"""

from dataclasses import dataclass
from enum import StrEnum

from ..preflight.model import Outcome, Severity

__all__ = ["Area", "Basis", "Finding", "Outcome", "Rule", "Scope", "Severity", "Source"]


class Scope(StrEnum):
    """Which question a rule answers. Each has its own verdict."""

    METADATA = "metadata"  # Is the authored KDP metadata acceptable on its own?
    CONSISTENCY = "consistency"  # Does it agree with the book, interior and cover?
    DISCLOSURE = "disclosure"  # Has the author declared content origin?
    ATTESTATION = "attestation"  # Has the author confirmed what software cannot verify?
    INTERIOR = "interior"  # Interior preflight verdicts, consumed unchanged.
    COVER = "cover"  # Cover preflight verdicts, consumed unchanged.
    ARTIFACTS = "artifacts"  # Are the built files present, intact and current?


class Basis(StrEnum):
    """Where a rule comes from (docs/publishing.md#official-sources)."""

    KDP_REQUIREMENT = "kdp_requirement"
    KDP_RECOMMENDATION = "kdp_recommendation"
    KDP_AMBIGUOUS = "kdp_ambiguous"  # Official wording conflicts or omits a value.
    PUZZLEPRESS_RULE = "puzzlepress_rule"
    HUMAN_REVIEW = "human_review"  # Only a person can decide; software records it.


class Area(StrEnum):
    """Where in Studio (or which CLI command) the issue is fixed."""

    PUBLISHING = "publishing"
    EDIT = "edit"
    BOOK = "book"
    PRINT = "print"
    COVER = "cover"


@dataclass(frozen=True)
class Source:
    title: str
    url: str

    def to_dict(self) -> dict[str, object]:
        return {"title": self.title, "url": self.url}


@dataclass(frozen=True)
class Rule:
    code: str
    scope: Scope
    severity: Severity
    title: str
    basis: Basis
    source: Source

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "scope": self.scope.value,
            "severity": self.severity.value,
            "title": self.title,
            "basis": self.basis.value,
            "source": self.source.to_dict(),
        }


Value = int | float | str


@dataclass(frozen=True)
class Finding:
    rule: Rule
    message: str
    field: str | None = None  # Source path, e.g. publishing.keywords.2 or book.title.
    artifact: str | None = None  # interior.pdf, cover.json...
    actual: Value | None = None
    required: Value | None = None
    action: str | None = None  # What a person must do; None when nothing remains.
    area: Area = Area.PUBLISHING
    related: str | None = None  # The underlying preflight rule, when consumed.

    @property
    def severity(self) -> Severity:
        return self.rule.severity

    def sort_key(self) -> tuple[object, ...]:
        return (
            list(Severity).index(self.rule.severity),
            list(Scope).index(self.rule.scope),
            self.rule.code,
            self.field or "",
            self.artifact or "",
            self.related or "",
            self.message,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.rule.code,
            "severity": self.rule.severity.value,
            "scope": self.rule.scope.value,
            "basis": self.rule.basis.value,
            "source": self.rule.source.to_dict(),
            "message": self.message,
            "field": self.field,
            "artifact": self.artifact,
            "actual": self.actual,
            "required": self.required,
            "action": self.action,
            "area": self.area.value,
            "related": self.related,
        }


@dataclass(frozen=True)
class RuleResult:
    rule: Rule
    outcome: Outcome
    findings: int
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.rule.code,
            "scope": self.rule.scope.value,
            "severity": self.rule.severity.value,
            "title": self.rule.title,
            "basis": self.rule.basis.value,
            "source": self.rule.source.to_dict(),
            "outcome": self.outcome.value,
            "findings": self.findings,
            "note": self.note,
        }


class Collector:
    """Gathers findings and per-rule outcomes; rules not touched have passed."""

    def __init__(self, rules: dict[str, Rule]) -> None:
        self.rules = rules
        self.findings: list[Finding] = []
        self.outcomes: dict[str, tuple[Outcome, str | None]] = {}

    def fail(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        artifact: str | None = None,
        actual: Value | None = None,
        required: Value | None = None,
        action: str | None = None,
        area: Area = Area.PUBLISHING,
        related: str | None = None,
    ) -> None:
        self.findings.append(
            Finding(
                self.rules[code], message, field, artifact, actual, required, action, area, related
            )
        )

    def skip(self, code: str, reason: str) -> None:
        """Not evaluated: a prerequisite is missing. Error rules then block."""
        self.outcomes.setdefault(code, (Outcome.NOT_EVALUATED, reason))

    def not_applicable(self, code: str, reason: str) -> None:
        self.outcomes.setdefault(code, (Outcome.NOT_APPLICABLE, reason))

    def note(self, code: str, text: str) -> None:
        self.outcomes.setdefault(code, (Outcome.PASSED, text))

    def results(self, codes: list[str] | tuple[str, ...]) -> tuple[RuleResult, ...]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.rule.code] = counts.get(finding.rule.code, 0) + 1
        results: list[RuleResult] = []
        for code in codes:
            rule = self.rules[code]
            if counts.get(code):
                results.append(RuleResult(rule, Outcome.FAILED, counts[code]))
                continue
            outcome, note = self.outcomes.get(code, (Outcome.PASSED, None))
            results.append(RuleResult(rule, outcome, 0, note))
        return tuple(results)
