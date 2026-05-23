"""Tests for refine.goal_status — heuristic primary-goal change classification."""

from refine.goal_status import classify_goal_status
from refine.state import GoalStatus


def _error_with_goal(goal_text: str) -> dict:
    return {
        "severity": 1,
        "messageText": "x",
        "goal": {"rendered": goal_text},
    }


def _error_with_term_goal(goal_text: str) -> dict:
    return {
        "severity": 1,
        "messageText": "x",
        "termGoal": {"goal": goal_text},
    }


def _warning() -> dict:
    return {"severity": 2, "messageText": "warn"}


class TestClassifyGoalStatus:
    def test_resolved_when_no_current_errors(self) -> None:
        assert (
            classify_goal_status([_error_with_goal("⊢ Nat")], []) == GoalStatus.RESOLVED
        )

    def test_resolved_when_only_warnings(self) -> None:
        assert (
            classify_goal_status([_error_with_goal("⊢ Nat")], [_warning()])
            == GoalStatus.RESOLVED
        )

    def test_unchanged_when_goal_text_identical(self) -> None:
        prev = [_error_with_goal("h : Nat\n⊢ h + 0 = h")]
        curr = [_error_with_goal("h : Nat\n⊢ h + 0 = h")]
        assert classify_goal_status(prev, curr) == GoalStatus.UNCHANGED

    def test_progress_when_goal_shrinks_meaningfully(self) -> None:
        prev = [_error_with_goal("h : Nat\ng : h > 0\nk : Nat\n⊢ h + 0 = h")]
        curr = [_error_with_goal("⊢ h = h")]
        assert classify_goal_status(prev, curr) == GoalStatus.PROGRESS

    def test_progress_when_target_substring_preserved(self) -> None:
        """Same target wrapped in a shorter context is progress even if
        the total length didn't shrink dramatically."""
        prev = [_error_with_goal("h : Foo\n⊢ x = y")]
        curr = [_error_with_goal("g : Bar\n⊢ x = y")]
        # Same length, same target, different context — substring rule fires.
        assert classify_goal_status(prev, curr) == GoalStatus.PROGRESS

    def test_shifted_when_goal_differs_without_shrink_or_inclusion(self) -> None:
        prev = [_error_with_goal("⊢ x = y")]
        curr = [_error_with_goal("⊢ a + b = c")]
        assert classify_goal_status(prev, curr) == GoalStatus.SHIFTED

    def test_term_goal_used_as_fallback(self) -> None:
        prev = [_error_with_term_goal("expected Nat")]
        curr = [_error_with_term_goal("expected Nat")]
        assert classify_goal_status(prev, curr) == GoalStatus.UNCHANGED

    def test_empty_previous_goal_classified_as_shifted(self) -> None:
        """No prior goal text: any current goal is, by definition, not
        clearly simpler. Falls through to SHIFTED."""
        prev: list[dict] = []
        curr = [_error_with_goal("⊢ x = y")]
        # No errors in prev → still classified by current's presence.
        # But prev has no errors so... actually goal_status compares whatever
        # is there. Let's check: curr has errors, prev has none → primary goal
        # text for prev is "" — that triggers the empty-string short-circuit
        # in _is_clearly_simpler.
        assert classify_goal_status(prev, curr) == GoalStatus.SHIFTED

    def test_normalized_messages_compare_equal(self) -> None:
        """Differing metavar IDs shouldn't trick UNCHANGED detection."""
        prev = [_error_with_goal("⊢ ?m.123 = ?m.123")]
        curr = [_error_with_goal("⊢ ?m.999 = ?m.999")]
        assert classify_goal_status(prev, curr) == GoalStatus.UNCHANGED

    def test_goal_text_without_turnstile_falls_through_to_shifted(self) -> None:
        """_extract_target's no-`⊢` branch: when neither goal has a
        turnstile, the substring check uses the whole text — and a
        sufficiently different message lands as SHIFTED."""
        prev = [_error_with_goal("plain text without turnstile aaaaa")]
        curr = [_error_with_goal("entirely different content here bbbbb")]
        assert classify_goal_status(prev, curr) == GoalStatus.SHIFTED
