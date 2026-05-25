"""Tests for LeanCompileChecker."""

from __future__ import annotations

from refine.checkers.lean_compile import LeanCompileChecker


class TestLeanCompileChecker:
    def test_passes_with_no_diagnostics(self) -> None:
        result = LeanCompileChecker().check("", [])
        assert result.passed is True
        assert result.pseudo_diagnostics == []

    def test_passes_with_warnings_only(self) -> None:
        """Warnings (severity=2 / 'warning') are not errors — pass."""
        diagnostics = [
            {"severity": 2, "messageText": "shadowed binding"},
            {"severity": "warning", "messageText": "another"},
        ]
        result = LeanCompileChecker().check("", diagnostics)
        assert result.passed is True

    def test_fails_with_integer_severity_one_error(self) -> None:
        diagnostics = [{"severity": 1, "messageText": "type mismatch"}]
        result = LeanCompileChecker().check("", diagnostics)
        assert result.passed is False

    def test_fails_with_string_severity_error(self) -> None:
        """leanforge.py serializes severity as a string; we accept both."""
        diagnostics = [{"severity": "error", "messageText": "unknown ident"}]
        result = LeanCompileChecker().check("", diagnostics)
        assert result.passed is False

    def test_does_not_emit_pseudo_diagnostics(self) -> None:
        """Lean's own diagnostics are already in the prompt; this
        checker is just a pass/fail signal."""
        diagnostics = [{"severity": 1, "messageText": "err"}]
        result = LeanCompileChecker().check("", diagnostics)
        assert result.passed is False
        assert result.pseudo_diagnostics == []
