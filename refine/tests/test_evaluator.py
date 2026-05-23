"""Tests for refine.evaluator — subprocess invocation + parsing.

We do NOT spawn real `uv run` here; that would couple every test run to
the network and to Lean. Pure functions (`_parse_leanforge_output`,
`assign_diagnostic_ids`) are tested directly. Subprocess paths
(`run_leanforge`, `_run_with_timeout`) are tested with `subprocess.Popen`
mocked — subprocess qualifies as an external dependency per code-standard
I-7. Real-subprocess coverage is left for the smoke test.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from refine.evaluator import (
    LeanforgeInvocationError,
    _parse_leanforge_output,
    _run_with_timeout,
    assign_diagnostic_ids,
    run_leanforge,
)


class TestParseLeanforgeOutput:
    def test_well_formed_output_parses(self) -> None:
        stdout = (
            '{"elaborationSucceeded": false, '
            '"diagnostics": [{"severity": 1, "messageText": "x"}]}'
        )
        diags, succeeded = _parse_leanforge_output(stdout)
        assert len(diags) == 1
        assert diags[0]["messageText"] == "x"
        assert succeeded is False

    def test_success_with_no_diagnostics(self) -> None:
        stdout = '{"elaborationSucceeded": true, "diagnostics": []}'
        diags, succeeded = _parse_leanforge_output(stdout)
        assert diags == []
        assert succeeded is True

    def test_empty_stdout_returns_empty_diagnostics(self) -> None:
        """Some failure modes (subprocess killed before output) yield an
        empty stdout. Parser returns ([], False); caller classifies by
        returncode separately."""
        diags, succeeded = _parse_leanforge_output("")
        assert diags == []
        assert succeeded is False

    def test_whitespace_only_stdout_treated_as_empty(self) -> None:
        diags, succeeded = _parse_leanforge_output("\n   \n")
        assert diags == []

    def test_invalid_json_raises_invocation_error(self) -> None:
        with pytest.raises(LeanforgeInvocationError, match="not valid JSON"):
            _parse_leanforge_output("not json at all")

    def test_diagnostics_not_a_list_raises(self) -> None:
        stdout = '{"diagnostics": "oops"}'
        with pytest.raises(LeanforgeInvocationError, match="diagnostics"):
            _parse_leanforge_output(stdout)

    def test_non_dict_diagnostics_filtered_out(self) -> None:
        """Tolerate stray non-dict entries from a malformed leanforge
        version rather than crashing the whole loop."""
        stdout = '{"diagnostics": [{"severity": 1}, "garbage", 42]}'
        diags, _ = _parse_leanforge_output(stdout)
        assert len(diags) == 1


class TestAssignDiagnosticIds:
    def test_ids_match_indices(self) -> None:
        diags = [{"messageText": "a"}, {"messageText": "b"}, {"messageText": "c"}]
        with_ids = assign_diagnostic_ids(diags)
        assert [d["id"] for d in with_ids] == [0, 1, 2]

    def test_original_diagnostics_not_mutated(self) -> None:
        diags = [{"messageText": "a"}]
        assign_diagnostic_ids(diags)
        assert "id" not in diags[0]

    def test_empty_list(self) -> None:
        assert assign_diagnostic_ids([]) == []


def _fake_popen(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    """Build a Popen mock that returns one (stdout, stderr) pair from
    communicate() and exposes the requested returncode."""
    process = MagicMock(spec=subprocess.Popen)
    process.communicate.return_value = (stdout, stderr)
    process.returncode = returncode
    return process


class TestRunWithTimeout:
    def test_normal_completion(self) -> None:
        fake = _fake_popen(stdout="ok", stderr="", returncode=0)
        with patch("refine.evaluator.subprocess.Popen", return_value=fake):
            out, err, rc, timed_out = _run_with_timeout(("anything",), 1.0)
        assert (out, err, rc, timed_out) == ("ok", "", 0, False)

    def test_timeout_triggers_sigterm_then_returns_timed_out(self) -> None:
        """First communicate() call raises TimeoutExpired → we SIGTERM →
        second communicate() returns cleanly. timed_out flag is True."""
        fake = MagicMock(spec=subprocess.Popen)
        fake.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="x", timeout=1.0),
            ("partial", ""),
        ]
        fake.returncode = -15  # SIGTERM
        with patch("refine.evaluator.subprocess.Popen", return_value=fake):
            out, err, rc, timed_out = _run_with_timeout(("anything",), 1.0)
        assert timed_out is True
        assert out == "partial"
        fake.send_signal.assert_called_once()

    def test_timeout_then_grace_expires_triggers_kill(self) -> None:
        """If SIGTERM doesn't finish within grace, we hard-kill."""
        fake = MagicMock(spec=subprocess.Popen)
        fake.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="x", timeout=1.0),  # first wait
            subprocess.TimeoutExpired(cmd="x", timeout=2.0),  # grace wait
            ("", ""),  # final after kill
        ]
        fake.returncode = -9
        with patch("refine.evaluator.subprocess.Popen", return_value=fake):
            _, _, rc, timed_out = _run_with_timeout(("anything",), 1.0)
        assert timed_out is True
        fake.kill.assert_called_once()


class TestRunLeanforge:
    def test_successful_run_returns_parsed_result(self, tmp_path: Path) -> None:
        stdout = '{"elaborationSucceeded": true, "diagnostics": []}'
        fake = _fake_popen(stdout=stdout, returncode=0)
        with patch("refine.evaluator.subprocess.Popen", return_value=fake):
            result = run_leanforge(tmp_path, "Foo.lean", timeout_seconds=1.0)
        assert result.elaboration_succeeded is True
        assert result.timed_out is False
        assert result.returncode == 0
        assert result.diagnostics == []

    def test_timeout_returns_empty_diagnostics_marker(self, tmp_path: Path) -> None:
        fake = MagicMock(spec=subprocess.Popen)
        fake.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="x", timeout=1.0),
            ("", ""),
        ]
        fake.returncode = -15
        with patch("refine.evaluator.subprocess.Popen", return_value=fake):
            result = run_leanforge(tmp_path, "Foo.lean", timeout_seconds=1.0)
        assert result.timed_out is True
        assert result.diagnostics == []
        assert result.elaboration_succeeded is False

    def test_invalid_json_raises_invocation_error(self, tmp_path: Path) -> None:
        fake = _fake_popen(stdout="not json", returncode=1)
        with (
            patch("refine.evaluator.subprocess.Popen", return_value=fake),
            pytest.raises(LeanforgeInvocationError),
        ):
            run_leanforge(tmp_path, "Foo.lean", timeout_seconds=1.0)
