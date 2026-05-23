"""Tests for refine.prompt_builder — message assembly for both modes."""

import json

import pytest

from refine.prompt_builder import (
    ASSISTANT_PREFILL,
    PROMPT_VERSION_GENERATE,
    PROMPT_VERSION_REPAIR,
    build_generation_messages,
    build_repair_messages,
)


def _diagnostic(
    id_: int = 0,
    severity: int = 1,
    message: str = "type mismatch",
    decl_name: str = "bad",
    goal: str | None = None,
) -> dict:
    start = {"line": 0, "character": 0}
    end = {"line": 0, "character": 1}
    diag = {
        "id": id_,
        "severity": severity,
        "messageText": message,
        "range": {"start": start, "end": end},
        "enclosingDeclaration": {"name": decl_name},
    }
    if goal is not None:
        diag["goal"] = {"rendered": goal}
    return diag


class TestBuildRepairMessages:
    def test_returns_four_tuple(self) -> None:
        result = build_repair_messages(
            goal="prove it",
            file_content="def x : Nat := 0",
            diagnostics=[],
        )
        assert len(result) == 4

    def test_prefill_is_open_brace(self) -> None:
        _, _, prefill, _ = build_repair_messages(
            goal="x", file_content="", diagnostics=[]
        )
        assert prefill == ASSISTANT_PREFILL

    def test_prompt_version_matches_constant(self) -> None:
        _, _, _, version = build_repair_messages(
            goal="x", file_content="", diagnostics=[]
        )
        assert version == PROMPT_VERSION_REPAIR

    def test_user_prompt_includes_goal(self) -> None:
        prompt, _, _, _ = build_repair_messages(
            goal="prove sqrt 2 is irrational",
            file_content="",
            diagnostics=[],
        )
        assert "prove sqrt 2 is irrational" in prompt

    def test_user_prompt_includes_line_numbered_file(self) -> None:
        prompt, _, _, _ = build_repair_messages(
            goal="x",
            file_content="def x : Nat := 0",
            diagnostics=[],
        )
        # 0-indexed: first line is "   0 | ..." (matches LSP convention)
        assert "   0 | def x : Nat := 0" in prompt

    def test_user_prompt_includes_diagnostic_ids(self) -> None:
        prompt, _, _, _ = build_repair_messages(
            goal="x",
            file_content="",
            diagnostics=[_diagnostic(id_=7, message="big problem")],
        )
        assert '"id": 7' in prompt
        assert "big problem" in prompt

    def test_focus_markers_wrap_enclosing_decl(self) -> None:
        """When a decl is in focus, its source range is wrapped with
        BEGIN/END FOCUS markers so the LLM can find it fast."""
        prompt, _, _, _ = build_repair_messages(
            goal="x",
            file_content='def good : Nat := 0\ndef bad : Nat := "oops"',
            diagnostics=[_diagnostic(decl_name="bad")],
            enclosing_decls_of_errors=["bad"],
        )
        assert "BEGIN FOCUS: bad" in prompt
        assert "END FOCUS" in prompt
        # The good decl should NOT be inside focus markers
        good_pos = prompt.index("def good")
        begin_pos = prompt.index("BEGIN FOCUS")
        assert good_pos < begin_pos

    def test_decl_list_marks_focus_with_asterisk(self) -> None:
        prompt, _, _, _ = build_repair_messages(
            goal="x",
            file_content="",
            diagnostics=[],
            decl_names=["foo", "bad", "baz"],
            enclosing_decls_of_errors=["bad"],
        )
        assert "foo, *bad, baz" in prompt

    def test_recent_failures_appear_as_structured_records(self) -> None:
        prompt, _, _, _ = build_repair_messages(
            goal="x",
            file_content="",
            diagnostics=[],
            recent_failures=[
                {
                    "iter": 3,
                    "status": "policy_violation",
                    "failure_or_warning": "sorry_introduced",
                    "declarations_affected": ["foo"],
                    "edits_applied": 1,
                    "rejected_because": "sorry was newly introduced in foo",
                }
            ],
        )
        assert "RECENT FAILURES" in prompt
        assert "sorry_introduced" in prompt
        assert "foo" in prompt

    def test_human_guidance_block_included_when_present(self) -> None:
        prompt, _, _, _ = build_repair_messages(
            goal="x",
            file_content="",
            diagnostics=[],
            human_guidance="try using Nat.prime_two.irrational_sqrt",
        )
        assert "HUMAN GUIDANCE" in prompt
        assert "Nat.prime_two" in prompt

    def test_human_guidance_block_skipped_when_absent(self) -> None:
        prompt, _, _, _ = build_repair_messages(
            goal="x", file_content="", diagnostics=[], human_guidance=None
        )
        assert "HUMAN GUIDANCE" not in prompt

    def test_strategy_nudge_appears_as_hint(self) -> None:
        prompt, _, _, _ = build_repair_messages(
            goal="x",
            file_content="",
            diagnostics=[],
            strategy_nudge="tactic_rewrite",
        )
        assert "STRATEGY HINT" in prompt
        assert "tactic_rewrite" in prompt

    def test_system_prompt_mentions_schema_and_rules(self) -> None:
        _, system, _, _ = build_repair_messages(
            goal="x", file_content="", diagnostics=[]
        )
        # Spot-check key contract phrases
        assert "JSON" in system
        assert "replace_range" in system
        assert "sorry" in system.lower()
        assert "axiom" in system.lower()

    def test_diagnostic_goal_included_when_present(self) -> None:
        prompt, _, _, _ = build_repair_messages(
            goal="x",
            file_content="",
            diagnostics=[_diagnostic(goal="⊢ Nat")],
        )
        # JSON inside the prompt should include the goal text
        assert "⊢ Nat" in prompt

    def test_diagnostic_severity_rendered_as_label(self) -> None:
        prompt, _, _, _ = build_repair_messages(
            goal="x",
            file_content="",
            diagnostics=[_diagnostic(severity=2)],
        )
        assert '"severity": "warning"' in prompt


class TestBuildGenerationMessages:
    def test_returns_four_tuple(self) -> None:
        result = build_generation_messages("prove it")
        assert len(result) == 4

    def test_prompt_version_matches_constant(self) -> None:
        _, _, _, version = build_generation_messages("x")
        assert version == PROMPT_VERSION_GENERATE

    def test_prefill_is_open_brace(self) -> None:
        _, _, prefill, _ = build_generation_messages("x")
        assert prefill == ASSISTANT_PREFILL

    def test_generation_system_prompt_describes_single_full_edit(self) -> None:
        _, system, _, _ = build_generation_messages("x")
        assert "generation" in system.lower()
        assert "replacement" in system

    def test_user_prompt_includes_goal(self) -> None:
        prompt, _, _, _ = build_generation_messages("prove sqrt 2 irrational")
        assert "prove sqrt 2 irrational" in prompt


@pytest.mark.parametrize(
    "severity,expected",
    [(1, "error"), (2, "warning"), (3, "information"), (4, "hint")],
)
def test_severity_label_mapping_in_diagnostics(severity: int, expected: str) -> None:
    prompt, _, _, _ = build_repair_messages(
        goal="x",
        file_content="",
        diagnostics=[_diagnostic(severity=severity)],
    )
    assert f'"severity": "{expected}"' in prompt


def test_diagnostics_block_is_valid_json() -> None:
    """The diagnostics block must be parseable JSON — guards against
    accidental string interpolation that would corrupt the structure."""
    prompt, _, _, _ = build_repair_messages(
        goal="x",
        file_content="",
        diagnostics=[_diagnostic(id_=0), _diagnostic(id_=1, message="other")],
    )
    # Extract the JSON array after "DIAGNOSTICS (...):\n"
    marker = "DIAGNOSTICS"
    start = prompt.index("[", prompt.index(marker))
    end = prompt.index("]", start) + 1
    parsed = json.loads(prompt[start:end])
    assert [d["id"] for d in parsed] == [0, 1]
