"""Pass when no `sorry` warnings remain in Lean's diagnostics.

Lean reports `sorry` as a warning with message text like
"declaration uses `sorry`". This checker scans warnings (severity=2)
for that pattern and fails if any are present.

Sorries are policy violations, not compile errors — the file
"compiles" with sorries, but the goal (a complete proof) is not met.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from refine.checkers.base import Checker, CheckResult

_WARNING_VALUES: tuple[object, ...] = (2, "warning")

# Match `sorry` enclosed in any of: backticks, single quotes, double
# quotes. Lean uses backticks; older messages used quotes.
_SORRY_PATTERN = re.compile(r"[`'\"]sorry[`'\"]")


@dataclass(frozen=True)
class NoSorryChecker(Checker):
    name: str = "no_sorry"

    def check(
        self,
        content: str,
        diagnostics: list[dict[str, Any]],
    ) -> CheckResult:
        del content
        sorries: list[dict[str, Any]] = []
        for d in diagnostics:
            if d.get("severity") not in _WARNING_VALUES:
                continue
            msg = str(d.get("messageText", ""))
            if _SORRY_PATTERN.search(msg):
                sorries.append(d)
        if not sorries:
            return CheckResult(passed=True)
        return CheckResult(
            passed=False,
            pseudo_diagnostics=sorries,
            summary=f"{len(sorries)} `sorry` warning(s)",
        )
