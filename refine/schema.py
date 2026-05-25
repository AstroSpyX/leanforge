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
from typing import Literal

from pydantic import BaseModel, Field


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
    kind: Literal["replace_range"]
    range: Range
    replacement: str


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
