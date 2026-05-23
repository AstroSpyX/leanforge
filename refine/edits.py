"""Apply LLM-proposed `replace_range` edits to a file's text.

The only operation supported is `replace_range`. Insert is a zero-width
range; delete is an empty replacement; full rewrite is `(0,0)..(EOF)`.

Edits are applied in descending order by start offset so that earlier
applications don't shift the coordinates of later ones.

Three classes of rejection raise typed errors before any text is touched:
  - OverlappingEditsError: two edits target ranges that intersect
  - OutOfBoundsError: an edit references a line/column past EOF
  - SemanticValidationError: post-Pydantic checks failed (well-formed
    range, valid diagnostic_ids, intended_scope names that exist)
"""

from __future__ import annotations

import logging

from refine.coords import position_to_offset, utf16_length
from refine.schema import Edit, RefineResponse

logger = logging.getLogger(__name__)


class EditApplyError(Exception):
    """Base for any failure during the apply pipeline."""


class OverlappingEditsError(EditApplyError):
    """Two edits' ranges intersect — caller must not silently merge."""


class OutOfBoundsError(EditApplyError):
    """An edit referenced a position past the file's end."""


class SemanticValidationError(EditApplyError):
    """A post-Pydantic check failed (range order, ID existence, etc.)."""


def validate_response(
    response: RefineResponse,
    valid_diagnostic_ids: set[int],
    valid_decl_names: set[str],
) -> list[str]:
    """Run the post-Pydantic semantic checks. Returns a list of error
    messages — empty list means the response is internally consistent
    against the current turn's context.

    Three checks:
      1. Every `range.end >= range.start` (line then character).
      2. Every `diagnostic_ids` entry references a current turn's ID.
      3. Every `intended_scope[*].name` references a current decl.
    """
    errors: list[str] = []
    for fix_index, fix in enumerate(response.fixes):
        for unknown_id in set(fix.diagnostic_ids) - valid_diagnostic_ids:
            errors.append(
                f"fixes[{fix_index}].diagnostic_ids contains {unknown_id}; "
                f"valid ids: {sorted(valid_diagnostic_ids)}"
            )
        for edit_index, edit in enumerate(fix.edits):
            start = (edit.range.start.line, edit.range.start.character)
            end = (edit.range.end.line, edit.range.end.character)
            if end < start:
                errors.append(
                    f"fixes[{fix_index}].edits[{edit_index}].range has "
                    f"end {end} before start {start}"
                )
    for scope_index, item in enumerate(response.intended_scope):
        if item.name not in valid_decl_names:
            errors.append(
                f"intended_scope[{scope_index}].name {item.name!r} is not "
                f"a top-level declaration in the current file"
            )
    return errors


def apply_edits(content: str, edits: list[Edit]) -> str:
    """Apply `edits` to `content` (which must be LF-normalized) and return
    the updated text.

    No-op when `edits` is empty. Raises OutOfBoundsError on positions past
    EOF, OverlappingEditsError when any pair of edits intersects.
    """
    if not edits:
        return content

    lines = content.split("\n")
    for edit in edits:
        _reject_if_out_of_bounds(edit, lines)

    indexed = [
        (
            position_to_offset(content, e.range.start.line, e.range.start.character),
            position_to_offset(content, e.range.end.line, e.range.end.character),
            e.replacement,
        )
        for e in edits
    ]
    indexed.sort(key=lambda triple: triple[0], reverse=True)

    # In descending order, the next edit (i+1) starts earlier in the file.
    # An overlap exists iff its end pokes into the current edit's start.
    for i in range(len(indexed) - 1):
        curr_start = indexed[i][0]
        _, next_end, _ = indexed[i + 1]
        if next_end > curr_start:
            raise OverlappingEditsError(
                f"edits at offsets {indexed[i + 1][:2]} and {indexed[i][:2]} overlap"
            )

    result = content
    for start, end, replacement in indexed:
        if result[start:end] == replacement:
            logger.debug("identity edit at offsets %d..%d skipped", start, end)
            continue
        result = result[:start] + replacement + result[end:]
    return result


def _reject_if_out_of_bounds(edit: Edit, lines: list[str]) -> None:
    line_count = len(lines)
    for label, pos in (("start", edit.range.start), ("end", edit.range.end)):
        if pos.line >= line_count:
            raise OutOfBoundsError(
                f"edit {label} references line {pos.line} but file has "
                f"only {line_count} lines"
            )
        line_units = utf16_length(lines[pos.line])
        if pos.character > line_units:
            raise OutOfBoundsError(
                f"edit {label} character {pos.character} exceeds line "
                f"{pos.line}'s UTF-16 length ({line_units})"
            )
