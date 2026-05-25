"""leanforge — Lean file → rich JSON diagnostics, single-file.

Captures the same data the Lean VS Code InfoView shows (diagnostics, goal
state, term goal, source context, enclosing declaration) and emits one
JSON document on stdout. Intended as the deterministic-evaluator stage
of an LLM-driven proof / fix loop.

Usage:
    uv run --with leanclient --python 3.12 leanforge.py <project_root> <file_relpath>

Example (using the bundled example project):
    uv run --with leanclient --python 3.12 leanforge.py examples/scratch Scratch/Basic.lean
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import leanclient as lc

# LSP DiagnosticSeverity: 1=Error, 2=Warning, 3=Info, 4=Hint
SEVERITY = {1: "error", 2: "warning", 3: "information", 4: "hint"}


def source_snippet(file_abs: Path, range_: dict, context: int = 3) -> dict:
    """Return ±context lines around the diagnostic range."""
    try:
        lines = file_abs.read_text().splitlines()
    except OSError as e:
        return {"error": str(e)}
    start_line = range_["start"]["line"]
    end_line = range_["end"]["line"]
    lo = max(0, start_line - context)
    hi = min(len(lines), end_line + context + 1)
    return {
        "startLine": lo,
        "lines": lines[lo:hi],
        "errorLineOffset": start_line - lo,
    }


def find_enclosing_decl(symbols: list[dict], line: int) -> dict | None:
    """Walk LSP document symbols, return the innermost one containing `line`."""

    def walk(syms: list[dict]) -> dict | None:
        for s in syms:
            r = s.get("range") or s.get("selectionRange")
            if not r:
                continue
            if r["start"]["line"] <= line <= r["end"]["line"]:
                deeper = walk(s.get("children") or [])
                return deeper or s
        return None

    return walk(symbols)


def enrich(
    sfc, file_abs: Path, doc_symbols: list[dict], diag: dict, interactive: dict | None
) -> dict:
    rng = diag["range"]
    line = rng["start"]["line"]
    char = rng["start"]["character"]

    try:
        goal = sfc.get_goal(line, char)
    except Exception as e:
        goal = {"_error": str(e)}
    try:
        term_goal = sfc.get_term_goal(line, char)
    except Exception as e:
        term_goal = {"_error": str(e)}

    enclosing = find_enclosing_decl(doc_symbols, line)
    enclosing_view = None
    if enclosing:
        enclosing_view = {
            "name": enclosing.get("name"),
            "kind": enclosing.get("kind"),
            "range": enclosing.get("range"),
        }

    return {
        "severity": SEVERITY.get(diag.get("severity"), str(diag.get("severity"))),
        "range": rng,
        "fullRange": diag.get("fullRange"),
        "messageText": diag.get("message"),
        "messageInteractive": (interactive or {}).get("message")
        if interactive
        else None,
        "source": diag.get("source"),
        "tags": diag.get("tags"),
        "goal": goal,
        "termGoal": term_goal,
        "enclosingDeclaration": enclosing_view,
        "sourceSnippet": source_snippet(file_abs, rng),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "project_root",
        help="Path to a Lake project root (has lakefile.* and lean-toolchain)",
    )
    ap.add_argument("file_relpath", help="Lean file path relative to project_root")
    args = ap.parse_args()

    project = Path(args.project_root).resolve()
    file_abs = (project / args.file_relpath).resolve()
    if not file_abs.exists():
        print(f"file not found: {file_abs}", file=sys.stderr)
        return 2

    print(f"[leanforge] opening project {project}", file=sys.stderr)
    client = lc.LeanLSPClient(str(project))
    try:
        sfc = client.create_file_client(args.file_relpath)

        print("[leanforge] waiting for elaboration...", file=sys.stderr)
        diags_result = sfc.get_diagnostics()
        diags = diags_result.diagnostics
        print(
            f"[leanforge] got {len(diags)} diagnostic(s), success={diags_result.success}",
            file=sys.stderr,
        )

        print("[leanforge] fetching interactive diagnostics...", file=sys.stderr)
        try:
            interactive_list = sfc.get_interactive_diagnostics()
        except Exception as e:
            print(f"[leanforge] interactive_diagnostics failed: {e}", file=sys.stderr)
            interactive_list = []

        print("[leanforge] fetching document symbols...", file=sys.stderr)
        try:
            doc_symbols = sfc.get_document_symbols()
        except Exception as e:
            print(f"[leanforge] document_symbols failed: {e}", file=sys.stderr)
            doc_symbols = []

        def key(d: dict) -> tuple:
            r = d["range"]
            return (
                r["start"]["line"],
                r["start"]["character"],
                r["end"]["line"],
                r["end"]["character"],
            )

        interactive_by_range = {key(d): d for d in interactive_list if "range" in d}

        enriched = []
        for d in diags:
            inter = interactive_by_range.get(key(d))
            enriched.append(enrich(sfc, file_abs, doc_symbols, d, inter))

        counts: dict[str, int] = {}
        for e in enriched:
            counts[e["severity"]] = counts.get(e["severity"], 0) + 1

        output = {
            "project": str(project),
            "file": args.file_relpath,
            "elaborationSucceeded": diags_result.success,
            "timedOut": diags_result.timed_out,
            "counts": counts,
            "diagnostics": enriched,
        }
        json.dump(output, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0
    finally:
        print("[leanforge] closing client", file=sys.stderr)
        client.close()


if __name__ == "__main__":
    sys.exit(main())
