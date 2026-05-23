"""Classify how the primary proof goal moved between iterations.

This is a heuristic, deliberately so — robust goal-tracking would require
elaborating both iterations and comparing metavariable contexts. v1
operates on the rendered goal text strings leanforge already returns.

Primary goal = goal text from the first error diagnostic that carries one
(falling back to termGoal). When no errors remain, the goal is RESOLVED.
"""

from __future__ import annotations

from typing import Any

from refine.fingerprint import normalize_message
from refine.state import GoalStatus

# A new iteration's normalized goal must be at least this fraction shorter
# than the previous to be classified as PROGRESS (vs SHIFTED). Tunable.
PROGRESS_SHRINK_FRACTION = 0.10

SEVERITY_ERROR_VALUES: tuple[int | str, ...] = (1, "error")


def classify_goal_status(
    prev_diagnostics: list[dict[str, Any]],
    curr_diagnostics: list[dict[str, Any]],
) -> GoalStatus:
    """Compare primary goals before/after one iteration.

    Returns:
      RESOLVED  — current diagnostics have no errors
      UNCHANGED — primary goal text is identical
      PROGRESS  — primary goal shrunk by ≥ PROGRESS_SHRINK_FRACTION
                  or previous target appears as a substring of current
      SHIFTED   — primary goal changed but is not clearly simpler
    """
    if not _has_errors(curr_diagnostics):
        return GoalStatus.RESOLVED

    prev = _primary_goal_text(prev_diagnostics)
    curr = _primary_goal_text(curr_diagnostics)

    if prev == curr:
        return GoalStatus.UNCHANGED

    if _is_clearly_simpler(prev, curr):
        return GoalStatus.PROGRESS
    return GoalStatus.SHIFTED


def _has_errors(diagnostics: list[dict[str, Any]]) -> bool:
    return any(d.get("severity") in SEVERITY_ERROR_VALUES for d in diagnostics)


def _primary_goal_text(diagnostics: list[dict[str, Any]]) -> str:
    """First diagnostic that exposes a renderable goal wins.

    Preference: tactic goal's `rendered` field > term goal's `goal` field.
    Empty string when nothing is available (which makes UNCHANGED-on-empty
    a natural early-iteration case).
    """
    for diag in diagnostics:
        goal = diag.get("goal")
        if isinstance(goal, dict) and isinstance(goal.get("rendered"), str):
            return normalize_message(goal["rendered"])
        term_goal = diag.get("termGoal")
        if isinstance(term_goal, dict) and isinstance(term_goal.get("goal"), str):
            return normalize_message(term_goal["goal"])
    return ""


def _is_clearly_simpler(prev: str, curr: str) -> bool:
    """Two cheap signals: meaningful character shrink, or target inclusion.

    Both are heuristic. The fraction threshold avoids classifying a one-
    character diff as PROGRESS. The substring check helps when normalization
    differs but the target proposition is preserved.
    """
    if not prev or not curr:
        return False
    shrink = (len(prev) - len(curr)) / len(prev)
    if shrink >= PROGRESS_SHRINK_FRACTION:
        return True
    prev_target = _extract_target(prev)
    curr_target = _extract_target(curr)
    return bool(prev_target) and prev_target in curr_target


def _extract_target(goal_text: str) -> str:
    """Return the conclusion (after `⊢`) for a tactic goal, or the whole
    text if no turnstile is present. Used only for the substring check —
    not stable enough to be a primary identity."""
    if "⊢" in goal_text:
        return goal_text.split("⊢", maxsplit=1)[1].strip()
    return goal_text.strip()
