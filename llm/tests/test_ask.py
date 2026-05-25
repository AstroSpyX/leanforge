"""Tests for the `llm.ask` dispatcher.

The dispatcher's responsibilities:
  1. Reject unknown models.
  2. Route to the correct provider based on cfg.provider.
  3. Include tools / tool_choice in the cache key.
  4. Reconstruct ToolCall objects on cache hits.

Real upstream calls are mocked at the provider-adapter layer.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from llm import ToolSpec, ask
from llm.ask import _build_cache_key, _response_from_cache_hit
from llm.response import Response, ToolCall


class TestCacheKey:
    def test_tools_included_in_key(self) -> None:
        """Same prompt + different tools = different cache entries."""
        key_no_tools = _build_cache_key(
            provider_model_id="m",
            system=None,
            prompt="p",
            temperature=0.0,
            max_tokens=100,
            tools=None,
            tool_choice=None,
        )
        key_with_tools = _build_cache_key(
            provider_model_id="m",
            system=None,
            prompt="p",
            temperature=0.0,
            max_tokens=100,
            tools=[ToolSpec(name="t", description="d", input_schema={})],
            tool_choice="t",
        )
        assert key_no_tools != key_with_tools

    def test_tool_choice_changes_key(self) -> None:
        tool = ToolSpec(name="t", description="d", input_schema={})
        key_auto = _build_cache_key(
            provider_model_id="m",
            system=None,
            prompt="p",
            temperature=0.0,
            max_tokens=100,
            tools=[tool],
            tool_choice="auto",
        )
        key_forced = _build_cache_key(
            provider_model_id="m",
            system=None,
            prompt="p",
            temperature=0.0,
            max_tokens=100,
            tools=[tool],
            tool_choice="t",
        )
        assert key_auto != key_forced


class TestCacheHitReconstruction:
    def test_tool_calls_rebuilt_from_dicts(self) -> None:
        """Cache stores tool_calls as dicts; on hit reconstruct ToolCall."""
        cached = {
            "text": "",
            "model": "sonnet",
            "provider": "anthropic",
            "provider_model_id": "claude-sonnet-4-6",
            "latency_ms": 0,
            "input_tokens": 1,
            "output_tokens": 2,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "stop_reason": "tool_use",
            "cached": False,
            "tool_calls": [{"id": "tu_01", "name": "submit_fix", "input": {"x": 1}}],
        }
        response = _response_from_cache_hit(cached)
        assert isinstance(response, Response)
        assert response.cached is True
        assert len(response.tool_calls) == 1
        assert isinstance(response.tool_calls[0], ToolCall)
        assert response.tool_calls[0].id == "tu_01"


class TestDispatch:
    def test_unknown_model_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="unknown model"):
            ask("p", model="nonexistent", use_cache=False)

    def test_anthropic_model_routed_to_anthropic_provider(self) -> None:
        sentinel = Response(
            text="hi",
            model="sonnet",
            provider="anthropic",
            provider_model_id="claude-sonnet-4-6",
            latency_ms=1,
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            stop_reason="end_turn",
            cached=False,
            tool_calls=[],
        )
        with patch("llm.providers.anthropic.call", return_value=sentinel) as mock_call:
            response = ask("p", model="sonnet", use_cache=False)
        assert response is sentinel
        assert mock_call.called
        called_kwargs = mock_call.call_args.kwargs
        assert called_kwargs["registry_key"] == "sonnet"

    def test_google_model_routed_to_google_provider(self) -> None:
        sentinel = Response(
            text="hi",
            model="gemini-flash",
            provider="google",
            provider_model_id="gemini-3.5-flash",
            latency_ms=1,
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            stop_reason="STOP",
            cached=False,
            tool_calls=[],
        )

        def fake_call(**kwargs: Any) -> Response:
            return sentinel

        with patch("llm.providers.google.call", side_effect=fake_call) as mock_call:
            response = ask("p", model="gemini-flash", use_cache=False)
        assert response is sentinel
        assert mock_call.called
