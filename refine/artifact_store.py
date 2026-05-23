"""Snapshot + history + event persistence for the refine loop.

Layout under `<project_root>/.refine/<file_slug>/`:

    iter_NNNN.lean      one per iteration, full snapshot
    current.json        pointer { current_iter, current_path, env_fingerprint }
    history.jsonl       per-iteration record, one JSON object per line
    events.jsonl        controller decisions + user actions
    raw/                optional LLM prompt + response snapshots
        iter_NNNN.prompt.json
        iter_NNNN.response.json

`file_slug` = `file_relpath` with `/` replaced by `__` so multi-file
support later is purely additive (each file gets its own sibling
directory under `.refine/`).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from refine.state import IterationState

REFINE_DIR = ".refine"
HISTORY_FILENAME = "history.jsonl"
EVENTS_FILENAME = "events.jsonl"
CURRENT_FILENAME = "current.json"
RAW_DIRNAME = "raw"
SNAPSHOT_NAME_TEMPLATE = "iter_{iteration:04d}.lean"
RAW_PROMPT_TEMPLATE = "iter_{iteration:04d}.prompt.json"
RAW_RESPONSE_TEMPLATE = "iter_{iteration:04d}.response.json"
SLUG_SEPARATOR = "__"


@dataclass(frozen=True)
class ArtifactStore:
    """File-system view over one refined file's history.

    Frozen because the (project_root, file_relpath) pair identifies a
    store for the whole loop's lifetime; mutating it mid-loop would mean
    the snapshots and history diverge.
    """

    project_root: Path
    file_relpath: str

    @property
    def file_slug(self) -> str:
        return self.file_relpath.replace("/", SLUG_SEPARATOR)

    @property
    def base_dir(self) -> Path:
        return self.project_root / REFINE_DIR / self.file_slug

    @property
    def history_path(self) -> Path:
        return self.base_dir / HISTORY_FILENAME

    @property
    def events_path(self) -> Path:
        return self.base_dir / EVENTS_FILENAME

    @property
    def current_pointer_path(self) -> Path:
        return self.base_dir / CURRENT_FILENAME

    @property
    def raw_dir(self) -> Path:
        return self.base_dir / RAW_DIRNAME

    @property
    def original_file_path(self) -> Path:
        return self.project_root / self.file_relpath

    def snapshot_path(self, iteration: int) -> Path:
        return self.base_dir / SNAPSHOT_NAME_TEMPLATE.format(iteration=iteration)

    def raw_prompt_path(self, iteration: int) -> Path:
        return self.raw_dir / RAW_PROMPT_TEMPLATE.format(iteration=iteration)

    def raw_response_path(self, iteration: int) -> Path:
        return self.raw_dir / RAW_RESPONSE_TEMPLATE.format(iteration=iteration)

    def initialize(self) -> None:
        """Create the directory tree. Safe to call repeatedly."""
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def start_new_run(self) -> Path | None:
        """Begin a fresh run: archive any prior state to a sibling
        `.archive-<timestamp>/` directory, then create an empty base_dir.

        Returns the path of the archive when one was created, else None
        (when there was no prior state to preserve).

        The archive suffix is the current wall-clock time at second
        precision. If two runs land in the same second the suffix gets
        a `-2`, `-3`, … disambiguator.
        """
        archive: Path | None = None
        if self.base_dir.exists():
            archive = self._allocate_archive_path()
            self.base_dir.rename(archive)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return archive

    def _allocate_archive_path(self) -> Path:
        """Pick a non-colliding archive path for the current second."""
        timestamp = time.strftime("%Y%m%dT%H%M%S")
        candidate = self.base_dir.with_name(f"{self.base_dir.name}.archive-{timestamp}")
        suffix = 2
        while candidate.exists():
            candidate = self.base_dir.with_name(
                f"{self.base_dir.name}.archive-{timestamp}-{suffix}"
            )
            suffix += 1
        return candidate

    def write_snapshot(self, iteration: int, content: str) -> Path:
        self.initialize()
        path = self.snapshot_path(iteration)
        path.write_text(content, encoding="utf-8")
        return path

    def read_snapshot(self, iteration: int) -> str:
        return self.snapshot_path(iteration).read_text(encoding="utf-8")

    def write_current_file(self, content: str) -> None:
        """Atomically replace the file the Lean compiler reads."""
        target = self.original_file_path
        tmp = target.with_suffix(target.suffix + ".refine-tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)

    def append_history(self, state: IterationState) -> None:
        self.initialize()
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(state), default=_json_default) + "\n")

    def append_event(self, event: dict[str, Any]) -> None:
        """`event` should at minimum have `event` (str) and `ts` (float).
        Caller is responsible for filling in the schema described in the
        spec's CONTROLLER EVENT LOG section."""
        self.initialize()
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=_json_default) + "\n")

    def write_raw_io(
        self,
        iteration: int,
        prompt: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.raw_prompt_path(iteration).write_text(
            json.dumps(prompt, indent=2, default=_json_default), encoding="utf-8"
        )
        self.raw_response_path(iteration).write_text(
            json.dumps(response, indent=2, default=_json_default), encoding="utf-8"
        )

    def update_current_pointer(
        self,
        current_iter: int,
        env_fingerprint: str,
    ) -> None:
        self.initialize()
        payload = {
            "current_iter": current_iter,
            "current_path": str(self.original_file_path),
            "original_path": str(self.original_file_path),
            "env_fingerprint": env_fingerprint,
            "updated_at": time.time(),
        }
        self.current_pointer_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    def restore_to_iteration(self, iteration: int) -> None:
        """Copy iter_NNNN.lean back to the original file path. Used by
        (Q) reset and by hard-failure rollback."""
        content = self.read_snapshot(iteration)
        self.write_current_file(content)


def _json_default(value: object) -> object:
    """Fallback serializer for types asdict produces but json.dumps doesn't
    natively understand (Path, set). StrEnum values are str subclasses
    and serialize natively without help here."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"object of type {type(value).__name__} is not JSON-serializable")
