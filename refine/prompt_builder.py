"""Build the system + user messages refine sends to `llm.ask`.

Two builders, one per loop mode:

  - build_repair_messages: REPAIR turn (file + diagnostics + memos)
  - build_generation_messages: GENERATION turn (goal only, no diagnostics)

Both return `(prompt, system, prompt_version)`. Callers pass these to
`ask(prompt, system=system, tools=[SUBMIT_FIX_TOOL],
tool_choice="submit_fix", ...)`. Structured output is enforced
server-side by the tool's strict schema — no prose-extraction needed.

The system prompt is intentionally long (~1.2k tokens) so Anthropic's
prompt cache kicks in across iterations — most repair runs reuse the
same system text with a changing user payload.
"""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION_REPAIR = "repair_v3"
PROMPT_VERSION_GENERATE = "generate_v3"

LEAN_TOOLCHAIN_PIN = "Lean 4.29.1, Mathlib v4.29.1"
MAX_CHANGED_LINES_DEFAULT = 30
MAX_CHANGED_DECLS_DEFAULT = 2

_FOCUS_BEGIN_TEMPLATE = "-- BEGIN FOCUS: {name}"
_FOCUS_END = "-- END FOCUS"


_REPAIR_SYSTEM_PROMPT = f"""You are a Lean 4 theorem-repair engine. \
Your job is to make the provided Lean file compile while preserving \
theorem statements and respecting the rules below.

Toolchain: {LEAN_TOOLCHAIN_PIN}.

OUTPUT.
Call the `submit_fix` tool. The tool's schema enforces field types
and structure server-side — you do not need to format JSON manually.

POSITIONS.
All `range` positions are 0-indexed LSP convention. `character` is a
UTF-16 code unit count, not a code-point count. ASCII and most Lean
Unicode (∀, ∃, →, ⟨, ⟩, ↦) is 1 UTF-16 unit; characters outside the
BMP take 2.

REPAIR STRATEGIES.
Pick the most specific applicable `strategy` value:
  import_fix, namespace_fix, tactic_rewrite, theorem_specialization,
  type_annotation_fix, coercion_fix, induction_repair, rewrite_chain_fix,
  generation, other.

EDIT KINDS.
Each Edit picks ONE of two kinds:

- `replace_text` (PREFERRED whenever possible). Provide `find_text` —
  the exact, unique substring to locate in the file — and
  `replacement`. The controller finds find_text and replaces it once.
  No coordinate arithmetic. If find_text is NOT unique in the file,
  the edit is rejected with a message asking you to add surrounding
  context lines to disambiguate. Use this for refactoring proof
  bodies, renaming, or any change where the target text is unique.

  Example:
    {{"kind": "replace_text",
     "find_text": "  rw [Γ.op a b]\\n  rfl",
     "replacement": "  rw [a * b]\\n  rfl"}}

- `replace_range` (FALLBACK). Use only when the target text is not
  unique (e.g. inserting at end-of-file, or the same snippet appears
  multiple times). Provide `range` with 0-indexed LSP positions and
  `replacement`. Insert = zero-width range; delete = empty
  replacement; full rewrite = (0,0)..(EOF).

EDIT RULES.
- The file content in the user message has 0-INDEXED line numbers
  prefixed (NNN | content). The first line of the file is line 0.
- Prefer `replace_text` — character counting on Unicode-heavy Lean
  files (Γ, ⁻¹, ∀, →, ⟨, ⟩) is unreliable and the resulting edit
  often fails apply with an out-of-bounds error. Text-based edits
  sidestep this entirely.
- Maximum {MAX_CHANGED_LINES_DEFAULT} lines changed per call.
  Maximum {MAX_CHANGED_DECLS_DEFAULT} declarations touched. Exceeding
  either is rejected.
- Do NOT introduce `sorry`. Do NOT introduce a top-level `axiom`.
  Do NOT remove any declaration that existed at the start.
- Preserve theorem statements (the part before `:= ...`). Refactoring
  a statement is rejected by default.

INTENDED_SCOPE.
Declare every top-level decl you plan to modify. The controller
cross-checks against the decls your edits actually touch; touching
a decl outside your declared scope is logged as a warning.

YOU MAY.
- modify proof bodies (replace tactics, rewrite the proof)
- insert imports at the top of the file
- adjust type annotations
- repair namespace references
- use existing Mathlib lemmas

IF YOU CANNOT FIX A DIAGNOSTIC, list its id as a STRING (e.g. "2") in
`remaining_blockers`.
"""


_GENERATE_SYSTEM_PROMPT = f"""You are a Lean 4 file generator. The user \
will give you a goal in natural language; produce a complete Lean 4 file \
that attempts to satisfy it.

Toolchain: {LEAN_TOOLCHAIN_PIN}.

OUTPUT.
Call the `submit_fix` tool. Use a SINGLE Fix with `diagnostic_ids: []`
and ONE Edit that replaces the (empty) starter content with your full
generated file. Set `strategy` to "generation" and `intended_scope` to
the empty list.

The edit's range should be:
  {{"start": {{"line": 0, "character": 0}},
   "end":   {{"line": 0, "character": 0}}}}

The full file contents go in the edit's `replacement` field.

YOU MAY produce any number of imports, definitions, theorems, etc.
Use `Mathlib` for standard math.
"""


def build_repair_messages(
    goal: str,
    file_content: str,
    diagnostics: list[dict[str, Any]],
    recent_failures: list[dict[str, Any]] | None = None,
    human_guidance: str | None = None,
    strategy_nudge: str | None = None,
    decl_names: list[str] | None = None,
    enclosing_decls_of_errors: list[str] | None = None,
) -> tuple[str, str, str]:
    """Build (user_prompt, system, prompt_version) for REPAIR mode.

    `diagnostics` must already carry the `id` field (use
    `refine.evaluator.assign_diagnostic_ids` before calling).
    """
    focus_set = set(enclosing_decls_of_errors or [])
    numbered_file = _format_numbered_file(file_content, focus_set)
    diag_block = _format_diagnostics(diagnostics)
    decl_block = _format_decl_list(decl_names or [], focus_set)
    failures_block = _format_recent_failures(recent_failures or [])
    guidance_block = _format_optional_block("HUMAN GUIDANCE", human_guidance)
    nudge_block = _format_optional_block("STRATEGY HINT FOR THIS TURN", strategy_nudge)

    user_prompt = "\n\n".join(
        section
        for section in (
            f"GOAL:\n{goal.strip()}",
            f"CURRENT FILE (0-indexed line numbers prefixed; first line "
            f"is line 0):\n{numbered_file}",
            f"DIAGNOSTICS (each carries an `id`; reference it in your "
            f"fixes' diagnostic_ids):\n{diag_block}",
            decl_block,
            failures_block,
            guidance_block,
            nudge_block,
        )
        if section
    )
    return user_prompt, _REPAIR_SYSTEM_PROMPT, PROMPT_VERSION_REPAIR


def build_generation_messages(goal: str) -> tuple[str, str, str]:
    """Build (user_prompt, system, prompt_version) for GENERATION."""
    user_prompt = (
        f"GOAL:\n{goal.strip()}\n\n"
        f"Toolchain: {LEAN_TOOLCHAIN_PIN}.\n\n"
        "Produce the complete initial Lean 4 file from scratch and pass "
        "it via the `submit_fix` tool's "
        "`fixes[0].edits[0].replacement` field."
    )
    return user_prompt, _GENERATE_SYSTEM_PROMPT, PROMPT_VERSION_GENERATE


def _format_numbered_file(content: str, focus_set: set[str]) -> str:
    """Prefix each line with `NNN | `, using 0-INDEXED line numbers to
    match the LSP convention the LLM's JSON output uses. Avoids the
    1-vs-0-indexed conversion error class that wasted iterations in
    early live runs."""
    if not content:
        return "(empty file)"
    numbered_lines = [
        f"{index:4d} | {line}" for index, line in enumerate(content.split("\n"))
    ]
    if not focus_set:
        return "\n".join(numbered_lines)
    return "\n".join(_inject_focus_markers(numbered_lines, focus_set))


def _inject_focus_markers(
    numbered_lines: list[str], focus_names: set[str]
) -> list[str]:
    """Wrap each focus declaration with `-- BEGIN FOCUS: name` / `-- END
    FOCUS`. v1 heuristic: a focus decl starts at any line whose content
    (after the `NNN | ` prefix) begins with one of:
      "theorem <name>", "def <name>", "lemma <name>", "axiom <name>",
      "instance <name>", "example <name>"
    The block ends at the next top-level decl line or EOF.
    """
    output: list[str] = []
    keywords = ("theorem", "def", "lemma", "axiom", "instance", "example")
    in_focus = False
    for line in numbered_lines:
        content_after_prefix = line.split("| ", maxsplit=1)
        body = content_after_prefix[1] if len(content_after_prefix) == 2 else ""
        starts_decl = any(body.startswith(f"{kw} ") for kw in keywords)
        if starts_decl:
            if in_focus:
                output.append(_FOCUS_END)
                in_focus = False
            decl_name = body.split(maxsplit=2)[1] if len(body.split()) >= 2 else ""
            if decl_name in focus_names:
                output.append(_FOCUS_BEGIN_TEMPLATE.format(name=decl_name))
                in_focus = True
        output.append(line)
    if in_focus:
        output.append(_FOCUS_END)
    return output


def _format_diagnostics(diagnostics: list[dict[str, Any]]) -> str:
    if not diagnostics:
        return "(no diagnostics)"
    compact = [
        {
            "id": diag.get("id"),
            "severity": _severity_label(diag.get("severity")),
            "range": diag.get("range"),
            "messageText": diag.get("messageText"),
            "goal": _maybe_extract_goal(diag),
            "enclosingDeclaration": _enclosing_decl_name(diag),
        }
        for diag in diagnostics
    ]
    # ensure_ascii=False keeps Lean Unicode (⊢, ∀, →) readable for the model.
    return json.dumps(compact, indent=2, ensure_ascii=False)


def _format_decl_list(decl_names: list[str], focus_set: set[str]) -> str:
    if not decl_names:
        return ""
    marked = [f"*{name}" if name in focus_set else name for name in decl_names]
    return "DECLARATIONS IN FILE (asterisk marks focus decls):\n  " + ", ".join(marked)


def _format_recent_failures(failures: list[dict[str, Any]]) -> str:
    if not failures:
        return ""
    return "RECENT FAILURES (avoid repeating these mistakes):\n" + json.dumps(
        failures, indent=2
    )


def _format_optional_block(heading: str, content: str | None) -> str:
    if not content:
        return ""
    return f"{heading}:\n{content.strip()}"


def _severity_label(severity: Any) -> str:
    """LSP severity int → readable label, with fallback to string."""
    return {1: "error", 2: "warning", 3: "information", 4: "hint"}.get(
        severity if isinstance(severity, int) else -1, str(severity)
    )


def _maybe_extract_goal(diagnostic: dict[str, Any]) -> str | None:
    goal = diagnostic.get("goal")
    if isinstance(goal, dict):
        rendered = goal.get("rendered")
        if isinstance(rendered, str):
            return rendered
    term_goal = diagnostic.get("termGoal")
    if isinstance(term_goal, dict):
        goal_text = term_goal.get("goal")
        if isinstance(goal_text, str):
            return goal_text
    return None


def _enclosing_decl_name(diagnostic: dict[str, Any]) -> str | None:
    enclosing = diagnostic.get("enclosingDeclaration")
    if isinstance(enclosing, dict):
        name = enclosing.get("name")
        if isinstance(name, str):
            return name
    return None
