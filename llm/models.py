"""Registry of Claude models available to ask_llm.

Hardcoding the model IDs here means version bumps are a one-line change.
Avoid scattering model strings through the codebase — always go via
MODELS[key].anthropic_id.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    provider: str  # "anthropic" | (future) "openai"
    provider_model_id: str  # exact model ID the provider expects
    default_temperature: float | None  # None = do NOT send temperature param
    context_window: int  # for sizing checks (informational)


MODELS: dict[str, ModelConfig] = {
    # Opus 4.7 deprecated the temperature parameter — must not be sent.
    "opus": ModelConfig("anthropic", "claude-opus-4-7", None, 200_000),
    "sonnet": ModelConfig("anthropic", "claude-sonnet-4-6", 0.0, 200_000),
    "haiku": ModelConfig("anthropic", "claude-haiku-4-5-20251001", 0.0, 200_000),
}

DEFAULT_MODEL = "sonnet"
