"""Pass when the LLM judge agrees the goal text has been met.

Configured with a cheap model (Haiku, Gemini Flash-Lite) and the
loop's goal text. Each iter, the judge gets the current file content
plus diagnostics plus the goal, and returns a structured verdict
via the `judge_goal` tool.

The judge is intentionally separate from the worker — using a
different model family (worker=Sonnet, judge=Haiku, or
worker=Gemini, judge=Haiku) reduces the chance of both LLMs sharing
the same blind spot on a hard goal.

Cost: one tool-use call per iter to a cheap model, typically
~$0.001-0.01 depending on model + file size. Short-circuited by
upstream stages, so the judge only runs once syntax/policy/style
have already passed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llm import ask
from llm.tools.judge_goal import JUDGE_GOAL_TOOL
from refine.checkers.base import Checker, CheckResult

_JUDGE_SYSTEM_PROMPT = (
    "You are a STRICT goal-completion judge for a Lean 4 repair loop. "
    "You receive: (1) the user's goal in natural language, (2) the "
    "current file content, (3) any remaining Lean diagnostics. You "
    "decide whether the goal has been fully met and call the "
    "judge_goal tool with the verdict.\n\n"
    "VERIFICATION DISCIPLINE — follow this exactly:\n"
    "  1. Parse the goal into a list of concrete items. Number them.\n"
    "  2. For EACH numbered item, search the file content for evidence:\n"
    "     - 'add theorem foo' → grep for 'theorem foo' as a substring;\n"
    "       it must be followed by a real proof body, NOT ':= sorry'.\n"
    "     - 'mark X with [simp]' → grep for '[simp]' immediately before "
    "       the X declaration, OR an 'attribute [simp] X' directive.\n"
    "     - 'refactor proof bodies to use Y' → confirm no occurrences of "
    "       the old form remain in proof body lines.\n"
    "     - 'preserve declaration foo byte-for-byte' → confirm foo's "
    "       signature line is unchanged from earlier iters' file content.\n"
    "  3. Only call passed=true when EVERY numbered item is verified.\n"
    "  4. When in doubt: passed=false. Always.\n\n"
    "REMAINING_WORK must enumerate, by item number, the specific "
    "goal items you could NOT verify. Use concrete names and "
    "line numbers from the file when possible (e.g. 'item 3: theorem "
    "subgroup_ext is not present in the file').\n\n"
    "False positives (declaring done when not done) waste user money "
    "and can ship broken code. False negatives just trigger another "
    "iteration at trivial cost. ALWAYS prefer false-negative."
)


@dataclass(frozen=True)
class LLMJudgeChecker(Checker):
    name: str
    model: str
    goal: str
    max_tokens: int = 2048

    def check(
        self,
        content: str,
        diagnostics: list[dict[str, Any]],
    ) -> CheckResult:
        diag_summary = self._format_diagnostics(diagnostics)
        prompt = (
            f"GOAL:\n{self.goal}\n\n"
            f"CURRENT FILE CONTENT:\n```\n{content}\n```\n\n"
            f"REMAINING DIAGNOSTICS:\n{diag_summary}\n\n"
            "Decide whether the goal has been met and call `judge_goal`."
        )
        response = ask(
            prompt,
            model=self.model,
            system=_JUDGE_SYSTEM_PROMPT,
            tools=[JUDGE_GOAL_TOOL],
            tool_choice="judge_goal",
            max_tokens=self.max_tokens,
        )
        if not response.tool_calls:
            # Strict tool use should make this impossible; surface
            # clearly if a provider regression breaks the contract.
            return CheckResult(
                passed=False,
                pseudo_diagnostics=[
                    {
                        "severity": "error",
                        "messageText": (
                            f"llm_judge[{self.name}]: judge model "
                            f"{self.model!r} did not return a "
                            f"tool_call; cannot decide goal completion"
                        ),
                    }
                ],
            )
        verdict = response.tool_calls[0].input
        passed = bool(verdict.get("passed", False))
        if passed:
            return CheckResult(passed=True)
        remaining = verdict.get("remaining_work") or []
        reasoning = str(verdict.get("reasoning", ""))
        pseudo: list[dict[str, Any]] = []
        if reasoning:
            pseudo.append(
                {
                    "severity": "error",
                    "messageText": f"llm_judge[{self.name}]: {reasoning}",
                }
            )
        for item in remaining:
            pseudo.append(
                {
                    "severity": "error",
                    "messageText": f"llm_judge[{self.name}]: {item}",
                }
            )
        # First line of reasoning is usually the most informative;
        # plus a count of remaining items.
        first_line = reasoning.split("\n", 1)[0][:120] if reasoning else ""
        summary = f"{len(remaining)} item(s) remaining" + (
            f"; {first_line}" if first_line else ""
        )
        return CheckResult(passed=False, pseudo_diagnostics=pseudo, summary=summary)

    @staticmethod
    def _format_diagnostics(diagnostics: list[dict[str, Any]]) -> str:
        if not diagnostics:
            return "(none — Lean compile + sibling checkers all passed)"
        lines: list[str] = []
        for d in diagnostics:
            severity = d.get("severity", "?")
            message = str(d.get("messageText", "?"))[:200]
            lines.append(f"  [{severity}] {message}")
        return "\n".join(lines)
