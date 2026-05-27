"""CLI entry: `python -m refine ...`.

Maps argparse → refine.controller.refine() and converts the final Status
into the exit-code scheme documented in REFINE.spec.txt §PUBLIC API / CLI.

Checker-framework flags compose extra stages on top of the default
pipeline (Lean compile → no sorries → signature preservation):

  --judge MODEL                  append an LLMJudgeChecker stage
                                 (the model is the cheap judge, e.g.
                                 'haiku' or 'gemini-flash-lite')
  --check-pattern-absent SPEC    append a PatternAbsentChecker stage.
                                 SPEC has the form NAME:PAT1,PAT2,...
                                 Patterns are Python regexes matched
                                 against proof body lines. Repeatable.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from llm.env import load_env_if_available
from refine.checkers import CheckerStage
from refine.checkers.llm_judge import LLMJudgeChecker
from refine.checkers.pattern_absent import PatternAbsentChecker
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
    parser.add_argument(
        "--judge",
        default=None,
        metavar="MODEL",
        help="Append an LLMJudgeChecker stage. Argument is the model "
        "key used for the judge (e.g. 'haiku', 'gemini-flash-lite'). "
        "Cheap models recommended — typically <1%% of worker cost.",
    )
    parser.add_argument(
        "--check-pattern-absent",
        action="append",
        default=[],
        metavar="NAME:PAT1,PAT2,...",
        help="Append a PatternAbsentChecker stage. NAME labels the "
        "stage for logging; the comma-separated patterns are Python "
        "regexes that must NOT match any proof-body line. Repeatable. "
        "Example: --check-pattern-absent 'no_gamma_op:Γ\\.op,Γ\\.inv'",
    )
    return parser.parse_args()


def _build_extra_stages(args: argparse.Namespace, goal: str) -> list[CheckerStage]:
    """Translate user-facing CLI flags into CheckerStage instances.

    Order: pattern-absent stages first (cheap, deterministic), judge
    last (the expensive semantic check). The stage runner short-
    circuits, so the judge only fires when prior stages pass.
    """
    stages: list[CheckerStage] = []
    for spec in args.check_pattern_absent:
        name, patterns = _parse_pattern_spec(spec)
        stages.append(
            CheckerStage(
                f"style:{name}",
                (PatternAbsentChecker(name=name, patterns=tuple(patterns)),),
            )
        )
    if args.judge is not None:
        stages.append(
            CheckerStage(
                "intent",
                (
                    LLMJudgeChecker(
                        name=f"judge:{args.judge}",
                        model=args.judge,
                        goal=goal,
                    ),
                ),
            )
        )
    return stages


_PATTERN_SPEC_RE = re.compile(r"^(?P<name>[A-Za-z0-9_-]+):(?P<patterns>.+)$")


def _parse_pattern_spec(spec: str) -> tuple[str, list[str]]:
    """Parse 'name:pat1,pat2,...' into (name, [pat1, pat2, ...])."""
    match = _PATTERN_SPEC_RE.match(spec)
    if match is None:
        raise SystemExit(
            f"--check-pattern-absent: bad spec {spec!r}; expected NAME:PAT1,PAT2,..."
        )
    return match["name"], [p for p in match["patterns"].split(",") if p]


def main() -> int:
    # Composition root (M-1 + M-2): the entry point owns side effects.
    # Load .env here so the llm package can stay pure on import.
    load_env_if_available()
    args = _parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )
    extra_stages = _build_extra_stages(args, args.goal)
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
        extra_stages=extra_stages,
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
