"""Tests for the Anthropic provider adapter.

Focused on the pure translation helpers (no API calls):
  - ToolSpec → Anthropic tool dict (with strict)
  - tool_choice string → Anthropic tool_choice dict
  - Anthropic Message → text + ToolCall extraction
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from llm.providers.anthropic import (
    _extract_text,
    _extract_tool_calls,
    _to_anthropic_tool_choice,
    _to_anthropic_tools,
)
from llm.tools import ToolSpec


def _mock_text_block(text: str) -> Any:
    return SimpleNamespace(type="text", text=text)


def _mock_tool_use_block(id_: str, name: str, input_: dict[str, Any]) -> Any:
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def _mock_message(content: list[Any]) -> Any:
    return SimpleNamespace(content=content)


class TestToAnthropicTools:
    def test_passes_name_description_schema_and_strict(self) -> None:
        spec = ToolSpec(
            name="search",
            description="search a thing",
            input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
            strict=True,
        )
        result = _to_anthropic_tools([spec])
        assert result == [
            {
                "name": "search",
                "description": "search a thing",
                "input_schema": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                },
                "strict": True,
            }
        ]

    def test_strict_false_passes_through(self) -> None:
        spec = ToolSpec(name="x", description="d", input_schema={}, strict=False)
        assert _to_anthropic_tools([spec])[0]["strict"] is False


class TestToAnthropicToolChoice:
    def test_auto_maps_to_auto_type(self) -> None:
        assert _to_anthropic_tool_choice("auto") == {"type": "auto"}

    def test_any_maps_to_any_type(self) -> None:
        assert _to_anthropic_tool_choice("any") == {"type": "any"}

    def test_specific_name_maps_to_tool_type(self) -> None:
        assert _to_anthropic_tool_choice("submit_fix") == {
            "type": "tool",
            "name": "submit_fix",
        }


class TestExtractText:
    def test_concatenates_text_blocks(self) -> None:
        msg = _mock_message([_mock_text_block("Hello "), _mock_text_block("world.")])
        assert _extract_text(msg) == "Hello world."

    def test_skips_tool_use_blocks(self) -> None:
        msg = _mock_message(
            [
                _mock_text_block("I'll search."),
                _mock_tool_use_block("t1", "search", {"q": "x"}),
            ]
        )
        assert _extract_text(msg) == "I'll search."


class TestExtractToolCalls:
    def test_collects_every_tool_use_block(self) -> None:
        msg = _mock_message(
            [
                _mock_text_block("prose"),
                _mock_tool_use_block("t1", "search", {"q": "x"}),
                _mock_tool_use_block("t2", "submit_fix", {"summary": "y"}),
            ]
        )
        calls = _extract_tool_calls(msg)
        assert len(calls) == 2
        assert calls[0].id == "t1"
        assert calls[0].name == "search"
        assert calls[0].input == {"q": "x"}
        assert calls[1].name == "submit_fix"

    def test_empty_when_only_text(self) -> None:
        msg = _mock_message([_mock_text_block("just prose")])
        assert _extract_tool_calls(msg) == []
