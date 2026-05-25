"""Tests for PatternAbsentChecker — regex grep over proof bodies."""

from __future__ import annotations

from refine.checkers.pattern_absent import PatternAbsentChecker

_NO_GAMMA_OP = PatternAbsentChecker(name="no_gamma_op", patterns=(r"Γ\.op",))


class TestPatternAbsentChecker:
    def test_passes_on_empty_file(self) -> None:
        assert _NO_GAMMA_OP.check("", []).passed is True

    def test_passes_when_pattern_only_in_signature(self) -> None:
        """The structure / signature region is exempt; patterns are
        flagged only inside proof bodies."""
        content = (
            "structure MyGroup (G : Type) where\n"
            "  op : G → G → G\n"
            "\n"
            "theorem foo (Γ : MyGroup G) (a : G) : a = a := rfl\n"
        )
        assert _NO_GAMMA_OP.check(content, []).passed is True

    def test_fails_when_pattern_in_proof_body(self) -> None:
        content = (
            "theorem foo (Γ : MyGroup G) (a : G) : a = a := by\n"
            "  exact Γ.op a Γ.e ▸ rfl\n"
        )
        result = _NO_GAMMA_OP.check(content, [])
        assert result.passed is False
        assert len(result.pseudo_diagnostics) == 1

    def test_multiple_patterns_all_checked(self) -> None:
        checker = PatternAbsentChecker(
            name="no_gamma_ops",
            patterns=(r"Γ\.op", r"Γ\.inv"),
        )
        content = (
            "theorem foo (Γ : MyGroup G) (a : G) : a = a := by\n"
            "  have : Γ.op a a = a := sorry\n"
            "  have : Γ.inv a = a := sorry\n"
            "  rfl\n"
        )
        result = checker.check(content, [])
        assert result.passed is False
        assert len(result.pseudo_diagnostics) == 2

    def test_pseudo_diagnostic_includes_line_range(self) -> None:
        content = (
            "theorem foo : True := by\n  have : Γ.op a a = a := sorry\n  trivial\n"
        )
        result = PatternAbsentChecker(name="x", patterns=(r"Γ\.op",)).check(content, [])
        diag = result.pseudo_diagnostics[0]
        assert diag["range"]["start"]["line"] == 1  # second line, 0-indexed
        assert "messageText" in diag
        assert "Γ.op" in diag["messageText"] or "x" in diag["messageText"]
