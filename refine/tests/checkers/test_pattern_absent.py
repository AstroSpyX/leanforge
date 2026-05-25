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


def _proof_body_with_n_matches(n: int) -> str:
    """Generate a synthetic file with N pattern occurrences in a single body."""
    body_lines = "\n".join("  have : Γ.op a a = a := sorry" for _ in range(n))
    return f"theorem foo : True := by\n{body_lines}\n  trivial\n"


class TestPatternAbsentCheckerCap:
    def test_cap_truncates_to_first_n_plus_summary(self) -> None:
        """With 100 matches and max_reported=20, surface 20 specific +
        1 summary = 21 total. Agent gets a workable batch per iter."""
        content = _proof_body_with_n_matches(100)
        checker = PatternAbsentChecker(
            name="x", patterns=(r"Γ\.op",), max_reported=20
        )
        result = checker.check(content, [])
        assert result.passed is False
        assert len(result.pseudo_diagnostics) == 21
        summary = result.pseudo_diagnostics[-1]
        assert "and 80 more" in summary["messageText"]

    def test_no_cap_emits_all_when_below_threshold(self) -> None:
        """5 matches with cap=20 → emit all 5, no summary line."""
        content = _proof_body_with_n_matches(5)
        checker = PatternAbsentChecker(
            name="x", patterns=(r"Γ\.op",), max_reported=20
        )
        result = checker.check(content, [])
        assert len(result.pseudo_diagnostics) == 5
        for d in result.pseudo_diagnostics:
            assert "and" not in d["messageText"] or "more" not in d["messageText"]

    def test_cap_at_threshold_exactly_no_summary(self) -> None:
        """Exactly max_reported matches → emit all, no summary."""
        content = _proof_body_with_n_matches(20)
        checker = PatternAbsentChecker(
            name="x", patterns=(r"Γ\.op",), max_reported=20
        )
        result = checker.check(content, [])
        assert len(result.pseudo_diagnostics) == 20

    def test_max_reported_zero_disables_cap(self) -> None:
        """Setting cap=0 means surface every match (legacy behavior)."""
        content = _proof_body_with_n_matches(50)
        checker = PatternAbsentChecker(
            name="x", patterns=(r"Γ\.op",), max_reported=0
        )
        result = checker.check(content, [])
        assert len(result.pseudo_diagnostics) == 50

    def test_default_cap_is_twenty(self) -> None:
        """The default value 20 is calibrated from real runs — pin it."""
        checker = PatternAbsentChecker(name="x", patterns=(r"x",))
        assert checker.max_reported == 20
