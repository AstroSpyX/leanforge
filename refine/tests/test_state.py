"""Tests for refine.state — enums and dataclasses."""

import pytest

from refine.state import (
    FailureReason,
    GoalStatus,
    History,
    IterationState,
    Status,
    WarningReason,
)


def _iteration(iter_num: int = 0, status: Status = Status.INITIAL) -> IterationState:
    """Construct a minimal IterationState for tests that only need identity."""
    return IterationState(
        iteration=iter_num,
        status=status,
        goal_status=GoalStatus.UNCHANGED,
        file_content="",
        file_sha256="",
        state_hash="",
        raw_diagnostics=[],
        canonical_diagnostics=[],
        diagnostics_fingerprints=[],
        error_count=0,
        warning_count=0,
        resolved_count=0,
        new_count=0,
        persistent_count=0,
        prompt_sha256="",
        response_sha256="",
        retry_count=0,
        model="sonnet",
        provider="anthropic",
        provider_model_id="claude-sonnet-4-6",
        temperature=0.0,
        llm_summary="",
        llm_strategy="",
        llm_confidence=0.0,
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
        cumulative_cost_usd=0.0,
        cumulative_input_tokens=0,
        cumulative_output_tokens=0,
        elapsed_ms=0,
    )


@pytest.mark.parametrize("value", [s.value for s in Status])
def test_every_status_value_round_trips(value: str) -> None:
    """Status values are written to history.jsonl — typos break replay."""
    assert Status(value).value == value


@pytest.mark.parametrize("value", [r.value for r in FailureReason])
def test_every_failure_reason_round_trips(value: str) -> None:
    assert FailureReason(value).value == value


@pytest.mark.parametrize("value", [w.value for w in WarningReason])
def test_every_warning_reason_round_trips(value: str) -> None:
    assert WarningReason(value).value == value


@pytest.mark.parametrize("value", [g.value for g in GoalStatus])
def test_every_goal_status_round_trips(value: str) -> None:
    assert GoalStatus(value).value == value


def test_history_latest_is_none_when_empty() -> None:
    history = History(
        project_root="/p",
        file_relpath="f.lean",
        goal="prove it",
        original_content="",
        env_fingerprint="abc",
        prompt_version="repair_v1",
    )
    assert history.latest is None


def test_history_latest_returns_last_iteration() -> None:
    history = History(
        project_root="/p",
        file_relpath="f.lean",
        goal="prove it",
        original_content="",
        env_fingerprint="abc",
        prompt_version="repair_v1",
    )
    history.iterations.append(_iteration(iter_num=0))
    history.iterations.append(_iteration(iter_num=1))
    history.iterations.append(_iteration(iter_num=2))
    assert history.latest is not None
    assert history.latest.iteration == 2


def test_iteration_state_carries_all_serializable_fields() -> None:
    """Catches accidental dataclass field deletions that would break the
    history.jsonl writer downstream."""
    state = _iteration()
    expected_fields = {
        "iteration",
        "status",
        "goal_status",
        "file_content",
        "file_sha256",
        "state_hash",
        "raw_diagnostics",
        "canonical_diagnostics",
        "diagnostics_fingerprints",
        "error_count",
        "warning_count",
        "resolved_count",
        "new_count",
        "persistent_count",
        "prompt_sha256",
        "response_sha256",
        "retry_count",
        "model",
        "provider",
        "provider_model_id",
        "temperature",
        "llm_summary",
        "llm_strategy",
        "llm_confidence",
        "llm_reasoning",
        "llm_intended_scope",
        "system_intended_scope",
        "edits_applied",
        "remaining_blockers",
        "hard_violations",
        "soft_warnings",
        "scope_warnings",
        "input_tokens",
        "output_tokens",
        "cache_creation_tokens",
        "cache_read_tokens",
        "base_cost_usd",
        "retry_multiplier",
        "cost_usd",
        "cumulative_cost_usd",
        "cumulative_input_tokens",
        "cumulative_output_tokens",
        "elapsed_ms",
        "cached",
        "started_at",
        "finished_at",
    }
    actual_fields = {f for f in state.__dataclass_fields__}
    assert actual_fields == expected_fields
