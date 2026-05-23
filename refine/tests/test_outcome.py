"""Tests for refine.outcome — classifier on synthetic diagnostic shapes."""

import signal

from refine.outcome import Outcome, classify_outcome


def _error(message: str = "x", kind: str = "") -> dict:
    return {"severity": 1, "messageText": message, "kind": kind}


def _warning() -> dict:
    return {"severity": 2, "messageText": "noted", "kind": ""}


class TestClassifyOutcome:
    def test_success_when_no_errors(self) -> None:
        assert (
            classify_outcome([], timed_out=False, subprocess_returncode=0)
            == Outcome.SUCCESS
        )

    def test_success_when_only_warnings(self) -> None:
        assert (
            classify_outcome([_warning()], timed_out=False, subprocess_returncode=0)
            == Outcome.SUCCESS
        )

    def test_timeout_takes_precedence_over_diagnostics(self) -> None:
        """When we killed the subprocess for timeout, the diagnostic list
        is unreliable. TIMEOUT wins regardless of what's in there."""
        diags = [_error()]
        assert (
            classify_outcome(diags, timed_out=True, subprocess_returncode=-9)
            == Outcome.TIMEOUT
        )

    def test_sigkill_without_timeout_is_oom(self) -> None:
        """Signal-9 termination without OUR timer means the OS killed it
        — overwhelmingly OOM on macOS."""
        assert (
            classify_outcome([], timed_out=False, subprocess_returncode=-signal.SIGKILL)
            == Outcome.OOM
        )

    def test_other_negative_returncode_is_panic(self) -> None:
        assert (
            classify_outcome([], timed_out=False, subprocess_returncode=-signal.SIGABRT)
            == Outcome.PANIC
        )

    def test_parse_error_from_kind(self) -> None:
        diags = [_error(message="x", kind="Lean.Parser.unknownTactic")]
        assert (
            classify_outcome(diags, timed_out=False, subprocess_returncode=1)
            == Outcome.PARSE_ERROR
        )

    def test_parse_error_from_unexpected_token_prefix(self) -> None:
        diags = [_error(message="unexpected token '⟩'; expected term")]
        assert (
            classify_outcome(diags, timed_out=False, subprocess_returncode=1)
            == Outcome.PARSE_ERROR
        )

    def test_import_error_from_unknown_module(self) -> None:
        diags = [_error(message="unknown module Mathlib.DoesNotExist")]
        assert (
            classify_outcome(diags, timed_out=False, subprocess_returncode=1)
            == Outcome.IMPORT_ERROR
        )

    def test_generic_error_classified_as_elab_error(self) -> None:
        diags = [_error(message="type mismatch")]
        assert (
            classify_outcome(diags, timed_out=False, subprocess_returncode=1)
            == Outcome.ELAB_ERROR
        )

    def test_first_classifiable_error_wins(self) -> None:
        """A parse error followed by elab errors classifies as PARSE_ERROR."""
        diags = [
            _error(message="unexpected token x"),
            _error(message="type mismatch"),
        ]
        assert (
            classify_outcome(diags, timed_out=False, subprocess_returncode=1)
            == Outcome.PARSE_ERROR
        )

    def test_returncode_none_with_errors_classifies_normally(self) -> None:
        diags = [_error(message="type mismatch")]
        assert (
            classify_outcome(diags, timed_out=False, subprocess_returncode=None)
            == Outcome.ELAB_ERROR
        )
