"""Lean declaration signature extraction + preservation check.

v1 uses text-based heuristics, NOT a real Lean parser. Top-level
declarations are recognized by their keyword (theorem/def/lemma/axiom/
instance/example) appearing at column 0. Nested decls inside namespaces
or sections are usually indented and therefore skipped — which is
acceptable for v1 (the spec explicitly notes this limitation).

Sorry/admit detection uses leanforge's own "declaration uses 'sorry'"
warning instead of string-scanning the source. String scanning false-
positives on comments, string literals, and identifiers like `not_sorry`.
The Lean compiler's determination is authoritative.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

# A top-level declaration starts at column 0 with one of these keywords
# followed by a space and the identifier. Anything indented (= inside a
# namespace, section, or mutual block) is intentionally skipped in v1.
DECL_KEYWORDS = ("theorem", "def", "lemma", "axiom", "instance", "example")
_DECL_LINE_PATTERN = re.compile(
    r"^(?P<kind>(?:theorem|def|lemma|axiom|instance|example))\s+(?P<name>[^\s({:]+)"
)
# Signature text is the part after the name up to one of these terminators.
_SIG_TERMINATOR_PATTERN = re.compile(r":=|\bwhere\b|\bby\b")

# Lean's standard linter emits "declaration uses `sorry`" — with
# BACKTICKS, not quotes. Accept all three quote styles for resilience
# across Lean versions and any future rewording.
_SORRY_WARNING_PATTERN = re.compile(r"declaration uses [`'\"]sorry[`'\"]")


@dataclass(frozen=True)
class DeclSignature:
    name: str
    kind: str  # "theorem", "def", "lemma", "axiom", "instance", "example"
    signature_text: str  # canonicalized: name + signature up to body
    start_line: int


@dataclass(frozen=True)
class PreservationResult:
    decl_removed: list[str]
    sig_changed: list[str]
    axiom_introduced: list[str]
    sorry_introduced: list[str]

    @property
    def has_hard_violation(self) -> bool:
        return bool(self.decl_removed or self.axiom_introduced or self.sorry_introduced)


def extract_signatures(content: str) -> list[DeclSignature]:
    """Find top-level declarations and return one DeclSignature per match.

    Handles single-line signatures cleanly. For multi-line signatures the
    captured text stops at the first := / where / by on the same line as
    the keyword — accurate for common cases, occasionally short for very
    long arg lists that span lines. v1 limitation.
    """
    results: list[DeclSignature] = []
    for line_index, line in enumerate(content.split("\n")):
        match = _DECL_LINE_PATTERN.match(line)
        if not match:
            continue
        kind = match["kind"]
        name = match["name"]
        rest = line[match.end() :]
        sig_text = _trim_to_body_start(rest).strip()
        results.append(
            DeclSignature(
                name=name,
                kind=kind,
                signature_text=f"{kind} {name} {sig_text}".strip(),
                start_line=line_index,
            )
        )
    return results


def signatures_to_hashes(signatures: list[DeclSignature]) -> dict[str, str]:
    """Map decl name → sha256(canonical signature text)."""
    return {
        sig.name: hashlib.sha256(sig.signature_text.encode("utf-8")).hexdigest()
        for sig in signatures
    }


def axiom_decl_names(signatures: list[DeclSignature]) -> set[str]:
    return {sig.name for sig in signatures if sig.kind == "axiom"}


def decls_with_sorry_warning(diagnostics: list[dict[str, Any]]) -> set[str]:
    """Names of declarations Lean flagged with the 'uses sorry' warning.

    The warning's enclosingDeclaration field carries the affected decl
    name; we collect those.
    """
    names: set[str] = set()
    for diag in diagnostics:
        message = str(diag.get("messageText", ""))
        if not _SORRY_WARNING_PATTERN.search(message):
            continue
        enclosing = diag.get("enclosingDeclaration") or {}
        if isinstance(enclosing, dict):
            name = enclosing.get("name")
            if isinstance(name, str) and name:
                names.add(name)
    return names


def check_preservation(
    original_sigs: dict[str, str],
    original_axioms: set[str],
    original_sorries: set[str],
    new_sigs: dict[str, str],
    new_axioms: set[str],
    new_sorries: set[str],
) -> PreservationResult:
    """Compare iter_0's signatures + axioms + sorries against current.

    Returns lists by violation kind. Three are HARD (rollback + pause):
    decl_removed, axiom_introduced, sorry_introduced. SIG_CHANGED is SOFT
    (handled by the caller as a warning that may escalate)."""
    return PreservationResult(
        decl_removed=sorted(set(original_sigs) - set(new_sigs)),
        sig_changed=sorted(
            name
            for name, sig_hash in original_sigs.items()
            if name in new_sigs and new_sigs[name] != sig_hash
        ),
        axiom_introduced=sorted(new_axioms - original_axioms),
        sorry_introduced=sorted(new_sorries - original_sorries),
    )


def _trim_to_body_start(text: str) -> str:
    """Keep only the part before `:=`, `where`, or `by` (whichever first)."""
    match = _SIG_TERMINATOR_PATTERN.search(text)
    if match is None:
        return text
    return text[: match.start()]
