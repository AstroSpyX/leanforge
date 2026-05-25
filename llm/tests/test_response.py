"""Tests for the Response and ToolCall dataclasses."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from llm.response import Response, ToolCall


class TestToolCall:
    def test_frozen_for_hashability(self) -> None:
        call = ToolCall(id="x", name="t", input={"a": 1})
        with pytest.raises(FrozenInstanceError):
            call.id = "y"  # type: ignore[misc]


class TestResponse:
    def test_tool_calls_defaults_to_empty_list(self) -> None:
        """A pure-text response has no tool calls but the field is always
        a list (never None) so callers can iterate unconditionally."""
        r = Response(
            text="hi",
            model="m",
            provider="p",
            provider_model_id="id",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            stop_reason="end_turn",
            cached=False,
        )
        assert r.tool_calls == []
