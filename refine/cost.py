"""Token-usage → USD cost estimation with per-retry inflation.

Cost table is hard-coded with a documented "verify at integration" note.
Pricing changes; this table is the single source of truth and gets bumped
when a provider publishes a change.

Cost numbers are cents per 1M tokens. The four kinds match what both
providers' APIs report in usage: input, output, cache_creation,
cache_read. (Gemini's caches API is not currently driven by our
adapter, so cache_* tokens are always 0 for Gemini in practice; the
rates are listed for completeness and to keep the schema uniform.)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

# Per-iteration cost is multiplied by (1 + RETRY_COST_INFLATION * retry_count)
# to account for the corrective-retry tokens that ask_llm pays for but the
# raw `Response.input_tokens` does not separately surface for the first try.
RETRY_COST_INFLATION: Final[float] = 0.15

# Cents per 1M tokens by provider_model_id. Keys MUST match
# llm/models.py `provider_model_id`. Tests cross-check (see
# tests/test_cost.py::test_every_registered_model_has_cost).
COSTS: Final[Mapping[str, Mapping[str, int]]] = {
    # ---- Anthropic (per anthropic.com/pricing) ----
    "claude-sonnet-4-6": {
        "input": 300,
        "output": 1500,
        "cache_creation": 375,
        "cache_read": 30,
    },
    "claude-opus-4-7": {
        "input": 1500,
        "output": 7500,
        "cache_creation": 1875,
        "cache_read": 150,
    },
    "claude-haiku-4-5-20251001": {
        "input": 100,
        "output": 500,
        "cache_creation": 125,
        "cache_read": 10,
    },
    # ---- Google Gemini (per ai.google.dev/gemini-api/docs/pricing) ----
    # Cached input is ~25% of regular input; we use Anthropic's
    # cache_creation/cache_read pattern even though Gemini bills
    # differently — the cache_* tokens are always 0 in our pipeline
    # today, so the exact ratio doesn't bind anything.
    "gemini-3.5-flash": {
        "input": 150,
        "output": 900,
        "cache_creation": 188,
        "cache_read": 38,
    },
    "gemini-3.1-pro-preview": {
        "input": 200,
        "output": 1200,
        "cache_creation": 250,
        "cache_read": 50,
    },
    "gemini-3.1-flash-lite": {
        "input": 25,
        "output": 150,
        "cache_creation": 31,
        "cache_read": 6,
    },
}

CENTS_PER_USD = 100
TOKENS_PER_MILLION = 1_000_000


class UnknownModelError(Exception):
    """The provider_model_id is not in the COSTS table — add it explicitly
    rather than fall back to a default that would silently mis-bill."""


def base_cost_usd(
    provider_model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Compute the un-retry-inflated cost for one Anthropic API call.

    Raises UnknownModelError if the model is not in the COSTS table —
    we never want to silently bill at a wrong rate by falling back.
    """
    table = COSTS.get(provider_model_id)
    if table is None:
        raise UnknownModelError(
            f"no cost entry for {provider_model_id!r}; known models: {sorted(COSTS)}"
        )
    cents = (
        table["input"] * input_tokens
        + table["output"] * output_tokens
        + table["cache_creation"] * cache_creation_tokens
        + table["cache_read"] * cache_read_tokens
    )
    return cents / TOKENS_PER_MILLION / CENTS_PER_USD


def iteration_cost_usd(base_cost: float, retry_count: int) -> float:
    """Inflate a base cost by 15% per retry.

    retry_count = 0 returns base_cost unchanged. We track retries here
    because ask_llm's Response only reports the FINAL successful call's
    tokens; corrective retries during JSON-parse failures cost extra
    tokens that the budget guard would otherwise underpredict.
    """
    if retry_count < 0:
        raise ValueError(f"retry_count must be non-negative, got {retry_count}")
    return base_cost * (1 + RETRY_COST_INFLATION * retry_count)
