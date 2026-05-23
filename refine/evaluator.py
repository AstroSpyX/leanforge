"""Subprocess wrapper around leanforge with hard timeout.

leanforge's internal LSP timeouts are insufficient — Lean can hang past
LSP-level deadlines during elaboration in ways that wedge the client.
This module spawns leanforge as a separate process and enforces a wall-
clock timeout via SIGTERM (with a grace period) then SIGKILL.

The leanforge CLI is invoked via `uv run` so its own dependencies
(leanclient) are provisioned the same way the rest of the project
manages dependencies.
"""

from __future__ import annotations

import json
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LEANFORGE_SCRIPT = "leanforge.py"
DEFAULT_LEAN_TIMEOUT_SECONDS = 30.0
SIGTERM_GRACE_SECONDS = 2.0

# uv invocation that matches how leanforge.py is documented to run.
UV_INVOCATION_PREFIX = (
    "uv",
    "run",
    "--with",
    "leanclient",
    "--python",
    "3.12",
    "--",
    "python",
)


@dataclass(frozen=True)
class EvalResult:
    """One leanforge run's complete observable result."""

    diagnostics: list[dict[str, Any]]
    elaboration_succeeded: bool
    timed_out: bool
    returncode: int | None
    raw_stdout: str
    raw_stderr: str
    wall_ms: int


class LeanforgeInvocationError(Exception):
    """leanforge exited cleanly but produced unparseable output."""


def run_leanforge(
    project_root: Path,
    file_relpath: str,
    timeout_seconds: float = DEFAULT_LEAN_TIMEOUT_SECONDS,
    leanforge_repo_root: Path | None = None,
) -> EvalResult:
    """Run leanforge on `project_root/file_relpath` and parse the result.

    `leanforge_repo_root` is where `leanforge.py` lives — defaults to the
    current working directory (the typical invocation site).
    """
    repo_root = leanforge_repo_root or Path.cwd()
    cmd = (
        *UV_INVOCATION_PREFIX,
        str(repo_root / LEANFORGE_SCRIPT),
        str(project_root),
        file_relpath,
    )

    started = time.monotonic()
    stdout, stderr, returncode, timed_out = _run_with_timeout(cmd, timeout_seconds)
    wall_ms = int((time.monotonic() - started) * 1000)

    if timed_out:
        return EvalResult(
            diagnostics=[],
            elaboration_succeeded=False,
            timed_out=True,
            returncode=returncode,
            raw_stdout=stdout,
            raw_stderr=stderr,
            wall_ms=wall_ms,
        )

    diagnostics, elaboration_succeeded = _parse_leanforge_output(stdout)
    return EvalResult(
        diagnostics=diagnostics,
        elaboration_succeeded=elaboration_succeeded,
        timed_out=False,
        returncode=returncode,
        raw_stdout=stdout,
        raw_stderr=stderr,
        wall_ms=wall_ms,
    )


def _run_with_timeout(
    cmd: tuple[str, ...],
    timeout_seconds: float,
) -> tuple[str, str, int | None, bool]:
    """Run `cmd`, killing it after `timeout_seconds`. Returns
    (stdout, stderr, returncode, timed_out)."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return stdout, stderr, process.returncode, False
    except subprocess.TimeoutExpired:
        process.send_signal(signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=SIGTERM_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        return stdout, stderr, process.returncode, True


def _parse_leanforge_output(stdout: str) -> tuple[list[dict[str, Any]], bool]:
    """leanforge produces a single JSON document on stdout. Parse it and
    pull out the diagnostics list + elaborationSucceeded flag.

    Empty stdout is treated as an LLM/Lean failure that produced no
    diagnostics; the caller decides how to classify (Outcome.PANIC vs
    Outcome.ELAB_ERROR depending on returncode)."""
    if not stdout.strip():
        return [], False
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise LeanforgeInvocationError(
            f"leanforge stdout was not valid JSON: {exc}"
        ) from exc
    diagnostics_raw = payload.get("diagnostics", [])
    if not isinstance(diagnostics_raw, list):
        raise LeanforgeInvocationError(
            f"leanforge.diagnostics is {type(diagnostics_raw).__name__}, expected list"
        )
    diagnostics: list[dict[str, Any]] = [
        d for d in diagnostics_raw if isinstance(d, dict)
    ]
    elaboration_succeeded = bool(payload.get("elaborationSucceeded", False))
    return diagnostics, elaboration_succeeded


def assign_diagnostic_ids(
    diagnostics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Inject a stable `id` field (the index in the original list) into
    each diagnostic. IDs are the LLM-facing handle in `diagnostic_ids`
    references on edits. Idempotent — re-running preserves IDs."""
    return [{**diag, "id": index} for index, diag in enumerate(diagnostics)]
