"""Tests for the pure-function helpers inside refine.controller.

The full `refine()` orchestrator is exercised by the integration smoke
test (refine/tests/test_smoke.py), which requires a live ANTHROPIC_API_KEY
and a working Lean toolchain. The helpers below are testable in isolation
and cover the convergence / classification logic.
"""

import pytest

from llm.ask_llm import AskLLMError
from refine.controller import (
    _classify_status,
    _compute_state_hash,
    _count_by_severity,
    _describe_rejection,
    _extract_json_object,
    _parse_response_or_fail,
    _progress_counts,
    _unique_enclosing_decl_names,
)
from refine.outcome import Outcome
from refine.state import Status


def _diag(severity: int = 1, decl: str | None = None) -> dict:
    diag: dict = {"severity": severity, "messageText": "x"}
    if decl is not None:
        diag["enclosingDeclaration"] = {"name": decl}
    return diag


class TestCountBySeverity:
    def test_separates_errors_and_warnings(self) -> None:
        errs, warns = _count_by_severity(
            [_diag(severity=1), _diag(severity=1), _diag(severity=2)]
        )
        assert errs == 2
        assert warns == 1

    def test_other_severities_ignored(self) -> None:
        errs, warns = _count_by_severity([_diag(severity=3), _diag(severity=4)])
        assert errs == 0
        assert warns == 0


class TestProgressCounts:
    def test_disjoint_fingerprints(self) -> None:
        resolved, new, persistent = _progress_counts({"a", "b"}, {"c", "d"})
        assert resolved == 2 and new == 2 and persistent == 0

    def test_full_overlap(self) -> None:
        resolved, new, persistent = _progress_counts({"a", "b"}, {"a", "b"})
        assert resolved == 0 and new == 0 and persistent == 2

    def test_partial_overlap(self) -> None:
        resolved, new, persistent = _progress_counts({"a", "b", "c"}, {"b", "d"})
        assert resolved == 2 and new == 1 and persistent == 1


class TestClassifyStatus:
    def test_success_when_no_errors_and_no_violations(self) -> None:
        assert _classify_status(Outcome.SUCCESS, 0, 0, 0, []) == Status.SUCCESS

    def test_policy_violation_wins_over_success(self) -> None:
        """Hard violations rollback even when the file 'compiles' (which
        happens when sorry was introduced — Lean reports it as a warning
        but the controller still rejects)."""
        assert (
            _classify_status(Outcome.SUCCESS, 0, 0, 0, ["sorry:foo"])
            == Status.POLICY_VIOLATION
        )

    def test_timeout_classified_as_stuck_timeout(self) -> None:
        assert _classify_status(Outcome.TIMEOUT, 0, 0, 0, []) == Status.STUCK_TIMEOUT

    def test_progress_when_resolved_some_no_new(self) -> None:
        assert _classify_status(Outcome.ELAB_ERROR, 1, 2, 0, []) == Status.PROGRESS

    def test_regression_when_more_new_than_resolved(self) -> None:
        assert _classify_status(Outcome.ELAB_ERROR, 5, 1, 4, []) == Status.REGRESSION

    def test_no_change_when_nothing_moved(self) -> None:
        assert _classify_status(Outcome.ELAB_ERROR, 3, 0, 0, []) == Status.NO_CHANGE

    def test_progress_when_resolved_and_new_overlap(self) -> None:
        """resolved + new both > 0 means churn-ish, but still net forward
        if resolved >= new — controller's v1 calls that PROGRESS."""
        assert _classify_status(Outcome.ELAB_ERROR, 3, 2, 2, []) == Status.PROGRESS


class TestComputeStateHash:
    def test_same_content_same_fps_same_hash(self) -> None:
        a = _compute_state_hash("file", ["fp1", "fp2"])
        b = _compute_state_hash("file", ["fp1", "fp2"])
        assert a == b

    def test_fingerprint_order_does_not_matter(self) -> None:
        """state_hash is on the sorted fingerprint set; the LLM ordering
        of diagnostics shouldn't change identity."""
        a = _compute_state_hash("file", ["fp1", "fp2"])
        b = _compute_state_hash("file", ["fp2", "fp1"])
        assert a == b

    def test_different_content_different_hash(self) -> None:
        a = _compute_state_hash("file1", ["fp"])
        b = _compute_state_hash("file2", ["fp"])
        assert a != b

    def test_different_fingerprints_different_hash(self) -> None:
        a = _compute_state_hash("file", ["fp1"])
        b = _compute_state_hash("file", ["fp2"])
        assert a != b


class TestUniqueEnclosingDeclNames:
    def test_preserves_first_occurrence_order(self) -> None:
        assert _unique_enclosing_decl_names(
            [_diag(decl="bad"), _diag(decl="foo"), _diag(decl="bad")]
        ) == ["bad", "foo"]

    def test_ignores_missing_enclosing(self) -> None:
        assert _unique_enclosing_decl_names([_diag()]) == []

    def test_ignores_non_string_names(self) -> None:
        diag = {"severity": 1, "enclosingDeclaration": {"name": 42}}
        assert _unique_enclosing_decl_names([diag]) == []


class TestDescribeRejection:
    def _state_with(self, **overrides):
        from refine.state import GoalStatus, IterationState

        defaults = dict(
            iteration=1,
            status=Status.POLICY_VIOLATION,
            goal_status=GoalStatus.UNCHANGED,
            file_content="",
            file_sha256="",
            state_hash="",
            raw_diagnostics=[],
            canonical_diagnostics=[],
            diagnostics_fingerprints=[],
            error_count=2,
            warning_count=0,
            resolved_count=0,
            new_count=0,
            persistent_count=2,
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
            cumulative_cost_usd=0.0,
            cumulative_input_tokens=0,
            cumulative_output_tokens=0,
            elapsed_ms=0,
        )
        defaults.update(overrides)
        return IterationState(**defaults)

    def test_hard_violation_in_description(self) -> None:
        state = self._state_with(hard_violations=["sorry:foo"])
        assert "sorry:foo" in _describe_rejection(state)

    def test_status_summary_when_no_violations(self) -> None:
        state = self._state_with(status=Status.REGRESSION, error_count=5)
        text = _describe_rejection(state)
        assert "regression" in text
        assert "5" in text


_VALID_PAYLOAD = (
    '{"summary":"x","strategy":"other","reasoning":"x","confidence":0.5,'
    '"intended_scope":[],"fixes":[],"remaining_blockers":[]}'
)


class TestExtractJsonObject:
    def test_pure_json_passes_through(self) -> None:
        assert _extract_json_object(_VALID_PAYLOAD) == _VALID_PAYLOAD

    def test_prose_prefix_is_stripped(self) -> None:
        prose = "Looking at the diagnostics, I will fix this.\n\n"
        text = prose + _VALID_PAYLOAD
        assert _extract_json_object(text) == _VALID_PAYLOAD

    def test_markdown_fence_prefix_is_stripped(self) -> None:
        text = "```json\n" + _VALID_PAYLOAD + "\n```"
        assert _extract_json_object(text) == _VALID_PAYLOAD

    def test_trailing_prose_is_stripped(self) -> None:
        text = _VALID_PAYLOAD + "\n\nLet me know if you need adjustments."
        assert _extract_json_object(text) == _VALID_PAYLOAD

    def test_missing_brace_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="no opening brace"):
            _extract_json_object("just prose, no json here")

    def test_unterminated_json_raises_value_error(self) -> None:
        """raw_decode raises JSONDecodeError (a ValueError) on truncated input."""
        with pytest.raises(ValueError):
            _extract_json_object('Some prose. {"summary":"x", ')


class TestParseResponseOrFail:
    def test_clean_json_parses(self) -> None:
        response = _parse_response_or_fail(_VALID_PAYLOAD)
        assert response.summary == "x"

    def test_prose_wrapped_json_parses(self) -> None:
        """The real bug from v1.0.6: Claude prefixed its JSON with
        'Looking at the diagnostics...' and the extractor must strip it."""
        text = (
            "Looking at the diagnostics, I'll fix pow_add by inducting on n.\n\n"
            + _VALID_PAYLOAD
        )
        response = _parse_response_or_fail(text)
        assert response.summary == "x"

    def test_no_json_raises_typed_error(self) -> None:
        with pytest.raises(AskLLMError, match="no JSON object"):
            _parse_response_or_fail("just prose, no JSON here")

    def test_schema_invalid_raises_typed_error(self) -> None:
        with pytest.raises(AskLLMError, match="did not match RefineResponse schema"):
            _parse_response_or_fail('{"not_a_refine_response": true}')
