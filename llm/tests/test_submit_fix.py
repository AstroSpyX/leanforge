"""Tests for the submit_fix tool spec.

The schema is derived from `refine.schema.RefineResponse` at import
time and post-processed for cross-provider strict-mode compatibility.
These tests pin the contract: no $refs, additionalProperties:false
on every object level, top-level required fields present.
"""

from __future__ import annotations

from typing import Any

from llm.tools.submit_fix import SUBMIT_FIX_TOOL


def _walk_objects(node: Any) -> list[dict[str, Any]]:
    """Return every dict inside `node` whose `type` is `object`."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            found.append(node)
        for v in node.values():
            found.extend(_walk_objects(v))
    elif isinstance(node, list):
        for v in node:
            found.extend(_walk_objects(v))
    return found


def _find_refs(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            if isinstance(ref, str):
                found.append(ref)
        for v in node.values():
            found.extend(_find_refs(v))
    elif isinstance(node, list):
        for v in node:
            found.extend(_find_refs(v))
    return found


class TestSubmitFixSchema:
    def test_tool_name_is_submit_fix(self) -> None:
        assert SUBMIT_FIX_TOOL.name == "submit_fix"

    def test_strict_is_true(self) -> None:
        """Strict mode is the whole point — provider enforces schema."""
        assert SUBMIT_FIX_TOOL.strict is True

    def test_top_level_object_type(self) -> None:
        schema = SUBMIT_FIX_TOOL.input_schema
        assert schema.get("type") == "object"

    def test_no_refs_remain_in_schema(self) -> None:
        """Anthropic strict mode requires self-contained schemas."""
        refs = _find_refs(SUBMIT_FIX_TOOL.input_schema)
        assert refs == [], f"unresolved refs: {refs}"

    def test_no_defs_block(self) -> None:
        """After inlining we strip $defs / definitions."""
        schema = SUBMIT_FIX_TOOL.input_schema
        assert "$defs" not in schema
        assert "definitions" not in schema

    def test_additional_properties_false_everywhere(self) -> None:
        """Lock down every object level — Bugs 12 and 13 cannot recur."""
        for obj in _walk_objects(SUBMIT_FIX_TOOL.input_schema):
            assert obj.get("additionalProperties") is False, (
                f"object missing additionalProperties:false: "
                f"{sorted(obj.get('properties', {}).keys())}"
            )

    def test_top_level_required_fields(self) -> None:
        """All RefineResponse fields without defaults must be required."""
        required = set(SUBMIT_FIX_TOOL.input_schema.get("required", []))
        # These are the fields without defaults on RefineResponse:
        for field in (
            "summary",
            "strategy",
            "reasoning",
            "confidence",
            "intended_scope",
            "fixes",
            "remaining_blockers",
        ):
            assert field in required, f"{field} missing from top-level required list"

    def test_remaining_blockers_is_array_of_strings(self) -> None:
        """The schema commits us to strings, not ints — strict mode
        means the model literally cannot emit ints here."""
        schema = SUBMIT_FIX_TOOL.input_schema
        blockers = schema["properties"]["remaining_blockers"]
        assert blockers["type"] == "array"
        assert blockers["items"]["type"] == "string"
