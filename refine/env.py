"""Environment fingerprint for replay-drift detection.

Hash of the two files that materially affect what `lake build` does:
  - lake-manifest.json (resolved dependency versions)
  - lean-toolchain     (Lean compiler version pin)

When a recorded history's env_fingerprint doesn't match the current one,
replay results may differ even with identical prompt+response payloads.
This module exists so the difference is observable instead of silent.

Missing files are tolerated (treated as empty bytes). A fresh Lake project
without dependencies will have an empty lake-manifest.json or none at all;
a project without a pinned toolchain will use the user's elan default.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

LAKE_MANIFEST_FILENAME = "lake-manifest.json"
LEAN_TOOLCHAIN_FILENAME = "lean-toolchain"
FIELD_SEPARATOR = b"\x1f"  # ASCII unit separator — never appears in either file


def env_fingerprint(project_root: Path) -> str:
    """Compute a sha256 fingerprint from the two env-bearing files."""
    manifest = _read_or_empty(project_root / LAKE_MANIFEST_FILENAME)
    toolchain = _read_or_empty(project_root / LEAN_TOOLCHAIN_FILENAME)
    payload = manifest + FIELD_SEPARATOR + toolchain
    return hashlib.sha256(payload).hexdigest()


def _read_or_empty(path: Path) -> bytes:
    if not path.exists():
        return b""
    return path.read_bytes()
