"""Tests for §16 verifiable receipt ordering (tools/ordering.py).

Hermetic, pure-function. Witnessed-red: every positive ships the mutation that
flips it — the clean chain is `ordered`; re-pointing a receipt at an in-use prev
forks it; a non-increasing beacon round backdates it; a dangling prev breaks it.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import ordering as o  # noqa: E402

EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "examples" / "receipt_ordering.v0.1.json"


def _chain():
    return [
        {"id": "r1", "subject": "S", "prev": None, "beacon_round": 1},
        {"id": "r2", "subject": "S", "prev": "r1", "beacon_round": 2},
        {"id": "r3", "subject": "S", "prev": "r2", "beacon_round": 3},
    ]


def _sub(res, subject="S"):
    return next(s for s in res["subjects"] if s["subject"] == subject)


def test_clean_chain_is_ordered():
    res = o.check_ordering(_chain())
    assert res["state"] == "ordered"
    assert _sub(res)["state"] == "ordered"


def test_worked_example_verifies_ordered():
    doc = json.loads(EXAMPLE.read_text())
    assert o.check_ordering(doc["receipts"])["state"] == "ordered"
    # the negatives, spliced in, must trip the detector (witnessed-red)
    forked = doc["receipts"] + [doc["_negatives"]["fork_same_prev"]]
    assert o.check_ordering(forked)["state"] == "forked"
    backdated = doc["receipts"] + [doc["_negatives"]["backdated"]]
    assert o.check_ordering(backdated)["state"] == "backdated"


def test_equivocation_fork_is_detected():
    # r2 and r2b both claim prev r1 — a published contradiction
    recs = _chain()[:2] + [{"id": "r2b", "subject": "S", "prev": "r1", "beacon_round": 2}]
    res = o.check_ordering(recs)
    assert res["state"] == "forked"
    assert any("equivocation fork" in n for n in _sub(res)["notes"])


def test_two_receipts_claiming_first_is_also_a_fork():
    recs = [{"id": "a", "subject": "S", "prev": None, "beacon_round": 1},
            {"id": "b", "subject": "S", "prev": None, "beacon_round": 1}]
    assert o.check_ordering(recs)["state"] == "forked"


def test_backdate_is_detected():
    recs = [{"id": "r1", "subject": "S", "prev": None, "beacon_round": 5},
            {"id": "r2", "subject": "S", "prev": "r1", "beacon_round": 5}]  # not strictly after
    res = o.check_ordering(recs)
    assert res["state"] == "backdated"
    assert any("backdate" in n for n in _sub(res)["notes"])


def test_dangling_prev_breaks_the_chain():
    recs = [{"id": "r2", "subject": "S", "prev": "ghost", "beacon_round": 2}]
    res = o.check_ordering(recs)
    assert res["state"] == "broken"


def test_forks_are_per_subject_not_global():
    # same prev id string under different subjects is NOT a fork
    recs = [{"id": "x1", "subject": "A", "prev": None, "beacon_round": 1},
            {"id": "x2", "subject": "A", "prev": "x1", "beacon_round": 2},
            {"id": "y1", "subject": "B", "prev": None, "beacon_round": 1},
            {"id": "y2", "subject": "B", "prev": "y1", "beacon_round": 2}]
    assert o.check_ordering(recs)["state"] == "ordered"


def test_worst_subject_state_rolls_up():
    recs = [{"id": "a", "subject": "A", "prev": None, "beacon_round": 1},
            {"id": "b1", "subject": "B", "prev": None, "beacon_round": 1},
            {"id": "b2", "subject": "B", "prev": None, "beacon_round": 1}]  # B forks
    assert o.check_ordering(recs)["state"] == "forked"
