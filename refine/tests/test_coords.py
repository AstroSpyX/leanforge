"""Tests for refine.coords — LSP UTF-16 ↔ Python code-point conversion."""

import pytest

from refine.coords import (
    codepoint_to_lsp_char,
    lsp_char_to_codepoint,
    normalize_line_endings,
    split_into_lines,
)


@pytest.mark.parametrize(
    "line_text,lsp_char,expected_codepoint",
    [
        # Empty line — only valid offset is 0
        ("", 0, 0),
        # Pure ASCII — UTF-16 units == code points
        ("hello", 0, 0),
        ("hello", 1, 1),
        ("hello", 5, 5),
        ("hello", 100, 5),
        # Lean BMP characters (∀, ∃ are 1 UTF-16 unit each = 1 code point)
        ("∀ x, ∃ y", 0, 0),
        ("∀ x, ∃ y", 1, 1),
        ("∀ x, ∃ y", 5, 5),
        # Supplementary plane: 🎉 is 2 UTF-16 units = 1 code point
        ("ab🎉", 0, 0),
        ("ab🎉", 1, 1),
        ("ab🎉", 2, 2),
        ("ab🎉", 4, 3),
        ("ab🎉", 100, 3),
        # Mixed: ASCII + BMP + supplementary
        ("a∀🎉z", 0, 0),
        ("a∀🎉z", 1, 1),
        ("a∀🎉z", 2, 2),
        ("a∀🎉z", 4, 3),
        ("a∀🎉z", 5, 4),
    ],
    ids=[
        "empty_at_zero",
        "ascii_start",
        "ascii_mid",
        "ascii_end",
        "ascii_clamp_past_end",
        "bmp_start",
        "bmp_after_forall",
        "bmp_after_exists",
        "supp_start",
        "supp_after_a",
        "supp_at_emoji",
        "supp_after_emoji",
        "supp_clamp_past_end",
        "mixed_start",
        "mixed_after_ascii",
        "mixed_after_bmp",
        "mixed_after_supp",
        "mixed_end",
    ],
)
def test_lsp_char_to_codepoint(
    line_text: str, lsp_char: int, expected_codepoint: int
) -> None:
    assert lsp_char_to_codepoint(line_text, lsp_char) == expected_codepoint


def test_lsp_char_to_codepoint_raises_inside_surrogate_pair() -> None:
    """Offset 3 inside "ab🎉" lands between the emoji's surrogate halves."""
    with pytest.raises(ValueError, match="surrogate pair"):
        lsp_char_to_codepoint("ab🎉", 3)


def test_lsp_char_to_codepoint_rejects_negative_offset() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        lsp_char_to_codepoint("hello", -1)


@pytest.mark.parametrize(
    "line_text,codepoint,expected_lsp",
    [
        # Empty
        ("", 0, 0),
        # ASCII
        ("hello", 0, 0),
        ("hello", 5, 5),
        ("hello", 100, 5),
        # BMP
        ("∀ x", 0, 0),
        ("∀ x", 1, 1),
        ("∀ x", 3, 3),
        # Supplementary
        ("ab🎉", 0, 0),
        ("ab🎉", 1, 1),
        ("ab🎉", 2, 2),
        ("ab🎉", 3, 4),
        ("ab🎉", 100, 4),
        # Mixed
        ("a∀🎉z", 4, 5),
    ],
    ids=[
        "empty",
        "ascii_start",
        "ascii_end",
        "ascii_clamp",
        "bmp_start",
        "bmp_after_forall",
        "bmp_end",
        "supp_start",
        "supp_after_a",
        "supp_at_emoji",
        "supp_after_emoji",
        "supp_clamp",
        "mixed_end",
    ],
)
def test_codepoint_to_lsp_char(
    line_text: str, codepoint: int, expected_lsp: int
) -> None:
    assert codepoint_to_lsp_char(line_text, codepoint) == expected_lsp


def test_codepoint_to_lsp_char_rejects_negative_index() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        codepoint_to_lsp_char("hello", -1)


@pytest.mark.parametrize(
    "before,after",
    [
        ("a\nb", "a\nb"),
        ("a\r\nb", "a\nb"),
        ("a\rb", "a\nb"),
        ("a\r\nb\rc\nd", "a\nb\nc\nd"),
        ("", ""),
        ("no_terminator", "no_terminator"),
    ],
    ids=["lf", "crlf", "bare_cr", "mixed", "empty", "no_terminator"],
)
def test_normalize_line_endings(before: str, after: str) -> None:
    assert normalize_line_endings(before) == after


def test_normalize_line_endings_is_idempotent() -> None:
    once = normalize_line_endings("a\r\nb\rc")
    assert normalize_line_endings(once) == once


@pytest.mark.parametrize(
    "content,expected_lines",
    [
        ("", [""]),
        ("a", ["a"]),
        ("a\nb", ["a", "b"]),
        ("a\nb\n", ["a", "b", ""]),
        ("a\r\nb\rc", ["a", "b", "c"]),
    ],
    ids=[
        "empty",
        "single_no_newline",
        "two_no_trailing",
        "two_with_trailing",
        "mixed_terminators",
    ],
)
def test_split_into_lines(content: str, expected_lines: list[str]) -> None:
    assert split_into_lines(content) == expected_lines


def test_round_trip_lsp_codepoint_lsp_is_identity_for_valid_offsets() -> None:
    """Catches asymmetry bugs: any valid LSP offset must survive the round trip."""
    line = "ab🎉c∀d"
    # UTF-16 units: a(1) + b(1) + 🎉(2) + c(1) + ∀(1) + d(1) = 7 total.
    # Valid (non-mid-surrogate) offsets: 0, 1, 2, 4, 5, 6, 7.
    for lsp_char in (0, 1, 2, 4, 5, 6, 7):
        codepoint = lsp_char_to_codepoint(line, lsp_char)
        assert codepoint_to_lsp_char(line, codepoint) == lsp_char
