"""Tests for refine.artifact_store — snapshots, history, events, pointer."""

import json
from pathlib import Path

import pytest

from refine.artifact_store import ArtifactStore
from refine.state import (
    FailureReason,
    GoalStatus,
    IterationState,
    Status,
)


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(project_root=tmp_path, file_relpath="Foo/Bar.lean")


def _minimal_iteration(num: int = 0) -> IterationState:
    return IterationState(
        iteration=num,
        status=Status.PROGRESS,
        goal_status=GoalStatus.UNCHANGED,
        file_content="",
        file_sha256="",
        state_hash="",
        raw_diagnostics=[],
        canonical_diagnostics=[],
        diagnostics_fingerprints=[],
        error_count=0,
        warning_count=0,
        resolved_count=0,
        new_count=0,
        persistent_count=0,
        prompt_sha256="",
        response_sha256="",
        retry_count=0,
        model="sonnet",
        provider="anthropic",
        provider_model_id="claude-sonnet-4-6",
        temperature=0.0,
        llm_summary="",
        llm_strategy="other",
        llm_confidence=0.5,
        llm_reasoning="",
        llm_intended_scope=[],
        system_intended_scope=[],
        edits_applied=0,
        remaining_blockers=[],
        hard_violations=[],
        soft_warnings=[],
        scope_warnings=[],
        input_tokens=0,
        output_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        base_cost_usd=0.0,
        retry_multiplier=1.0,
        cost_usd=0.0,
        cumulative_cost_usd=0.0,
        cumulative_input_tokens=0,
        cumulative_output_tokens=0,
        elapsed_ms=0,
    )


class TestPathLayout:
    def test_file_slug_replaces_slash_with_double_underscore(
        self, store: ArtifactStore
    ) -> None:
        assert store.file_slug == "Foo__Bar.lean"

    def test_base_dir_under_refine_subdirectory(self, store: ArtifactStore) -> None:
        assert store.base_dir.name == "Foo__Bar.lean"
        assert store.base_dir.parent.name == ".refine"

    def test_snapshot_name_is_zero_padded(self, store: ArtifactStore) -> None:
        assert store.snapshot_path(7).name == "iter_0007.lean"
        assert store.snapshot_path(1234).name == "iter_1234.lean"


class TestSnapshots:
    def test_write_and_read_round_trip(self, store: ArtifactStore) -> None:
        store.write_snapshot(0, "import Mathlib\n")
        assert store.read_snapshot(0) == "import Mathlib\n"

    def test_write_creates_base_dir(self, store: ArtifactStore) -> None:
        store.write_snapshot(0, "x")
        assert store.base_dir.exists()


class TestCurrentFile:
    def test_write_current_atomically_replaces_target(
        self, store: ArtifactStore
    ) -> None:
        store.original_file_path.parent.mkdir(parents=True, exist_ok=True)
        store.original_file_path.write_text("original")
        store.write_current_file("rewritten")
        assert store.original_file_path.read_text() == "rewritten"
        # The tmp file should be gone
        tmp = store.original_file_path.with_suffix(
            store.original_file_path.suffix + ".refine-tmp"
        )
        assert not tmp.exists()


class TestHistory:
    def test_append_writes_one_jsonl_line_per_call(self, store: ArtifactStore) -> None:
        store.append_history(_minimal_iteration(num=0))
        store.append_history(_minimal_iteration(num=1))
        contents = store.history_path.read_text()
        lines = contents.strip().split("\n")
        assert len(lines) == 2

    def test_history_round_trips_through_json(self, store: ArtifactStore) -> None:
        state = _minimal_iteration(num=42)
        store.append_history(state)
        parsed = json.loads(store.history_path.read_text())
        assert parsed["iteration"] == 42
        assert parsed["status"] == "progress"  # StrEnum serializes natively

    def test_strenum_fields_serialize_to_their_string_value(
        self, store: ArtifactStore
    ) -> None:
        """Catches the bug where StrEnum members serialize as enum repr
        instead of the string value (would happen if asdict converted
        them to a non-str type)."""
        state = _minimal_iteration()
        state_with_explicit_enums = type(state)(
            **{
                **state.__dict__,
                "status": Status.LOOP_DETECTED,
                "goal_status": GoalStatus.SHIFTED,
            }
        )
        store.append_history(state_with_explicit_enums)
        parsed = json.loads(store.history_path.read_text())
        assert parsed["status"] == "loop_detected"
        assert parsed["goal_status"] == "shifted"


class TestEvents:
    def test_append_event(self, store: ArtifactStore) -> None:
        store.append_event(
            {"ts": 1.0, "event": "pause", "reason": "LOOP_DETECTED", "iter": 5}
        )
        parsed = json.loads(store.events_path.read_text())
        assert parsed["reason"] == "LOOP_DETECTED"

    def test_failure_reason_enum_serializes_in_events(
        self, store: ArtifactStore
    ) -> None:
        store.append_event(
            {"ts": 1.0, "event": "pause", "reason": FailureReason.TIMEOUT_LEAN}
        )
        parsed = json.loads(store.events_path.read_text())
        assert parsed["reason"] == "timeout_lean"


class TestRawIo:
    def test_raw_files_under_raw_subdirectory(self, store: ArtifactStore) -> None:
        store.write_raw_io(
            0,
            prompt={"messages": [{"role": "user", "content": "hi"}]},
            response={"text": "ok"},
        )
        assert store.raw_dir.exists()
        assert store.raw_prompt_path(0).exists()
        assert store.raw_response_path(0).exists()
        prompt = json.loads(store.raw_prompt_path(0).read_text())
        assert prompt["messages"][0]["content"] == "hi"


class TestCurrentPointer:
    def test_pointer_records_current_iter(self, store: ArtifactStore) -> None:
        store.update_current_pointer(current_iter=7, env_fingerprint="abc")
        parsed = json.loads(store.current_pointer_path.read_text())
        assert parsed["current_iter"] == 7
        assert parsed["env_fingerprint"] == "abc"


class TestRestore:
    def test_restore_copies_snapshot_to_original_path(
        self, store: ArtifactStore
    ) -> None:
        store.write_snapshot(0, "original content\n")
        store.original_file_path.parent.mkdir(parents=True, exist_ok=True)
        store.original_file_path.write_text("garbage from a bad iteration")
        store.restore_to_iteration(0)
        assert store.original_file_path.read_text() == "original content\n"


class TestStartNewRun:
    def test_returns_none_when_no_prior_state(self, store: ArtifactStore) -> None:
        result = store.start_new_run()
        assert result is None
        assert store.base_dir.exists()
        assert list(store.base_dir.iterdir()) == []

    def test_prior_state_archived_and_new_dir_is_empty(
        self, store: ArtifactStore
    ) -> None:
        store.write_snapshot(0, "old run snapshot")
        store.append_history(_minimal_iteration())

        archive = store.start_new_run()

        assert archive is not None
        assert archive.exists()
        assert "archive-" in archive.name
        # New base_dir exists and is empty.
        assert store.base_dir.exists()
        assert list(store.base_dir.iterdir()) == []
        # Old snapshot is still inside the archive (no data loss).
        assert (archive / "iter_0000.lean").read_text() == "old run snapshot"
        assert (archive / "history.jsonl").exists()

    def test_collision_disambiguator(self, store: ArtifactStore) -> None:
        """Two new-runs within the same wall-clock second must produce
        distinct archive paths via the -2, -3, … suffix."""
        store.write_snapshot(0, "run 1 content")
        first_archive = store.start_new_run()
        store.write_snapshot(0, "run 2 content")
        # Pre-create what would be the natural second-archive path to
        # force the collision branch. We strip any -N suffix off the
        # first archive's name so the second archive lands on the
        # same base timestamp and must disambiguate.
        assert first_archive is not None
        base_archive_name = (
            first_archive.name.rsplit("-", 1)[0]
            if first_archive.name.count("-") >= 2
            and first_archive.name.rsplit("-", 1)[1].isdigit()
            else first_archive.name
        )
        # Force the natural candidate to collide.
        forced = first_archive.parent / base_archive_name
        if not forced.exists():
            forced.mkdir()

        second_archive = store.start_new_run()

        assert second_archive is not None
        assert second_archive != first_archive
        assert second_archive != forced
        assert (second_archive / "iter_0000.lean").read_text() == "run 2 content"


def test_set_field_serializes_as_sorted_list(store: ArtifactStore) -> None:
    """The _json_default fallback converts sets — used when event payloads
    contain set-valued fields like a list of touched decls collected from
    a heuristic."""
    store.append_event({"ts": 1.0, "event": "x", "decls": {"b", "a", "c"}})
    parsed = json.loads(store.events_path.read_text())
    assert parsed["decls"] == ["a", "b", "c"]
