"""Tests for refine.signature — declaration extraction + preservation check."""

from refine.signature import (
    PreservationResult,
    axiom_decl_names,
    check_preservation,
    decls_with_sorry_warning,
    extract_signatures,
    signatures_to_hashes,
)


class TestExtractSignatures:
    def test_single_theorem(self) -> None:
        sigs = extract_signatures("theorem foo : Nat = Nat := by rfl")
        assert len(sigs) == 1
        assert sigs[0].name == "foo"
        assert sigs[0].kind == "theorem"
        assert "Nat = Nat" in sigs[0].signature_text

    def test_def_with_arguments(self) -> None:
        sigs = extract_signatures("def add (x y : Nat) : Nat := x + y")
        assert len(sigs) == 1
        assert sigs[0].name == "add"
        assert sigs[0].kind == "def"

    def test_axiom_declaration(self) -> None:
        sigs = extract_signatures("axiom choice : Nonempty α → α")
        assert len(sigs) == 1
        assert sigs[0].kind == "axiom"

    def test_multiple_top_level_decls(self) -> None:
        content = """def x : Nat := 1
def y : Nat := 2
theorem z : x = x := rfl"""
        sigs = extract_signatures(content)
        names = [s.name for s in sigs]
        assert names == ["x", "y", "z"]

    def test_indented_decls_skipped(self) -> None:
        """v1 only catches column-0 declarations. Nested decls require
        indentation and are intentionally skipped."""
        content = """namespace Foo
  theorem nested : True := trivial
end Foo"""
        sigs = extract_signatures(content)
        assert sigs == []

    def test_signature_text_excludes_proof_body(self) -> None:
        sig = extract_signatures("theorem foo : T := proof_text")[0]
        assert "proof_text" not in sig.signature_text

    def test_signature_text_excludes_by_clause(self) -> None:
        sig = extract_signatures("theorem foo : T := by tactic1")[0]
        assert "tactic1" not in sig.signature_text

    def test_signature_text_excludes_where_clause(self) -> None:
        sig = extract_signatures("def foo : T where field := v")[0]
        assert "field" not in sig.signature_text

    def test_line_number_recorded(self) -> None:
        content = "comment\n\ndef x : Nat := 1"
        sigs = extract_signatures(content)
        assert sigs[0].start_line == 2

    def test_non_decl_lines_ignored(self) -> None:
        content = "import Mathlib\n-- comment\nopen Foo"
        assert extract_signatures(content) == []


class TestSignaturesToHashes:
    def test_same_signature_same_hash(self) -> None:
        s1 = extract_signatures("theorem foo : T := proof")
        s2 = extract_signatures("theorem foo : T := proof")
        assert signatures_to_hashes(s1) == signatures_to_hashes(s2)

    def test_different_signature_different_hash(self) -> None:
        h1 = signatures_to_hashes(extract_signatures("theorem foo : T := x"))
        h2 = signatures_to_hashes(extract_signatures("theorem foo : U := x"))
        assert h1["foo"] != h2["foo"]


class TestAxiomDeclNames:
    def test_collects_only_axiom_kinds(self) -> None:
        sigs = extract_signatures("axiom a : Nat\ndef d : Nat := 1\naxiom b : Bool")
        assert axiom_decl_names(sigs) == {"a", "b"}


class TestDeclsWithSorryWarning:
    def test_extracts_names_from_uses_sorry_warning(self) -> None:
        diags = [
            {
                "severity": 2,
                "messageText": "declaration uses `sorry`",
                "enclosingDeclaration": {"name": "foo"},
            },
            {
                "severity": 2,
                "messageText": "declaration uses 'sorry'",
                "enclosingDeclaration": {"name": "bar"},
            },
        ]
        assert decls_with_sorry_warning(diags) == {"foo", "bar"}

    def test_ignores_other_warnings(self) -> None:
        diags = [
            {
                "severity": 2,
                "messageText": "unused variable x",
                "enclosingDeclaration": {"name": "foo"},
            }
        ]
        assert decls_with_sorry_warning(diags) == set()

    def test_handles_missing_enclosing_declaration(self) -> None:
        diags = [{"severity": 2, "messageText": "declaration uses 'sorry'"}]
        assert decls_with_sorry_warning(diags) == set()


class TestCheckPreservation:
    def test_no_changes(self) -> None:
        result = check_preservation(
            original_sigs={"foo": "h1"},
            original_axioms=set(),
            original_sorries=set(),
            new_sigs={"foo": "h1"},
            new_axioms=set(),
            new_sorries=set(),
        )
        assert result == PreservationResult([], [], [], [])
        assert not result.has_hard_violation

    def test_decl_removed_is_hard_violation(self) -> None:
        result = check_preservation(
            original_sigs={"foo": "h1", "bar": "h2"},
            original_axioms=set(),
            original_sorries=set(),
            new_sigs={"foo": "h1"},
            new_axioms=set(),
            new_sorries=set(),
        )
        assert result.decl_removed == ["bar"]
        assert result.has_hard_violation

    def test_sig_changed_is_soft(self) -> None:
        result = check_preservation(
            original_sigs={"foo": "h1"},
            original_axioms=set(),
            original_sorries=set(),
            new_sigs={"foo": "h2"},
            new_axioms=set(),
            new_sorries=set(),
        )
        assert result.sig_changed == ["foo"]
        assert not result.has_hard_violation

    def test_axiom_introduced_is_hard(self) -> None:
        result = check_preservation(
            original_sigs={},
            original_axioms=set(),
            original_sorries=set(),
            new_sigs={},
            new_axioms={"sneaky"},
            new_sorries=set(),
        )
        assert result.axiom_introduced == ["sneaky"]
        assert result.has_hard_violation

    def test_sorry_introduced_is_hard(self) -> None:
        result = check_preservation(
            original_sigs={},
            original_axioms=set(),
            original_sorries=set(),
            new_sigs={},
            new_axioms=set(),
            new_sorries={"foo"},
        )
        assert result.sorry_introduced == ["foo"]
        assert result.has_hard_violation

    def test_preexisting_sorry_not_flagged(self) -> None:
        """If the starter had a sorry in decl `foo`, keeping it isn't a
        violation — the loop's job is to fix it, not pretend it wasn't
        there."""
        result = check_preservation(
            original_sigs={"foo": "h1"},
            original_axioms=set(),
            original_sorries={"foo"},
            new_sigs={"foo": "h1"},
            new_axioms=set(),
            new_sorries={"foo"},
        )
        assert result.sorry_introduced == []
