"""CLI entry: `python -m refine ...`.

Maps argparse → refine.controller.refine() and converts the final Status
into the exit-code scheme documented in REFINE.spec.txt §PUBLIC API / CLI.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from refine.controller import refine
from refine.state import Status

EXIT_SUCCESS = 0
EXIT_PAUSED_QUIT = 1
EXIT_MAX_ITERS = 2
EXIT_LLM_ERROR = 3
EXIT_APPLY_ERROR = 4
EXIT_POLICY_VIOLATION = 5
EXIT_TIMEOUT_LEAN = 6
EXIT_LOOP_DETECTED = 7
EXIT_BUDGET_EXCEEDED = 8

_STATUS_EXIT_MAP: dict[Status, int] = {
    Status.SUCCESS: EXIT_SUCCESS,
    Status.MAX_ITERS: EXIT_MAX_ITERS,
    Status.LLM_ERROR: EXIT_LLM_ERROR,
    Status.APPLY_ERROR: EXIT_APPLY_ERROR,
    Status.POLICY_VIOLATION: EXIT_POLICY_VIOLATION,
    Status.STUCK_TIMEOUT: EXIT_TIMEOUT_LEAN,
    Status.LOOP_DETECTED: EXIT_LOOP_DETECTED,
    Status.BUDGET_EXCEEDED: EXIT_BUDGET_EXCEEDED,
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="refine",
        description="Run the refine loop on a Lean 4 file.",
    )
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument(
        "--file",
        required=True,
        dest="file_relpath",
        help="Path to the Lean file, relative to --project-root.",
    )
    parser.add_argument("--goal", required=True, help="English description of intent.")
    parser.add_argument("--mode", default="policy", choices=("auto", "step", "policy"))
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--max-iters", type=int, default=8)
    parser.add_argument("--lean-timeout", type=float, default=30.0)
    parser.add_argument("--max-cost-usd", type=float, default=1.00)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=8192,
        help="Per-call cap on LLM response tokens. Larger files / "
        "multi-fix responses need more headroom; truncation produces "
        "unterminated-JSON errors.",
    )
    parser.add_argument("--no-keep-raw-llm-io", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="Suppress info logs.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )
    history = refine(
        project_root=args.project_root,
        file_relpath=args.file_relpath,
        goal=args.goal,
        mode=args.mode,
        model=args.model,
        max_iters=args.max_iters,
        lean_timeout_seconds=args.lean_timeout,
        max_cost_usd=args.max_cost_usd,
        max_tokens=args.max_tokens,
        keep_raw_llm_io=not args.no_keep_raw_llm_io,
    )
    final = history.final_status or Status.MAX_ITERS
    print(
        f"final_status={final.value}  iterations={len(history.iterations)}  "
        f"cost=${history.iterations[-1].cumulative_cost_usd:.4f}"
        if history.iterations
        else f"final_status={final.value}  iterations=0",
        file=sys.stderr,
    )
    return _STATUS_EXIT_MAP.get(final, EXIT_PAUSED_QUIT)


if __name__ == "__main__":
    sys.exit(main())
