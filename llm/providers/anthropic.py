"""Anthropic provider adapter.

Translates the provider-agnostic `call()` API into Anthropic's
Messages API, with:
  - Native tool-use with `strict: true` for schema-guaranteed output.
  - SDK exception mapping → `llm.errors.AskLLMError` hierarchy.
  - Retry policy: exponential backoff on RateLimit/Overloaded, single
    retry on Timeout/ServerError, no retry on Auth/BadRequest/404.
  - Prompt-cache hint on the system prompt when `cache_prompt=True`
    (Anthropic enforces a 1024-token minimum block size; ignored
    silently if the system prompt is too short).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

import anthropic

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

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise AuthError("ANTHROPIC_API_KEY not set in environment")
        _client = anthropic.Anthropic()
    return _client


def _classify(e: Exception) -> AskLLMError:
    if isinstance(e, anthropic.AuthenticationError):
        return AuthError(str(e))
    if isinstance(e, anthropic.RateLimitError):
        return RateLimitError(str(e))
    if isinstance(e, anthropic.APITimeoutError):
        return APITimeout(str(e))
    if isinstance(e, anthropic.APIStatusError):
        sc = e.status_code
        if sc == 529:
            return OverloadedError(str(e))
        if sc == 404:
            return ModelNotFound(str(e))
        if sc in (401, 403):
            return AuthError(str(e))
        if sc == 400:
            return APIBadRequest(str(e))
        if sc >= 500:
            return APIServerError(str(e))
        return AskLLMError(f"HTTP {sc}: {e}")
    return AskLLMError(str(e))


def _retry(
    fn: Callable[[], anthropic.types.Message],
    max_retries: int = 3,
) -> anthropic.types.Message:
    delay = 1.0
    last: AskLLMError | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except anthropic.APIError as raw_e:
            typed = _classify(raw_e)
            last = typed
            retryable_many = isinstance(typed, RateLimitError | OverloadedError)
            retryable_once = isinstance(typed, APITimeout | APIServerError)
            if retryable_many and attempt < max_retries:
                time.sleep(delay)
                delay *= 2
                continue
            if retryable_once and attempt == 0:
                time.sleep(delay)
                continue
            raise typed from raw_e
    raise last if last else AskLLMError("retry exhausted")


_STRICT_UNSUPPORTED_KEYS = (
    # Anthropic strict mode rejects numeric range constraints with
    # "For 'number' type, properties maximum, minimum are not supported".
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    # And string-length / pattern constraints with similar errors.
    "minLength",
    "maxLength",
    "pattern",
    # And array/object size constraints.
    "minItems",
    "maxItems",
    "minProperties",
    "maxProperties",
)


def _anthropic_strict_compat_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip JSON Schema keywords Anthropic strict mode doesn't support.

    Pydantic emits `minimum`/`maximum` for `Field(ge=, le=)`, `pattern`
    for regex constraints, etc. Anthropic strict mode rejects all of
    these with HTTP 400 ("properties X are not supported"). Strip them
    from the schema we send to Anthropic — client-side Pydantic
    validation on the way back still enforces the original constraints.
    """
    from copy import deepcopy

    schema = deepcopy(schema)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key in _STRICT_UNSUPPORTED_KEYS:
                node.pop(key, None)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


def _to_anthropic_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Translate ToolSpec → Anthropic's tool dict shape.

    `strict: true` makes Anthropic validate the model's tool_use input
    against `input_schema` server-side; the model retries internally
    on schema mismatch, so callers receive a guaranteed-valid input.
    Strict-mode schema constraints are narrower than full JSON Schema
    — strip the unsupported keywords here before sending.
    """
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": (
                _anthropic_strict_compat_schema(t.input_schema)
                if t.strict
                else t.input_schema
            ),
            "strict": t.strict,
        }
        for t in tools
    ]


def _to_anthropic_tool_choice(tool_choice: str) -> dict[str, str]:
    """Map our small enum to Anthropic's tool_choice dict."""
    if tool_choice == "auto":
        return {"type": "auto"}
    if tool_choice == "any":
        return {"type": "any"}
    # Anything else is interpreted as a specific tool name to force.
    return {"type": "tool", "name": tool_choice}


def _extract_tool_calls(msg: anthropic.types.Message) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for block in msg.content:
        if block.type == "tool_use":
            calls.append(
                ToolCall(
                    id=block.id,
                    name=block.name,
                    input=dict(block.input) if isinstance(block.input, dict) else {},
                )
            )
    return calls


def _extract_text(msg: anthropic.types.Message) -> str:
    return "".join(b.text for b in msg.content if b.type == "text")


def call(
    *,
    cfg: ModelConfig,
    system: str | None,
    prompt: str,
    max_tokens: int,
    temperature: float | None,
    timeout_s: float,
    cache_prompt: bool,
    tools: list[ToolSpec] | None,
    tool_choice: str | None,
    registry_key: str,
) -> Response:
    """Make one Anthropic Messages API call and adapt the response.

    `registry_key` is our internal model key (e.g. "sonnet") that
    populates Response.model — distinct from cfg.provider_model_id
    (the upstream ID like "claude-sonnet-4-6").
    """
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    kwargs: dict[str, Any] = {
        "model": cfg.provider_model_id,
        "max_tokens": max_tokens,
        "messages": messages,
        "timeout": timeout_s,
    }

    if system is not None:
        if cache_prompt:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            kwargs["system"] = system

    if temperature is not None:
        kwargs["temperature"] = temperature

    if tools:
        kwargs["tools"] = _to_anthropic_tools(tools)
        if tool_choice is not None:
            kwargs["tool_choice"] = _to_anthropic_tool_choice(tool_choice)

    client = _get_client()
    started = time.monotonic()

    def do_call() -> anthropic.types.Message:
        result: anthropic.types.Message = client.messages.create(**kwargs)
        return result

    msg = _retry(do_call)
    latency_ms = int((time.monotonic() - started) * 1000)
    usage = msg.usage

    return Response(
        text=_extract_text(msg),
        model=registry_key,
        provider=cfg.provider,
        provider_model_id=cfg.provider_model_id,
        latency_ms=latency_ms,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        stop_reason=msg.stop_reason or "unknown",
        cached=False,
        tool_calls=_extract_tool_calls(msg),
    )
