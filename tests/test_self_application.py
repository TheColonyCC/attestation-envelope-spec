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
    assert r["axes"]["reasoning"]["k_floor"] == 5   # would have passed
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
    assert "cannot be raised from inside" in r["remedy"]
    assert "MECHANISED PROOF CHECKER" in r["remedy"]
    assert "STANDS" in r["remedy"]   # the concession is not withdrawn


def test_the_verdict_does_not_exempt_its_author():
    r = sa.self_audit()
    assert "would be the thing it was written to catch" in r["verdict"]
