"""Google Gemini provider adapter (google-genai SDK).

Translates the provider-agnostic `call()` API into Gemini's
`generate_content` API:
  - `tools` → `types.Tool(function_declarations=[…])` mapping name,
    description, parameters from our ToolSpec.
  - `tool_choice="auto"` → mode AUTO; `"any"` → mode ANY; any other
    string → mode ANY with allowed_function_names=[that_name].
  - System prompt goes in `system_instruction` (separate field, not
    a message role).
  - Errors mapped to `llm.errors.AskLLMError` hierarchy by HTTP status
    code where available.

Cache hint is a no-op here: Gemini's explicit content-caching API
(`client.caches`) is unrelated to per-request hints, and we already
operate behind `llm.cache` for the disk cache.
"""

from __future__ import annotations

import os
import time
from typing import Any

from google import genai
from google.genai import types

from llm.errors import (
    APIBadRequest,
    APIServerError,
    APITimeout,
    AskLLMError,
    AuthError,
    ModelNotFound,
    OverloadedError,
    RateLimitError,
)
from llm.models import ModelConfig
from llm.response import Response, ToolCall
from llm.tools import ToolSpec

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not os.environ.get("GOOGLE_API_KEY"):
            raise AuthError("GOOGLE_API_KEY not set in environment")
        _client = genai.Client()
    return _client


def _classify(e: Exception) -> AskLLMError:
    """Map Gemini SDK exceptions to our error hierarchy.

    The google-genai SDK surfaces upstream errors with a `.code` (HTTP
    status) attribute. Fall back to string matching on the exception
    message when the attribute is absent, then to a generic AskLLMError.
    """
    code: int | None = getattr(e, "code", None) or getattr(e, "status_code", None)
    msg = str(e)

    if code in (401, 403) or "PERMISSION_DENIED" in msg or "UNAUTHENTICATED" in msg:
        return AuthError(msg)
    if code == 429 or "RESOURCE_EXHAUSTED" in msg:
        return RateLimitError(msg)
    if code == 404 or "NOT_FOUND" in msg:
        return ModelNotFound(msg)
    if code == 400 or "INVALID_ARGUMENT" in msg:
        return APIBadRequest(msg)
    if code == 503 or "UNAVAILABLE" in msg:
        return OverloadedError(msg)
    if code == 504 or "DEADLINE_EXCEEDED" in msg:
        return APITimeout(msg)
    if code is not None and code >= 500:
        return APIServerError(msg)
    return AskLLMError(msg)


def _gemini_compat_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Translate a JSON Schema dict to Gemini's accepted subset.

    Gemini's `types.Schema` (a strict Pydantic model) plus the upstream
    `generativelanguage.googleapis.com` validator reject some standard
    JSON Schema keywords. Known incompatibilities we handle:

      - `const: X` → `enum: [X]`. Pydantic emits `const` for
        `Literal[...]` types; Gemini's Schema has no `const` field.
      - `additionalProperties` is dropped entirely. Anthropic strict
        mode requires it; Gemini's upstream API rejects it as an
        unknown field (schema enforcement is implicit in Gemini's
        function-calling model, so the keyword is redundant there).

    The transform walks a deep copy so the caller's dict isn't mutated.
    """
    from copy import deepcopy

    schema = deepcopy(schema)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "const" in node:
                # Always drop const (Gemini rejects it). Promote to enum
                # only if no enum already exists — never overwrite.
                value = node.pop("const")
                if "enum" not in node:
                    node["enum"] = [value]
            node.pop("additionalProperties", None)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


def _to_gemini_tools(tools: list[ToolSpec]) -> types.Tool:
    """Translate ToolSpec list → a single types.Tool with all declarations.

    Gemini packs all function declarations into ONE Tool object (the
    .function_declarations list), unlike Anthropic's flat list of dicts.
    """
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=t.name,
                description=t.description,
                # SDK accepts a JSON-Schema dict at runtime; its type stub
                # narrowed to Schema only. Pass-through is the documented
                # google-genai pattern.
                parameters=_gemini_compat_schema(t.input_schema),  # type: ignore[arg-type]
            )
            for t in tools
        ]
    )


def _to_gemini_tool_config(tool_choice: str) -> types.ToolConfig:
    if tool_choice == "auto":
        mode: Any = "AUTO"
        allowed: list[str] | None = None
    elif tool_choice == "any":
        mode = "ANY"
        allowed = None
    else:
        # Treat anything else as a specific tool name to force.
        mode = "ANY"
        allowed = [tool_choice]

    cfg = types.FunctionCallingConfig(mode=mode, allowed_function_names=allowed)
    return types.ToolConfig(function_calling_config=cfg)


def _extract_text(response: Any) -> str:
    """Concatenate any text parts in the first candidate."""
    parts: list[str] = []
    for cand in response.candidates or []:
        content = getattr(cand, "content", None)
        if content is None:
            continue
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _extract_tool_calls(response: Any) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for cand in response.candidates or []:
        content = getattr(cand, "content", None)
        if content is None:
            continue
        for part in getattr(content, "parts", None) or []:
            fc = getattr(part, "function_call", None)
            if fc is None:
                continue
            # Gemini's id is optional; synthesize a positional id if missing
            # so callers can still round-trip the call when handing back
            # function_response parts.
            call_id = getattr(fc, "id", None) or f"gemini-call-{len(calls)}"
            args = getattr(fc, "args", None) or {}
            calls.append(ToolCall(id=call_id, name=fc.name, input=dict(args)))
    return calls


def _stop_reason(response: Any) -> str:
    """Pick the first candidate's finish_reason as the stop reason."""
    for cand in response.candidates or []:
        fr = getattr(cand, "finish_reason", None)
        if fr is not None:
            return str(fr)
    return "unknown"


def call(
    *,
    cfg: ModelConfig,
    system: str | None,
    prompt: str,
    max_tokens: int,
    temperature: float | None,
    timeout_s: float,
    cache_prompt: bool,  # accepted for API symmetry; no-op for Gemini.
    tools: list[ToolSpec] | None,
    tool_choice: str | None,
    registry_key: str,
) -> Response:
    del cache_prompt  # explicit no-op for parity with Anthropic adapter

    config_kwargs: dict[str, Any] = {"max_output_tokens": max_tokens}
    if system is not None:
        config_kwargs["system_instruction"] = system
    if temperature is not None:
        config_kwargs["temperature"] = temperature
    if tools:
        config_kwargs["tools"] = [_to_gemini_tools(tools)]
        if tool_choice is not None:
            config_kwargs["tool_config"] = _to_gemini_tool_config(tool_choice)

    config = types.GenerateContentConfig(**config_kwargs)
    client = _get_client()
    started = time.monotonic()

    try:
        response = client.models.generate_content(
            model=cfg.provider_model_id,
            contents=prompt,
            config=config,
        )
    except Exception as raw_e:
        raise _classify(raw_e) from raw_e

    latency_ms = int((time.monotonic() - started) * 1000)
    usage = getattr(response, "usage_metadata", None)

    return Response(
        text=_extract_text(response),
        model=registry_key,
        provider=cfg.provider,
        provider_model_id=cfg.provider_model_id,
        latency_ms=latency_ms,
        input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
        output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        # google-genai exposes cache_creation only via the caches API:
        cache_creation_tokens=0,
        cache_read_tokens=getattr(usage, "cached_content_token_count", 0) or 0,
        stop_reason=_stop_reason(response),
        cached=False,
        tool_calls=_extract_tool_calls(response),
    )
