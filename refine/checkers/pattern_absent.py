"""Pass when none of the given patterns appear in proof bodies.

Use for refactor goals like "every proof should use the `*` notation
in place of `Γ.op`": configure with patterns=[r"Γ\\.op", r"Γ\\.inv"]
and the checker fails until those literals are gone from proof
bodies. Pattern matches inside structure/signature regions are
ignored — the underlying fields still need to exist.

A "proof body" heuristic: everything inside a top-level declaration
that is either:
  - The right-hand side of `:= by ...`
  - The right-hand side of `:= ⟨...⟩` / `:= rfl` / `:= ...` (term mode)
The signature (the part before `:=`) is exempt.

The heuristic is intentionally generous — false negatives (missing a
real occurrence) are worse than false positives. If a pattern slips
through, the iteration loop will catch it on the next pass via the
follow-up judge or pattern check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from refine.checkers.base import Checker, CheckResult


@dataclass(frozen=True)
class PatternAbsentChecker(Checker):
    """Configurable regex-grep checker.

    Each pattern is matched against every line that the heuristic
    classifies as a proof body. Matches become pseudo-diagnostics
    pointing at the offending line.

    `max_reported` caps how many per-line pseudo-diagnostics are
    surfaced to the next iter's prompt. Above the cap, the rest are
    summarized into a single "... and N more" entry. Without the cap,
    surfacing 100+ matches at once overwhelms the worker LLM — it
    attempts mass edits that hit coordinate-drift apply_edits
    failures (~40% iter waste observed on gemini-flash). With the
    cap, the agent gets a workable batch each iter and converges
    steadily. Set to 0 for unlimited.
    """

    name: str
    patterns: tuple[str, ...]
    max_reported: int = 20
    # Lines whose stripped form starts with one of these prefixes are
    # treated as declaration HEADERS (signatures), not proof bodies.
    # The "is this a body?" state is sticky: after a header we're "in
    # body" until we hit a blank line or another header.
    _decl_prefixes: tuple[str, ...] = field(
        default=("theorem ", "lemma ", "def ", "structure ", "instance ", "example ")
    )

    def check(
        self,
        content: str,
        diagnostics: list[dict[str, Any]],
    ) -> CheckResult:
        del diagnostics
        offenses: list[dict[str, Any]] = []
        compiled = [re.compile(p) for p in self.patterns]
        in_body = False
        for line_idx, line in enumerate(content.splitlines()):
            stripped = line.lstrip()
            # New top-level declaration → header, not body.
            if any(stripped.startswith(prefix) for prefix in self._decl_prefixes):
                in_body = ":=" in line and not stripped.startswith("example ")
                # `theorem foo : T := by ...` opens a body on the same line.
                # But the header content itself is exempt — only flag
                # subsequent lines.
                continue
            if not stripped:
                # Blank line ends the current body.
                in_body = False
                continue
            # `:= by ...` or `:= term` on its own line opens a body.
            if stripped.startswith(":=") or ":= by" in line:
                in_body = True
            if not in_body:
                continue
            for pat in compiled:
                m = pat.search(line)
                if m is None:
                    continue
                offenses.append(
                    {
                        "severity": "error",
                        "messageText": (
                            f"pattern_absent[{self.name}]: "
                            f"matched {pat.pattern!r} in proof body — "
                            f"refactor this occurrence"
                        ),
                        "range": {
                            "start": {"line": line_idx, "character": m.start()},
                            "end": {"line": line_idx, "character": m.end()},
                        },
                    }
                )
        if not offenses:
            return CheckResult(passed=True)
        if self.max_reported > 0 and len(offenses) > self.max_reported:
            reported = offenses[: self.max_reported]
            remainder = len(offenses) - self.max_reported
            reported.append(
                {
                    "severity": "error",
                    "messageText": (
                        f"pattern_absent[{self.name}]: ... and {remainder} "
                        f"more match(es) elsewhere in the file (showing "
                        f"first {self.max_reported}; the next iter will "
                        f"surface a fresh batch after these are fixed)"
                    ),
                }
            )
            return CheckResult(passed=False, pseudo_diagnostics=reported)
        return CheckResult(passed=False, pseudo_diagnostics=offenses)
