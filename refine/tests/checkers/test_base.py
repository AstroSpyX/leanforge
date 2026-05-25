"""Tests for the Checker / CheckResult / CheckerStage dataclasses."""

from __future__ import annotations

from refine.checkers import CheckerStage, CheckResult, StageResult
from refine.checkers.base import Checker


class TestCheckResult:
    def test_default_pseudo_diagnostics_is_empty_list(self) -> None:
        r = CheckResult(passed=True)
        assert r.pseudo_diagnostics == []

    def test_can_carry_diagnostics_when_failed(self) -> None:
        r = CheckResult(
            passed=False,
            pseudo_diagnostics=[{"severity": "error", "messageText": "x"}],
        )
        assert len(r.pseudo_diagnostics) == 1


class _DummyChecker:
    name = "dummy"

    def check(self, content, diagnostics):  # type: ignore[no-untyped-def]
        return CheckResult(passed=True)


class TestCheckerProtocol:
    def test_class_implementing_protocol_is_accepted(self) -> None:
        """Duck typing — any object with name + check matches."""
        c: Checker = _DummyChecker()  # type: ignore[assignment]
        result = c.check("", [])
        assert result.passed is True


class TestCheckerStage:
    def test_stage_is_constructible_with_tuple_of_checkers(self) -> None:
        stage = CheckerStage("syntax", (_DummyChecker(),))  # type: ignore[arg-type]
        assert stage.name == "syntax"
        assert len(stage.checkers) == 1


class TestStageResult:
    def test_passed_stage_has_empty_diagnostics(self) -> None:
        r = StageResult(stage_name="all", passed=True)
        assert r.pseudo_diagnostics == []
