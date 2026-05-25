"""Tests for the stage runner: ordering, AND-within-stage, short-circuit."""

from __future__ import annotations

from dataclasses import dataclass

from refine.checkers import CheckerStage, CheckResult
from refine.checkers.runner import run_stages


@dataclass
class _StubChecker:
    """Returns a pre-set result; tracks invocation count for short-circuit tests."""

    name: str
    result: CheckResult
    calls: list[None]

    def check(self, content, diagnostics):  # type: ignore[no-untyped-def]
        self.calls.append(None)
        return self.result


def _stub(name: str, passed: bool, diags: list | None = None) -> _StubChecker:
    return _StubChecker(
        name=name,
        result=CheckResult(passed=passed, pseudo_diagnostics=diags or []),
        calls=[],
    )


class TestRunStages:
    def test_all_pass_returns_green_all(self) -> None:
        stages = [
            CheckerStage("a", (_stub("a1", True), _stub("a2", True))),  # type: ignore[arg-type]
            CheckerStage("b", (_stub("b1", True),)),  # type: ignore[arg-type]
        ]
        result = run_stages(stages, "", [])
        assert result.passed is True
        assert result.stage_name == "all"
        assert result.pseudo_diagnostics == []

    def test_first_failure_short_circuits_later_stages(self) -> None:
        """A failing first stage must prevent later stages from running."""
        b1 = _stub("b1", True)
        stages = [
            CheckerStage(
                "a",
                (_stub("a1", False, [{"messageText": "from a1"}]),),  # type: ignore[arg-type]
            ),
            CheckerStage("b", (b1,)),  # type: ignore[arg-type]
        ]
        result = run_stages(stages, "", [])
        assert result.passed is False
        assert result.stage_name == "a"
        assert len(result.pseudo_diagnostics) == 1
        assert b1.calls == []  # b never ran

    def test_within_stage_all_checkers_run_even_if_one_fails(self) -> None:
        """AND-within-stage: every checker in the stage executes so the
        agent sees all sibling issues at once."""
        c1 = _stub("c1", False, [{"messageText": "from c1"}])
        c2 = _stub("c2", False, [{"messageText": "from c2"}])
        c3 = _stub("c3", True)
        stages = [CheckerStage("policy", (c1, c2, c3))]  # type: ignore[arg-type]
        result = run_stages(stages, "", [])
        assert c1.calls == c2.calls == c3.calls == [None]
        assert len(result.pseudo_diagnostics) == 2  # only failing ones

    def test_empty_stages_passes_trivially(self) -> None:
        result = run_stages([], "", [])
        assert result.passed is True

    def test_failing_checker_summary_flows_into_stage_result(self) -> None:
        """Each failing checker's summary appears in StageResult.summaries
        prefixed with the checker's name so log lines can render
        per-checker context (total counts, judge reasoning, etc.)."""

        @dataclass
        class _SummaryStub:
            name: str
            result: CheckResult
            calls: list[None]

            def check(self, content, diagnostics):  # type: ignore[no-untyped-def]
                self.calls.append(None)
                return self.result

        c1 = _SummaryStub(
            name="errors",
            result=CheckResult(passed=False, summary="5 errors"),
            calls=[],
        )
        c2 = _SummaryStub(
            name="sorries",
            result=CheckResult(passed=False, summary="2 sorries"),
            calls=[],
        )
        stages = [CheckerStage("policy", (c1, c2))]  # type: ignore[arg-type]
        result = run_stages(stages, "", [])
        assert result.summaries == ["errors: 5 errors", "sorries: 2 sorries"]

    def test_passing_checker_summary_omitted_from_stage_result(self) -> None:
        """A checker that passes contributes no summary (its result
        isn't in StageResult.summaries even if .summary was set)."""

        @dataclass
        class _Stub:
            name: str
            result: CheckResult
            calls: list[None]

            def check(self, content, diagnostics):  # type: ignore[no-untyped-def]
                self.calls.append(None)
                return self.result

        passing = _Stub(
            name="ok",
            result=CheckResult(passed=True, summary="nothing wrong"),
            calls=[],
        )
        failing = _Stub(
            name="bad",
            result=CheckResult(passed=False, summary="3 problems"),
            calls=[],
        )
        stages = [CheckerStage("mix", (passing, failing))]  # type: ignore[arg-type]
        result = run_stages(stages, "", [])
        assert result.summaries == ["bad: 3 problems"]

    def test_diagnostics_propagated_to_checkers(self) -> None:
        """Stage runner must pass content + diagnostics through."""
        seen_args: dict = {}

        class _Capturer:
            name = "cap"

            def check(self, content, diagnostics):  # type: ignore[no-untyped-def]
                seen_args["content"] = content
                seen_args["diagnostics"] = diagnostics
                return CheckResult(passed=True)

        run_stages(
            [CheckerStage("cap", (_Capturer(),))],  # type: ignore[arg-type]
            "file content here",
            [{"severity": "error"}],
        )
        assert seen_args["content"] == "file content here"
        assert seen_args["diagnostics"] == [{"severity": "error"}]
