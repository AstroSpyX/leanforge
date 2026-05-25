"""The `judge_goal` tool — a cheap-model verdict on goal completion.

Used by `refine.checkers.llm_judge.LLMJudgeChecker`. The judge LLM
receives the user's goal text plus the current file state plus the
latest diagnostics, and returns a structured verdict:

  passed: bool        — has the goal been met?
  reasoning: str      — one to three sentences explaining the verdict
  remaining_work: [str] — specific items still to do (empty when passed)

Strict mode + provider-side schema validation guarantee the shape.
"""

from __future__ import annotations

from llm.tools import ToolSpec

_DESCRIPTION = (
    "Decide whether the user's goal has been achieved by the current "
    "file state. Be strict: passed=true means there is literally "
    "nothing left to do per the goal text. In remaining_work, cite "
    "specific evidence — declaration names, line numbers, what's "
    "still wrong — so the worker LLM can act on each item."
)

# Schema kept hand-written rather than Pydantic-derived because it's
# simple, never grows, and we want the descriptions to be tuned for
# the judge specifically (not reused for any other purpose).
_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "passed": {
            "type": "boolean",
            "description": (
                "True iff the user's goal is fully satisfied by the "
                "current file. Default to False when uncertain."
            ),
        },
        "reasoning": {
            "type": "string",
            "description": (
                "One to three sentences explaining the verdict. "
                "Cite the specific aspects of the goal that were "
                "(or were not) met."
            ),
        },
        "remaining_work": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Concrete items still to do, one per element. Each "
                "item should name the declaration / line / pattern "
                "involved so the worker LLM can act on it directly. "
                "MUST be empty when passed=true."
            ),
        },
    },
    "required": ["passed", "reasoning", "remaining_work"],
}


JUDGE_GOAL_TOOL = ToolSpec(
    name="judge_goal",
    description=_DESCRIPTION,
    input_schema=_INPUT_SCHEMA,
    strict=True,
)
