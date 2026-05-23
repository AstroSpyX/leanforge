"""Textual diff statistics between two iterations' file content.

`compute_text_diff` is the only public surface. Returns a small dataclass
with lines added, removed, "changed" (= min(added, removed) — a cheap
heuristic for visualizing churn), and the largest single edit-block span
in lines.

declarations_touched and error_delta are NOT computed here — they require
context (the declaration map, the previous iteration's fingerprints) that
this module deliberately doesn't take. The controller composes those with
the text-diff stats into the full DiffSummary record stored in history.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from refine.coords import normalize_line_endings


@dataclass(frozen=True)
class TextDiffStats:
    lines_added: int
    lines_removed: int
    lines_changed: int
    max_edit_size_lines: int


def compute_text_diff(before: str, after: str) -> TextDiffStats:
    """Compute textual diff stats. Both inputs are normalized to LF
    before diffing so CRLF/CR variations don't pollute the counts."""
    before_lines = normalize_line_endings(before).split("\n")
    after_lines = normalize_line_endings(after).split("\n")

    added = 0
    removed = 0
    max_block_size = 0
    current_block_size = 0

    for line in difflib.unified_diff(before_lines, after_lines, lineterm=""):
        if line.startswith(("+++", "---", "@@")):
            current_block_size = 0
            continue
        if line.startswith("+"):
            added += 1
            current_block_size += 1
        elif line.startswith("-"):
            removed += 1
            current_block_size += 1
        else:
            max_block_size = max(max_block_size, current_block_size)
            current_block_size = 0
    max_block_size = max(max_block_size, current_block_size)

    return TextDiffStats(
        lines_added=added,
        lines_removed=removed,
        lines_changed=min(added, removed),
        max_edit_size_lines=max_block_size,
    )
