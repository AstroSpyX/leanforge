"""Tests for the position_to_offset and utf16_length additions to coords."""

import pytest

from refine.coords import position_to_offset, utf16_length


@pytest.mark.parametrize(
    "line_text,expected_units",
    [
        ("", 0),
        ("hello", 5),
        ("∀ x", 3),  # ∀ is 1 UTF-16 unit (BMP), space + x = 2
        ("a🎉b", 4),  # 🎉 is 2 UTF-16 units
    ],
    ids=["empty", "ascii", "bmp", "supplementary"],
)
def test_utf16_length(line_text: str, expected_units: int) -> None:
    assert utf16_length(line_text) == expected_units


class TestPositionToOffset:
    def test_first_line_first_column(self) -> None:
        assert position_to_offset("hello\nworld", 0, 0) == 0

    def test_first_line_mid_column(self) -> None:
        assert position_to_offset("hello\nworld", 0, 3) == 3

    def test_second_line_first_column(self) -> None:
        # "hello\n" is 6 code points; position (1, 0) starts at offset 6
        assert position_to_offset("hello\nworld", 1, 0) == 6

    def test_second_line_mid_column(self) -> None:
        assert position_to_offset("hello\nworld", 1, 2) == 8

    def test_line_past_eof_clamps_to_length(self) -> None:
        assert position_to_offset("hello", 99, 0) == 5

    def test_negative_line_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            position_to_offset("hello", -1, 0)

    def test_supplementary_plane_in_earlier_line(self) -> None:
        """🎉 on line 0 is 1 code point; line 1 still starts after it."""
        content = "🎉\nb"
        assert position_to_offset(content, 1, 0) == 2

    def test_supplementary_plane_in_current_line(self) -> None:
        """LSP char 4 on "a🎉b" is after the emoji (1+2+1=4 units)."""
        assert position_to_offset("a🎉b", 0, 4) == 3
