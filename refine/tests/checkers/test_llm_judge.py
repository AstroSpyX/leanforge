"""Tests for LLMJudgeChecker — judge LLM call is mocked at llm.ask."""

from __future__ import annotations

from unittest.mock import patch

from llm.response import Response, ToolCall
from refine.checkers.llm_judge import LLMJudgeChecker


def _judge_response(verdict: dict) -> Response:
    return Response(
        text="",
        model="haiku",
        provider="anthropic",
        provider_model_id="claude-haiku-4-5",
        latency_ms=10,
        input_tokens=100,
        output_tokens=20,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        stop_reason="tool_use",
        cached=False,
        tool_calls=[ToolCall(id="t1", name="judge_goal", input=verdict)],
    )


class TestLLMJudgeChecker:
    def test_passes_when_judge_returns_true(self) -> None:
        checker = LLMJudgeChecker(name="j", model="haiku", goal="do it")
        verdict = {"passed": True, "reasoning": "done", "remaining_work": []}
        with patch(
            "refine.checkers.llm_judge.ask", return_value=_judge_response(verdict)
        ):
            result = checker.check("content", [])
        assert result.passed is True
        assert result.pseudo_diagnostics == []

    def test_fails_when_judge_returns_false_with_remaining_work(self) -> None:
        checker = LLMJudgeChecker(name="j", model="haiku", goal="do it")
        verdict = {
            "passed": False,
            "reasoning": "missing X and Y",
            "remaining_work": ["finish theorem A", "remove sorry in B"],
        }
        with patch(
            "refine.checkers.llm_judge.ask", return_value=_judge_response(verdict)
        ):
            result = checker.check("content", [])
        assert result.passed is False
        # 1 reasoning entry + 2 remaining_work items
        assert len(result.pseudo_diagnostics) == 3
        for d in result.pseudo_diagnostics:
            assert "llm_judge[j]" in d["messageText"]

    def test_fails_when_no_tool_call_returned(self) -> None:
        """Defense in depth: if a provider regression breaks strict
        tool use and the judge returns plain text, surface clearly."""
        empty_response = Response(
            text="I cannot decide",
            model="haiku",
            provider="anthropic",
            provider_model_id="claude-haiku-4-5",
            latency_ms=10,
            input_tokens=100,
            output_tokens=10,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            stop_reason="end_turn",
            cached=False,
            tool_calls=[],
        )
        checker = LLMJudgeChecker(name="j", model="haiku", goal="do it")
        with patch("refine.checkers.llm_judge.ask", return_value=empty_response):
            result = checker.check("content", [])
        assert result.passed is False
        assert any(
            "did not return a tool_call" in d["messageText"]
            for d in result.pseudo_diagnostics
        )

    def test_invokes_ask_with_judge_tool_and_forced_choice(self) -> None:
        """Sanity check the call shape."""
        checker = LLMJudgeChecker(name="j", model="haiku", goal="make file compile")
        verdict = {"passed": True, "reasoning": "ok", "remaining_work": []}
        with patch(
            "refine.checkers.llm_judge.ask", return_value=_judge_response(verdict)
        ) as mock_ask:
            checker.check("the file", [])
        kwargs = mock_ask.call_args.kwargs
        assert kwargs["model"] == "haiku"
        assert kwargs["tool_choice"] == "judge_goal"
        assert len(kwargs["tools"]) == 1
        assert kwargs["tools"][0].name == "judge_goal"
