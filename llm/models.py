"""Registry of LLM models known to leanforge.

Adding a model means: pick a stable internal key (e.g. "sonnet") that
abstracts over the upstream version, point it at a current
`provider_model_id`, and set its `provider` field. Version-bumping a
model is then a one-line `provider_model_id` change here.

Avoid scattering model strings through the codebase — always look up
via MODELS[key].
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    provider: str  # "anthropic" | "google"
    provider_model_id: str  # the exact ID the upstream API expects
    default_temperature: float | None  # None = do NOT send temperature
    context_window: int  # input-token capacity (informational)


MODELS: dict[str, ModelConfig] = {
    # ---- Anthropic ----
    # Opus 4.7 deprecated the temperature parameter — must not be sent.
    "opus": ModelConfig("anthropic", "claude-opus-4-7", None, 200_000),
    "sonnet": ModelConfig("anthropic", "claude-sonnet-4-6", 0.0, 200_000),
    "haiku": ModelConfig("anthropic", "claude-haiku-4-5-20251001", 0.0, 200_000),
    # ---- Google Gemini (google-genai SDK) ----
    # Names follow our stable-key convention; bump provider_model_id as
    # Google releases new versions without touching call sites.
    "gemini-flash-lite": ModelConfig("google", "gemini-2.5-flash-lite", 0.0, 1_000_000),
    "gemini-flash": ModelConfig("google", "gemini-3.5-flash", 0.0, 1_000_000),
    "gemini-pro": ModelConfig("google", "gemini-3.1-pro", 0.0, 2_000_000),
}

DEFAULT_MODEL = "sonnet"
