"""Pluggable success-criteria framework for the refine loop.

A `Checker` is anything that takes the current file content + Lean
diagnostics and answers "is the goal met yet?". A `CheckerStage`
groups checkers that should be reported together. Stages are run
sequentially with short-circuit — if `syntax` fails, we don't bother
running `intent` (the LLM judge).

The framework absorbs:
  - Deterministic checks (Lean compile, no sorries, regex grep,
    signature preservation, ...)
  - LLM-judge checks (cheap-model verdict on whether goal text is met)
  - External-tool checks (subprocess; pass on exit 0)

All conform to the same Checker Protocol. The controller doesn't
distinguish — failing checkers emit `pseudo_diagnostics` that flow
into the next iter's prompt alongside Lean's real diagnostics.
"""

from __future__ import annotations

from refine.checkers.base import Checker, CheckerStage, CheckResult, StageResult

__all__ = ["Checker", "CheckResult", "CheckerStage", "StageResult"]
