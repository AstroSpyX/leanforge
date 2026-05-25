"""Pydantic models for the LLM's structured refine response.

These shapes are the contract that the `submit_fix` tool's input
schema is derived from (see `llm.tools.submit_fix`). Tool use with
`strict=True` makes the provider validate model output against this
schema server-side; by the time `RefineResponse(**call.input)` runs
client-side, the dict is structurally valid by construction. The
client-side validation here remains as a defense-in-depth check and
to handle any future non-strict provider.

SEMANTIC validity (range.end >= range.start, diagnostic_ids exist,
intended_scope names exist) is enforced in
`refine.edits.validate_response`, which has access to the contextual
state Pydantic does not.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class RepairStrategy(StrEnum):
    IMPORT_FIX = "import_fix"
    NAMESPACE_FIX = "namespace_fix"
    TACTIC_REWRITE = "tactic_rewrite"
    THEOREM_SPECIALIZATION = "theorem_specialization"
    TYPE_ANNOTATION_FIX = "type_annotation_fix"
    COERCION_FIX = "coercion_fix"
    INDUCTION_REPAIR = "induction_repair"
    REWRITE_CHAIN_FIX = "rewrite_chain_fix"
    GENERATION = "generation"
    OTHER = "other"


class Position(BaseModel):
    line: int = Field(ge=0)
    character: int = Field(ge=0)


class Range(BaseModel):
    start: Position
    end: Position


class ScopeItem(BaseModel):
    name: str
    range: Range | None = None


class Edit(BaseModel):
    """One file edit. Two variants distinguished by `kind`.

    `kind="replace_text"` (PREFERRED): provide `find_text` — the
    exact, unique substring to locate in the file — and `replacement`.
    Eliminates the coordinate-precision problem: the model doesn't
    have to count UTF-16 units on Unicode-heavy lines. Requires that
    `find_text` appears EXACTLY ONCE in the file; ambiguous matches
    are rejected so the model knows to be more specific.

    `kind="replace_range"` (FALLBACK): provide `range` (start/end
    positions in 0-indexed LSP UTF-16 units) and `replacement`. Use
    when the target text is not unique or when only positional info
    is reliable (e.g. inserting at end-of-file).
    """

    kind: Literal["replace_range", "replace_text"]
    range: Range | None = None
    find_text: str | None = None
    replacement: str

    @model_validator(mode="after")
    def _validate_kind_fields(self) -> Self:
        if self.kind == "replace_range":
            if self.range is None:
                raise ValueError(
                    "Edit with kind='replace_range' requires a `range` field"
                )
            if self.find_text is not None:
                raise ValueError(
                    "Edit with kind='replace_range' must not set `find_text`"
                )
        elif self.kind == "replace_text":
            if self.find_text is None:
                raise ValueError(
                    "Edit with kind='replace_text' requires a `find_text` field"
                )
            if self.range is not None:
                raise ValueError(
                    "Edit with kind='replace_text' must not set `range`"
                )
            if not self.find_text:
                raise ValueError(
                    "Edit with kind='replace_text' has empty `find_text`; "
                    "find_text must be a non-empty substring"
                )
        return self


class Fix(BaseModel):
    diagnostic_ids: list[int]
    edits: list[Edit]


class RefineResponse(BaseModel):
    summary: str
    strategy: RepairStrategy
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    intended_scope: list[ScopeItem]
    fixes: list[Fix]
    remaining_blockers: list[str]
