"""The `submit_fix` tool — refine's structured-output contract.

Derived directly from `refine.schema.RefineResponse` via Pydantic's
`model_json_schema()`, then massaged for cross-provider strict-mode
compatibility:

  1. **Ref inlining.** Pydantic emits a top-level schema with `$defs`
     and `$ref` to factor out nested models (Position, Range, Fix,
     etc.). Anthropic's strict tool use requires a single self-contained
     schema with no refs.

  2. **Additional-properties lockdown.** Set
     `additionalProperties: false` on every object type. Combined with
     Anthropic's `strict: true`, this means the model literally cannot
     emit a field that isn't declared in the schema — Bugs 12 and 13
     become structurally impossible.

  3. **$schema strip.** Anthropic and Gemini both reject this top-level
     key; harmless to omit.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from llm.tools import ToolSpec
from refine.schema import RefineResponse


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline every $ref against the schema's $defs / definitions, then
    drop the $defs block. Mutates a deep copy and returns it.

    Cycles aren't possible in the schemas we generate (RefineResponse
    has no recursive types), so a straightforward recursive substitution
    is safe.
    """
    schema = deepcopy(schema)
    defs = schema.pop("$defs", None) or schema.pop("definitions", None) or {}

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node and len(node) == 1:
                ref = node["$ref"]
                # We only handle local refs like "#/$defs/Range".
                key = ref.rsplit("/", 1)[-1]
                if key not in defs:
                    raise ValueError(f"unresolvable $ref: {ref}")
                return resolve(defs[key])
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)  # type: ignore[no-any-return]


def _lock_additional_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively set `additionalProperties: false` on every object type.

    Mutates a deep copy and returns it. Combined with strict tool use,
    this eliminates the "model emitted an unexpected field" failure mode.
    """
    schema = deepcopy(schema)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "additionalProperties" not in node:
                node["additionalProperties"] = False
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


def _build_input_schema() -> dict[str, Any]:
    raw = RefineResponse.model_json_schema()
    raw.pop("$schema", None)
    raw.pop("title", None)  # provider-side noise; not load-bearing
    return _lock_additional_properties(_inline_refs(raw))


_DESCRIPTION = (
    "Submit a structured fix for the Lean diagnostics. Each call must "
    "include a one-line `summary`, a `strategy` tag, a `reasoning` "
    "paragraph, a confidence in [0,1], the `intended_scope` of "
    "declarations you intend to modify, a list of `fixes` (each a set "
    "of `edits` keyed to the diagnostic IDs they resolve), and any "
    "`remaining_blockers` (diagnostic IDs you cannot fix in this turn, "
    "as STRINGS). The refine controller applies your `edits` directly "
    "to the file, then re-elaborates with Lean. Prefer small targeted "
    "edits over full-file rewrites."
)


SUBMIT_FIX_TOOL = ToolSpec(
    name="submit_fix",
    description=_DESCRIPTION,
    input_schema=_build_input_schema(),
    strict=True,
)
