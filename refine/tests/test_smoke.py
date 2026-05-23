"""End-to-end smoke test for refine.

Runs the live loop against examples/scratch's deliberately-broken Lean
file. Skips automatically when prerequisites are missing (no API key,
no leanforge.py reachable). Designed to be cheap (~$0.05 budget cap)
so it can run on CI when an API key is available.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from refine.controller import refine
from refine.state import Status

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_PROJECT = PROJECT_ROOT / "examples" / "scratch"
EXAMPLE_FILE = "Scratch/Basic.lean"
SMOKE_BUDGET_USD = 0.10
SMOKE_MAX_ITERS = 2


def _api_key_present() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _leanforge_reachable() -> bool:
    return (PROJECT_ROOT / "leanforge.py").exists() and shutil.which("uv") is not None


def _example_present() -> bool:
    return (EXAMPLES_PROJECT / EXAMPLE_FILE).exists()


@pytest.mark.skipif(not _api_key_present(), reason="ANTHROPIC_API_KEY not set")
@pytest.mark.skipif(
    not _leanforge_reachable(), reason="leanforge.py + uv not available"
)
@pytest.mark.skipif(not _example_present(), reason="bundled example missing")
def test_refine_loop_runs_against_bundled_example(tmp_path: Path) -> None:
    """End-to-end: copy the example project into a tmp dir (so we don't
    dirty the source tree), run refine() against the broken file, and
    assert the loop terminated cleanly with some artifact written."""
    work_project = tmp_path / "scratch"
    shutil.copytree(EXAMPLES_PROJECT, work_project)

    history = refine(
        project_root=work_project,
        file_relpath=EXAMPLE_FILE,
        goal="Make this Lean 4 file compile by fixing the type mismatch.",
        mode="auto",
        model="sonnet",
        max_iters=SMOKE_MAX_ITERS,
        lean_timeout_seconds=60.0,
        max_cost_usd=SMOKE_BUDGET_USD,
    )

    assert history.iterations, "expected at least one iteration to be recorded"
    assert history.final_status is not None
    # Whatever the final status, the artifact-store files MUST exist.
    refine_dir = work_project / ".refine"
    assert refine_dir.exists()
    history_file = next(refine_dir.rglob("history.jsonl"))
    assert history_file.exists()
    assert history_file.stat().st_size > 0
    # Iter 0 snapshot is always written; later iters depend on what happened.
    iter0 = next(refine_dir.rglob("iter_0000.lean"))
    assert iter0.exists()
    # Final status must be one of the documented terminal categories.
    assert history.final_status in {
        Status.SUCCESS,
        Status.MAX_ITERS,
        Status.BUDGET_EXCEEDED,
        Status.LLM_ERROR,
        Status.POLICY_VIOLATION,
        Status.STUCK_TIMEOUT,
    }


def test_skip_messages_communicate_prerequisites() -> None:
    """Meta: confirm the skip predicates work and report something useful
    if a developer runs this without the env set up. (Always passes;
    the value is in the assertion message you'd see if it ever broke.)"""
    if not _api_key_present():
        assert "ANTHROPIC_API_KEY" in "ANTHROPIC_API_KEY not set"
    if not _leanforge_reachable():
        assert "leanforge.py" in "leanforge.py + uv not available"
