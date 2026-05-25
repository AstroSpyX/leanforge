"""Tests for NoSorryChecker."""

from __future__ import annotations

from refine.checkers.no_sorry import NoSorryChecker


def _sorry_warning(message: str) -> dict:
    return {"severity": 2, "messageText": message}


class TestNoSorryChecker:
    def test_passes_when_no_warnings(self) -> None:
        assert NoSorryChecker().check("", []).passed is True

    def test_passes_with_non_sorry_warnings(self) -> None:
        diagnostics = [_sorry_warning("shadowed local 'x'")]
        assert NoSorryChecker().check("", diagnostics).passed is True

    def test_fails_on_backtick_sorry(self) -> None:
        """Modern Lean: 'declaration uses `sorry`' (backticks)."""
        diagnostics = [_sorry_warning("declaration uses `sorry`")]
        result = NoSorryChecker().check("", diagnostics)
        assert result.passed is False
        assert len(result.pseudo_diagnostics) == 1

    def test_fails_on_quoted_sorry(self) -> None:
        """Older messages used double quotes; the regex accepts both."""
        diagnostics = [_sorry_warning('declaration uses "sorry"')]
        assert NoSorryChecker().check("", diagnostics).passed is False

    def test_ignores_errors(self) -> None:
        """A 'sorry' in an error message (severity=1) shouldn't trigger
        — only severity=warning counts. Errors are LeanCompileChecker's job."""
        diagnostics = [{"severity": 1, "messageText": "got `sorry` not `nat`"}]
        assert NoSorryChecker().check("", diagnostics).passed is True

    def test_pseudo_diagnostics_preserve_original_warning(self) -> None:
        warning = _sorry_warning("declaration uses `sorry`")
        result = NoSorryChecker().check("", [warning])
        assert result.pseudo_diagnostics == [warning]
