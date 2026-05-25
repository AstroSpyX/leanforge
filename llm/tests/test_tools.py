"""Tests for the ToolSpec dataclass."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from llm.tools import ToolSpec


class TestToolSpec:
    def test_strict_defaults_true(self) -> None:
        """Strict mode is the deliberate default — callers must opt out."""
        spec = ToolSpec(name="x", description="d", input_schema={"type": "object"})
        assert spec.strict is True

    def test_frozen_dataclass_rejects_mutation(self) -> None:
        """ToolSpec is frozen so registries can dedupe / hash safely."""
        spec = ToolSpec(name="x", description="d", input_schema={})
        with pytest.raises(FrozenInstanceError):
            spec.name = "y"  # type: ignore[misc]
