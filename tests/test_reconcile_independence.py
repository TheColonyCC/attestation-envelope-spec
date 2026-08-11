"""Tests for §18 (RFC) declared-vs-observed independence reconciliation.

Witnessed-red: every positive ships the mutation that flips it. The load-bearing
assertions are the *asymmetry* (correlation refutes, divergence never confirms) and the
pessimistic default (unobserved == merged, not credited).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import reconcile_independence as ri  # noqa: E402


def _quorum(*origin_sets):
    return {"seats": [{"key_id": f"did:key:z{chr(65+i)}", "upstream_origin_set": list(o)}
                      for i, o in enumerate(origin_sets)]}


def _obs(n, pattern):
    """pattern: callable(epoch) -> {key_id: failed_bool}"""
    return [{"epoch": i, "outcome": pattern(i)} for i in range(n)]


A, B, C = "did:key:zA", "did:key:zB", "did:key:zC"


def test_declared_disjoint_but_perfectly_comoving_is_refuted():
    # Two seats declare DISJOINT origins -> §11 says k=2. They then fail together, always.
    q = _quorum(["sha256:aa"], ["sha256:bb"])
    obs = _obs(6, lambda i: {A: i % 2 == 0, B: i % 2 == 0})  # identical fail-vectors
    r = ri.reconcile(q, obs)
    assert r["k_declared"] == 2
    assert r["k_floor"] == 1                      # the world merged them back
    assert r["gap"] == 1                          # capture signal
    assert r["captured"] is True
    assert r["verdicts"][0]["verdict"] == "refuted"


def test_one_differential_failure_leaves_the_declaration_unrefuted():
    # Same declaration; now ONE epoch where A fails and B does not. That is the mutation.
    q = _quorum(["sha256:aa"], ["sha256:bb"])
    obs = _obs(6, lambda i: {A: i % 2 == 0, B: (i % 2 == 0) and i != 4})  # diverge at i=4
    r = ri.reconcile(q, obs)
    assert r["k_declared"] == 2
    assert r["k_floor"] == 2                      # not refuted -> declaration survives
    assert r["gap"] == 0
    assert r["captured"] is False
    v = r["verdicts"][0]
    assert v["verdict"] == "unrefuted"
    assert v["differential_failures"] == 1


def test_divergence_never_yields_a_confirmed_state():
    # THE asymmetry. A perfectly anti-correlated pair is still only 'unrefuted' —
    # §11's point stands: they may be decorrelating outputs over a shared input.
    q = _quorum(["sha256:aa"], ["sha256:bb"])
    obs = _obs(8, lambda _i: {A: True, B: False})  # maximal divergence
    r = ri.reconcile(q, obs)
    assert {v["verdict"] for v in r["verdicts"]} == {"unrefuted"}
    # the verdict vocabulary is closed, and "confirmed" is deliberately not in it
    assert {v["verdict"] for v in r["verdicts"]} <= {"refuted", "unrefuted", "unobserved"}
    # and maximal divergence buys no more than a single dated split: k_floor is still a FLOOR
    assert r["k_floor"] == r["k_declared"] == 2


def test_unobserved_pairs_are_merged_not_credited():
    # Pessimistic default: no observation at all -> one failure domain, NOT two.
    q = _quorum(["sha256:aa"], ["sha256:bb"])
    r = ri.reconcile(q, observations=[])
    assert r["k_declared"] == 2                   # the declaration still says 2...
    assert r["k_floor"] == 1                      # ...and the floor refuses to believe it
    assert r["gap"] == 1
    assert r["verdicts"][0]["verdict"] == "unobserved"


def test_thin_observation_is_still_unobserved():
    # Below min_epochs the pair is not even refutable; it must not earn credit.
    q = _quorum(["sha256:aa"], ["sha256:bb"])
    obs = _obs(2, lambda i: {A: True, B: False})  # divergent, but only 2 common epochs
    r = ri.reconcile(q, obs, min_epochs=3)
    assert r["verdicts"][0]["verdict"] == "unobserved"
    assert r["k_floor"] == 1
    # mutation: give it enough epochs and the same divergence now survives refutation
    r2 = ri.reconcile(q, _obs(3, lambda i: {A: True, B: False}), min_epochs=3)
    assert r2["verdicts"][0]["verdict"] == "unrefuted"
    assert r2["k_floor"] == 2


def test_merges_are_instant_splits_are_provisional():
    # Diverged early, then co-moved for the whole recent window -> re-merged.
    q = _quorum(["sha256:aa"], ["sha256:bb"])
    obs = ([{"epoch": 0, "outcome": {A: True, B: False}},      # an old, real split
            {"epoch": 1, "outcome": {A: False, B: True}}]
           + [{"epoch": i, "outcome": {A: i % 2 == 0, B: i % 2 == 0}} for i in range(2, 8)])  # then lockstep
    full = ri.reconcile(q, obs)                    # whole history: the old split still counts
    assert full["verdicts"][0]["verdict"] == "unrefuted"
    recent = ri.reconcile(q, obs, recent_window=6)  # only the recent window: pure co-movement
    assert recent["verdicts"][0]["verdict"] == "refuted"
    assert recent["k_floor"] == 1                  # fresh correlation beats a stale divergence


def test_shared_origin_is_already_one_seat_and_needs_no_observation():
    # §11 merged them on declared evidence alone; there is no declaration left to refute.
    q = _quorum(["sha256:aa"], ["sha256:aa"])
    r = ri.reconcile(q, observations=[])
    assert r["k_declared"] == 1
    assert r["k_floor"] == 1
    assert r["gap"] == 0
    assert r["verdicts"] == []                     # same declared cluster -> no pair to judge


def test_three_seats_one_captured_pair():
    # A,B collude (declared disjoint, always co-move); C genuinely diverges from both.
    q = _quorum(["sha256:aa"], ["sha256:bb"], ["sha256:cc"])
    obs = _obs(6, lambda i: {A: i % 2 == 0, B: i % 2 == 0, C: i % 3 == 0})
    r = ri.reconcile(q, obs)
    assert r["k_declared"] == 3
    assert r["k_floor"] == 2                       # A+B collapse into one; C stands
    assert r["gap"] == 1
    assert r["captured"] is False                  # not a fully captured quorum — C is real
    byp = {tuple(v["pair"]): v["verdict"] for v in r["verdicts"]}
    assert byp[(A, B)] == "refuted"
    assert byp[(A, C)] == "unrefuted"


def test_undisclosed_origins_earn_nothing_and_are_reported():
    # §11 fail-closed carries through: a seat with no origin set is not a declared party.
    q = {"seats": [{"key_id": A, "upstream_origin_set": ["sha256:aa"]},
                   {"key_id": B}]}  # B discloses nothing
    r = ri.reconcile(q, observations=[])
    assert B in r["undisclosed"]
    assert r["k_declared"] == 1                    # B never counted in the first place
    assert r["verdicts"] == []
