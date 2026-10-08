"""ISBN-13 format and check-digit validation. PuzzlePress never generates ISBNs.

The authored value is preserved exactly as entered; only hyphens and spaces are
ignored when checking it. A valid check digit says nothing about registration,
ownership or the registered title, author and imprint: those stay with the
author and KDP's own check against the ISBN agency.
"""

import re
from dataclasses import dataclass

_SEPARATORS = re.compile(r"[\s-]")


@dataclass(frozen=True)
class IsbnCheck:
    digits: str | None  # Thirteen digits when valid.
    problem: str | None  # Why it is not a valid ISBN-13.
    required: str | None = None  # The expected check digit, when only that is wrong.


def isbn13_check_digit(first12: str) -> str:
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(first12))
    return str((10 - total % 10) % 10)


def isbn10_valid(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{9}[0-9Xx]", value):
        return False
    total = sum((10 - i) * (10 if c in "Xx" else int(c)) for i, c in enumerate(value))
    return total % 11 == 0


def check_isbn(entered: str) -> IsbnCheck:
    compact = _SEPARATORS.sub("", entered)
    if "--" in entered or entered.strip("- ") != entered.strip():
        return IsbnCheck(None, "Hyphens may only separate digit groups.")
    if len(compact) == 10 and isbn10_valid(compact):
        return IsbnCheck(
            None,
            "This is an ISBN-10. Enter the ISBN-13 your ISBN agency issued for this book.",
        )
    if not re.fullmatch(r"[0-9]{13}", compact):
        return IsbnCheck(None, "An ISBN-13 has exactly 13 digits (hyphens and spaces allowed).")
    if compact[:3] not in ("978", "979"):
        return IsbnCheck(None, "An ISBN-13 begins with 978 or 979.")
    expected = isbn13_check_digit(compact[:12])
    if compact[12] != expected:
        return IsbnCheck(
            None, "The check digit does not match; check for a typing error.", expected
        )
    return IsbnCheck(compact, None)
