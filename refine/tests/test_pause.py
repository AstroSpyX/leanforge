"""Tests for refine.pause — interactive menu interpretation.

Each test injects stdin/stdout via the in_stream/out_stream parameters so
the prompt loop is fully testable without TTY shenanigans.
"""

import io

import pytest

from refine.pause import (
    CONFIRMATION_TOKEN,
    PauseChoice,
    prompt_user,
    render_status_block,
)
from refine.state import GoalStatus, IterationState, Status


def _state(
    iteration: int = 1,
    status: Status = Status.NO_CHANGE,
    goal_status: GoalStatus = GoalStatus.UNCHANGED,
    error_count: int = 2,
    cost_usd: float = 0.05,
) -> IterationState:
    return IterationState(
        iteration=iteration,
        status=status,
        goal_status=goal_status,
        file_content="",
        file_sha256="",
        state_hash="",
        raw_diagnostics=[],
        canonical_diagnostics=[],
        diagnostics_fingerprints=[],
        error_count=error_count,
        warning_count=0,
        resolved_count=1,
        new_count=0,
        persistent_count=error_count,
        prompt_sha256="",
        response_sha256="",
        retry_count=0,
        model="sonnet",
        provider="anthropic",
        provider_model_id="claude-sonnet-4-6",
        temperature=0.0,
        llm_summary="",
        llm_strategy="other",
        llm_confidence=0.5,
        llm_reasoning="",
        llm_intended_scope=[],
        system_intended_scope=[],
        edits_applied=0,
        remaining_blockers=[],
        hard_violations=[],
        soft_warnings=[],
        scope_warnings=[],
        input_tokens=0,
        output_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        base_cost_usd=0.0,
        retry_multiplier=1.0,
        cost_usd=0.0,
        cumulative_cost_usd=cost_usd,
        cumulative_input_tokens=0,
        cumulative_output_tokens=0,
        elapsed_ms=0,
    )


def _run(user_input: str) -> tuple[PauseChoice, str]:
    in_stream = io.StringIO(user_input)
    out_stream = io.StringIO()
    choice = prompt_user(_state(), in_stream=in_stream, out_stream=out_stream)
    return choice, out_stream.getvalue()


class TestRenderStatusBlock:
    def test_includes_iteration_and_status(self) -> None:
        block = render_status_block(_state(iteration=3, status=Status.CHURN))
        assert "iter 3" in block
        assert "churn" in block

    def test_includes_cost_formatted_to_four_decimals(self) -> None:
        block = render_status_block(_state(cost_usd=0.123456))
        assert "$0.1235" in block

    def test_hard_violations_line_only_when_present(self) -> None:
        block_without = render_status_block(_state())
        assert "hard violations" not in block_without

        state = _state()
        state_with = type(state)(**{**state.__dict__, "hard_violations": ["foo"]})
        block_with = render_status_block(state_with)
        assert "hard violations: foo" in block_with


class TestSimpleMenuChoices:
    @pytest.mark.parametrize(
        "key,expected_kind",
        [
            ("c", "continue"),
            ("a", "accept"),
            ("q", "quit"),
            ("s", "show"),
            ("d", "diags"),
            ("h", "history"),
            ("g", "diff"),
        ],
    )
    def test_one_letter_choices(self, key: str, expected_kind: str) -> None:
        choice, _ = _run(f"{key}\n")
        assert choice.kind == expected_kind
        assert choice.payload is None


class TestRevise:
    def test_revise_collects_followup_text(self) -> None:
        choice, _ = _run("r\nplease use simp\n")
        assert choice.kind == "revise"
        assert choice.payload == "please use simp"


class TestNudge:
    def test_nudge_accepts_valid_strategy(self) -> None:
        choice, _ = _run("n\ntactic_rewrite\n")
        assert choice.kind == "nudge"
        assert choice.payload == "tactic_rewrite"

    def test_nudge_rejects_unknown_strategy_as_noop(self) -> None:
        choice, output = _run("n\nmagic_unicorn\n")
        assert choice.kind == "noop"
        assert "unrecognized strategy" in output


class TestResetConfirmation:
    def test_reset_requires_YES_confirmation(self) -> None:
        choice, _ = _run(f"Q\n{CONFIRMATION_TOKEN}\n")
        assert choice.kind == "reset"

    def test_reset_cancelled_on_anything_else(self) -> None:
        choice, output = _run("Q\nno way\n")
        assert choice.kind == "noop"
        assert "cancelled" in output

    def test_reset_cancelled_on_lowercase_yes(self) -> None:
        """Confirmation is case-sensitive — `yes` is not the token."""
        choice, _ = _run("Q\nyes\n")
        assert choice.kind == "noop"


class TestBudget:
    def test_budget_accepts_numeric_value(self) -> None:
        choice, _ = _run("b\n2.50\n")
        assert choice.kind == "budget"
        assert choice.payload == "2.50"

    def test_budget_rejects_non_numeric_as_noop(self) -> None:
        choice, output = _run("b\nlots\n")
        assert choice.kind == "noop"
        assert "unrecognized budget" in output


class TestEmptyAndUnknown:
    def test_empty_input_is_noop(self) -> None:
        choice, _ = _run("")
        assert choice.kind == "noop"

    def test_unknown_first_letter_is_noop(self) -> None:
        choice, output = _run("z\n")
        assert choice.kind == "noop"
        assert "unrecognized" in output
