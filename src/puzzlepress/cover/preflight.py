"""Cover preflight: structural validity and modeled KDP readiness of cover.pdf.

Observational, like interior preflight: it reads cover.pdf, cover.json, the
interior beside them and the pinned photograph, renders the expected cover in
memory with the same pure pipeline as `cover build`, and compares. It never
writes, repairs, re-crops or re-renders anything on disk. Rule vocabulary is the
interior preflight's (scopes, severities, outcomes, basis); verdicts are separate.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..interior.inspection import same_box
from ..interior.issues import LayoutIssue
from ..interior.model import Box
from ..interior.spec import KDP, KDP_COVER, to_inches
from ..models import Project
from ..preflight.model import (
    Basis,
    Category,
    Finding,
    Measure,
    Outcome,
    RuleResult,
    Scope,
    Severity,
)
from ..preflight.model import Rule as PreflightRule
from .assets import decode_photo, read_asset
from .build import (
    IDENTITY_INPUTS,
    MANIFEST_NAME,
    MANIFEST_VERSION,
    PDF_NAME,
    CoverBuild,
    InteriorFacts,
    cover_identity,
    read_interior_facts,
    render_cover,
)
from .font_assets import NO_FONTS, CoverFonts, load_cover_fonts
from .inspection import STROKE_OPERATORS, CoverPdfFacts, cover_contract_issues, read_cover_facts
from .issues import CoverError
from .model import CoverLayout
from .validation import validate_cover_layout

REPORT_VERSION = 1
RULESET_ID = "puzzlepress-kdp-cover"
RULESET_VERSION = 2
KDP_RULES_CHECKED = "2026-10-07"
COVER_HELP = "KDP help: Create a Paperback Cover"
BARCODE_HELP = "KDP help: Low-Content Book Barcode Details"
SUBMISSION = "KDP help: Paperback Submission Guidelines"
CONTRACT = "PuzzlePress cover contract (docs/cover.md)"
FORMATTING_HELP = "KDP help: Fix Paperback and Hardcover Formatting Issues"
MANIFEST_FIELDS: dict[str, type] = {
    "manifest_version": int,
    "book_id": str,
    "cover_identity": str,
    "cover": dict,
    "copy": dict,
    "interior": dict,
    "cover_profile": dict,
    "toolchain": dict,
    "provenance": dict,
    "pdf": dict,
}
# Rules whose failure means the cover predates its current inputs.
STALE_RULES = ("cover_current", "interior_current")


@dataclass(frozen=True)
class CoverArtifacts:
    pdf: bytes | None
    manifest: bytes | None
    problems: tuple[LayoutIssue, ...] = ()


def read_cover_artifacts(directory: Path) -> CoverArtifacts:
    """Read only cover.pdf and cover.json; symlinks and non-files are reported."""
    problems: list[LayoutIssue] = []

    def read(name: str) -> bytes | None:
        path = directory / name
        try:
            if path.is_symlink() or (path.exists() and not path.is_file()):
                problems.append(
                    LayoutIssue("artifact_unsafe", f"{name} is not a file.", region=name)
                )
                return None
            if not path.exists():
                problems.append(LayoutIssue("artifact_missing", f"{name} is missing.", region=name))
                return None
            return path.read_bytes()
        except OSError as error:
            problems.append(LayoutIssue("artifact_unreadable", f"Cannot read {name}: {error}"))
            return None

    return CoverArtifacts(read(PDF_NAME), read(MANIFEST_NAME), tuple(problems))


def parse_cover_manifest(data: bytes) -> tuple[dict[str, object] | None, str | None]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        return None, f"cover.json is not valid JSON: {error}"
    if not isinstance(value, dict) or value.get("manifest_version") != MANIFEST_VERSION:
        return None, "cover.json is not a supported cover manifest."
    for key, kind in MANIFEST_FIELDS.items():
        if not isinstance(value.get(key), kind) or isinstance(value.get(key), bool):
            return None, f"cover.json field {key!r} is missing or malformed."
    pdf = value["pdf"]
    if not isinstance(pdf.get("sha256"), str) or not isinstance(pdf.get("bytes"), int):
        return None, "cover.json field 'pdf' lacks sha256 or bytes."
    return value, None


@dataclass(frozen=True)
class CoverContext:
    project: Project
    artifacts: CoverArtifacts
    manifest: dict[str, object] | None
    manifest_problem: str | None
    interior: InteriorFacts | None
    interior_error: CoverError | None
    photo_error: CoverError | None
    font_error: CoverError | None
    fonts: CoverFonts
    expected: CoverBuild | None
    expected_error: CoverError | None
    facts: CoverPdfFacts | None
    facts_problem: LayoutIssue | None

    @property
    def matches(self) -> bool:
        return (
            self.expected is not None
            and self.artifacts.pdf is not None
            and self.artifacts.pdf == self.expected.pdf
        )

    @property
    def layout(self) -> CoverLayout | None:
        return self.expected.layout if self.expected and self.matches else None


@dataclass(frozen=True)
class Check:
    findings: tuple[Finding, ...] = ()
    outcome: Outcome | None = None
    note: str | None = None
    measure: Measure | None = None


def _skip(reason: str) -> Check:
    return Check(outcome=Outcome.NOT_EVALUATED, note=reason)


def _na(reason: str) -> Check:
    return Check(outcome=Outcome.NOT_APPLICABLE, note=reason)


Evaluator = Callable[[PreflightRule, CoverContext], Check]
CATALOGUE: list[tuple[PreflightRule, Evaluator]] = []
NO_LAYOUT = "cover.pdf is not the rendering of the current cover layout."
NO_PDF = "cover.pdf is unavailable or unreadable."


def rule(
    code: str,
    scope: Scope,
    category: Category,
    title: str,
    description: str,
    source: str,
    basis: Basis | None = None,
    severity: Severity = Severity.ERROR,
) -> Callable[[Evaluator], Evaluator]:
    if basis is None:
        basis = Basis.PUZZLEPRESS_CONTRACT if scope is Scope.STRUCTURAL else Basis.KDP_REQUIREMENT
    definition = PreflightRule(code, scope, category, severity, title, description, basis, source)

    def register(evaluate: Evaluator) -> Evaluator:
        CATALOGUE.append((definition, evaluate))
        return evaluate

    return register


def _finding(
    r: PreflightRule,
    message: str,
    *,
    region: str | None = None,
    measure: Measure | None = None,
    issue: LayoutIssue | None = None,
) -> Finding:
    if issue is not None:
        region = region or issue.region
        if measure is None and issue.actual is not None:
            measure = Measure(issue.actual, issue.required)
    return Finding(r, message, None, None, region, None, measure)


def _issues(r: PreflightRule, issues: list[LayoutIssue] | tuple[LayoutIssue, ...]) -> Check:
    return Check(tuple(_finding(r, f"[{i.code}] {i.message}", issue=i) for i in issues))


# ---------------------------------------------------------------- structural


@rule(
    "cover_configured",
    Scope.STRUCTURAL,
    Category.ARTIFACT,
    "Cover configured",
    "The project has a valid cover section.",
    CONTRACT,
)
def _configured(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.project.cover is None:
        return Check((_finding(r, "[cover_missing] The project has no cover section."),))
    return Check(note=f"Cover version {ctx.project.cover.version}, {ctx.project.cover.layout}.")


@rule(
    "cover_artifacts",
    Scope.STRUCTURAL,
    Category.ARTIFACT,
    "Cover files present",
    "cover.pdf and cover.json exist as regular files beside the interior.",
    CONTRACT,
)
def _artifacts(r: PreflightRule, ctx: CoverContext) -> Check:
    return Check(
        tuple(_finding(r, p.message, region=p.region) for p in ctx.artifacts.problems),
        note="Both cover artifacts are present.",
    )


@rule(
    "cover_manifest",
    Scope.STRUCTURAL,
    Category.INTEGRITY,
    "Cover manifest describes this PDF",
    "cover.json is a supported manifest naming this book, its identity recomputes from "
    "its recorded inputs, and cover.pdf's SHA-256 and size equal its record.",
    CONTRACT,
)
def _manifest(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.artifacts.manifest is None:
        return _skip("cover.json is unavailable.")
    if ctx.manifest is None:
        return Check((_finding(r, ctx.manifest_problem or "Unreadable.", region="cover.json"),))
    m = ctx.manifest
    findings: list[Finding] = []
    if m["book_id"] != ctx.project.book.id:
        findings.append(_finding(r, "The cover belongs to another book.", region="book_id"))
    if any(key not in m for key in IDENTITY_INPUTS) or cover_identity(m) != m["cover_identity"]:
        findings.append(
            _finding(r, "cover.json's identity does not recompute.", region="cover_identity")
        )
    pdf = ctx.artifacts.pdf
    recorded = m["pdf"]
    assert isinstance(recorded, dict)
    if pdf is not None and (
        recorded["sha256"] != hashlib.sha256(pdf).hexdigest() or recorded["bytes"] != len(pdf)
    ):
        findings.append(
            _finding(r, "cover.pdf is not the file this manifest describes.", region="pdf.sha256")
        )
    return Check(tuple(findings), note="Manifest, identity and PDF digest agree.")


@rule(
    "interior_current",
    Scope.STRUCTURAL,
    Category.INTEGRITY,
    "Interior current",
    "interior.pdf and interior.json exist, agree, and were built from the current "
    "source, print profile and toolchain; the page count is read from the PDF.",
    CONTRACT,
)
def _interior(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.interior_error is not None:
        return _issues(r, ctx.interior_error.issues)
    assert ctx.interior is not None
    i = ctx.interior
    return Check(note=f"{i.page_count} pages, {i.profile['profile_id']}, {i.paper.value} paper.")


@rule(
    "cover_photo",
    Scope.STRUCTURAL,
    Category.CONTENT,
    "Photograph available",
    "The configured photograph is in cover-assets, matches its pinned SHA-256 and decodes.",
    CONTRACT,
)
def _photo(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.project.cover is None:
        return _skip("No cover section.")
    if ctx.photo_error is not None:
        return _issues(r, ctx.photo_error.issues)
    return Check(note=f"{ctx.project.cover.image.path} matches its digest.")


@rule(
    "cover_fonts",
    Scope.STRUCTURAL,
    Category.FONT,
    "Imported fonts available",
    "Every imported font is in cover-assets/fonts, matches its pinned SHA-256, is a "
    "static TrueType-outline font and permits embedding and subsetting.",
    CONTRACT,
)
def _fonts(r: PreflightRule, ctx: CoverContext) -> Check:
    cover = ctx.project.cover
    if cover is None:
        return _skip("No cover section.")
    if not cover.fonts:
        return _na("The cover uses bundled fonts only.")
    if ctx.font_error is not None:
        return _issues(r, ctx.font_error.issues)
    names = ", ".join(
        f"{font_id} ({loaded.info.full_name}, {loaded.info.embedding.replace('_', ' ')})"
        for font_id, loaded in ctx.fonts.by_id.items()
    )
    return Check(note=f"Loaded: {names}.")


@rule(
    "cover_font_license",
    Scope.KDP,
    Category.FONT,
    "Imported font license recorded",
    "Each imported font records its license and source. KDP asks for fully embedded "
    "fonts and notes that some fonts do not allow commercial use; PuzzlePress reads "
    "the font's embedding flags but cannot confirm your license.",
    FORMATTING_HELP,
    Basis.KDP_AMBIGUOUS,
    Severity.WARNING,
)
def _font_license(r: PreflightRule, ctx: CoverContext) -> Check:
    cover = ctx.project.cover
    if cover is None:
        return _skip("No cover section.")
    if not cover.fonts:
        return _na("The cover uses bundled fonts (SIL OFL 1.1 and the Bitstream Vera license).")
    findings = [
        _finding(
            r,
            f"Font {font.id!r} has no recorded "
            f"{' or '.join(k for k in ('license', 'source') if getattr(font, k) is None)}. "
            "Record where it came from and the license that permits commercial print use.",
            region=f"cover.fonts.{font.id}",
        )
        for font in cover.fonts
        if font.license is None or font.source is None
    ]
    return Check(tuple(findings), note="Every imported font records its license and source.")


@rule(
    "cover_buildable",
    Scope.STRUCTURAL,
    Category.INTEGRITY,
    "Cover lays out",
    "The current cover configuration lays out, validates and renders.",
    CONTRACT,
)
def _buildable(r: PreflightRule, ctx: CoverContext) -> Check:
    if (
        ctx.project.cover is None
        or ctx.interior is None
        or ctx.photo_error is not None
        or ctx.font_error is not None
    ):
        return _skip("The interior, photograph or an imported font is unavailable.")
    if ctx.expected_error is not None:
        return _issues(r, ctx.expected_error.issues)
    return Check(note="Current inputs render a verified cover.")


def stale_reasons(recorded: dict[str, object], expected: dict[str, object]) -> list[str]:
    """Which cover inputs changed, in words, for a stale cover."""
    reasons: list[str] = []
    old_interior, new_interior = recorded.get("interior"), expected.get("interior")
    if isinstance(old_interior, dict) and isinstance(new_interior, dict):
        for key, label in (
            ("page_count", "interior page count"),
            ("paper", "paper"),
            ("profile_id", "print profile"),
            ("profile_version", "print profile version"),
            ("trim_in", "trim size"),
            ("ink", "ink"),
        ):
            if old_interior.get(key) != new_interior.get(key):
                reasons.append(
                    f"{label} changed ({old_interior.get(key)} -> {new_interior.get(key)})"
                )
    old_cover, new_cover = recorded.get("cover"), expected.get("cover")
    if isinstance(old_cover, dict) and isinstance(new_cover, dict):
        if old_cover.get("image") != new_cover.get("image"):
            reasons.append("photograph changed")
        if old_cover.get("crop") != new_cover.get("crop"):
            reasons.append("crop changed")
        if {k: v for k, v in old_cover.items() if k not in ("image", "crop")} != {
            k: v for k, v in new_cover.items() if k not in ("image", "crop")
        }:
            reasons.append("cover design changed")
    for key, label in (
        ("copy", "cover text changed"),
        ("cover_profile", "cover geometry rules changed"),
        ("toolchain", "renderer, libraries or fonts changed"),
        ("book_id", "book ID changed"),
    ):
        if recorded.get(key) != expected.get(key):
            reasons.append(label)
    return reasons or ["cover inputs changed"]


@rule(
    "cover_current",
    Scope.STRUCTURAL,
    Category.INTEGRITY,
    "Cover current",
    "The recorded cover identity equals the identity of the current configuration, "
    "photograph, cover text, interior physical facts, cover rules and toolchain.",
    CONTRACT,
)
def _current(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.manifest is None:
        return _skip("No readable cover manifest.")
    if ctx.expected is None:
        return _skip("The expected cover cannot be built from current inputs.")
    recorded = ctx.manifest["cover_identity"]
    expected = ctx.expected.manifest["cover_identity"]
    if recorded != expected:
        reasons = stale_reasons(ctx.manifest, ctx.expected.manifest)
        return Check(
            (
                _finding(
                    r,
                    "[cover_stale] The cover is out of date: " + "; ".join(reasons) + ".",
                    region="cover_identity",
                    measure=Measure(str(recorded), str(expected), comparison="equal"),
                ),
            )
        )
    return Check(note="The cover reflects its current inputs.")


@rule(
    "cover_interior_provenance",
    Scope.STRUCTURAL,
    Category.INTEGRITY,
    "Built against this interior",
    "Warns when the interior was rebuilt after the cover with the same physical facts: "
    "the cover still fits, but its provenance names the earlier interior.",
    CONTRACT,
    severity=Severity.WARNING,
)
def _provenance(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.manifest is None or ctx.interior is None:
        return _skip("No readable cover manifest or current interior.")
    provenance = ctx.manifest["provenance"]
    assert isinstance(provenance, dict)
    if provenance.get("interior_identity") != ctx.interior.interior_identity:
        return Check(
            (
                _finding(
                    r,
                    "The interior was rebuilt after this cover. Rebuild the cover to record "
                    "the current interior.",
                    region="provenance.interior_identity",
                ),
            )
        )
    return Check(note="Recorded against the current interior.")


@rule(
    "cover_matches_render",
    Scope.STRUCTURAL,
    Category.INTEGRITY,
    "PDF matches a fresh render",
    "cover.pdf's bytes equal a fresh deterministic render of the current layout.",
    CONTRACT,
)
def _matches(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.artifacts.pdf is None:
        return _skip("cover.pdf is unavailable.")
    if ctx.expected is None:
        return _skip("The expected cover cannot be built from current inputs.")
    if not ctx.matches:
        return Check((_finding(r, "cover.pdf differs from a fresh render of the current layout."),))
    return Check(note="Byte-identical to a fresh render.")


@rule(
    "cover_pdf_structure",
    Scope.STRUCTURAL,
    Category.ARTIFACT,
    "Cover PDF structure",
    "One unrotated page with MediaBox and BleedBox equal to the wrap and TrimBox to the "
    "trim; bundled fonts; one metadata-free DeviceRGB JPEG; no strokes or metadata.",
    CONTRACT,
)
def _structure(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.facts_problem is not None:
        return Check((_finding(r, ctx.facts_problem.message, region="cover.pdf"),))
    if ctx.facts is None:
        return _skip(NO_PDF)
    if ctx.layout is None or ctx.expected is None:
        return _skip(NO_LAYOUT)
    return _issues(r, cover_contract_issues(ctx.facts, ctx.layout, ctx.expected.image_size))


# ---------------------------------------------------------------- KDP


@rule(
    "kdp_cover_page_count",
    Scope.KDP,
    Category.CONTENT,
    "Paperback page count",
    f"The interior has at least {KDP.min_pages} pages, KDP's paperback minimum.",
    SUBMISSION,
)
def _page_count(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.interior is None:
        return _skip("No current interior.")
    pages = ctx.interior.page_count
    measure = Measure(pages, KDP.min_pages, "pages", "at_least")
    if pages < KDP.min_pages:
        return Check(
            (
                _finding(
                    r,
                    f"The interior has {pages} pages; KDP requires {KDP.min_pages}.",
                    measure=measure,
                ),
            ),
            measure=measure,
        )
    return Check(note=f"{pages} pages.", measure=measure)


@rule(
    "kdp_cover_dimensions",
    Scope.KDP,
    Category.GEOMETRY,
    "Full-wrap size",
    "Page size equals bleed + back + spine + front + bleed by bleed + trim + bleed, with "
    "spine = page count x paper thickness, from the current interior.",
    COVER_HELP,
)
def _dimensions(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.facts is None or ctx.interior is None:
        return _skip("The cover PDF or current interior is unavailable.")
    i = ctx.interior
    bleed = KDP_COVER.bleed
    width = 2 * bleed + 2 * i.trim_width + KDP_COVER.spine_width(i.page_count, i.paper)
    height = 2 * bleed + i.trim_height
    expected = Box(0, 0, width, height)
    media = ctx.facts.base.pages[0].media if ctx.facts.base.pages else None
    measure = Measure(
        f"{to_inches(media[2] - media[0]):.4f}x{to_inches(media[3] - media[1]):.4f}"
        if media
        else "?",
        f"{to_inches(width):.4f}x{to_inches(height):.4f}",
        "in",
        "equal",
    )
    if not same_box(media, expected):
        return Check(
            (_finding(r, "[invalid_wrap_dimensions] The wrap size is wrong.", measure=measure),),
            measure=measure,
        )
    return Check(note=f"{measure.actual} in.", measure=measure)


def _layout_rule(codes: tuple[str, ...]) -> Evaluator:
    def evaluate(r: PreflightRule, ctx: CoverContext) -> Check:
        layout = ctx.layout
        if layout is None or ctx.interior is None:
            return _skip(NO_LAYOUT)
        issues = [
            issue
            for issue in validate_cover_layout(
                layout, ctx.interior.trim_width, ctx.interior.trim_height
            )
            if issue.code in codes
        ]
        return _issues(r, issues)

    return evaluate


rule(
    "kdp_cover_bleed",
    Scope.KDP,
    Category.GEOMETRY,
    "Bleed",
    f"Background and photograph extend {to_inches(KDP_COVER.bleed):g} in beyond the trim "
    "on every outer edge.",
    COVER_HELP,
)(_layout_rule(("insufficient_bleed", "invalid_wrap_dimensions", "photo_placement")))


@rule(
    "kdp_cover_image_resolution",
    Scope.KDP,
    Category.CONTENT,
    "Photo resolution",
    f"Effective resolution after cropping and scaling is at least {KDP_COVER.min_image_dpi:g} DPI.",
    COVER_HELP,
)
def _resolution(r: PreflightRule, ctx: CoverContext) -> Check:
    layout = ctx.layout
    if layout is None:
        return _skip(NO_LAYOUT)
    res = layout.resolution
    measure = Measure(round(res.effective_dpi, 1), res.minimum_dpi, "dpi", "at_least")
    if res.status == "image_too_small":
        message = (
            f"[image_too_small] The photograph reaches at most {res.max_dpi:.0f} DPI here "
            "even without zoom; use a larger photograph."
        )
    elif res.status == "image_low_effective_dpi":
        message = (
            f"[image_low_effective_dpi] The crop prints at {res.effective_dpi:.0f} DPI; "
            f"zoom out (up to {res.max_dpi:.0f} DPI is available)."
        )
    else:
        return Check(note=f"{res.effective_dpi:.0f} DPI.", measure=measure)
    return Check((_finding(r, message, region="cover.crop", measure=measure),), measure=measure)


rule(
    "kdp_cover_text_safe_area",
    Scope.KDP,
    Category.GEOMETRY,
    "Front and back text safe area",
    f"Front and back text is at least {to_inches(KDP_COVER.text_safe_inset):g} in inside "
    "the trim and fold lines.",
    COVER_HELP,
)(_layout_rule(("unsafe_front_text", "unsafe_back_text")))

rule(
    "kdp_spine_text",
    Scope.KDP,
    Category.GEOMETRY,
    "Spine text",
    f"Spine text appears only from {KDP_COVER.spine_text_min_pages} pages and keeps "
    f"{to_inches(KDP_COVER.spine_text_clearance):g} in from each fold.",
    COVER_HELP,
    Basis.KDP_AMBIGUOUS,
)(_layout_rule(("spine_text_not_allowed", "unsafe_spine_text")))

rule(
    "kdp_barcode_area",
    Scope.KDP,
    Category.GEOMETRY,
    "Barcode area clear",
    "No text in the lower-right corner of the back cover where KDP prints a "
    "2 x 1.2 in barcode (offsets are a PuzzlePress assumption).",
    BARCODE_HELP,
    Basis.KDP_AMBIGUOUS,
)(_layout_rule(("barcode_region_conflict",)))

rule(
    "kdp_cover_font_size",
    Scope.KDP,
    Category.TYPOGRAPHY,
    "Minimum type size",
    f"All cover text is at least {KDP_COVER.min_font_size:g} pt.",
    COVER_HELP,
)(_layout_rule(("font_too_small",)))


def _facts_rule(test: Callable[[CoverPdfFacts], list[str]], passed: str) -> Evaluator:
    def evaluate(r: PreflightRule, ctx: CoverContext) -> Check:
        if ctx.facts is None:
            return _skip(NO_PDF)
        return Check(tuple(_finding(r, m) for m in test(ctx.facts)), note=passed)

    return evaluate


rule(
    "kdp_cover_fonts_embedded",
    Scope.KDP,
    Category.FONT,
    "Fonts embedded",
    "Every font program is embedded.",
    COVER_HELP,
)(
    _facts_rule(
        lambda f: [
            f"[font_not_embedded] {font.name} is not embedded."
            for page in f.base.pages
            for font in page.fonts
            if not font.embedded
        ],
        "All fonts embedded.",
    )
)
rule(
    "kdp_cover_flattened",
    Scope.KDP,
    Category.CONTENT,
    "Flattened",
    "No transparency or layers.",
    COVER_HELP,
)(
    _facts_rule(
        lambda f: (
            (["The cover uses transparency."] if any(p.transparency for p in f.base.pages) else [])
            + (["The cover has layers."] if f.base.optional_content else [])
        ),
        "No transparency or layers.",
    )
)
rule(
    "kdp_cover_no_marks",
    Scope.KDP,
    Category.CONTENT,
    "No marks or interactive features",
    "No crop marks or other stroked guides, annotations, forms, actions or bookmarks.",
    COVER_HELP,
)(
    _facts_rule(
        lambda f: (
            (
                ["[unexpected_pdf_feature] The cover strokes paths (guides or marks)."]
                if f.operators & STROKE_OPERATORS
                else []
            )
            + [
                f"[unexpected_pdf_feature] Page {p.number} has annotations."
                for p in f.base.pages
                if p.annotations
            ]
            + [f"[unexpected_pdf_feature] Catalog entry {k}." for k in f.base.interactive]
            + (["[unexpected_pdf_feature] The cover has bookmarks."] if f.base.outline else [])
        ),
        "No marks, annotations, forms or bookmarks.",
    )
)
rule(
    "kdp_cover_not_encrypted",
    Scope.KDP,
    Category.ARTIFACT,
    "Not encrypted",
    "The cover is not locked or encrypted.",
    SUBMISSION,
)(_facts_rule(lambda f: ["The cover is encrypted."] if f.base.encrypted else [], "Unlocked."))


@rule(
    "kdp_cover_file_size",
    Scope.KDP,
    Category.ARTIFACT,
    "File size limit",
    f"cover.pdf is at most {KDP_COVER.max_file_bytes // 1_000_000} MB.",
    COVER_HELP,
)
def _file_size(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.artifacts.pdf is None:
        return _skip(NO_PDF)
    size = len(ctx.artifacts.pdf)
    measure = Measure(size, KDP_COVER.max_file_bytes, "bytes", "at_most")
    if size > KDP_COVER.max_file_bytes:
        return Check(
            (_finding(r, "cover.pdf exceeds KDP's limit.", measure=measure),), measure=measure
        )
    return Check(note=f"{size / 1_000_000:.1f} MB.", measure=measure)


@rule(
    "kdp_cover_file_size_recommended",
    Scope.KDP,
    Category.ARTIFACT,
    "Recommended file size",
    f"KDP recommends cover files of {KDP_COVER.recommended_file_bytes // 1_000_000} MB or less.",
    COVER_HELP,
    severity=Severity.WARNING,
)
def _recommended(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.artifacts.pdf is None:
        return _skip(NO_PDF)
    size = len(ctx.artifacts.pdf)
    measure = Measure(size, KDP_COVER.recommended_file_bytes, "bytes", "at_most")
    if size > KDP_COVER.recommended_file_bytes:
        return Check(
            (_finding(r, "cover.pdf is larger than KDP recommends.", measure=measure),),
            measure=measure,
        )
    return Check(note=f"{size / 1_000_000:.1f} MB.", measure=measure)


@rule(
    "kdp_cover_color_space",
    Scope.KDP,
    Category.CONTENT,
    "Color space",
    "KDP says cover images 'should be in CMYK'. PuzzlePress writes sRGB-normalized "
    "DeviceRGB and does not convert to CMYK; printed color may shift.",
    COVER_HELP,
    Basis.KDP_AMBIGUOUS,
    Severity.WARNING,
)
def _color(r: PreflightRule, ctx: CoverContext) -> Check:
    if ctx.facts is None:
        return _skip(NO_PDF)
    if any(image.color_space == "/DeviceRGB" for image in ctx.facts.images):
        return Check(
            (
                _finding(
                    r,
                    "The photograph is RGB; KDP recommends CMYK and converts RGB itself. "
                    "Review color in a printed proof.",
                    region="cover.photo",
                ),
            )
        )
    return Check(note="No RGB images.")


# ---------------------------------------------------------------- engine


@dataclass(frozen=True)
class CoverPreflightReport:
    book_id: str
    state: str  # no_config, missing, current, stale or invalid.
    context: CoverContext
    results: tuple[RuleResult, ...]
    findings: tuple[Finding, ...]

    def _blocking(self, scope: Scope) -> bool:
        return any(
            r.rule.scope is scope
            and r.rule.severity is Severity.ERROR
            and r.outcome in (Outcome.FAILED, Outcome.NOT_EVALUATED)
            for r in self.results
        )

    @property
    def structurally_valid(self) -> bool:
        return not self._blocking(Scope.STRUCTURAL)

    @property
    def kdp_ready(self) -> bool:
        return self.structurally_valid and not self._blocking(Scope.KDP)

    def to_dict(self) -> dict[str, object]:
        ctx = self.context
        counts: dict[str, dict[str, int]] = {
            "severity": {s.value: 0 for s in Severity},
            "scope": {s.value: 0 for s in Scope},
            "outcome": {o.value: 0 for o in Outcome},
        }
        for finding in self.findings:
            counts["severity"][finding.rule.severity.value] += 1
            counts["scope"][finding.rule.scope.value] += 1
        for result in self.results:
            counts["outcome"][result.outcome.value] += 1
        pdf, manifest = ctx.artifacts.pdf, ctx.artifacts.manifest
        expected = ctx.expected
        layout = expected.layout if expected else None
        return {
            "report_version": REPORT_VERSION,
            "ruleset": {
                "id": RULESET_ID,
                "version": RULESET_VERSION,
                "kdp_rules_checked": KDP_RULES_CHECKED,
            },
            "book_id": self.book_id,
            "state": self.state,
            "cover_identity": {
                "recorded": ctx.manifest["cover_identity"] if ctx.manifest else None,
                "expected": expected.manifest["cover_identity"] if expected else None,
            },
            "interior": None
            if ctx.interior is None
            else {
                "interior_identity": ctx.interior.interior_identity,
                "pdf_sha256": ctx.interior.pdf_sha256,
                **ctx.interior.physical(),
            },
            "geometry": layout.geometry.to_dict() if layout else None,
            "resolution": layout.resolution.to_dict() if layout else None,
            "spine_text": layout.spine.to_dict() if layout else None,
            "artifacts": {
                "pdf": None
                if pdf is None
                else {"sha256": hashlib.sha256(pdf).hexdigest(), "bytes": len(pdf)},
                "manifest": None
                if manifest is None
                else {"sha256": hashlib.sha256(manifest).hexdigest(), "bytes": len(manifest)},
                "matches_render": ctx.matches,
            },
            "structural": {"status": "valid" if self.structurally_valid else "invalid"},
            "kdp": {"status": "ready" if self.kdp_ready else "not_ready"},
            "counts": counts,
            "findings": [f.to_dict() for f in self.findings],
            "rules": [
                r.to_dict() | {"help": "docs/cover.md#cover-preflight"} for r in self.results
            ],
        }


def report_bytes(report: CoverPreflightReport) -> bytes:
    text = json.dumps(report.to_dict(), sort_keys=True, indent=2, ensure_ascii=True)
    return (text + "\n").encode("ascii")


def preflight_cover(
    project: Project,
    project_directory: Path,
    directory: Path,
    expected: CoverBuild | None = None,
) -> CoverPreflightReport:
    """Inspect the cover in `directory` (already boundary-checked). Writes nothing.

    `expected` may reuse a cover just rendered from these exact inputs.
    """
    artifacts = read_cover_artifacts(directory)
    manifest, problem = (
        parse_cover_manifest(artifacts.manifest) if artifacts.manifest is not None else (None, None)
    )
    interior: InteriorFacts | None = None
    interior_error = photo_error = font_error = expected_error = None
    fonts = NO_FONTS
    try:
        interior = read_interior_facts(directory, project)
    except CoverError as error:
        interior_error = error
    if project.cover is not None:
        try:
            fonts = load_cover_fonts(project_directory, project.cover)
        except CoverError as error:
            font_error = error
        try:
            photo = decode_photo(read_asset(project_directory, project.cover.image))
        except CoverError as error:
            photo_error = error
        else:
            if interior is not None and expected is None and font_error is None:
                try:
                    expected = render_cover(project, interior, photo, fonts=fonts)
                except CoverError as error:
                    expected_error = error
    if (
        interior is None
        or photo_error is not None
        or font_error is not None
        or project.cover is None
    ):
        expected = None
    facts_or_issue = read_cover_facts(artifacts.pdf) if artifacts.pdf is not None else None
    ctx = CoverContext(
        project,
        artifacts,
        manifest,
        problem,
        interior,
        interior_error,
        photo_error,
        font_error,
        fonts,
        expected,
        expected_error,
        None if isinstance(facts_or_issue, LayoutIssue) else facts_or_issue,
        facts_or_issue if isinstance(facts_or_issue, LayoutIssue) else None,
    )
    results: list[RuleResult] = []
    findings: list[Finding] = []
    for definition, evaluate in CATALOGUE:
        check = evaluate(definition, ctx)
        outcome = check.outcome or (Outcome.FAILED if check.findings else Outcome.PASSED)
        results.append(
            RuleResult(
                definition,
                outcome,
                len(check.findings),
                None if outcome is Outcome.FAILED else check.note,
                check.measure,
            )
        )
        findings.extend(check.findings)
    failed = {r.rule.code for r in results if r.outcome is Outcome.FAILED}
    if project.cover is None:
        state = "no_config"
    elif artifacts.pdf is None and artifacts.manifest is None:
        state = "missing"
    elif failed & set(STALE_RULES):
        state = "stale"
    else:
        state = (
            "current"
            if not any(
                r.rule.scope is Scope.STRUCTURAL
                and r.rule.severity is Severity.ERROR
                and r.outcome in (Outcome.FAILED, Outcome.NOT_EVALUATED)
                for r in results
            )
            else "invalid"
        )
    return CoverPreflightReport(
        project.book.id,
        state,
        ctx,
        tuple(results),
        tuple(sorted(findings, key=Finding.sort_key)),
    )
