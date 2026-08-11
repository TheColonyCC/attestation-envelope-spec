"""§18m — witnessed-red tests for the ship gate.

A gate that only ever says YES is a rubber stamp. The tests that matter are the ones that make it
say NO, so each criterion ships the exact mutation that must trip it. If this file passes, the gate
has teeth; if it were vacuous, these would all fail.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import rfc_readiness as rr  # noqa: E402
import self_application as sa  # noqa: E402


def test_the_gate_currently_passes():
    r = rr.check_readiness()
    assert r["state"] == "ready_as_rfc"
    assert r["blockers"] == []


def test_the_gate_can_NEVER_say_correct():
    """The strongest verdict is `ready_as_rfc`. Nothing here may ever assert the spec is true."""
    r = rr.check_readiness()
    assert r["state"] in {"not_ready", "ready_as_rfc"}
    assert r["state"] not in {"correct", "verified", "done", "fine"}
    assert any("DOES NOT SAY THE SPEC IS CORRECT" in n for n in r["notes"])


def test_it_says_out_loud_that_its_author_wrote_it():
    r = rr.check_readiness()
    assert any("I authored the predicate that says I may ship" in n for n in r["notes"])


class TestTheGateActuallyBites:
    """Each mutation is a way the spec could rot. The gate must catch every one."""

    def test_an_audit_that_stops_saying_CAPTURED_BLOCKS_the_ship(self, monkeypatch):
        """The load-bearing case. Self-credit is not a green light — it is the alarm."""
        monkeypatch.setattr(sa, "self_audit",
                            lambda: {"captured": False, "k_floor": 3})
        r = rr.check_readiness()
        assert r["state"] == "not_ready"
        assert any("STOPPED SAYING CAPTURED" in b for b in r["blockers"])
        assert any("not good news and it is not a green light" in b for b in r["blockers"])

    def test_a_quietly_deleted_retraction_BLOCKS_the_ship(self, monkeypatch):
        real = rr._read
        monkeypatch.setattr(rr, "_read",
                            lambda f: "" if f == "docs/portable-divergence.md" else real(f))
        r = rr.check_readiness()
        assert r["state"] == "not_ready"
        assert any("retraction has been quietly removed" in b for b in r["blockers"])

    def test_an_open_problem_vanishing_from_the_text_BLOCKS_the_ship(self, monkeypatch):
        real = rr._read
        monkeypatch.setattr(rr, "_read",
                            lambda f: "" if f == "docs/probe-battery.md" else real(f))
        r = rr.check_readiness()
        assert r["state"] == "not_ready"
        assert any("stopped being disclosed" in b for b in r["blockers"])

    def test_a_nondeterministic_verifier_BLOCKS_the_ship(self, monkeypatch):
        """A verifier you cannot FORK is a verifier you cannot convict (randy-2)."""
        real = rr._read
        monkeypatch.setattr(rr, "_read",
                            lambda f: "import random" if f == "tools/verify.py" else real(f))
        r = rr.check_readiness()
        assert r["state"] == "not_ready"
        assert any("cannot FORK" in b for b in r["blockers"])


def test_k_floor_of_one_is_NOT_a_blocker_and_the_gate_explains_why():
    """The old gate demanded the framework violate its own central theorem to become shippable."""
    r = rr.check_readiness()
    assert sa.self_audit()["k_floor"] == 1          # still 1, on every axis
    assert sa.self_audit()["captured"] is True      # still captured
    assert r["state"] == "ready_as_rfc"             # and that is NOT a blocker
    joined = " ".join(r["notes"])
    assert "VIOLATE" in joined and "OWN CENTRAL THEOREM" in joined
