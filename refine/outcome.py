"""Classify a leanforge run into a coarse-grained Outcome.

leanforge returns `elaborationSucceeded` and a list of diagnostics; this
module turns those into an `Outcome` enum the controller can pattern-match
on. The classifier is heuristic — Lean does not tag its diagnostics with
"this is a parser error" vs "this is a tactic error" — so we infer from
message text and from the subprocess exit signal.
"""

from __future__ import annotations

import signal
from enum import StrEnum
from typing import Any

# LSP severity is integer 1=Error, but leanforge.py serializes as string
# labels ("error"). Accept both so this classifier works regardless of
# which side the diagnostic came through.
SEVERITY_ERROR_VALUES: tuple[int | str, ...] = (1, "error")

# Python subprocess.returncode for signal-terminated processes is -N where
# N is the signal number. SIGKILL on macOS is the dominant OOM indicator.
SIGKILL_RETURNCODE = -signal.SIGKILL


class Outcome(StrEnum):
    SUCCESS = "success"
    PARSE_ERROR = "parse_error"
    ELAB_ERROR = "elab_error"
    IMPORT_ERROR = "import_error"
    TIMEOUT = "timeout"
    PANIC = "panic"
    OOM = "oom"


def classify_outcome(
    diagnostics: list[dict[str, Any]],
    timed_out: bool,
    subprocess_returncode: int | None,
) -> Outcome:
    """Classify the leanforge run. Inputs encode the subprocess result;
    output is the coarsest category that informs controller policy.

    Ordering matters:
      1. Our own timeout signal takes precedence (we may have killed Lean
         mid-elaboration; the diagnostic list is unreliable).
      2. Signal-based termination by the OS (SIGKILL → OOM, other signals →
         PANIC) is next.
      3. With a healthy process, the diagnostic list classifies:
         parser-derived → PARSE_ERROR, import-line errors → IMPORT_ERROR,
         anything else with errors → ELAB_ERROR, no errors → SUCCESS.
    """
    if timed_out:
        return Outcome.TIMEOUT
    if subprocess_returncode is not None and subprocess_returncode < 0:
        if subprocess_returncode == SIGKILL_RETURNCODE:
            return Outcome.OOM
        return Outcome.PANIC

    errors = [d for d in diagnostics if d.get("severity") in SEVERITY_ERROR_VALUES]
    if not errors:
        return Outcome.SUCCESS

    for diag in errors:
        if _is_parse_error(diag):
            return Outcome.PARSE_ERROR
        if _is_import_error(diag):
            return Outcome.IMPORT_ERROR
    return Outcome.ELAB_ERROR


def _is_parse_error(diagnostic: dict[str, Any]) -> bool:
    kind = str(diagnostic.get("kind", "")).lower()
    message = str(diagnostic.get("messageText", ""))
    return "parser" in kind or message.startswith("unexpected token")


def _is_import_error(diagnostic: dict[str, Any]) -> bool:
    """An error on a line that begins with `import` (after stripping
    leading whitespace) is treated as an import resolution failure.
    Heuristic: we only have access to the diagnostic, not the source
    line; we rely on Lean's own messages mentioning 'import' or
    'unknown module' / 'could not find' patterns.
    """
    message = str(diagnostic.get("messageText", "")).lower()
    return (
        "unknown module" in message
        or "could not find file" in message
        or "failed to load module" in message
    )
