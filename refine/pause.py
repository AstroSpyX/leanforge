"""Interactive pause prompt for the controller.

When the controller decides to pause, it calls `prompt_user(state)` which
prints a status block and reads the user's single-letter choice. Returns
a `PauseChoice` the controller dispatches on.

The `(q) quit` command is NON-destructive — it exits with the current
file in place. The DESTRUCTIVE rollback is `(Q) reset` and requires
typing literal `YES` to confirm. This is intentional: rollback-on-
keystroke is a silent-data-loss trap.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TextIO

from refine.schema import RepairStrategy
from refine.state import IterationState

CONFIRMATION_TOKEN = "YES"


@dataclass(frozen=True)
class PauseChoice:
    """User's response to a pause prompt."""

    kind: str  # "continue" | "revise" | "nudge" | "accept" | "quit"
    # | "reset" | "show" | "diags" | "history" | "diff"
    # | "budget" | "noop"
    payload: str | None = None  # revise text, strategy, new budget, etc.


def render_status_block(state: IterationState) -> str:
    """Format the status header shown before the menu."""
    lines = [
        f"[paused at iter {state.iteration}]  status: {state.status.value}",
        (
            f"goal_status: {state.goal_status.value}  "
            f"errors: {state.error_count}  warnings: {state.warning_count}"
        ),
        (
            f"resolved-this-turn: {state.resolved_count}  "
            f"new-this-turn: {state.new_count}  "
            f"persistent: {state.persistent_count}"
        ),
        (
            f"cost: ${state.cumulative_cost_usd:.4f}  "
            f"tokens in/out: {state.cumulative_input_tokens}/"
            f"{state.cumulative_output_tokens}  retries: {state.retry_count}"
        ),
    ]
    if state.hard_violations:
        lines.append(f"hard violations: {', '.join(state.hard_violations)}")
    if state.soft_warnings:
        lines.append(f"soft warnings: {', '.join(state.soft_warnings)}")
    return "\n".join(lines)


_MENU_TEXT = """
  (c) continue       keep going on the same plan
  (r) revise         add free-form guidance to next prompt
  (n) nudge          switch repair strategy (input one of the enum values)
  (a) accept         exit with the current file as final
  (q) quit           NON-destructive: exit with current file in place
  (Q) reset          DESTRUCTIVE: rollback to iter_0000 (confirms with YES)
  (s) show           print current file
  (d) diags          print current diagnostics
  (h) history        print error/resolved/goal_status timeline
  (g) diff           diff vs previous iteration
  (b) budget         raise cost cap (input new USD amount)

choice> """


def prompt_user(
    state: IterationState,
    *,
    in_stream: TextIO | None = None,
    out_stream: TextIO | None = None,
) -> PauseChoice:
    """Print status + menu, read one choice. in/out streams are injectable
    for tests."""
    out = out_stream or sys.stdout
    in_ = in_stream or sys.stdin

    print(render_status_block(state), file=out)
    out.write(_MENU_TEXT)
    out.flush()
    raw = (in_.readline() or "").strip()
    return _interpret_choice(raw, in_, out)


def _interpret_choice(raw: str, in_: TextIO, out: TextIO) -> PauseChoice:
    """Map the user's keystroke to a PauseChoice, prompting for follow-up
    input where required."""
    if not raw:
        return PauseChoice(kind="noop")
    match raw[0]:
        case "c":
            return PauseChoice(kind="continue")
        case "r":
            return PauseChoice(
                kind="revise", payload=_read_followup("revision text", in_, out)
            )
        case "n":
            return _read_strategy_nudge(in_, out)
        case "a":
            return PauseChoice(kind="accept")
        case "q":
            return PauseChoice(kind="quit")
        case "Q":
            return _confirm_reset(in_, out)
        case "s":
            return PauseChoice(kind="show")
        case "d":
            return PauseChoice(kind="diags")
        case "h":
            return PauseChoice(kind="history")
        case "g":
            return PauseChoice(kind="diff")
        case "b":
            return _read_budget(in_, out)
        case _:
            out.write(f"unrecognized choice {raw!r}\n")
            return PauseChoice(kind="noop")


def _read_followup(label: str, in_: TextIO, out: TextIO) -> str:
    out.write(f"{label}> ")
    out.flush()
    return (in_.readline() or "").rstrip("\n")


def _read_strategy_nudge(in_: TextIO, out: TextIO) -> PauseChoice:
    valid = [s.value for s in RepairStrategy]
    out.write(f"strategy ({'|'.join(valid)})> ")
    out.flush()
    choice = (in_.readline() or "").strip()
    if choice not in valid:
        out.write(f"unrecognized strategy {choice!r}; nudge ignored\n")
        return PauseChoice(kind="noop")
    return PauseChoice(kind="nudge", payload=choice)


def _confirm_reset(in_: TextIO, out: TextIO) -> PauseChoice:
    out.write(
        f"About to roll back to iter_0000 and discard all changes. "
        f"Type {CONFIRMATION_TOKEN} to confirm> "
    )
    out.flush()
    response = (in_.readline() or "").strip()
    if response == CONFIRMATION_TOKEN:
        return PauseChoice(kind="reset")
    out.write("reset cancelled\n")
    return PauseChoice(kind="noop")


def _read_budget(in_: TextIO, out: TextIO) -> PauseChoice:
    out.write("new max-cost-usd> ")
    out.flush()
    raw = (in_.readline() or "").strip()
    try:
        float(raw)
    except ValueError:
        out.write(f"unrecognized budget {raw!r}; budget unchanged\n")
        return PauseChoice(kind="noop")
    return PauseChoice(kind="budget", payload=raw)
