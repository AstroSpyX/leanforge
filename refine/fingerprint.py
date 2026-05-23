"""Diagnostic fingerprinting + Lean-message normalization.

A fingerprint is a stable identity for a diagnostic that survives unrelated
edits but distinguishes truly different errors. It's a sha256 over four
normalized fields:

    severity | normalized_message | enclosing_declaration | normalized_goal

Position is intentionally excluded — every edit shifts line/column numbers
and a position-based fingerprint destabilizes after the first iteration.

Same `normalize_message` is applied to both the message text and the goal
text. Both come from Lean and carry the same transient identifiers
(metavar IDs, hygienic suffixes, etc.).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# Lean wraps elaborator-internal identities in stable prefixes followed by a
# numeric tail. Stripping the tail leaves a fingerprint-stable token.
_METAVAR_PATTERN = re.compile(r"\?m\.\d+")
_UNIVERSE_METAVAR_PATTERN = re.compile(r"\?u\.\d+")
_HYGIENIC_UNIQ_PATTERN = re.compile(r"_uniq\.\d+")
_HYGIENIC_HYG_PATTERN = re.compile(r"_hyg\.\d+")
# Messages sometimes embed file line numbers (e.g. "at Foo.lean:42:7"). The
# line number itself is identity-bearing across iterations only by accident.
_FILE_LINE_PATTERN = re.compile(r"(?:line|:)\s*\d+(?::\d+)?")
_WHITESPACE_RUN_PATTERN = re.compile(r"\s+")


def normalize_message(text: str) -> str:
    """Strip transient identifiers from a Lean message or goal text so the
    output hashes to the same value across cosmetically different iterations
    of the same underlying error.
    """
    text = _METAVAR_PATTERN.sub("?m", text)
    text = _UNIVERSE_METAVAR_PATTERN.sub("?u", text)
    text = _HYGIENIC_UNIQ_PATTERN.sub("_uniq", text)
    text = _HYGIENIC_HYG_PATTERN.sub("_hyg", text)
    text = _FILE_LINE_PATTERN.sub("<line>", text)
    text = _WHITESPACE_RUN_PATTERN.sub(" ", text).strip()
    return text


def canonicalize_diagnostic(diagnostic: dict[str, Any]) -> dict[str, Any]:
    """Return a diagnostic with its message and goal fields normalized.

    Used for storage in `canonical_diagnostics` alongside the raw record.
    The raw diagnostic is preserved untouched for debugging; this is for
    fingerprinting and display.
    """
    canonical: dict[str, Any] = dict(diagnostic)
    canonical["messageText"] = normalize_message(diagnostic.get("messageText", ""))
    goal = diagnostic.get("goal") or {}
    if isinstance(goal, dict) and "rendered" in goal:
        canonical["goal"] = {**goal, "rendered": normalize_message(goal["rendered"])}
    term_goal = diagnostic.get("termGoal") or {}
    if isinstance(term_goal, dict) and "goal" in term_goal:
        canonical["termGoal"] = {
            **term_goal,
            "goal": normalize_message(term_goal["goal"]),
        }
    return canonical


def fingerprint_diagnostic(diagnostic: dict[str, Any]) -> str:
    """Compute the stable sha256 fingerprint for one leanforge diagnostic.

    Inputs are the raw diagnostic dict; normalization happens here so
    callers don't have to remember which fields to pre-process.
    """
    severity = str(diagnostic.get("severity", ""))
    message = normalize_message(diagnostic.get("messageText", ""))
    enclosing = diagnostic.get("enclosingDeclaration") or {}
    decl_name = enclosing.get("name", "") if isinstance(enclosing, dict) else ""
    goal_text = _extract_goal_text(diagnostic)
    payload = "\x1f".join([severity, message, decl_name, goal_text])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_goal_text(diagnostic: dict[str, Any]) -> str:
    """Prefer the tactic goal's rendered form; fall back to term goal."""
    goal = diagnostic.get("goal")
    if isinstance(goal, dict) and isinstance(goal.get("rendered"), str):
        return normalize_message(goal["rendered"])
    term_goal = diagnostic.get("termGoal")
    if isinstance(term_goal, dict) and isinstance(term_goal.get("goal"), str):
        return normalize_message(term_goal["goal"])
    return ""
