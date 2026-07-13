"""Tests for §18g append-only, adversary-open probe battery (tools/probe_battery.py).

Witnessed-red. The load-bearing cases:
  - an ADVERSARY's probe is admitted on the same terms as the subject's (it can only lower);
  - the DEFENDER cannot shrink the exam (removal forks the committed chain);
  - an UNSETTLEABLE probe is refused (the one gate that is actually load-bearing);
  - and a flood of adversary probes makes ignorance VISIBLE rather than making the claim
    less verified — which is the correct outcome, not a vulnerability.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import probe_battery as pb  # noqa: E402


def _p(q, by, settleable="drand+oracle"):
    return {"question": q, "settleable_by": settleable, "contributed_by": by}


def test_anyone_may_add_including_a_declared_adversary():
    b = pb.build_battery([
        _p("q1", "the-subject"),
        _p("q2", "A-DECLARED-ADVERSARY"),
        _p("q3", "a-stranger"),
    ])
    assert b["probe_count"] == 3
    assert not b["rejected"]
    contributors = {p["contributed_by"] for p in b["probes"]}
    assert "A-DECLARED-ADVERSARY" in contributors  # admitted, unqualified
    assert any("NEVER CONSULTED" in n for n in b["notes"])


def test_the_defender_cannot_shrink_the_exam():
    """THE attack smolag named: shrink the coverage space to make coverage look high."""
    old = pb.build_battery([_p("q1", "x"), _p("q2", "adversary"), _p("q3", "y")])
    shrunk = pb.build_battery([_p("q1", "x"), _p("q3", "y")])  # q2 quietly dropped
    r = pb.verify_append_only(old, shrunk)
    assert r["ok"] is False
    assert r["state"] == "forked"
    assert "removed" in r["reason"]


def test_appending_is_fine_and_can_only_lower_coverage():
    # THE mutation on the above: same battery, plus a probe. Not an attack.
    old = pb.build_battery([_p("q1", "x")])
    grown = pb.build_battery([_p("q1", "x"), _p("q2", "AN-ADVERSARY")])
    r = pb.verify_append_only(old, grown)
    assert r["ok"] is True
    assert r["state"] == "appended" and r["added"] == 1
    assert "not an attack" in r["note"]


def test_reordering_is_also_a_fork():
    old = pb.build_battery([_p("q1", "x"), _p("q2", "y")])
    reordered = pb.build_battery([_p("q2", "y"), _p("q1", "x")])
    assert pb.verify_append_only(old, reordered)["ok"] is False


def test_an_unsettleable_probe_is_refused():
    """The one gate that does real work: an unsettleable probe is noise, not a question.

    Without it an adversary floods the battery with unanswerable probes and degrades the
    signal without ever being wrong.
    """
    b = pb.build_battery([
        _p("q1", "x"),
        {"question": "is this beautiful?", "contributed_by": "adversary"},  # no settleable_by
    ])
    assert b["probe_count"] == 1
    assert any("NOT SETTLEABLE" in r["reason"] for r in b["rejected"])
    assert any("open problem" in r["reason"] for r in b["rejected"])  # honestly flagged


def test_the_same_question_twice_is_one_probe():
    # Content-addressed: a contributor cannot pad the denominator by resubmitting.
    b = pb.build_battery([_p("q1", "x"), _p("q1", "adversary"), _p("q1", "another")])
    assert b["probe_count"] == 1


def test_an_adversarial_flood_is_paid_for_not_free():
    """CORRECTED by dynamo (2026-07-13). The flood does NOT simply "dissolve".

    It is true that coverage is a FLOOR on what was checked, so the 3 answered probes stay
    answered. But that is true of the COUNT and false of the DRAW: §18c draws the scored probe
    from the battery by beacon, so a flood of junk means the drawn probe is almost certainly
    junk and THE REAL TEST NEVER RUNS. That is a DoS.

    What stops it is not "coverage is a floor". It is that every probe must be SETTLEABLE --
    so a flood costs one constructed, checkable question per unit of dilution bought. The
    attack is possible and it is PAID FOR, which is the same answer as everywhere else here.
    """
    honest = pb.build_battery([_p(f"q{i}", "subject") for i in range(3)])
    flooded = pb.build_battery(
        [_p(f"q{i}", "subject") for i in range(3)]
        + [_p(f"flood{i}", "ADVERSARY") for i in range(500)]
    )
    assert pb.verify_append_only(honest, flooded)["ok"] is True   # appending is always allowed
    assert flooded["probe_count"] == 503
    # The 3 original probes are untouched and still content-address identically.
    assert [p["probe_id"] for p in flooded["probes"][:3]] == [p["probe_id"] for p in honest["probes"]]


def test_free_lowering_is_refused_which_is_the_whole_anti_dos_mechanism():
    """dynamo's objection, as an invariant.

    "Let anyone lower it" was an OVERGENERALISATION. What makes a fork safe is not that it
    lowers — it is that it is UNFORGEABLE (you need the target's signature). A probe is *not*
    unforgeable: anyone can write a question. So a probe must cost something, and the
    settleability gate IS that cost. An entry that costs nothing is refused.
    """
    b = pb.build_battery([
        {"question": "free junk", "contributed_by": "flooder"},          # costs nothing -> refused
        {"question": "real", "settleable_by": "drand+oracle", "contributed_by": "flooder"},
    ])
    assert b["probe_count"] == 1                      # only the one that cost something got in
    assert any("NOT SETTLEABLE" in r["reason"] for r in b["rejected"])


def test_a_costless_flood_buys_nothing():
    # 10_000 unsettleable probes: every one refused. Dilution of the beacon draw: zero.
    b = pb.build_battery(
        [{"question": "real", "settleable_by": "oracle", "contributed_by": "subject"}]
        + [{"question": f"junk{i}", "contributed_by": "ADVERSARY"} for i in range(10_000)]
    )
    assert b["probe_count"] == 1
    assert len(b["rejected"]) == 10_000
