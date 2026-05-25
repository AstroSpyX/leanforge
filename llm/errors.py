"""Typed error hierarchy raised by `llm.ask` and the provider adapters.

Every provider maps its own SDK exceptions onto this hierarchy so callers
never see provider-native exception types. Add new subclasses when they
correspond to a distinct retry policy or user-facing message, not for
every status code variant.
"""

from __future__ import annotations


class AskLLMError(Exception):
    """Base for all errors surfaced by `llm.ask`."""


class AuthError(AskLLMError):
    """Missing API key or rejected credentials (401/403)."""


class RateLimitError(AskLLMError):
    """Provider rate limit hit (429)."""


class OverloadedError(AskLLMError):
    """Provider temporarily overloaded (Anthropic 529)."""


class ModelNotFound(AskLLMError):
    """Provider does not recognize the requested model (404)."""


class APITimeout(AskLLMError):
    """Request exceeded our `timeout_s` without the provider responding."""


class APIServerError(AskLLMError):
    """Provider returned a 5xx other than the overloaded case."""


class APIBadRequest(AskLLMError):
    """Provider rejected the request payload as malformed (400)."""
