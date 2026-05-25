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
    _anthropic_strict_compat_schema,
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


class TestAnthropicStrictCompatSchema:
    def test_minimum_maximum_stripped_on_numbers(self) -> None:
        """Anthropic strict mode: 'For number type, properties maximum,
        minimum are not supported'. We strip; client-side Pydantic
        validation still enforces the constraint."""
        schema = {
            "type": "object",
            "properties": {
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        }
        result = _anthropic_strict_compat_schema(schema)
        conf = result["properties"]["confidence"]
        assert "minimum" not in conf
        assert "maximum" not in conf
        assert conf["type"] == "number"

    def test_strips_string_constraints(self) -> None:
        schema = {"type": "string", "minLength": 1, "maxLength": 100, "pattern": "^x"}
        result = _anthropic_strict_compat_schema(schema)
        assert result == {"type": "string"}

    def test_strips_nested_constraints(self) -> None:
        """The transform must walk into nested objects."""
        schema = {
            "type": "object",
            "properties": {
                "fixes": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "integer", "minimum": 0},
                }
            },
        }
        result = _anthropic_strict_compat_schema(schema)
        assert "minItems" not in result["properties"]["fixes"]
        assert "minimum" not in result["properties"]["fixes"]["items"]

    def test_preserves_supported_keywords(self) -> None:
        """type, properties, required, enum, additionalProperties stay."""
        schema = {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["a", "b"]},
            },
            "required": ["kind"],
            "additionalProperties": False,
        }
        result = _anthropic_strict_compat_schema(schema)
        assert result == schema  # nothing stripped


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

    def test_strict_strips_unsupported_constraints(self) -> None:
        """A strict spec whose schema has minimum/maximum gets cleaned up
        before being sent to Anthropic."""
        spec = ToolSpec(
            name="t",
            description="d",
            input_schema={"type": "number", "minimum": 0.0, "maximum": 1.0},
            strict=True,
        )
        sent = _to_anthropic_tools([spec])[0]["input_schema"]
        assert "minimum" not in sent
        assert "maximum" not in sent

    def test_strict_false_preserves_schema_as_is(self) -> None:
        """Non-strict tools keep their constraints — those are only
        rejected by strict mode."""
        spec = ToolSpec(
            name="t",
            description="d",
            input_schema={"type": "number", "minimum": 0.0},
            strict=False,
        )
        sent = _to_anthropic_tools([spec])[0]["input_schema"]
        assert sent == {"type": "number", "minimum": 0.0}
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
