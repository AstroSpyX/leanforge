"""Smoke test: confirms leanclient works on the bundled example project.

Verifies the three primitives the rest of the pipeline depends on:
  1. get_diagnostics                  — plain LSP diagnostics
  2. get_goal / get_term_goal         — InfoView-equivalent goal state
  3. get_interactive_diagnostics      — structured TaggedText messages

Run:
    uv run --with leanclient --python 3.12 smoke_test.py
"""
import json
import sys
from pathlib import Path

import leanclient as lc

PROJECT = Path(__file__).parent / "examples" / "scratch"
FILE = "Scratch/Basic.lean"


def main() -> int:
    print(f"[smoke] opening {PROJECT}", file=sys.stderr)
    client = lc.LeanLSPClient(str(PROJECT))
    try:
        sfc = client.create_file_client(FILE)

        print("[smoke] requesting diagnostics...", file=sys.stderr)
        diags = sfc.get_diagnostics().diagnostics
        print(f"[smoke] got {len(diags)} diagnostic(s)", file=sys.stderr)

        first_err = next((d for d in diags if d.get("severity") == 1), None)
        if first_err is None:
            print("[smoke] no error found — example file may have changed", file=sys.stderr)
            return 1

        rng = first_err["range"]["start"]
        line, char = rng["line"], rng["character"]
        print(f"[smoke] probing goal at line={line} char={char}", file=sys.stderr)
        goal = sfc.get_goal(line, char)
        term = sfc.get_term_goal(line, char)
        idiags = sfc.get_interactive_diagnostics()

        print(json.dumps({
            "diagnostics_count": len(diags),
            "first_error_message": first_err["message"][:80],
            "goal_at_error": goal,
            "term_goal_at_error": term,
            "interactive_diagnostics_count": len(idiags),
        }, indent=2, default=str))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
