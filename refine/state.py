"""IterationState, History, and the four controller-facing enums.

Pure data + enums. Logic that operates over these (computing
fingerprint deltas, detecting loops, classifying outcomes) lives in
the modules that own each concern, not here. Keeping this module
allocation-free makes test setup cheap throughout the rest of the
codebase.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    """How the controller classifies an iteration overall."""

    INITIAL = "initial"
    PROGRESS = "progress"
    NO_CHANGE = "no_change"
    REGRESSION = "regression"
    CHURN = "churn"
    SUCCESS = "success"
    STUCK_TIMEOUT = "stuck_timeout"
    LOOP_DETECTED = "loop_detected"
    POLICY_VIOLATION = "policy_violation"
    LLM_ERROR = "llm_error"
    APPLY_ERROR = "apply_error"
    BUDGET_EXCEEDED = "budget_exceeded"
    MAX_ITERS = "max_iters"


class FailureReason(StrEnum):
    """Why an iteration's edits could not be applied or were rolled back.

    A FailureReason ALWAYS pairs with a rollback + pause; this differs
    from WarningReason, which is a non-rolling-back annotation.
    """

    INVALID_JSON = "invalid_json"
    SCHEMA_VALIDATION = "schema_validation"
    EMPTY_RESPONSE = "empty_response"
    OVERLAPPING_EDITS = "overlapping_edits"
    OOB_EDIT = "oob_edit"
    NON_LOCAL_REWRITE = "non_local_rewrite"
    POLICY_VIOLATION = "policy_violation"
    LOOP_DETECTED = "loop_detected"
    TIMEOUT_LEAN = "timeout_lean"
    BUDGET_EXCEEDED = "budget_exceeded"


class WarningReason(StrEnum):
    """Soft signals that get recorded and may escalate to a pause on repeat
    but never rollback the iteration on their own.
    """

    SIG_CHANGED = "sig_changed"
    SCOPE_DRIFT = "scope_drift"
    ENV_DRIFT = "env_drift"
    LOOP_NEAR_REPEAT = "loop_near_repeat"


class GoalStatus(StrEnum):
    """How the primary goal text moved between iterations."""

    UNCHANGED = "unchanged"
    PROGRESS = "progress"
    SHIFTED = "shifted"
    RESOLVED = "resolved"


@dataclass
class IterationState:
    """One iteration's complete record. Mirrors a row of history.jsonl
    1:1 — anything serialized to disk has its source here."""

    iteration: int
    status: Status
    goal_status: GoalStatus
    file_content: str
    file_sha256: str
    state_hash: str
    # LSP-derived JSON shape; values are str | int | bool | dict | list, so
    # the dict-value type is genuinely heterogeneous at this boundary.
    raw_diagnostics: list[dict[str, Any]]
    canonical_diagnostics: list[dict[str, Any]]
    diagnostics_fingerprints: list[str]
    error_count: int
    warning_count: int
    resolved_count: int
    new_count: int
    persistent_count: int
    prompt_sha256: str
    response_sha256: str
    retry_count: int
    model: str
    provider: str
    provider_model_id: str
    temperature: float | None
    llm_summary: str
    llm_strategy: str
    llm_confidence: float
    llm_reasoning: str
    llm_intended_scope: list[dict[str, Any]]
    system_intended_scope: list[str]
    edits_applied: int
    remaining_blockers: list[str]
    hard_violations: list[str]
    soft_warnings: list[str]
    scope_warnings: list[str]
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    base_cost_usd: float
    retry_multiplier: float
    cost_usd: float
    cumulative_cost_usd: float
    cumulative_input_tokens: int
    cumulative_output_tokens: int
    elapsed_ms: int
    # True when the LLM response came from the local disk cache rather
    # than a fresh API call. Cost and token fields are 0 in that case so
    # cumulative_cost_usd reflects actual billing, not "would-have-been".
    cached: bool = False
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0


@dataclass
class History:
    """Rolling sequence of iterations plus loop-level identity."""

    project_root: str
    file_relpath: str
    goal: str
    original_content: str
    env_fingerprint: str
    prompt_version: str
    iterations: list[IterationState] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    final_status: Status | None = None

    @property
    def latest(self) -> IterationState | None:
        return self.iterations[-1] if self.iterations else None
