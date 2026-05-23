"""Tests for refine.diff_summary — textual diff stats over file content."""

import pytest

from refine.diff_summary import TextDiffStats, compute_text_diff


def test_no_change_returns_zero_stats() -> None:
    stats = compute_text_diff("a\nb\nc", "a\nb\nc")
    assert stats == TextDiffStats(0, 0, 0, 0)


def test_single_line_addition() -> None:
    stats = compute_text_diff("a\nb", "a\nb\nc")
    assert stats.lines_added == 1
    assert stats.lines_removed == 0
    assert stats.lines_changed == 0  # min(added, removed) = 0


def test_single_line_removal() -> None:
    stats = compute_text_diff("a\nb\nc", "a\nb")
    assert stats.lines_added == 0
    assert stats.lines_removed == 1


def test_single_line_replacement_counts_as_one_add_and_one_remove() -> None:
    stats = compute_text_diff("a\nb\nc", "a\nX\nc")
    assert stats.lines_added == 1
    assert stats.lines_removed == 1
    assert stats.lines_changed == 1  # min(1, 1)


def test_line_ending_variation_does_not_inflate_diff() -> None:
    """CRLF vs LF on identical content should produce zero diff."""
    stats = compute_text_diff("a\r\nb\r\nc", "a\nb\nc")
    assert stats == TextDiffStats(0, 0, 0, 0)


@pytest.mark.parametrize(
    "before,after,expected_max_block",
    [
        ("a", "a", 0),
        # One contiguous block of 3 added lines
        ("a\nz", "a\nb\nc\nd\nz", 3),
        # Two separate replacements (a→X and d→Y); each is one -/one + so
        # the contiguous diff block is 2 lines per replacement.
        ("a\nb\nc\nd", "X\nb\nc\nY", 2),
    ],
    ids=["no_edits", "one_block_of_three", "two_blocks_of_two"],
)
def test_max_edit_size_lines(before: str, after: str, expected_max_block: int) -> None:
    stats = compute_text_diff(before, after)
    assert stats.max_edit_size_lines == expected_max_block


def test_empty_before_to_content_after() -> None:
    """An empty 'before' string splits into [''], so unified_diff sees it as
    one empty line removed plus the new lines added."""
    stats = compute_text_diff("", "a\nb")
    assert stats.lines_added >= 2
