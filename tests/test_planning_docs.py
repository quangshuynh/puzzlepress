"""The planning contract in docs/book-planning.md names every rule the engine reports."""

from planning_helpers import ROOT

from puzzlepress.planning.rules import CATALOGUE, Gate


def test_every_rule_is_documented_and_editorial_rules_never_block() -> None:
    content = (ROOT / "docs" / "book-planning.md").read_text(encoding="utf-8")
    for rule in CATALOGUE:
        assert f"`{rule.code}`" in content, rule.code
        if rule.gate is Gate.EDITORIAL:
            assert rule.severity.value in ("warning", "info"), rule.code
