"""Public LLM entry point — provider-agnostic dispatcher.

```python
from llm import ask, ToolSpec
from llm.tools.submit_fix import SUBMIT_FIX_TOOL

response = ask(
    "Fix the type error on line 5",
    model="sonnet",
    system="You are an expert Lean 4 engineer.",
    tools=[SUBMIT_FIX_TOOL],
    tool_choice="submit_fix",
)
fix = response.tool_calls[0].input  # already schema-validated by the provider
```

Routing rules:
  - Validate the model exists in `llm.models.MODELS`.
  - Compute a deterministic cache key over the full request payload
    (including tools and tool_choice — different tool sets must not
    share a cache entry even when prompts collide).
  - If `use_cache=True` and the key hits the disk cache, reconstruct
    the Response (with `cached=True`) and skip the API call.
  - Otherwise dispatch to the adapter in `llm.providers.{provider}`.
  - On success, write the Response to the disk cache.

Tool-use is a first-class shape. There is no separate prose-only
fallback path: callers who don't want tools just pass `tools=None`.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from typing import Any

from llm import cache
from llm.models import DEFAULT_MODEL, MODELS
from llm.response import Response, ToolCall
from llm.tools import ToolSpec


def _build_cache_key(
    *,
    provider_model_id: str,
    system: str | None,
    prompt: str,
    temperature: float | None,
    max_tokens: int,
    tools: list[ToolSpec] | None,
    tool_choice: str | None,
) -> dict[str, Any]:
    """Stable, JSON-serializable representation of the API request.

    Tools and tool_choice are part of the key — same prompt with
    different tool sets must produce different cached entries.
    """
    serialized_tools: list[dict[str, Any]] | None = None
    if tools:
        serialized_tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "strict": t.strict,
            }
            for t in tools
        ]
    return {
        "provider_model_id": provider_model_id,
        "system": system,
        "prompt": prompt,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "tools": serialized_tools,
        "tool_choice": tool_choice,
    }


def _response_from_cache_hit(hit: dict[str, Any]) -> Response:
    """Reconstruct a Response from a cached dict, restoring tool_calls."""
    payload = {**hit, "cached": True}
    raw_calls = payload.pop("tool_calls", None) or []
    payload["tool_calls"] = [ToolCall(**c) for c in raw_calls]
    return Response(**payload)


def ask(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int = 8192,
    timeout_s: float = 120.0,
    use_cache: bool = True,
    cache_prompt: bool = True,
    tools: list[ToolSpec] | None = None,
    tool_choice: str | None = None,
) -> Response:
    """Make one LLM call. Returns a provider-agnostic Response.

    `system` is the system prompt (model-instructions). Pass `None` to
    omit; provider adapters either skip the field or use their own
    default (Gemini's `system_instruction` is optional).

    `tools` enables structured tool use. With `tool_choice` set to a
    tool name, the provider guarantees the response will contain a
    matching tool_use block — text may still be present alongside it.

    Caching is keyed on the full payload (model, system, prompt, temp,
    max_tokens, tools, tool_choice). Mutating any of these produces a
    new cache entry.
    """
    if model not in MODELS:
        raise ValueError(f"unknown model: {model!r}; registry keys: {list(MODELS)}")

    cfg = MODELS[model]
    temp = cfg.default_temperature if temperature is None else temperature

    cache_key = _build_cache_key(
        provider_model_id=cfg.provider_model_id,
        system=system,
        prompt=prompt,
        temperature=temp,
        max_tokens=max_tokens,
        tools=tools,
        tool_choice=tool_choice,
    )

    if use_cache:
        hit = cache.get(cache_key)
        if hit is not None:
            print(
                f"[ask] CACHE HIT  model={model} "
                f"({cfg.provider}:{cfg.provider_model_id})  "
                f"saved tokens in/out={hit['input_tokens']}/{hit['output_tokens']}  "
                f"(no API call)",
                file=sys.stderr,
            )
            return _response_from_cache_hit(hit)

    tools_count = len(tools) if tools else 0
    print(
        f"[ask] model={model} ({cfg.provider}:{cfg.provider_model_id}) "
        f"temp={temp} max_tokens={max_tokens} timeout={timeout_s}s "
        f"tools={tools_count} tool_choice={tool_choice} cache_prompt={cache_prompt}",
        file=sys.stderr,
    )

    if cfg.provider == "anthropic":
        from llm.providers import anthropic as anthropic_provider

        response = anthropic_provider.call(
            cfg=cfg,
            system=system,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temp,
            timeout_s=timeout_s,
            cache_prompt=cache_prompt,
            tools=tools,
            tool_choice=tool_choice,
            registry_key=model,
        )
    elif cfg.provider == "google":
        from llm.providers import google as google_provider

        response = google_provider.call(
            cfg=cfg,
            system=system,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temp,
            timeout_s=timeout_s,
            cache_prompt=cache_prompt,
            tools=tools,
            tool_choice=tool_choice,
            registry_key=model,
        )
    else:
        raise ValueError(f"unknown provider: {cfg.provider!r} (model={model})")

    if use_cache:
        cache.put(cache_key, asdict(response))

    return response
