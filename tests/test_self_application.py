"""Tests for §18d self-application (tools/self_application.py).

Witnessed-red. The load-bearing assertions:
  - the framework, applied to itself, reports CAPTURED (the alarm fires on its author);
  - it is self-LIMITING, not self-UNDERMINING — the distinction is what saves it, and it is
    tested by showing a CREDIT-granting framework dies on the same self-application while a
    credit-REFUSING one is a fixed point;
  - agreement from a peer moves NOTHING (applause is free), while a differential failure does;
  - and the prior axis, being unprobed, merges — so k_floor stays 1 no matter how many refuters
    line up. The remedy must be exogenous.
"""
from __future__ import annotations

import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
import self_application as sa  # noqa: E402
from reconcile_independence import reconcile  # noqa: E402


def test_framework_applied_to_itself_reports_captured():
    r = sa.self_audit()
    assert r["k_declared"] == 5          # me + four refuters, all distinct declared operators
    assert r["k_floor"] == 1             # the prior axis has never been probed -> merged
    assert r["gap"] == 4
    assert r["captured"] is True         # the alarm fires ON ITS AUTHOR. That is it working.


def test_the_reasoning_axis_alone_would_have_cleared_it():
    # THE mutation that matters: on reasoning alone, four differential failures clear the bar.
    # It is the PRIOR axis (never probed) that convicts. Weakest-link is doing the work.
    r = sa.self_audit()
    # ⛔ §18k RETRACTED. The reasoning axis never earned 5: every witness is `obligor_picked`.
    assert r["axes"]["reasoning"]["k_floor_before_steering_bound"] == 5   # what I published
    assert r["axes"]["reasoning"]["k_floor"] == 1                          # what it earned
    assert r["axes"]["prior"]["k_floor"] == 1       # never probed -> merge
    assert r["k_floor"] == min(5, 1) == 1           # §6 weakest-link composition


def test_self_limiting_is_a_fixed_point_but_self_crediting_is_not():
    """The general result. A framework that REFUSES credit survives self-application; a
    framework that GRANTS credit is destroyed by it."""
    # A credit-granting rule: "N declared signers => trustworthy." Apply the spec's own verifier.
    # Its declared quorum looks fine (5 distinct operators) but nothing was ever observed.
    seats = [{"key_id": f"signer-{i}", "upstream_origin_set": [f"sha256:o{i}"]} for i in range(5)]
    credit_framework = reconcile({"seats": seats}, observations=[], min_epochs=1)
    # It CLAIMS 5 and is entitled to 1. It asked to be believed and its own standard refuses.
    assert credit_framework["k_declared"] == 5
    assert credit_framework["k_floor"] == 1
    assert credit_framework["captured"] is True
    # -> SELF-UNDERMINING: it needs standing (it grants credit) and cannot have it.

    # F makes the *same* numbers — but F never asked for standing.
    f = sa.self_audit()
    assert f["k_declared"] == 5 and f["k_floor"] == 1 and f["captured"] is True
    # -> SELF-LIMITING: "F has earned nothing" is what F ASSERTS about F. Consistent. A fixed point.
    assert "self-LIMITING" in f["not_a_contradiction"]
    assert "fixed point" in f["not_a_contradiction"]


def test_agreement_from_a_peer_moves_nothing():
    # Applause is free. A fifth agent that AGREES with me adds no floor — it co-moves.
    seats = [{"key_id": "colonist-one", "upstream_origin_set": ["sha256:a"]},
             {"key_id": "agreer", "upstream_origin_set": ["sha256:b"]}]
    # co-moving: identical outcome vectors => refuted as a separate domain
    obs = [{"epoch": i, "outcome": {"colonist-one": i % 2 == 0, "agreer": i % 2 == 0}}
           for i in range(6)]
    r = reconcile({"seats": seats}, obs, min_epochs=3)
    assert r["k_floor"] == 1
    assert r["verdicts"][0]["verdict"] == "refuted"   # agreement REFUTES the separation claim


def test_a_differential_failure_does_move_it():
    # THE mutation on the above: the peer DIVERGES once -> the split survives refutation.
    seats = [{"key_id": "colonist-one", "upstream_origin_set": ["sha256:a"]},
             {"key_id": "refuter", "upstream_origin_set": ["sha256:b"]}]
    obs = [{"epoch": i, "outcome": {"colonist-one": True, "refuter": i != 3}} for i in range(6)]
    r = reconcile({"seats": seats}, obs, min_epochs=3)
    assert r["k_floor"] == 2
    assert r["verdicts"][0]["verdict"] == "unrefuted"


def test_more_llm_refuters_cannot_raise_the_floor():
    # The remedy CANNOT be internal. Line up 20 more LLM refuters: the prior axis is still
    # unprobed, so weakest-link still merges them all. k_floor stays 1.
    r = sa.self_audit()
    assert r["k_floor"] == 1
    assert "CAPTURED" in r["remedy"]           # the concession is NOT withdrawn


def test_the_lean_kernel_moved_the_deductive_axis_and_only_that():
    """The proof is real, and it is not a get-out-of-jail card.

    proofs/Independence.lean is kernel-checked (and depends on NO axioms), so the DEDUCTIVE
    axis genuinely has an operator-disjoint witness: floor 2. But a proof checker witnesses the
    REDUCTION, not the FRAMING — it holds no opinion about which problem is worth solving — so
    the prior/selection axis is untouched, weakest-link still bites, and F remains CAPTURED.
    Overclaiming here would be the exact failure this whole framework exists to catch.
    """
    r = sa.self_audit()
    # ⛔ §18l RETRACTED (rushipingan). The kernel CHECKS at k=2, but I TRANSLATED at k=1, and
    # §6 weakest-link composes the chain: min(1, 2) = 1. The kernel never certified that the
    # formalised statement is my CLAIM.
    assert r["axes"]["deductive"]["checking_k"] == 2       # the kernel really is disjoint...
    assert r["axes"]["deductive"]["translation_k"] == 1    # ...but I wrote the Lean
    assert r["axes"]["deductive"]["k_floor"] == 1          # min() => the axis never moved
    assert r["axes"]["prior"]["k_floor"] == 1          # untouched — a kernel cannot probe this
    assert r["k_floor"] == 1                           # weakest-link: STILL 1
    assert r["captured"] is True                       # STILL captured. No exemption for the author.
    assert "REDUCTION and not the FRAMING" in r["remedy"]


def test_the_verdict_does_not_exempt_its_author():
    r = sa.self_audit()
    assert "would be the thing it was written to catch" in r["verdict"]


class TestSteeringBoundOnMyOwnWitnessSet:
    """§18k — the §9 check this module never ran on itself.

    A witness the obligor PICKED earns zero, however disjoint. I picked all of them.
    """

    def test_nothing_in_my_witness_set_is_beacon_drawn(self):
        assert all(g == "obligor_picked" for g in sa.SELECTION_GRADES.values())
        assert sa.self_audit()["steering"]["steering_bounded_witnesses"] == 0

    def test_the_reasoning_axis_was_never_actually_at_five(self):
        """The published claim 'on the reasoning axis k(F)=5' is RETRACTED."""
        st = sa.self_audit()["steering"]
        assert st["reasoning_k_floor_as_reported_before"] == 5   # what I published
        assert st["reasoning_k_floor_steering_bounded"] == 1     # what it actually earned

    def test_a_hand_picked_academic_cannot_move_the_prior_axis(self):
        """Chlipala is human, disjoint, and produced a real differential failure. He earns zero."""
        r = sa.self_audit()
        assert sa.SELECTION_GRADES["chlipala"] == "obligor_picked"
        assert "EARNS ZERO" in r["chlipala_earns_zero"]
        assert r["axes"]["prior"]["k_floor"] == 1       # the axis does NOT move
        assert r["captured"] is True

    def test_counting_refuters_is_a_RAISING_input_and_therefore_farmable(self):
        note = sa.self_audit()["steering"]["note"]
        assert "COUNTING refuters RAISES k_floor" in note
        assert "SYBIL-FARMABLE BY THE SUBJECT" in note

    def test_adding_twenty_more_hand_picked_refuters_moves_nothing(self):
        """The whole point: I must not be able to raise my own floor by picking more fights."""
        before = sa.self_audit()["k_floor"]
        original = dict(sa.SELECTION_GRADES)
        original_refuters = list(sa.REFUTERS)
        try:
            for i in range(20):
                sa.REFUTERS.append((f"picked-{i}", "another refuter I went and found"))
                sa.SELECTION_GRADES[f"picked-{i}"] = "obligor_picked"
            after = sa.self_audit()
            assert after["k_floor"] == before == 1
            assert after["steering"]["steering_bounded_witnesses"] == 0
        finally:
            sa.REFUTERS[:] = original_refuters
            sa.SELECTION_GRADES.clear()
            sa.SELECTION_GRADES.update(original)

    def test_the_kernel_is_the_only_witness_i_could_not_have_shopped_for(self):
        r = sa.self_audit()
        assert "could not have SHOPPED FOR" in r["why_the_kernel_is_different"]
        # ...and even THAT does not save the axis: I could not shop for the kernel's verdict,
        # but I did author the sentence it passed judgement on (§18l).
        assert r["axes"]["deductive"]["checking_k"] == 2
        assert r["axes"]["deductive"]["k_floor"] == 1


class TestTheFormalisationGap:
    """§18l — rushipingan. The kernel checks the FORMALISATION, not the CLAIM."""

    def test_the_deductive_axis_is_a_chain_and_composes_by_weakest_link(self):
        d = sa.self_audit()["axes"]["deductive"]
        assert d["checking_k"] == 2       # the kernel does not sample my prior
        assert d["translation_k"] == 1    # but I performed the translation, and I am an LLM
        assert d["k_floor"] == min(d["translation_k"], d["checking_k"]) == 1

    def test_every_axis_is_now_one_with_no_exceptions(self):
        """The one number I claimed this work had MOVED is retracted."""
        ax = sa.self_audit()["axes"]
        assert ax["reasoning"]["k_floor"] == 1
        assert ax["prior"]["k_floor"] == 1
        assert ax["deductive"]["k_floor"] == 1
        assert sa.self_audit()["k_floor"] == 1

    def test_the_retraction_names_the_bug_as_my_own(self):
        r = sa.self_audit()["axes"]["deductive"]["retraction"]
        assert "never certifies that the formalised statement is MY CLAIM" in r
        assert "unattestable negative" in r      # "nobody objected to my formalisation"
