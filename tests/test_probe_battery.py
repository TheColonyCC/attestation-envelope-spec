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


def test_an_adversarial_flood_makes_ignorance_visible_not_the_claim_weaker():
    """The symmetric worry, dissolved.

    An adversary adds 500 probes. Coverage (a ratio) collapses. But coverage is a FLOOR on
    what has been checked, not a score anyone advertises: the 3 probes actually answered are
    still answered. The flood does not make the claim less verified — it makes the extent of
    what was never asked *visible*, which is the correct outcome.
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
