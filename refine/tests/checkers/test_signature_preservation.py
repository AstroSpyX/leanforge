"""Tests for SignaturePreservationChecker."""

from __future__ import annotations

from refine.checkers.signature_preservation import SignaturePreservationChecker
from refine.signature import extract_signatures, signatures_to_hashes

_BASELINE_FILE = (
    "theorem foo (a : Nat) : a = a := rfl\n"
    "\n"
    "theorem bar (a b : Nat) : a + b = b + a := Nat.add_comm a b\n"
)


def _hashes_of(content: str) -> dict[str, str]:
    return signatures_to_hashes(extract_signatures(content))


class TestSignaturePreservationChecker:
    def test_passes_when_signatures_unchanged(self) -> None:
        baseline = _hashes_of(_BASELINE_FILE)
        checker = SignaturePreservationChecker(name="sig", original_sigs=baseline)
        # Same content → same sigs → pass
        assert checker.check(_BASELINE_FILE, []).passed is True

    def test_passes_when_only_proof_body_changes(self) -> None:
        """Refactoring a proof body must NOT trigger this checker."""
        baseline = _hashes_of(_BASELINE_FILE)
        refactored = (
            "theorem foo (a : Nat) : a = a := by trivial\n"  # body changed
            "\n"
            "theorem bar (a b : Nat) : a + b = b + a := Nat.add_comm a b\n"
        )
        checker = SignaturePreservationChecker(name="sig", original_sigs=baseline)
        assert checker.check(refactored, []).passed is True

    def test_fails_when_decl_removed(self) -> None:
        baseline = _hashes_of(_BASELINE_FILE)
        truncated = "theorem foo (a : Nat) : a = a := rfl\n"
        checker = SignaturePreservationChecker(name="sig", original_sigs=baseline)
        result = checker.check(truncated, [])
        assert result.passed is False
        assert any(
            "bar" in d["messageText"] and "missing" in d["messageText"]
            for d in result.pseudo_diagnostics
        )

    def test_fails_when_signature_weakened(self) -> None:
        baseline = _hashes_of(_BASELINE_FILE)
        weakened = (
            "theorem foo (a : Nat) : True := trivial\n"  # signature changed
            "\n"
            "theorem bar (a b : Nat) : a + b = b + a := Nat.add_comm a b\n"
        )
        checker = SignaturePreservationChecker(name="sig", original_sigs=baseline)
        result = checker.check(weakened, [])
        assert result.passed is False
        assert any("foo" in d["messageText"] for d in result.pseudo_diagnostics)
