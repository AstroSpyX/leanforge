"""Tests for refine.schema — Pydantic structural validation."""

from typing import Any

import pytest
from pydantic import ValidationError

from refine.schema import (
    Edit,
    Fix,
    Position,
    Range,
    RefineResponse,
    RepairStrategy,
    ScopeItem,
)


def _range(
    start_line: int = 0,
    start_char: int = 0,
    end_line: int = 0,
    end_char: int = 0,
) -> Range:
    return Range(
        start=Position(line=start_line, character=start_char),
        end=Position(line=end_line, character=end_char),
    )


def _valid_response_payload() -> dict[str, Any]:
    return {
        "summary": "fix type mismatch in `bad`",
        "strategy": "type_annotation_fix",
        "reasoning": "the body is a String literal but the declared type is Nat",
        "confidence": 0.9,
        "intended_scope": [{"name": "bad", "range": None}],
        "fixes": [
            {
                "diagnostic_ids": [0],
                "edits": [
                    {
                        "kind": "replace_range",
                        "range": {
                            "start": {"line": 7, "character": 17},
                            "end": {"line": 7, "character": 31},
                        },
                        "replacement": "0",
                    }
                ],
            }
        ],
        "remaining_blockers": [],
    }


class TestRefineResponse:
    def test_valid_payload_parses_with_typed_fields(self) -> None:
        response = RefineResponse(**_valid_response_payload())
        assert response.strategy is RepairStrategy.TYPE_ANNOTATION_FIX
        assert response.confidence == 0.9
        assert len(response.fixes) == 1
        assert response.fixes[0].edits[0].replacement == "0"

    @pytest.mark.parametrize(
        "confidence",
        [-0.01, -1.0, 1.01, 2.0],
        ids=["epsilon_below_zero", "negative_one", "epsilon_above_one", "two"],
    )
    def test_confidence_outside_zero_to_one_rejected(self, confidence: float) -> None:
        payload = _valid_response_payload()
        payload["confidence"] = confidence
        with pytest.raises(ValidationError):
            RefineResponse(**payload)

    @pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
    def test_confidence_at_boundaries_accepted(self, confidence: float) -> None:
        payload = _valid_response_payload()
        payload["confidence"] = confidence
        RefineResponse(**payload)

    def test_unknown_strategy_rejected(self) -> None:
        payload = _valid_response_payload()
        payload["strategy"] = "magic_unicorn"
        with pytest.raises(ValidationError):
            RefineResponse(**payload)

    def test_remaining_blockers_coerces_ints_to_strings(self) -> None:
        """Bug 12: models sometimes emit diagnostic IDs as ints in
        remaining_blockers (mirroring Fix.diagnostic_ids: list[int]).
        Coerce to strings so validation doesn't fail on a recoverable
        type mismatch."""
        payload = _valid_response_payload()
        payload["remaining_blockers"] = [2, 4, 11]
        response = RefineResponse(**payload)
        assert response.remaining_blockers == ["2", "4", "11"]

    def test_remaining_blockers_accepts_mixed_int_and_str(self) -> None:
        """A list containing both forms also normalizes to all strings."""
        payload = _valid_response_payload()
        payload["remaining_blockers"] = [2, "lemma X missing", 5]
        response = RefineResponse(**payload)
        assert response.remaining_blockers == ["2", "lemma X missing", "5"]

    def test_intended_scope_with_range_parses(self) -> None:
        payload = _valid_response_payload()
        payload["intended_scope"] = [
            {
                "name": "bad",
                "range": {
                    "start": {"line": 7, "character": 0},
                    "end": {"line": 7, "character": 31},
                },
            }
        ]
        response = RefineResponse(**payload)
        scope = response.intended_scope[0]
        assert scope.range is not None
        assert scope.range.end.character == 31

    def test_missing_required_field_rejected(self) -> None:
        payload = _valid_response_payload()
        del payload["summary"]
        with pytest.raises(ValidationError, match="summary"):
            RefineResponse(**payload)


class TestPosition:
    @pytest.mark.parametrize("line", [-1, -100])
    def test_negative_line_rejected(self, line: int) -> None:
        with pytest.raises(ValidationError):
            Position(line=line, character=0)

    @pytest.mark.parametrize("character", [-1, -100])
    def test_negative_character_rejected(self, character: int) -> None:
        with pytest.raises(ValidationError):
            Position(line=0, character=character)


class TestEdit:
    def test_unsupported_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Edit(
                kind="delete",  # type: ignore[arg-type]
                range=_range(),
                replacement="",
            )

    def test_replace_range_with_empty_replacement_accepted(self) -> None:
        """Empty replacement = delete; replace_range is the universal op."""
        edit = Edit(kind="replace_range", range=_range(), replacement="")
        assert edit.replacement == ""


class TestFix:
    def test_fix_can_have_multiple_edits(self) -> None:
        edits = [
            Edit(kind="replace_range", range=_range(), replacement="a"),
            Edit(kind="replace_range", range=_range(1, 0, 1, 0), replacement="b"),
        ]
        fix = Fix(diagnostic_ids=[3], edits=edits)
        assert len(fix.edits) == 2

    def test_fix_can_target_multiple_diagnostics(self) -> None:
        fix = Fix(
            diagnostic_ids=[1, 2, 3],
            edits=[Edit(kind="replace_range", range=_range(), replacement="x")],
        )
        assert fix.diagnostic_ids == [1, 2, 3]


class TestScopeItem:
    def test_range_defaults_to_none(self) -> None:
        item = ScopeItem(name="foo")
        assert item.range is None


@pytest.mark.parametrize("value", [s.value for s in RepairStrategy])
def test_every_repair_strategy_value_round_trips(value: str) -> None:
    """Strategy values are part of the LLM contract; a typo here breaks parsing."""
    assert RepairStrategy(value).value == value
