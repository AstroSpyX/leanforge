"""Disk cache for ask_llm responses.

Keyed on the SHA-256 of the final payload sent to the API. Same prompt
+ same model + same params = instant return, no API call. Exception
paths store nothing.

This is independent of Anthropic's prompt cache. Both are useful:
  - This cache    : avoid API call entirely on identical inputs (dev iteration)
  - Anthropic's   : cheaper input tokens on near-identical inputs (prod)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).parent / ".cache"


def _key(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def get(payload: dict[str, Any]) -> dict[str, Any] | None:
    p = CACHE_DIR / f"{_key(payload)}.json"
    if not p.exists():
        return None
    try:
        loaded: dict[str, Any] = json.loads(p.read_text())
        return loaded
    except (OSError, json.JSONDecodeError):
        return None


def put(payload: dict[str, Any], response: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / f"{_key(payload)}.json"
    p.write_text(json.dumps(response, indent=2))


def clear(provider_model_id: str | None = None) -> int:
    """Wipe everything, or only entries from a specific provider model.
    Returns count of files deleted."""
    if not CACHE_DIR.exists():
        return 0
    deleted = 0
    for p in CACHE_DIR.glob("*.json"):
        if provider_model_id is None:
            p.unlink()
            deleted += 1
            continue
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("provider_model_id") == provider_model_id:
            p.unlink()
            deleted += 1
    return deleted


def size() -> int:
    if not CACHE_DIR.exists():
        return 0
    return sum(p.stat().st_size for p in CACHE_DIR.glob("*.json"))


def prune(max_bytes: int) -> int:
    """Delete oldest entries until total size <= max_bytes. Returns count."""
    if not CACHE_DIR.exists():
        return 0
    files = sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    deleted = 0
    while files and size() > max_bytes:
        files.pop(0).unlink()
        deleted += 1
    return deleted
