"""Core protocols and data classes for the checker framework.

A `Checker` is stateless and called once per iteration. It receives the
post-edit file content and Lean's diagnostics, and decides whether the
loop is done (`passed=True`). On `passed=False` it can emit
`pseudo_diagnostics` shaped like Lean diagnostics — the controller
merges these into the next iter's prompt so the agent sees them
exactly the way it sees real errors.

A `CheckerStage` is one or more checkers that should be reported
together. Stages run sequentially with short-circuit: if syntax fails,
policy/style/intent don't run that iter. This keeps the agent's
attention on the most foundational issues first and avoids paying
for the LLM judge when Lean is still broken.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    """One checker's verdict.

    `pseudo_diagnostics` is a list of dict-shaped diagnostics in the
    same format Lean produces (severity / messageText / range /
    enclosingDeclaration). The controller assigns IDs and merges them
    with Lean's real diagnostics for the next iter's prompt.

    `summary` is a short one-liner the checker offers for log lines —
    typically the total count of issues (which may exceed
    pseudo_diagnostics length when the checker caps surfaced items)
    or a brief verdict explanation. Logged by the controller as
    "stage_name (checker_name: summary)". Optional; checkers that
    pass usually leave it None.
    """

    passed: bool
    pseudo_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    summary: str | None = None


@dataclass(frozen=True)
class StageResult:
    """Outcome of running one CheckerStage (all checkers in a stage).

    `summaries` aggregates the `summary` field of every checker in
    the stage that failed (in the order checkers appear), so the
    controller can render a one-line stage status without re-walking
    individual results.
    """

    stage_name: str
    passed: bool
    pseudo_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)


class Checker(ABC):
    """Stateless predicate over (file content, Lean diagnostics).

    `name` is a short identifier used in logs and CLI specs (e.g.
    "lean_compile", "no_sorry", "pattern_absent:no_gamma_op").

    Concrete implementations inherit from this class so mypy can
    verify the Checker contract at the call sites that construct
    `CheckerStage(name, (concrete_checker, ...))`. (A Protocol would
    work conceptually but mypy's variance handling for frozen
    dataclasses inside tuple/Sequence types is fragile.)
    """

    name: str

    @abstractmethod
    def check(
        self,
        content: str,
        diagnostics: list[dict[str, Any]],
    ) -> CheckResult:
        """Decide whether the loop's goal is met given the current state."""
        raise NotImplementedError


@dataclass(frozen=True)
class CheckerStage:
    """One or more checkers that are reported as a group.

    Stages encode priority: cheap-and-foundational first (syntax,
    policy), expensive-but-semantic last (LLM judge). The stage
    runner short-circuits — the first failing stage's pseudo
    diagnostics are surfaced and remaining stages don't run.

    `checkers` is typed as `Sequence[Checker]` (covariant) so a
    concrete tuple like `(LeanCompileChecker(),)` is accepted without
    explicit Checker casts at every call site.
    """

    name: str
    checkers: Sequence[Checker]
