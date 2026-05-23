"""Tests for refine.env — environment fingerprint over Lake project metadata."""

import hashlib
from pathlib import Path

import pytest

from refine.env import FIELD_SEPARATOR, env_fingerprint


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


class TestEnvFingerprint:
    def test_empty_project_produces_stable_hash(self, project: Path) -> None:
        """Both files absent — hash should still be deterministic."""
        first = env_fingerprint(project)
        second = env_fingerprint(project)
        assert first == second

    def test_changing_manifest_changes_hash(self, project: Path) -> None:
        before = env_fingerprint(project)
        (project / "lake-manifest.json").write_bytes(b'{"deps": []}')
        after = env_fingerprint(project)
        assert before != after

    def test_changing_toolchain_changes_hash(self, project: Path) -> None:
        before = env_fingerprint(project)
        (project / "lean-toolchain").write_bytes(b"leanprover/lean4:v4.29.1\n")
        after = env_fingerprint(project)
        assert before != after

    def test_both_files_combined_into_one_hash(self, project: Path) -> None:
        (project / "lake-manifest.json").write_bytes(b"M")
        (project / "lean-toolchain").write_bytes(b"T")
        expected = hashlib.sha256(b"M" + FIELD_SEPARATOR + b"T").hexdigest()
        assert env_fingerprint(project) == expected

    def test_field_separator_prevents_concatenation_collision(
        self, project: Path
    ) -> None:
        """Without the separator, ("AB", "") and ("A", "B") would hash the
        same. The separator byte is reserved in both files (it's a control
        character that never appears in JSON or version strings)."""
        (project / "lake-manifest.json").write_bytes(b"AB")
        first = env_fingerprint(project)
        (project / "lake-manifest.json").write_bytes(b"A")
        (project / "lean-toolchain").write_bytes(b"B")
        second = env_fingerprint(project)
        assert first != second
