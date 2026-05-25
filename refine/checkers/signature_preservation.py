"""Pass when every original declaration's signature is unchanged.

Constructed with `original_sigs: dict[name -> sig_hash]` captured at
loop start. Each iter, the checker re-extracts signatures from the
current file and reports two failure kinds:

  - `decl_removed`: a declaration that existed at iter 0 is gone now
  - `sig_changed`: a declaration's signature hash differs from iter 0

Both surface as pseudo-diagnostics. This catches the "agent silently
weakens a theorem statement to make the proof pass" failure mode.

Axiom-introduction and sorry-introduction are handled by sibling
checkers (NoAxiomChecker / NoSorryChecker) so each checker has a
single responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from refine.checkers.base import Checker, CheckResult
from refine.signature import extract_signatures, signatures_to_hashes


@dataclass(frozen=True)
class SignaturePreservationChecker(Checker):
    name: str
    original_sigs: dict[str, str]

    def check(
        self,
        content: str,
        diagnostics: list[dict[str, Any]],
    ) -> CheckResult:
        del diagnostics
        current_sigs = signatures_to_hashes(extract_signatures(content))
        removed = sorted(set(self.original_sigs) - set(current_sigs))
        changed = sorted(
            name
            for name, sig_hash in self.original_sigs.items()
            if name in current_sigs and current_sigs[name] != sig_hash
        )
        if not removed and not changed:
            return CheckResult(passed=True)
        pseudo: list[dict[str, Any]] = []
        for name in removed:
            pseudo.append(
                {
                    "severity": "error",
                    "messageText": (
                        f"signature preservation: declaration {name!r} "
                        f"was present at iter 0 but is now missing — "
                        f"restore it"
                    ),
                }
            )
        for name in changed:
            pseudo.append(
                {
                    "severity": "error",
                    "messageText": (
                        f"signature preservation: declaration {name!r} "
                        f"had its signature changed since iter 0 — "
                        f"restore the original signature"
                    ),
                }
            )
        return CheckResult(passed=False, pseudo_diagnostics=pseudo)
