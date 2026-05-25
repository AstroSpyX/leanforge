"""leanforge.llm — provider-agnostic LLM access.

Public API:
    ask(prompt, model=..., system=..., tools=..., tool_choice=...) -> Response
    Response, ToolCall                 (response shapes)
    ToolSpec                           (tool declaration)
    AskLLMError + subclasses           (typed errors)
    MODELS, DEFAULT_MODEL              (model registry)

On import, auto-loads variables from a project-root `.env` file into
the process environment, WITHOUT overwriting variables that are already
set. This makes ANTHROPIC_API_KEY / GOOGLE_API_KEY available to `ask`
without the user having to `export` them in every shell session.
"""

from __future__ import annotations

try:
    from dotenv import load_dotenv

    # Walk up from this file to find .env in the project root, then load.
    # override=False means env vars set by the shell win over the file.
    load_dotenv(override=False)
except ImportError:
    # python-dotenv not installed — fall back to whatever's in os.environ.
    # ask() will surface a clear AuthError if the key is missing.
    pass

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
