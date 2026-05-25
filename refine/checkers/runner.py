"""Stage runner — execute a list of stages with short-circuit semantics.

Given an ordered list of CheckerStage, this module returns the first
failing stage (with all its failing checkers' pseudo_diagnostics
merged), or a green StageResult named "all" when every stage passes.

Within a stage, all checkers run unconditionally and their results
are AND-combined. This lets sibling checkers in the same stage
report independent issues at once (e.g. no_sorry AND no_axiom both
complain in the policy stage so the agent fixes both together).

Across stages, the first failure short-circuits — the agent sees one
class of issue at a time, ordered from most foundational to most
semantic.
"""

from __future__ import annotations

from typing import Any

from refine.checkers.base import CheckerStage, StageResult


def run_stages(
    stages: list[CheckerStage],
    content: str,
    diagnostics: list[dict[str, Any]],
) -> StageResult:
    """Run stages in order, short-circuiting on the first failing stage.

    Returns the StageResult for the first failing stage, or a green
    StageResult named "all" when every stage passes.
    """
    for stage in stages:
        results = [c.check(content, diagnostics) for c in stage.checkers]
        if not all(r.passed for r in results):
            failing: list[dict[str, Any]] = []
            summaries: list[str] = []
            for checker, r in zip(stage.checkers, results, strict=True):
                if r.passed:
                    continue
                failing.extend(r.pseudo_diagnostics)
                if r.summary is not None:
                    summaries.append(f"{checker.name}: {r.summary}")
            return StageResult(
                stage_name=stage.name,
                passed=False,
                pseudo_diagnostics=failing,
                summaries=summaries,
            )
    return StageResult(stage_name="all", passed=True)
