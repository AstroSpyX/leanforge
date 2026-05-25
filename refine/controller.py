"""The refine loop: orchestrate evaluator → LLM → edits, iterate."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from llm import AskLLMError, Response, ask
from llm.tools.submit_fix import SUBMIT_FIX_TOOL
from refine.artifact_store import ArtifactStore
from refine.coords import normalize_line_endings
from refine.cost import base_cost_usd, iteration_cost_usd
from refine.diff_summary import compute_text_diff
from refine.edits import (
    EditApplyError,
    apply_edits,
    validate_response,
)
from refine.env import env_fingerprint
from refine.evaluator import (
    EvalResult,
    assign_diagnostic_ids,
    run_leanforge,
)
from refine.fingerprint import canonicalize_diagnostic, fingerprint_diagnostic
from refine.goal_status import classify_goal_status
from refine.outcome import Outcome, classify_outcome
from refine.prompt_builder import (
    PROMPT_VERSION_REPAIR,
    build_generation_messages,
    build_repair_messages,
)
from refine.schema import RefineResponse
from refine.signature import (
    axiom_decl_names,
    check_preservation,
    decls_with_sorry_warning,
    extract_signatures,
    signatures_to_hashes,
)
from refine.state import (
    GoalStatus,
    History,
    IterationState,
    Status,
)

logger = logging.getLogger(__name__)

# leanforge.py emits severity as a string label, not the LSP integer.
# Accept both for robustness — int matches the raw LSP, string is what
# leanforge actually serializes.
SEVERITY_ERROR_LABELS = (1, "error")
SEVERITY_WARNING_LABELS = (2, "warning")
RECENT_FAILURES_LIMIT = 3
LOOP_DETECTION_WINDOW = 5


def refine(
    project_root: str | Path,
    file_relpath: str,
    goal: str,
    mode: str = "policy",
    model: str = "sonnet",
    max_iters: int = 8,
    lean_timeout_seconds: float = 30,
    max_cost_usd: float = 1.00,
    max_tokens: int = 8192,
    keep_raw_llm_io: bool = True,
) -> History:
    """Drive the refine loop end-to-end. Returns the populated History."""
    project_path = Path(project_root).resolve()
    store = ArtifactStore(project_root=project_path, file_relpath=file_relpath)
    archived = store.start_new_run()
    if archived is not None:
        logger.info("archived prior run state to %s", archived.name)

    starter_content = _bootstrap_starter(
        store=store,
        goal=goal,
        model=model,
        max_tokens=max_tokens,
        keep_raw_llm_io=keep_raw_llm_io,
    )

    initial_eval = run_leanforge(project_path, file_relpath, lean_timeout_seconds)
    starter_sigs = extract_signatures(starter_content)
    original_sigs = signatures_to_hashes(starter_sigs)
    original_axioms = axiom_decl_names(starter_sigs)
    original_sorries = decls_with_sorry_warning(initial_eval.diagnostics)

    history = History(
        project_root=str(project_path),
        file_relpath=file_relpath,
        goal=goal,
        original_content=starter_content,
        env_fingerprint=env_fingerprint(project_path),
        prompt_version=PROMPT_VERSION_REPAIR,
    )
    store.update_current_pointer(0, history.env_fingerprint)

    initial_state = _build_baseline_state(
        starter_content=starter_content, eval_result=initial_eval
    )
    history.iterations.append(initial_state)
    store.append_history(initial_state)
    # The loop is done only when there are no errors AND no remaining sorries.
    # Lean reports `sorry` as a warning, not an error, so error_count alone
    # would short-circuit on a file full of unproven theorems.
    if initial_state.error_count == 0 and not original_sorries:
        history.final_status = Status.SUCCESS
        return history

    cumulative_input = 0
    cumulative_output = 0
    cumulative_cost = 0.0

    for iteration in range(1, max_iters + 1):
        latest = history.iterations[-1]
        try:
            outcome_state = _run_one_iteration(
                iteration=iteration,
                history=history,
                store=store,
                model=model,
                lean_timeout_seconds=lean_timeout_seconds,
                cumulative_input=cumulative_input,
                cumulative_output=cumulative_output,
                cumulative_cost=cumulative_cost,
                max_cost_usd=max_cost_usd,
                max_tokens=max_tokens,
                original_sigs=original_sigs,
                original_axioms=original_axioms,
                original_sorries=original_sorries,
                keep_raw_llm_io=keep_raw_llm_io,
                prev_state=latest,
            )
        except AskLLMError as exc:
            logger.error("LLM call failed at iter %d: %s", iteration, exc)
            history.final_status = Status.LLM_ERROR
            break

        history.iterations.append(outcome_state)
        store.append_history(outcome_state)
        cumulative_input = outcome_state.cumulative_input_tokens
        cumulative_output = outcome_state.cumulative_output_tokens
        cumulative_cost = outcome_state.cumulative_cost_usd

        if outcome_state.status == Status.SUCCESS:
            history.final_status = Status.SUCCESS
            break
        if outcome_state.status == Status.BUDGET_EXCEEDED:
            history.final_status = Status.BUDGET_EXCEEDED
            break

    if history.final_status is None:
        history.final_status = (
            Status.SUCCESS
            if history.latest and history.latest.status == Status.SUCCESS
            else Status.MAX_ITERS
        )
    return history


def _bootstrap_starter(
    store: ArtifactStore,
    goal: str,
    model: str,
    max_tokens: int,
    keep_raw_llm_io: bool,
) -> str:
    """Return the starter content. Reads the user's file when present and
    non-empty; otherwise asks the LLM to generate one from the goal."""
    if store.original_file_path.exists():
        existing = normalize_line_endings(store.original_file_path.read_text())
        if existing.strip():
            store.write_snapshot(0, existing)
            return existing

    user_prompt, system, _ = build_generation_messages(goal)
    response = ask(
        user_prompt,
        model=model,
        system=system,
        max_tokens=max_tokens,
        tools=[SUBMIT_FIX_TOOL],
        tool_choice="submit_fix",
    )
    refine_response = _parse_tool_response(response)
    if not refine_response.fixes or not refine_response.fixes[0].edits:
        raise RuntimeError("generation produced no edits")
    generated = normalize_line_endings(refine_response.fixes[0].edits[0].replacement)
    store.original_file_path.parent.mkdir(parents=True, exist_ok=True)
    store.write_current_file(generated)
    store.write_snapshot(0, generated)
    if keep_raw_llm_io:
        store.write_raw_io(
            0,
            prompt={"system": system, "user": user_prompt},
            response={
                "text": response.text,
                "tool_calls": [
                    {"id": c.id, "name": c.name, "input": c.input}
                    for c in response.tool_calls
                ],
            },
        )
    return generated


def _build_baseline_state(
    starter_content: str, eval_result: EvalResult
) -> IterationState:
    """The iteration-0 record captures the starter + its initial diagnostics
    with no LLM call attributed to it."""
    canonical = [canonicalize_diagnostic(d) for d in eval_result.diagnostics]
    fingerprints = [fingerprint_diagnostic(d) for d in eval_result.diagnostics]
    error_count, warning_count = _count_by_severity(eval_result.diagnostics)
    file_hash = _sha256(starter_content)
    state_hash = _compute_state_hash(starter_content, fingerprints)
    now = time.time()
    return IterationState(
        iteration=0,
        status=Status.INITIAL,
        goal_status=GoalStatus.UNCHANGED,
        file_content=starter_content,
        file_sha256=file_hash,
        state_hash=state_hash,
        raw_diagnostics=list(eval_result.diagnostics),
        canonical_diagnostics=canonical,
        diagnostics_fingerprints=fingerprints,
        error_count=error_count,
        warning_count=warning_count,
        resolved_count=0,
        new_count=len(fingerprints),
        persistent_count=0,
        prompt_sha256="",
        response_sha256="",
        retry_count=0,
        model="",
        provider="",
        provider_model_id="",
        temperature=None,
        llm_summary="",
        llm_strategy="",
        llm_confidence=0.0,
        llm_reasoning="",
        llm_intended_scope=[],
        system_intended_scope=[],
        edits_applied=0,
        remaining_blockers=[],
        hard_violations=[],
        soft_warnings=[],
        scope_warnings=[],
        input_tokens=0,
        output_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        base_cost_usd=0.0,
        retry_multiplier=1.0,
        cost_usd=0.0,
        cumulative_cost_usd=0.0,
        cumulative_input_tokens=0,
        cumulative_output_tokens=0,
        elapsed_ms=eval_result.wall_ms,
        started_at=now,
        finished_at=now,
    )


def _run_one_iteration(
    iteration: int,
    history: History,
    store: ArtifactStore,
    model: str,
    lean_timeout_seconds: float,
    cumulative_input: int,
    cumulative_output: int,
    cumulative_cost: float,
    max_cost_usd: float,
    max_tokens: int,
    original_sigs: dict[str, str],
    original_axioms: set[str],
    original_sorries: set[str],
    keep_raw_llm_io: bool,
    prev_state: IterationState,
) -> IterationState:
    """Build prompt, call LLM, apply edits, re-run leanforge, classify.
    Returns the iteration's IterationState (also writes snapshot + raw io)."""
    started_at = time.time()
    project_path = Path(history.project_root)

    diagnostics_with_ids = assign_diagnostic_ids(prev_state.raw_diagnostics)
    enclosing_decls = _unique_enclosing_decl_names(diagnostics_with_ids)
    decl_names = [s.name for s in extract_signatures(prev_state.file_content)]
    recent_failures = _assemble_recent_failures(history)

    user_prompt, system, _ = build_repair_messages(
        goal=history.goal,
        file_content=prev_state.file_content,
        diagnostics=diagnostics_with_ids,
        recent_failures=recent_failures,
        decl_names=decl_names,
        enclosing_decls_of_errors=enclosing_decls,
    )
    response = ask(
        user_prompt,
        model=model,
        system=system,
        max_tokens=max_tokens,
        tools=[SUBMIT_FIX_TOOL],
        tool_choice="submit_fix",
    )

    if keep_raw_llm_io:
        store.write_raw_io(
            iteration,
            prompt={"system": system, "user": user_prompt},
            response={
                "text": response.text,
                "tool_calls": [
                    {"id": c.id, "name": c.name, "input": c.input}
                    for c in response.tool_calls
                ],
            },
        )

    refine_response = _parse_tool_response(response)
    semantic_errors = validate_response(
        refine_response,
        valid_diagnostic_ids={d["id"] for d in diagnostics_with_ids},
        valid_decl_names=set(decl_names),
    )
    if semantic_errors:
        logger.warning("semantic validation errors: %s", semantic_errors)

    flat_edits = [edit for fix in refine_response.fixes for edit in fix.edits]
    apply_error_message: str | None = None
    try:
        new_content = apply_edits(prev_state.file_content, flat_edits)
    except EditApplyError as exc:
        logger.error("apply_edits failed at iter %d: %s", iteration, exc)
        new_content = prev_state.file_content
        apply_error_message = f"{type(exc).__name__}: {exc}"

    store.write_snapshot(iteration, new_content)
    store.write_current_file(new_content)
    store.update_current_pointer(iteration, history.env_fingerprint)

    eval_result = run_leanforge(
        project_path, history.file_relpath, lean_timeout_seconds
    )
    finished_at = time.time()

    canonical = [canonicalize_diagnostic(d) for d in eval_result.diagnostics]
    curr_fps = [fingerprint_diagnostic(d) for d in eval_result.diagnostics]
    error_count, warning_count = _count_by_severity(eval_result.diagnostics)
    resolved, new, persistent = _progress_counts(
        set(prev_state.diagnostics_fingerprints), set(curr_fps)
    )
    goal_status = classify_goal_status(
        prev_state.raw_diagnostics, list(eval_result.diagnostics)
    )
    outcome = classify_outcome(
        eval_result.diagnostics, eval_result.timed_out, eval_result.returncode
    )

    new_sigs = signatures_to_hashes(extract_signatures(new_content))
    new_axioms = axiom_decl_names(extract_signatures(new_content))
    new_sorries = decls_with_sorry_warning(eval_result.diagnostics)
    preservation = check_preservation(
        original_sigs,
        original_axioms,
        original_sorries,
        new_sigs,
        new_axioms,
        new_sorries,
    )
    hard: list[str] = []
    if preservation.decl_removed:
        hard.extend(f"decl_removed:{name}" for name in preservation.decl_removed)
    if preservation.axiom_introduced:
        hard.extend(f"axiom:{name}" for name in preservation.axiom_introduced)
    if preservation.sorry_introduced:
        hard.extend(f"sorry:{name}" for name in preservation.sorry_introduced)
    soft = [f"sig_changed:{name}" for name in preservation.sig_changed]
    if apply_error_message is not None:
        soft.append(f"apply_error: {apply_error_message}")

    file_hash = _sha256(new_content)
    state_hash = _compute_state_hash(new_content, curr_fps)
    status = _classify_status(
        outcome=outcome,
        error_count=error_count,
        resolved=resolved,
        new_count=new,
        hard_violations=hard,
        unresolved_sorry_count=len(new_sorries),
    )

    # Cache hits don't bill — zero out their tokens and cost so cumulative
    # totals reflect ACTUAL spend rather than what-would-have-been.
    billed = not response.cached
    input_tokens = response.input_tokens if billed else 0
    output_tokens = response.output_tokens if billed else 0
    cache_creation = response.cache_creation_tokens if billed else 0
    cache_read = response.cache_read_tokens if billed else 0

    base_cost = base_cost_usd(
        response.provider_model_id,
        input_tokens,
        output_tokens,
        cache_creation,
        cache_read,
    )
    cost = iteration_cost_usd(base_cost, retry_count=0)
    new_cumulative_cost = cumulative_cost + cost
    if new_cumulative_cost > max_cost_usd:
        status = Status.BUDGET_EXCEEDED

    diff = compute_text_diff(prev_state.file_content, new_content)
    logger.info(
        "iter=%d status=%s outcome=%s errors=%d resolved=%d new=%d cost=$%.4f",
        iteration,
        status.value,
        outcome.value,
        error_count,
        resolved,
        new,
        cost,
    )
    if diff.lines_added or diff.lines_removed:
        logger.debug(
            "diff +%d -%d max-block=%d",
            diff.lines_added,
            diff.lines_removed,
            diff.max_edit_size_lines,
        )

    return IterationState(
        iteration=iteration,
        status=status,
        goal_status=goal_status,
        file_content=new_content,
        file_sha256=file_hash,
        state_hash=state_hash,
        raw_diagnostics=list(eval_result.diagnostics),
        canonical_diagnostics=canonical,
        diagnostics_fingerprints=curr_fps,
        error_count=error_count,
        warning_count=warning_count,
        resolved_count=resolved,
        new_count=new,
        persistent_count=persistent,
        prompt_sha256=_sha256(user_prompt),
        response_sha256=_sha256(response.text),
        retry_count=0,
        model=model,
        provider=response.provider,
        provider_model_id=response.provider_model_id,
        temperature=None,
        llm_summary=refine_response.summary,
        llm_strategy=refine_response.strategy.value,
        llm_confidence=refine_response.confidence,
        llm_reasoning=refine_response.reasoning,
        llm_intended_scope=[
            asdict_safe(item) for item in refine_response.intended_scope
        ],
        system_intended_scope=sorted(_decls_touched_by_edits(flat_edits, decl_names)),
        edits_applied=len(flat_edits),
        remaining_blockers=list(refine_response.remaining_blockers),
        hard_violations=hard,
        soft_warnings=soft,
        scope_warnings=[],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation,
        cache_read_tokens=cache_read,
        base_cost_usd=base_cost,
        retry_multiplier=1.0,
        cost_usd=cost,
        cumulative_cost_usd=new_cumulative_cost,
        cumulative_input_tokens=cumulative_input + input_tokens,
        cumulative_output_tokens=cumulative_output + output_tokens,
        elapsed_ms=int((finished_at - started_at) * 1000),
        cached=response.cached,
        started_at=started_at,
        finished_at=finished_at,
    )


def _parse_tool_response(response: Response) -> RefineResponse:
    """Pull the submit_fix tool_call payload out of a Response and validate.

    With strict tool use (strict=True on the tool spec + tool_choice
    pinning the submit_fix tool), the provider guarantees the model
    will emit a submit_fix call with schema-conformant input. The
    ValidationError branch below is defensive — it can only fire if a
    provider regresses on its strict-mode contract.
    """
    submit_calls = [c for c in response.tool_calls if c.name == "submit_fix"]
    if not submit_calls:
        raise AskLLMError(
            f"expected a submit_fix tool call; response had "
            f"stop_reason={response.stop_reason!r} and "
            f"{len(response.tool_calls)} other tool call(s)"
        )
    try:
        return RefineResponse(**submit_calls[0].input)
    except ValidationError as exc:
        raise AskLLMError(
            f"submit_fix payload did not match RefineResponse schema: {exc}"
        ) from exc


def _count_by_severity(diagnostics: list[dict[str, Any]]) -> tuple[int, int]:
    errors = sum(1 for d in diagnostics if d.get("severity") in SEVERITY_ERROR_LABELS)
    warnings = sum(
        1 for d in diagnostics if d.get("severity") in SEVERITY_WARNING_LABELS
    )
    return errors, warnings


def _progress_counts(prev_fps: set[str], curr_fps: set[str]) -> tuple[int, int, int]:
    return (
        len(prev_fps - curr_fps),
        len(curr_fps - prev_fps),
        len(prev_fps & curr_fps),
    )


def _classify_status(
    outcome: Outcome,
    error_count: int,
    resolved: int,
    new_count: int,
    hard_violations: list[str],
    unresolved_sorry_count: int = 0,
) -> Status:
    # SUCCESS demands zero errors AND no remaining sorries — a `sorry`
    # only shows up as a warning in Lean but represents unfinished work
    # from the loop's perspective.
    if (
        outcome == Outcome.SUCCESS
        and error_count == 0
        and unresolved_sorry_count == 0
        and not hard_violations
    ):
        return Status.SUCCESS
    if hard_violations:
        return Status.POLICY_VIOLATION
    if outcome == Outcome.TIMEOUT:
        return Status.STUCK_TIMEOUT
    if resolved > 0 and new_count == 0:
        return Status.PROGRESS
    if new_count > resolved and new_count > 0:
        return Status.REGRESSION
    if resolved == 0 and new_count == 0:
        return Status.NO_CHANGE
    return Status.PROGRESS


def _assemble_recent_failures(history: History) -> list[dict[str, Any]]:
    # Look at the last RECENT_FAILURES_LIMIT iterations INCLUDING the most
    # recent one. The previous off-by-one (`[-N-1:-1]`) excluded the very
    # iteration whose failure we most need the LLM to learn from.
    relevant = [
        it
        for it in history.iterations[-RECENT_FAILURES_LIMIT:]
        if it.hard_violations
        or it.soft_warnings
        or it.status in (Status.REGRESSION, Status.NO_CHANGE, Status.POLICY_VIOLATION)
    ]
    if not relevant:
        return []
    records = []
    for it in relevant[-RECENT_FAILURES_LIMIT:]:
        first_label = (it.hard_violations or it.soft_warnings or [""])[0]
        records.append(
            {
                "iter": it.iteration,
                "status": it.status.value,
                "failure_or_warning": first_label,
                "declarations_affected": it.system_intended_scope,
                "edits_applied": it.edits_applied,
                "rejected_because": _describe_rejection(it),
            }
        )
    return records


def _describe_rejection(state: IterationState) -> str:
    if state.hard_violations:
        return "; ".join(state.hard_violations[:3])
    if state.soft_warnings:
        return "; ".join(state.soft_warnings[:3])
    return f"status was {state.status.value} (errors {state.error_count})"


def _unique_enclosing_decl_names(diagnostics: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for diag in diagnostics:
        enc = diag.get("enclosingDeclaration")
        if isinstance(enc, dict):
            name = enc.get("name")
            if isinstance(name, str) and name and name not in names:
                names.append(name)
    return names


def _decls_touched_by_edits(edits: Iterable[Any], decl_names: list[str]) -> set[str]:
    """Heuristic: a decl is 'touched' if any edit's start line is at or
    after its position. v1 has no decl-range map, so we conservatively
    return every decl that exists when any edit was made — the more
    precise decl_ranges check comes with v1.5 declaration slicing."""
    edits_list = list(edits)
    if not edits_list:
        return set()
    return set(decl_names)


def _compute_state_hash(file_content: str, fingerprints: list[str]) -> str:
    payload = _sha256(file_content) + "\x1f" + "\x1f".join(sorted(fingerprints))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def asdict_safe(obj: Any) -> dict[str, Any]:
    """Convert a Pydantic model to dict for storage in history."""
    if hasattr(obj, "model_dump"):
        dumped: dict[str, Any] = obj.model_dump()
        return dumped
    return dict(obj) if isinstance(obj, dict) else {"value": str(obj)}
