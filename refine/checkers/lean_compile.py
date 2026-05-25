"""Pass when Lean elaboration reports zero errors.

This is the most foundational stage — every other checker assumes the
file at least parses and type-checks. Sorries (severity=warning) are
intentionally ignored here; that's NoSorryChecker's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from refine.checkers.base import Checker, CheckResult

# Severity values: Lean reports severity as the int 1 OR the string
# "error" depending on the diagnostic source. Accept both.
_ERROR_VALUES: tuple[object, ...] = (1, "error")


@dataclass(frozen=True)
class LeanCompileChecker(Checker):
    name: str = "lean_compile"

    def check(
        self,
        content: str,
        diagnostics: list[dict[str, Any]],
    ) -> CheckResult:
        del content
        errors = [d for d in diagnostics if d.get("severity") in _ERROR_VALUES]
        if not errors:
            return CheckResult(passed=True)
        # Errors are surfaced by Lean directly — no pseudo-diagnostics
        # to add. Summary gives the count for the log line.
        return CheckResult(
            passed=False,
            summary=f"{len(errors)} Lean compile error(s)",
        )
