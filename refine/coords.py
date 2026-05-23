"""Coordinate conversion between LSP UTF-16 positions and Python code-point indices.

LSP specifies `Position.character` as a count of UTF-16 code units within a
line. Python strings are sequences of code points. For the BMP characters
that dominate Lean source (∀, →, etc.) the two counts coincide; they
diverge only for characters outside the BMP (e.g. emoji, supplementary-plane
math symbols) which require a UTF-16 surrogate pair (2 units) to represent
a single code point.

All converters operate on a single line of text — line numbers themselves
are identical between LSP and Python (0-indexed in both conventions).
"""

from __future__ import annotations

# A code point at or above this value requires 2 UTF-16 code units
# (encoded as a surrogate pair).
SUPPLEMENTARY_PLANE_START = 0x10000


def normalize_line_endings(content: str) -> str:
    """Convert CRLF and bare CR line endings to LF; idempotent on LF input."""
    return content.replace("\r\n", "\n").replace("\r", "\n")


def split_into_lines(content: str) -> list[str]:
    """Split content into lines with no trailing terminators.

    A trailing newline produces a trailing empty string, matching the
    behaviour every downstream consumer (file slicing, edit application)
    expects when reasoning about "line N" in a buffer.
    """
    return normalize_line_endings(content).split("\n")


def _utf16_units(codepoint: int) -> int:
    return 2 if codepoint >= SUPPLEMENTARY_PLANE_START else 1


def utf16_length(line_text: str) -> int:
    """Total UTF-16 code units required to encode `line_text`."""
    return sum(_utf16_units(ord(ch)) for ch in line_text)


def position_to_offset(content: str, line: int, lsp_char: int) -> int:
    """Convert an LSP `(line, character)` position to an absolute code-point
    offset within `content`.

    `content` MUST be LF-normalized (run through `normalize_line_endings`
    first if uncertain). Line numbers past EOF clamp to `len(content)`,
    matching the LSP convention that one-past-end is a valid insertion
    position. lsp_char's surrogate-pair check applies per-line; offsets
    past line-end clamp to that line's last code point.

    Raises ValueError if `line` is negative.
    """
    if line < 0:
        raise ValueError(f"line must be non-negative, got {line}")
    lines = content.split("\n")
    if line >= len(lines):
        return len(content)
    # Each preceding line contributes its length plus one for the \n separator.
    line_start = sum(len(prev) + 1 for prev in lines[:line])
    return line_start + lsp_char_to_codepoint(lines[line], lsp_char)


def lsp_char_to_codepoint(line_text: str, lsp_char: int) -> int:
    """Convert an LSP UTF-16 character offset within a line to a Python
    code-point index.

    Offsets past the last UTF-16 unit clamp to `len(line_text)` — LSP
    permits one-past-end as an insertion position.

    Raises ValueError if `lsp_char` is negative, or if it lands strictly
    inside a surrogate pair (which would mean the caller's coordinate
    is mid-character — uniformly an upstream bug, not something to
    silently round).
    """
    if lsp_char < 0:
        raise ValueError(f"lsp_char must be non-negative, got {lsp_char}")

    units_remaining = lsp_char
    for codepoint_index, ch in enumerate(line_text):
        if units_remaining == 0:
            return codepoint_index
        units = _utf16_units(ord(ch))
        if units_remaining < units:
            raise ValueError(
                f"lsp_char {lsp_char} falls inside a surrogate pair "
                f"at code point {codepoint_index} (char {ch!r})"
            )
        units_remaining -= units
    return len(line_text)


def codepoint_to_lsp_char(line_text: str, codepoint_index: int) -> int:
    """Convert a Python code-point index within a line to an LSP UTF-16
    character offset.

    Offsets past `len(line_text)` clamp to the line's total UTF-16 length.

    Raises ValueError if `codepoint_index` is negative.
    """
    if codepoint_index < 0:
        raise ValueError(f"codepoint_index must be non-negative, got {codepoint_index}")

    upper = min(codepoint_index, len(line_text))
    return sum(_utf16_units(ord(ch)) for ch in line_text[:upper])
