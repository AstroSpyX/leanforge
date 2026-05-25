"""Tests for the CLI's --check-pattern-absent SPEC parser."""

from __future__ import annotations

import pytest

from refine.__main__ import _parse_pattern_spec


class TestParsePatternSpec:
    def test_simple_single_pattern(self) -> None:
        name, patterns = _parse_pattern_spec("no_gamma_op:Γ\\.op")
        assert name == "no_gamma_op"
        assert patterns == ["Γ\\.op"]

    def test_multiple_patterns_comma_separated(self) -> None:
        name, patterns = _parse_pattern_spec("nogamma:Γ\\.op,Γ\\.inv,Γ\\.e")
        assert name == "nogamma"
        assert patterns == ["Γ\\.op", "Γ\\.inv", "Γ\\.e"]

    def test_bad_spec_no_colon_raises(self) -> None:
        with pytest.raises(SystemExit, match="bad spec"):
            _parse_pattern_spec("no_colon_here")

    def test_bad_spec_empty_name_raises(self) -> None:
        with pytest.raises(SystemExit, match="bad spec"):
            _parse_pattern_spec(":Γ\\.op")
