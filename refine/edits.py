"""Apply LLM-proposed edits to a file's text.

Two edit kinds:

  - `replace_text` (preferred): supply `find_text`, an exact unique
    substring of the file. We locate it, replace it once. No coordinate
    arithmetic. Rejected when find_text doesn't appear or appears more
    than once (the agent must make it more specific).

  - `replace_range` (fallback): supply LSP-style `range` with UTF-16
    coordinates. We compute the byte offsets and splice. Applied in
    descending start-offset order so earlier edits don't shift later
    edits' positions.

Application order: all replace_text edits first (each find is
independent — uniqueness in the file is the contract), then all
replace_range edits in reverse-sorted order. This means a range edit's
coords are interpreted against the POST-text-edit content.

Four classes of rejection raise typed errors before any text is touched:
  - FindTextNotFoundError: a replace_text edit's find_text doesn't appear
  - FindTextAmbiguousError: a replace_text edit's find_text appears >1 times
  - OverlappingEditsError: two range edits target ranges that intersect
  - OutOfBoundsError: a range edit references a line/column past EOF
  - SemanticValidationError: post-Pydantic checks failed
"""

from __future__ import annotations

import logging

from refine.coords import position_to_offset, utf16_length
from refine.schema import Edit, RefineResponse

logger = logging.getLogger(__name__)


class EditApplyError(Exception):
    """Base for any failure during the apply pipeline."""


class OverlappingEditsError(EditApplyError):
    """Two range edits intersect — caller must not silently merge."""


class OutOfBoundsError(EditApplyError):
    """A range edit referenced a position past the file's end."""


class FindTextNotFoundError(EditApplyError):
    """A replace_text edit's find_text doesn't appear in the file."""


class FindTextAmbiguousError(EditApplyError):
    """A replace_text edit's find_text appears more than once — the
    agent must make it more specific (add surrounding context lines)."""


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
      1. Every range edit has `range.end >= range.start`.
      2. Every `diagnostic_ids` entry references a current turn's ID.
      3. Every `intended_scope[*].name` references a current decl.

    Text edits (kind="replace_text") skip the range check since they
    don't carry positional info — their find_text uniqueness is
    verified at apply time.
    """
    errors: list[str] = []
    for fix_index, fix in enumerate(response.fixes):
        for unknown_id in set(fix.diagnostic_ids) - valid_diagnostic_ids:
            errors.append(
                f"fixes[{fix_index}].diagnostic_ids contains {unknown_id}; "
                f"valid ids: {sorted(valid_diagnostic_ids)}"
            )
        for edit_index, edit in enumerate(fix.edits):
            if edit.range is None:
                continue  # replace_text edit; no range to validate here
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
    """Apply `edits` to `content` (LF-normalized) and return the result.

    Two-pass: every `replace_text` edit first (one-to-one substring
    replacement), then every `replace_range` edit in descending
    start-offset order. Range edits' coordinates are interpreted
    against the POST-text-edit content.

    Raises:
      - FindTextNotFoundError: a find_text doesn't appear in the file
      - FindTextAmbiguousError: a find_text appears more than once
      - OutOfBoundsError: a range edit references past EOF
      - OverlappingEditsError: two range edits intersect
    """
    if not edits:
        return content

    result = content

    text_edits = [e for e in edits if e.kind == "replace_text"]
    for edit in text_edits:
        result = _apply_text_edit(result, edit)

    range_edits = [e for e in edits if e.kind == "replace_range"]
    if range_edits:
        result = _apply_range_edits(result, range_edits)

    return result


def _apply_text_edit(content: str, edit: Edit) -> str:
    """Replace the unique occurrence of edit.find_text in content."""
    assert edit.find_text is not None  # Pydantic validator
    needle = edit.find_text
    count = content.count(needle)
    if count == 0:
        raise FindTextNotFoundError(
            f"replace_text: find_text not present in file. "
            f"find_text was {needle!r}. "
            f"Hint: check whitespace / line endings / Unicode characters; "
            f"the match must be byte-exact."
        )
    if count > 1:
        raise FindTextAmbiguousError(
            f"replace_text: find_text appears {count} times — must be "
            f"unique. Add surrounding context (preceding/following lines) "
            f"to disambiguate. find_text was {needle!r}."
        )
    return content.replace(needle, edit.replacement, 1)


def _apply_range_edits(content: str, edits: list[Edit]) -> str:
    """Apply range edits in descending start-offset order."""
    lines = content.split("\n")
    for edit in edits:
        _reject_if_range_out_of_bounds(edit, lines)

    indexed = []
    for e in edits:
        assert e.range is not None  # Pydantic validator
        start_off = position_to_offset(
            content, e.range.start.line, e.range.start.character
        )
        end_off = position_to_offset(
            content, e.range.end.line, e.range.end.character
        )
        indexed.append((start_off, end_off, e.replacement))
    indexed.sort(key=lambda triple: triple[0], reverse=True)

    # In descending order, the next edit (i+1) starts earlier in the file.
    # An overlap exists iff its end pokes into the current edit's start.
    for i in range(len(indexed) - 1):
        curr_start = indexed[i][0]
        _, next_end, _ = indexed[i + 1]
        if next_end > curr_start:
            raise OverlappingEditsError(
                f"edits at offsets {indexed[i + 1][:2]} and "
                f"{indexed[i][:2]} overlap"
            )

    result = content
    for start, end, replacement in indexed:
        if result[start:end] == replacement:
            logger.debug("identity edit at offsets %d..%d skipped", start, end)
            continue
        result = result[:start] + replacement + result[end:]
    return result


def _reject_if_range_out_of_bounds(edit: Edit, lines: list[str]) -> None:
    assert edit.range is not None  # Pydantic validator
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
