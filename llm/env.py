"""Environment loading for the llm package — entry-point use only.

Per CODE_QUALITY_STANDARD M-1 (composition root) + M-2 (no side
effects on import), the llm package itself does NOT load .env at
import time. Any entry point that wants .env auto-loaded calls
`load_env_if_available()` exactly once, before invoking `llm.ask`
or anything else that reads env vars.

This is the M-3 exception in action: a dedicated config-loader
module containing the only env-read side effect, called from the
entry point.
"""

from __future__ import annotations


def load_env_if_available() -> bool:
    """Load variables from a project-root `.env` into the process env
    if `python-dotenv` is installed. Existing env vars are NOT
    overwritten (shell wins over file).

    Returns True if dotenv was loaded, False if python-dotenv wasn't
    installed. The False path is silent — callers that REQUIRE
    .env-style loading should install python-dotenv as a hard dep.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    load_dotenv(override=False)
    return True
