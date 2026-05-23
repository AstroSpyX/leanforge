"""ask_llm — Claude-backed LLM interface for leanforge.

Public surface:
  ask_llm(prompt, ...) -> Response         core function
  ask_llm_text(prompt, ...) -> str         ergonomic shortcut (just the text)
  ask_llm_fix(diagnostic, ...) -> Response fix-mode entry point

Requires ANTHROPIC_API_KEY in env (loaded from project-root .env
automatically by llm/__init__.py). Models registered in models.py.

Run the smoke test:
  uv run --with anthropic --with python-dotenv --python 3.12 \\
      -m llm.smoke_anthropic
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

import anthropic

from llm import cache
from llm.models import DEFAULT_MODEL, MODELS

# ---------- Response ----------


@dataclass
class Response:
    text: str
    model: str  # registry key, e.g. "sonnet"
    provider: str  # "anthropic" | (future) "openai"
    provider_model_id: str  # actual provider model ID used
    mode: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int  # tokens written into provider's prompt cache
    cache_read_tokens: int  # tokens served from provider's prompt cache
    stop_reason: str
    cached: bool  # served from our local disk cache


# ---------- Errors ----------


class AskLLMError(Exception):
    """Base for all errors surfaced by ask_llm."""


class AuthError(AskLLMError):
    """Missing API key or rejected credentials (401/403)."""


class RateLimitError(AskLLMError):
    """Provider rate limit hit (429)."""


class OverloadedError(AskLLMError):
    """Provider temporarily overloaded (529 for Anthropic)."""


class ModelNotFound(AskLLMError):
    """Provider does not recognize the requested model (404)."""


class APITimeout(AskLLMError):
    """Request exceeded our timeout_s without the provider responding."""


class APIServerError(AskLLMError):
    """Provider returned a 5xx other than the overloaded case."""


class APIBadRequest(AskLLMError):
    """Provider rejected the request payload as malformed (400)."""


# ---------- System prompts per mode ----------

SYSTEM_PROMPTS: dict[str, str] = {
    "raw": "You are a helpful assistant.",
    "tactic": (
        "You are an expert in Lean 4. When asked for a tactic, output only "
        "the tactic line(s) inside a single ```lean4 code block. No prose."
    ),
}


# ---------- Client (lazy, module-level) ----------

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise AuthError("ANTHROPIC_API_KEY not set in environment")
        _client = anthropic.Anthropic()
    return _client


# ---------- Retry policy ----------


def _classify_and_raise(e: Exception) -> AskLLMError:
    """Map an anthropic SDK exception to our typed hierarchy."""
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


def _retry_call(
    fn: Callable[[], anthropic.types.Message],
    max_retries: int = 3,
) -> anthropic.types.Message:
    """Exponential backoff on RateLimit/Overloaded, single retry on
    Timeout/ServerError, no retry on Auth/BadRequest/ModelNotFound."""
    delay = 1.0
    last_typed: AskLLMError | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except anthropic.APIError as raw_e:
            typed = _classify_and_raise(raw_e)
            last_typed = typed
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
    # Loop exits without return only on the final-retry raise above; this
    # path is defensive but mypy needs the explicit return signal.
    raise last_typed if last_typed else AskLLMError("retry exhausted")


# ---------- Core function ----------


def ask_llm(
    prompt: str,
    model: str = DEFAULT_MODEL,
    mode: str = "raw",
    temperature: float | None = None,
    max_tokens: int = 2048,
    timeout_s: float = 120.0,
    use_cache: bool = True,
    cache_prompt: bool = True,
    system_override: str | None = None,
    prefill: str | None = None,
) -> Response:
    """Call Claude with a single user prompt.

    `system_override` replaces SYSTEM_PROMPTS[mode] for callers (like
    refine) that own their own system prompt content. `prefill` adds a
    final assistant turn so the model literally continues from that
    string — used by JSON-only callers to force the first byte. When
    prefill is set, `response.text` returns prefill + the model's
    completion so callers always get the full intended string.
    """
    if model not in MODELS:
        raise ValueError(f"unknown model: {model!r}; registry keys: {list(MODELS)}")
    if system_override is None and mode not in SYSTEM_PROMPTS:
        raise ValueError(f"unknown mode: {mode!r}; valid modes: {list(SYSTEM_PROMPTS)}")

    cfg = MODELS[model]
    if cfg.provider != "anthropic":
        # OpenAI etc. not implemented yet — see LLM.spec.txt rev 5
        # "Future transport" section. Adding requires a parallel
        # _call_openai branch and SDK error mapping.
        raise AskLLMError(
            f"provider {cfg.provider!r} not yet implemented "
            f"(model={model}, only 'anthropic' supported in current build)"
        )

    # Resolve effective temperature. None means: don't send it (some
    # newer models, e.g. Opus 4.7, deprecated the parameter).
    temp = cfg.default_temperature if temperature is None else temperature

    system_str = (
        system_override if system_override is not None else SYSTEM_PROMPTS[mode]
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    if prefill is not None:
        messages.append({"role": "assistant", "content": prefill})

    # Cache key reflects the actual payload, including model+system+temp.
    cache_key = {
        "provider_model_id": cfg.provider_model_id,
        "system": system_str,
        "messages": messages,
        "temperature": temp,
        "max_tokens": max_tokens,
    }
    if use_cache:
        hit = cache.get(cache_key)
        if hit is not None:
            print(
                f"[ask_llm] CACHE HIT  model={model} "
                f"({cfg.provider}:{cfg.provider_model_id})  "
                f"saved tokens in/out={hit['input_tokens']}/{hit['output_tokens']}  "
                f"(no API call)",
                file=sys.stderr,
            )
            return Response(**{**hit, "cached": True})

    # If caching the system prompt at the API level, wrap it as a content
    # block with cache_control. Short system prompts won't actually be
    # cached (Anthropic minimum block size applies), but cache_control
    # is harmless when ignored.
    if cache_prompt:
        system_payload: Any = [
            {"type": "text", "text": system_str, "cache_control": {"type": "ephemeral"}}
        ]
    else:
        system_payload = system_str

    print(
        f"[ask_llm] model={model} ({cfg.provider}:{cfg.provider_model_id}) "
        f"mode={mode} temp={temp} max_tokens={max_tokens} "
        f"timeout={timeout_s}s cache_prompt={cache_prompt}",
        file=sys.stderr,
    )

    client = _get_client()
    started = time.monotonic()

    # Build kwargs — omit `temperature` entirely when resolved value is
    # None (Opus 4.7 etc. reject the parameter).
    kwargs: dict[str, Any] = dict(
        model=cfg.provider_model_id,
        max_tokens=max_tokens,
        system=system_payload,
        messages=messages,
        timeout=timeout_s,
    )
    if temp is not None:
        kwargs["temperature"] = temp

    def call() -> anthropic.types.Message:
        # The Anthropic SDK's create() return type widens to Any via overloads
        # when `messages` is dynamic; cast explicitly to keep mypy --strict happy.
        result: anthropic.types.Message = client.messages.create(**kwargs)
        return result

    msg = _retry_call(call)
    latency_ms = int((time.monotonic() - started) * 1000)

    generated = "".join(b.text for b in msg.content if hasattr(b, "text"))
    # When the caller prefilled, the model continues FROM the prefill;
    # response.content is just what was added. Reconstruct the complete
    # text so JSON parsers etc. see the whole document.
    text = (prefill + generated) if prefill is not None else generated
    usage = msg.usage

    response = Response(
        text=text,
        model=model,
        provider=cfg.provider,
        provider_model_id=cfg.provider_model_id,
        mode=mode,
        latency_ms=latency_ms,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        stop_reason=msg.stop_reason or "unknown",
        cached=False,
    )

    if use_cache:
        cache.put(cache_key, asdict(response))

    return response


def ask_llm_text(prompt: str, **kw: Any) -> str:
    return ask_llm(prompt, **kw).text


# ---------- Fix mode ----------


def ask_llm_fix(
    diagnostic: dict[str, Any],
    model: str = DEFAULT_MODEL,
    **kw: Any,
) -> Response:
    """Take one record from leanforge's diagnostics JSON, assemble a
    fix prompt, and call ask_llm. Returns a Response containing
    (ideally) a single ```lean4 code block with corrected code."""
    parts: list[str] = []
    parts.append("Fix the Lean 4 error described below.\n")
    parts.append(f"\nError message:\n{diagnostic.get('messageText', '(no message)')}\n")

    rng = diagnostic.get("range") or {}
    start = rng.get("start") or {}
    parts.append(
        f"\nLocation: line {start.get('line', '?')}, "
        f"column {start.get('character', '?')}\n"
    )

    goal = diagnostic.get("goal")
    if isinstance(goal, dict) and goal.get("rendered"):
        parts.append(f"\nTactic goal at error position:\n{goal['rendered']}\n")

    term_goal = diagnostic.get("termGoal")
    if isinstance(term_goal, dict) and term_goal.get("goal"):
        parts.append(f"\nExpected type at error position: {term_goal['goal']}\n")

    enc = diagnostic.get("enclosingDeclaration")
    if isinstance(enc, dict):
        parts.append(
            f"\nEnclosing declaration: {enc.get('name')} (kind={enc.get('kind')})\n"
        )

    snippet = diagnostic.get("sourceSnippet") or {}
    if snippet.get("lines"):
        parts.append("\nSource around the error:\n```lean4\n")
        parts.append("\n".join(snippet["lines"]))
        parts.append("\n```\n")

    parts.append(
        "\nProduce a corrected version of the enclosing declaration. "
        "Output ONLY a single ```lean4 code block containing the fixed "
        "declaration. No prose. No explanation outside the code block."
    )

    return ask_llm(prompt="".join(parts), model=model, mode="raw", **kw)
