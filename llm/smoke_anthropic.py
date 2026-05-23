"""Smoke test: one call per model + verify local disk cache hit.

Run:
  uv run --with anthropic --with python-dotenv --python 3.12 \\
      -m llm.smoke_anthropic

Requires ANTHROPIC_API_KEY in env. The .env in the project root is
auto-loaded on import (see llm/__init__.py).
"""

from __future__ import annotations

import sys

from llm.ask_llm import AskLLMError, ask_llm

PROMPT = "Reply with the single word: OK"


def main() -> int:
    failed = 0
    for model in ("haiku", "sonnet", "opus"):
        print(f"\n=== {model} ===", file=sys.stderr)
        try:
            r1 = ask_llm(PROMPT, model=model)
            print(f"text:        {r1.text!r}")
            print(f"latency_ms:  {r1.latency_ms}")
            print(f"tokens in/out: {r1.input_tokens}/{r1.output_tokens}")
            print(
                f"cache create/read: {r1.cache_creation_tokens}/{r1.cache_read_tokens}"
            )
            print(f"stop_reason: {r1.stop_reason}")
            print(f"cached:      {r1.cached}  (expect False on first call)")

            # Second identical call should hit the local disk cache.
            r2 = ask_llm(PROMPT, model=model)
            print(
                f"second call cached: {r2.cached}  "
                f"(expect True)  latency_ms={r2.latency_ms}"
            )
            if not r2.cached:
                print("  WARN: second call was not a cache hit", file=sys.stderr)
        except AskLLMError as e:
            print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
