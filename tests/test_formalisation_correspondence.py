"""§18n — the Lean self-audit must stay DISCLOSED.

Witnessed-red, in the §18m sense: a hole that stops being named has stopped being disclosed,
which is strictly worse than a named hole. These tests fail if a future edit silently removes the
retraction of the docstring over-claims, drops the correspondence doc, or stops naming the two
theorems that hold by `rfl`-on-a-definition. The mutation that erases the disclosure trips them.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEAN = (ROOT / "proofs" / "Independence.lean").read_text(encoding="utf-8")
DOC = (ROOT / "docs" / "formalisation-correspondence.md").read_text(encoding="utf-8")
SELFAPP = (ROOT / "docs" / "self-application.md").read_text(encoding="utf-8")

# The theorems the audit marks as NOT carrying their comments' weight.
RFL_BY_DEFINITION = ("messenger_is_irrelevant", "attempts_earn_nothing")
TAUTOLOGY_DRESSED = "split_implies_signed_error"
FAITHFUL_WITH_CONTENT = "one_machine_cannot_split"


def test_correspondence_doc_exists_and_states_the_finding():
    # The headline must survive verbatim: coherence of the model, not truth of the claim.
    assert "coherence of the formal" in DOC
    assert "not truth of the informal" in DOC


def test_doc_names_every_audited_theorem():
    for name in (*RFL_BY_DEFINITION, TAUTOLOGY_DRESSED, FAITHFUL_WITH_CONTENT):
        assert name in DOC, f"correspondence doc no longer names {name}"


def test_lean_retraction_stays_visible():
    # The §18n marker and the withdrawn phrase must both remain in the Lean file — the retraction
    # is only disclosed if the thing being retracted is still quoted next to it.
    assert "§18n" in LEAN
    assert "load-bearing economic claim" in LEAN  # the quoted over-claim, kept visible
    assert "Retraction" in LEAN or "withdrawn" in LEAN


def test_self_application_links_the_audit():
    assert "§18n" in SELFAPP
    assert "formalisation-correspondence" in SELFAPP


def test_audit_does_not_promote_itself_to_a_proof():
    # The one line the audit must never cross: it lowers, it does not close. A future edit that
    # lets this file claim the gap is closed/verified is exactly the §18l pattern reasserting.
    lowered = ("does not close" in DOC) or ("it does not close it" in LEAN)
    assert lowered, "the audit must state it lowers but does not close the axis"
