"""Provider-agnostic tool definitions.

A `ToolSpec` describes one callable the model can invoke. Each provider
adapter translates ToolSpec → its native tool format on the way out
(Anthropic: tool dict with `strict: true`; Gemini: `Tool` with
`function_declarations`). The model's structured response comes back
as `Response.tool_calls: list[ToolCall]`.

Domain-specific tools live as modules in this package (e.g.
`llm.tools.submit_fix`). The dataclass itself stays in
`__init__.py` so callers import via `from llm.tools import ToolSpec`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    """One tool declaration shared across providers.

    `input_schema` is a JSON Schema (Draft 2020-12 compatible).
    `strict=True` asks the provider to guarantee model output matches
    the schema exactly — Anthropic supports this server-side; Gemini
    effectively enforces it via its schema-driven function calling.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    strict: bool = True
