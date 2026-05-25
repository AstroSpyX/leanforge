"""Tests for refine.edits — apply, bounds, overlap, semantic validation."""

import pytest
from pydantic import ValidationError

from refine.edits import (
    FindTextAmbiguousError,
    FindTextNotFoundError,
    OutOfBoundsError,
    OverlappingEditsError,
    apply_edits,
    validate_response,
)
from refine.schema import Edit, Fix, Position, Range, RefineResponse, RepairStrategy


def _text_edit(find: str, replacement: str) -> Edit:
    return Edit(kind="replace_text", find_text=find, replacement=replacement)


def _range(start_line: int, start_char: int, end_line: int, end_char: int) -> Range:
    return Range(
        start=Position(line=start_line, character=start_char),
        end=Position(line=end_line, character=end_char),
    )


def _edit(
    start_line: int, start_char: int, end_line: int, end_char: int, replacement: str
) -> Edit:
    return Edit(
        kind="replace_range",
        range=_range(start_line, start_char, end_line, end_char),
        replacement=replacement,
    )


def _response(fixes: list[Fix], intended_scope_names: list[str]) -> RefineResponse:
    return RefineResponse(
        summary="x",
        strategy=RepairStrategy.OTHER,
        reasoning="x",
        confidence=0.5,
        intended_scope=[{"name": n, "range": None} for n in intended_scope_names],  # type: ignore[arg-type]
        fixes=fixes,
        remaining_blockers=[],
    )


class TestApplyEdits:
    def test_no_edits_returns_content_unchanged(self) -> None:
        assert apply_edits("hello", []) == "hello"

    def test_single_edit_replaces_range(self) -> None:
        # "def x := 1" → replace "1" (col 9..10) with "42"
        new = apply_edits("def x := 1", [_edit(0, 9, 0, 10, "42")])
        assert new == "def x := 42"

    def test_insert_at_position_via_zero_width_range(self) -> None:
        new = apply_edits("ab", [_edit(0, 1, 0, 1, "X")])
        assert new == "aXb"

    def test_delete_via_empty_replacement(self) -> None:
        new = apply_edits("abc", [_edit(0, 1, 0, 2, "")])
        assert new == "ac"

    def test_two_non_overlapping_edits_applied_descending(self) -> None:
        """The descending-apply order means later edits in the file are
        applied first; the test catches off-by-one bugs in the ordering."""
        new = apply_edits(
            "abcdef",
            [_edit(0, 0, 0, 1, "A"), _edit(0, 4, 0, 5, "E")],
        )
        assert new == "AbcdEf"

    def test_multi_line_edit(self) -> None:
        content = "line0\nline1\nline2"
        # Replace "1\nline2" — chars 4..end of line 2
        new = apply_edits(content, [_edit(1, 4, 2, 5, "ONE\nTWO")])
        assert new == "line0\nlineONE\nTWO"

    def test_identity_edit_skipped(self) -> None:
        """Identity replacement is silently skipped (logged at DEBUG)."""
        content = "hello"
        new = apply_edits(content, [_edit(0, 0, 0, 5, "hello")])
        assert new == content

    def test_overlap_at_inner_edit_raises(self) -> None:
        with pytest.raises(OverlappingEditsError):
            apply_edits(
                "abcdef",
                [_edit(0, 0, 0, 3, "X"), _edit(0, 2, 0, 5, "Y")],
            )

    def test_oob_line_raises(self) -> None:
        with pytest.raises(OutOfBoundsError, match="line 5"):
            apply_edits("abc", [_edit(5, 0, 5, 1, "x")])

    def test_oob_character_raises(self) -> None:
        with pytest.raises(OutOfBoundsError, match="character 99"):
            apply_edits("abc", [_edit(0, 99, 0, 99, "x")])

    def test_end_of_line_position_is_in_bounds(self) -> None:
        """LSP permits a position one-past-end as an insertion point."""
        new = apply_edits("abc", [_edit(0, 3, 0, 3, "X")])
        assert new == "abcX"

    def test_supplementary_plane_offset_uses_utf16_units(self) -> None:
        """🎉 takes 2 UTF-16 units (offsets 1 and 2); 'b' starts at offset 3.
        Inserting at LSP char 3 puts text BETWEEN the emoji and 'b'."""
        new = apply_edits("a🎉b", [_edit(0, 3, 0, 3, "X")])
        assert new == "a🎉Xb"

    def test_insertion_at_end_of_supplementary_plane_line(self) -> None:
        """End-of-line for "a🎉b" is LSP char 4 (1 + 2 + 1)."""
        new = apply_edits("a🎉b", [_edit(0, 4, 0, 4, "X")])
        assert new == "a🎉bX"


class TestReplaceTextEdit:
    def test_single_unique_find_replaces_once(self) -> None:
        content = "theorem foo : True := by\n  rw [Γ.op a b]\n  rfl\n"
        new = apply_edits(content, [_text_edit("Γ.op a b", "a * b")])
        assert "Γ.op a b" not in new
        assert "a * b" in new

    def test_find_text_not_found_raises(self) -> None:
        with pytest.raises(FindTextNotFoundError, match="not present"):
            apply_edits("hello", [_text_edit("absent", "x")])

    def test_ambiguous_find_text_raises_with_count(self) -> None:
        content = "foo\nfoo\nfoo\n"
        with pytest.raises(FindTextAmbiguousError, match="3 times"):
            apply_edits(content, [_text_edit("foo", "bar")])

    def test_multiple_text_edits_apply_in_order(self) -> None:
        """Each text edit runs against the post-previous-edits content."""
        content = "alpha beta gamma\n"
        new = apply_edits(
            content,
            [
                _text_edit("alpha", "ALPHA"),
                _text_edit("gamma", "GAMMA"),
            ],
        )
        assert new == "ALPHA beta GAMMA\n"

    def test_text_edit_replaces_multi_line_block(self) -> None:
        """find_text can span lines — newlines included in the match."""
        content = "header\nblock line 1\nblock line 2\nfooter\n"
        new = apply_edits(
            content,
            [_text_edit("block line 1\nblock line 2", "replaced")],
        )
        assert new == "header\nreplaced\nfooter\n"

    def test_mixed_text_and_range_edits_text_runs_first(self) -> None:
        """A text edit shifts byte positions before range edits run, so
        range coords are interpreted against the post-text content."""
        content = "alpha beta gamma\n"
        # After text edit: "ALPHA beta gamma\n"
        # Range edit: line 0 chars 6..10 ("beta") in post-text content
        new = apply_edits(
            content,
            [
                _text_edit("alpha", "ALPHA"),
                _edit(0, 6, 0, 10, "BETA"),
            ],
        )
        assert new == "ALPHA BETA gamma\n"

    def test_unicode_find_text_works(self) -> None:
        """The whole point: Unicode-heavy substrings don't need
        coordinate arithmetic on the agent side."""
        content = "  exact Γ.op a Γ.e ▸ rfl\n"
        new = apply_edits(content, [_text_edit("Γ.op a Γ.e", "a * e")])
        assert "a * e" in new
        assert "Γ.op" not in new


class TestEditKindValidation:
    def test_replace_range_without_range_rejected(self) -> None:
        with pytest.raises(ValidationError, match="requires a `range`"):
            Edit(kind="replace_range", replacement="x")

    def test_replace_range_with_find_text_rejected(self) -> None:
        rng = _range(0, 0, 0, 1)
        with pytest.raises(ValidationError, match="must not set `find_text`"):
            Edit(kind="replace_range", range=rng, find_text="x", replacement="y")

    def test_replace_text_without_find_text_rejected(self) -> None:
        with pytest.raises(ValidationError, match="requires a `find_text`"):
            Edit(kind="replace_text", replacement="x")

    def test_replace_text_with_range_rejected(self) -> None:
        rng = _range(0, 0, 0, 1)
        with pytest.raises(ValidationError, match="must not set `range`"):
            Edit(kind="replace_text", range=rng, find_text="x", replacement="y")

    def test_replace_text_with_empty_find_text_rejected(self) -> None:
        with pytest.raises(ValidationError, match="empty `find_text`"):
            Edit(kind="replace_text", find_text="", replacement="x")


class TestValidateResponse:
    def test_clean_response_returns_no_errors(self) -> None:
        response = _response(
            fixes=[Fix(diagnostic_ids=[0], edits=[_edit(0, 0, 0, 1, "x")])],
            intended_scope_names=["foo"],
        )
        errors = validate_response(
            response,
            valid_diagnostic_ids={0, 1},
            valid_decl_names={"foo", "bar"},
        )
        assert errors == []

    def test_unknown_diagnostic_id_flagged(self) -> None:
        response = _response(
            fixes=[Fix(diagnostic_ids=[99], edits=[_edit(0, 0, 0, 1, "x")])],
            intended_scope_names=["foo"],
        )
        errors = validate_response(
            response,
            valid_diagnostic_ids={0, 1},
            valid_decl_names={"foo"},
        )
        assert any("99" in e for e in errors)

    def test_unknown_intended_scope_decl_flagged(self) -> None:
        response = _response(
            fixes=[Fix(diagnostic_ids=[0], edits=[_edit(0, 0, 0, 1, "x")])],
            intended_scope_names=["nonexistent"],
        )
        errors = validate_response(
            response,
            valid_diagnostic_ids={0},
            valid_decl_names={"foo"},
        )
        assert any("nonexistent" in e for e in errors)

    def test_backwards_range_flagged(self) -> None:
        """end before start is structurally valid Pydantic but semantically broken."""
        response = _response(
            fixes=[Fix(diagnostic_ids=[0], edits=[_edit(0, 5, 0, 2, "x")])],
            intended_scope_names=["foo"],
        )
        errors = validate_response(
            response,
            valid_diagnostic_ids={0},
            valid_decl_names={"foo"},
        )
        assert any("end" in e and "before start" in e for e in errors)

    def test_multiple_violations_all_reported(self) -> None:
        response = _response(
            fixes=[Fix(diagnostic_ids=[99], edits=[_edit(0, 5, 0, 2, "x")])],
            intended_scope_names=["nope"],
        )
        errors = validate_response(
            response,
            valid_diagnostic_ids={0},
            valid_decl_names={"foo"},
        )
        assert len(errors) == 3  # unknown id, unknown decl, bad range
