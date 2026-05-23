"""Tests for refine.fingerprint — message normalization + sha256 stability."""

import pytest

from refine.fingerprint import (
    canonicalize_diagnostic,
    fingerprint_diagnostic,
    normalize_message,
)


@pytest.mark.parametrize(
    "before,after",
    [
        # Metavariables: differing IDs collapse to ?m
        ("type mismatch ?m.123 != ?m.456", "type mismatch ?m != ?m"),
        # Universe metavars
        ("Sort ?u.7", "Sort ?u"),
        # Hygienic uniq / hyg
        ("_uniq.42 has type Nat", "_uniq has type Nat"),
        ("_hyg.99 not defined", "_hyg not defined"),
        # Whitespace collapse
        ("foo   bar\n\nbaz", "foo bar baz"),
        # File line reference scrubbed
        ("error at Foo.lean:42:7", "error at Foo.lean<line>"),
        # Mixed
        ("?m.1 vs ?m.2 _uniq.3 line 999", "?m vs ?m _uniq <line>"),
        # No transient identifiers - identity (after whitespace trim)
        ("type mismatch in foo", "type mismatch in foo"),
        # Empty
        ("", ""),
    ],
    ids=[
        "metavars",
        "universe_metavar",
        "hyg_uniq",
        "hyg_hyg",
        "whitespace",
        "file_line",
        "mixed",
        "identity_clean",
        "empty",
    ],
)
def test_normalize_message_strips_transient_identifiers(
    before: str, after: str
) -> None:
    assert normalize_message(before) == after


def test_normalize_is_idempotent() -> None:
    once = normalize_message("?m.1 with _uniq.2 at line 5")
    assert normalize_message(once) == once


class TestFingerprintDiagnostic:
    def _diagnostic(
        self,
        message: str = "type mismatch",
        severity: int = 1,
        decl_name: str = "foo",
        goal: str | None = None,
    ) -> dict:
        diag: dict = {
            "severity": severity,
            "messageText": message,
            "enclosingDeclaration": {"name": decl_name},
        }
        if goal is not None:
            diag["goal"] = {"rendered": goal}
        return diag

    def test_two_diagnostics_with_same_normalized_fields_match(self) -> None:
        a = self._diagnostic(message="type mismatch ?m.123")
        b = self._diagnostic(message="type mismatch ?m.999")
        assert fingerprint_diagnostic(a) == fingerprint_diagnostic(b)

    def test_different_messages_produce_different_fingerprints(self) -> None:
        a = self._diagnostic(message="type mismatch")
        b = self._diagnostic(message="unknown identifier `bar`")
        assert fingerprint_diagnostic(a) != fingerprint_diagnostic(b)

    def test_different_enclosing_decls_produce_different_fingerprints(self) -> None:
        """Same message in two different proofs is two different problems."""
        a = self._diagnostic(decl_name="foo")
        b = self._diagnostic(decl_name="bar")
        assert fingerprint_diagnostic(a) != fingerprint_diagnostic(b)

    def test_different_goals_produce_different_fingerprints(self) -> None:
        """Same message + decl + different proof state is two different problems."""
        a = self._diagnostic(goal="⊢ Nat")
        b = self._diagnostic(goal="⊢ Int")
        assert fingerprint_diagnostic(a) != fingerprint_diagnostic(b)

    def test_term_goal_used_when_tactic_goal_absent(self) -> None:
        a = {
            "severity": 1,
            "messageText": "type mismatch",
            "enclosingDeclaration": {"name": "foo"},
            "termGoal": {"goal": "expected Nat"},
        }
        b = {
            "severity": 1,
            "messageText": "type mismatch",
            "enclosingDeclaration": {"name": "foo"},
            "termGoal": {"goal": "expected String"},
        }
        assert fingerprint_diagnostic(a) != fingerprint_diagnostic(b)

    def test_missing_optional_fields_does_not_crash(self) -> None:
        minimal = {"severity": 1, "messageText": "x"}
        fingerprint_diagnostic(minimal)  # no exception


def test_canonicalize_diagnostic_normalizes_message_and_goal() -> None:
    raw = {
        "severity": 1,
        "messageText": "type mismatch ?m.123",
        "goal": {"rendered": "⊢ ?m.456 = ?m.456"},
        "termGoal": {"goal": "expected ?m.789"},
        "enclosingDeclaration": {"name": "foo"},
    }
    canonical = canonicalize_diagnostic(raw)
    assert canonical["messageText"] == "type mismatch ?m"
    assert canonical["goal"]["rendered"] == "⊢ ?m = ?m"
    assert canonical["termGoal"]["goal"] == "expected ?m"
    # Raw is not mutated
    assert raw["messageText"] == "type mismatch ?m.123"


def test_canonicalize_preserves_unrelated_fields() -> None:
    raw = {
        "severity": 1,
        "messageText": "x",
        "range": {"start": {"line": 7, "character": 0}},
        "source": "Lean 4",
    }
    canonical = canonicalize_diagnostic(raw)
    assert canonical["range"] == raw["range"]
    assert canonical["source"] == raw["source"]
