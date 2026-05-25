"""Tests for the Google Gemini provider adapter.

Focused on pure translation helpers (no API calls):
  - ToolSpec → Gemini types.Tool
  - tool_choice string → Gemini types.ToolConfig
  - Gemini response → text + ToolCall extraction
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from llm.providers.google import (
    _extract_text,
    _extract_tool_calls,
    _gemini_compat_schema,
    _to_gemini_tool_config,
    _to_gemini_tools,
)
from llm.tools import ToolSpec


def _mock_part_text(text: str) -> Any:
    return SimpleNamespace(text=text, function_call=None)


def _mock_part_function_call(name: str, args: dict[str, Any], id_: str | None) -> Any:
    fc = SimpleNamespace(name=name, args=args, id=id_)
    return SimpleNamespace(text=None, function_call=fc)


def _mock_candidate(parts: list[Any]) -> Any:
    return SimpleNamespace(content=SimpleNamespace(parts=parts), finish_reason="STOP")


def _mock_response(candidates: list[Any]) -> Any:
    return SimpleNamespace(candidates=candidates)


class TestGeminiCompatSchema:
    def test_const_rewritten_as_enum(self) -> None:
        """Pydantic emits `const` for Literal[...] types; Gemini's Schema
        Pydantic model has no `const` field and rejects it. Convert
        to the semantically equivalent single-element enum."""
        schema = {"type": "string", "const": "replace_range"}
        result = _gemini_compat_schema(schema)
        assert "const" not in result
        assert result["enum"] == ["replace_range"]

    def test_const_at_nested_depth_rewritten(self) -> None:
        """The transform must walk into nested objects and arrays."""
        schema = {
            "type": "object",
            "properties": {
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"kind": {"const": "x"}},
                    },
                }
            },
        }
        result = _gemini_compat_schema(schema)
        kind_schema = result["properties"]["edits"]["items"]["properties"]["kind"]
        assert kind_schema == {"enum": ["x"]}

    def test_existing_enum_not_overwritten(self) -> None:
        """If both const and enum somehow coexist, enum wins (we don't
        clobber an explicit choice)."""
        schema = {"const": "x", "enum": ["a", "b"]}
        result = _gemini_compat_schema(schema)
        assert result == {"enum": ["a", "b"]}

    def test_input_dict_not_mutated(self) -> None:
        """Caller's dict is preserved (we deepcopy before walking)."""
        schema = {"const": "x"}
        _gemini_compat_schema(schema)
        assert schema == {"const": "x"}

    def test_additional_properties_stripped(self) -> None:
        """Gemini's upstream API rejects additionalProperties as an
        unknown field; Anthropic strict mode requires it. We strip
        for Gemini, keep for Anthropic."""
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "nested": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {},
                }
            },
        }
        result = _gemini_compat_schema(schema)
        assert "additionalProperties" not in result
        assert "additionalProperties" not in result["properties"]["nested"]


class TestToGeminiTools:
    def test_packs_all_specs_into_one_tool_with_function_declarations(self) -> None:
        spec_a = ToolSpec(name="a", description="A", input_schema={"type": "object"})
        spec_b = ToolSpec(name="b", description="B", input_schema={"type": "object"})
        tool = _to_gemini_tools([spec_a, spec_b])
        assert len(tool.function_declarations) == 2
        assert tool.function_declarations[0].name == "a"
        assert tool.function_declarations[1].name == "b"


class TestToGeminiToolConfig:
    def test_auto_sets_mode_auto(self) -> None:
        cfg = _to_gemini_tool_config("auto")
        assert cfg.function_calling_config.mode == "AUTO"
        assert cfg.function_calling_config.allowed_function_names is None

    def test_any_sets_mode_any_unrestricted(self) -> None:
        cfg = _to_gemini_tool_config("any")
        assert cfg.function_calling_config.mode == "ANY"
        assert cfg.function_calling_config.allowed_function_names is None

    def test_specific_name_restricts_to_that_function(self) -> None:
        cfg = _to_gemini_tool_config("submit_fix")
        assert cfg.function_calling_config.mode == "ANY"
        assert cfg.function_calling_config.allowed_function_names == ["submit_fix"]


class TestExtractText:
    def test_concatenates_text_parts(self) -> None:
        resp = _mock_response(
            [_mock_candidate([_mock_part_text("Hi "), _mock_part_text("there.")])]
        )
        assert _extract_text(resp) == "Hi there."

    def test_returns_empty_when_only_function_calls(self) -> None:
        resp = _mock_response(
            [_mock_candidate([_mock_part_function_call("x", {}, "id1")])]
        )
        assert _extract_text(resp) == ""


class TestExtractToolCalls:
    def test_collects_function_calls_with_ids(self) -> None:
        resp = _mock_response(
            [
                _mock_candidate(
                    [
                        _mock_part_text("prose"),
                        _mock_part_function_call("submit_fix", {"a": 1}, "id1"),
                    ]
                )
            ]
        )
        calls = _extract_tool_calls(resp)
        assert len(calls) == 1
        assert calls[0].name == "submit_fix"
        assert calls[0].input == {"a": 1}
        assert calls[0].id == "id1"

    def test_synthesizes_id_when_provider_omits_one(self) -> None:
        """Gemini's function_call.id is optional; we still need a stable
        round-trip identifier for the function_response part."""
        resp = _mock_response(
            [_mock_candidate([_mock_part_function_call("submit_fix", {}, None)])]
        )
        calls = _extract_tool_calls(resp)
        assert calls[0].id == "gemini-call-0"
