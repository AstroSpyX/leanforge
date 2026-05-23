"""leanforge.llm — Claude-backed LLM interface.

On import, auto-loads variables from a project-root `.env` file (if any)
into the process environment, WITHOUT overwriting variables that are
already set. This makes ANTHROPIC_API_KEY available to ask_llm without
the user having to `export` it every shell session.
"""

try:
    from dotenv import load_dotenv

    # Walk up from this file to find .env in the project root, then load.
    # override=False means env vars set by the shell win over the file.
    load_dotenv(override=False)
except ImportError:
    # python-dotenv not installed — fall back to whatever's in os.environ.
    # ask_llm will still surface a clear AuthError if the key is missing.
    pass
