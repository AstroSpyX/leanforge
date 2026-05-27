"""leanforge.llm — provider-agnostic LLM access.

Public API:
    ask(prompt, model=..., system=..., tools=..., tool_choice=...) -> Response
    Response, ToolCall                 (response shapes)
    ToolSpec                           (tool declaration)
    AskLLMError + subclasses           (typed errors)
    MODELS, DEFAULT_MODEL              (model registry)

Per CODE_QUALITY_STANDARD M-1 + M-2, this module does NOT load `.env`
or perform any other I/O on import. Entry points that want `.env`
auto-loaded must call `llm.env.load_env_if_available()` once at
startup. `refine.__main__` and `llm.smoke_anthropic` already do this.
Library-only callers (REPLs, notebooks, third-party CLIs) are
responsible for ensuring relevant API keys are set in os.environ
before calling `ask`.
"""

from __future__ import annotations

from llm.ask import ask
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
from llm.models import DEFAULT_MODEL, MODELS, ModelConfig
from llm.response import Response, ToolCall
from llm.tools import ToolSpec

__all__ = [
    "APIBadRequest",
    "APIServerError",
    "APITimeout",
    "AskLLMError",
    "AuthError",
    "DEFAULT_MODEL",
    "MODELS",
    "ModelConfig",
    "ModelNotFound",
    "OverloadedError",
    "RateLimitError",
    "Response",
    "ToolCall",
    "ToolSpec",
    "ask",
]
