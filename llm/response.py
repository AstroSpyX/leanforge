"""Response and ToolCall — the provider-agnostic shape `llm.ask` returns.

Every provider adapter constructs these directly; callers never touch
provider-native types. `tool_calls` is always a list (empty if the
model chose not to call any tools). `text` is always a string (empty
if the model emitted only tool calls).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """One structured tool invocation requested by the model.

    `input` is already schema-validated by the provider (Anthropic with
    strict=true, Gemini via input_schema). Callers can pass `input`
    straight to their Pydantic model constructor without re-parsing.
    """

    id: str  # opaque provider-issued ID; round-trip in tool_result
    name: str
    input: dict[str, Any]


@dataclass
class Response:
    """One completion from any provider.

    `text` and `tool_calls` are both populated for any response — text
    may be empty when only tool calls were emitted, and `tool_calls`
    is empty when the model produced only text.
    """

    text: str
    model: str  # our registry key, e.g. "sonnet" or "gemini-flash"
    provider: str  # "anthropic" | "google"
    provider_model_id: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int  # provider prompt-cache write
    cache_read_tokens: int  # provider prompt-cache hit
    stop_reason: str
    cached: bool  # served from our local disk cache
    tool_calls: list[ToolCall] = field(default_factory=list)
