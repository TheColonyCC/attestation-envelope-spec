"""Tests for §18i signed merge / self-collapse (tools/signed_merge.py).

Witnessed-red. The load-bearing case is the one that catches the bug I would have shipped:
a ONE-SIDED merge — "I control you" — must be rejected as an ATTACK, not accepted as a
confession. "Let anyone lower it" would have waved it straight through and handed every agent
a free weapon for destroying a stranger's independence by assertion.
"""
from __future__ import annotations

import base64
import pathlib
import sys

import base58
import nacl.signing

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import signed_merge as sm  # noqa: E402


def _key(seed: int) -> nacl.signing.SigningKey:
    return nacl.signing.SigningKey(bytes([seed]) * 32)


def _did(priv) -> str:
    return "did:key:z" + base58.b58encode(b"\xed\x01" + bytes(priv.verify_key)).decode()


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


A, B, C = _key(0x11), _key(0x22), _key(0x33)
DID_A, DID_B, DID_C = _did(A), _did(B), _did(C)


def _merge(collapses, signers, reason="self-collapse", beacon=6284142):
    m = {"domain": sm.DOMAIN, "collapses": collapses, "reason": reason, "beacon_round": beacon}
    msg = sm.merge_message(m)
    m["signatures"] = [{"did": _did(k), "sig": _b64u(k.sign(msg).signature)} for k in signers]
    return m


class TestMutualCollapse:
    def test_a_mutual_merge_collapses(self):
        r = sm.check_merge(_merge([DID_A, DID_B], [A, B]))
        assert r["state"] == "collapsed"
        assert sorted(r["collapsed"]) == sorted([DID_A, DID_B])
        assert not r["missing_signatures"]

    def test_the_collapse_is_monotone_and_says_so(self):
        r = sm.check_merge(_merge([DID_A, DID_B], [A, B]))
        assert any("never again prove they are two" in n for n in r["notes"])

    def test_it_states_what_dies_and_what_survives(self):
        r = sm.check_merge(_merge([DID_A, DID_B], [A, B]))
        joined = " ".join(r["notes"])
        assert "CORROBORATION" in joined            # what dies
        assert "refutation carries no identity term" in joined   # what survives, at full strength

    def test_three_keys_can_collapse_together(self):
        r = sm.check_merge(_merge([DID_A, DID_B, DID_C], [A, B, C]))
        assert r["state"] == "collapsed"
        assert len(r["collapsed"]) == 3


class TestAOneSidedMergeIsAnAttack:
    """THE test. This is the bug 'let anyone lower it' would have shipped."""

    def test_i_cannot_merge_you_by_asserting_i_run_you(self):
        # A signs a merge of {A, B}. B never agreed. This is an assault on B's independence.
        r = sm.check_merge(_merge([DID_A, DID_B], [A]))
        assert r["state"] == "attack"
        assert r["state"] != "collapsed"
        assert DID_B in r["missing_signatures"]
        assert any("confession's clothes" in n for n in r["notes"])

    def test_the_mutation_that_makes_it_legitimate(self):
        # THE mutation, stated as a pair: the SAME set, one signature apart.
        assault = sm.check_merge(_merge([DID_A, DID_B], [A]))       # A alone: "I run B"
        confession = sm.check_merge(_merge([DID_A, DID_B], [A, B]))  # B signs too
        assert assault["state"] == "attack"
        assert confession["state"] == "collapsed"
        # One signature is the entire difference between a confession and an assault.

    def test_a_bare_assertion_with_no_signatures_is_incomplete(self):
        m = {"domain": sm.DOMAIN, "collapses": [DID_A, DID_B], "reason": "trust me",
             "beacon_round": 1, "signatures": []}
        r = sm.check_merge(m)
        assert r["state"] == "incomplete"
        assert any("bare assertion" in n for n in r["notes"])

    def test_a_third_party_cannot_merge_two_keys_it_does_not_hold(self):
        # C signs a merge of {A, B}. C is not in the set. Its signature must count for nothing.
        m = {"domain": sm.DOMAIN, "collapses": [DID_A, DID_B], "reason": "x", "beacon_round": 1}
        msg = sm.merge_message(m)
        m["signatures"] = [{"did": DID_C, "sig": _b64u(C.sign(msg).signature)}]
        r = sm.check_merge(m)
        assert r["state"] == "incomplete"          # C's signature bought nothing
        assert any("not in `collapses`" in x["reason"] for x in r["rejected"])

    def test_a_tampered_signature_does_not_complete_a_merge(self):
        m = _merge([DID_A, DID_B], [A, B])
        raw = base64.urlsafe_b64decode(m["signatures"][1]["sig"] + "==")
        m["signatures"][1]["sig"] = _b64u(bytes(b ^ 0xFF for b in raw))
        r = sm.check_merge(m)
        assert r["state"] == "attack"              # only A's signature survives -> one-sided
        assert any("does not verify" in x["reason"] for x in r["rejected"])


class TestMonotone:
    def test_a_merged_set_may_grow(self):
        r = sm.verify_merge_monotone([DID_A, DID_B], [DID_A, DID_B, DID_C])
        assert r["ok"] is True and r["added"] == [DID_C]

    def test_a_merged_set_may_NEVER_shrink(self):
        """Keys can prove they are one. They can never again prove they are two."""
        r = sm.verify_merge_monotone([DID_A, DID_B], [DID_A])
        assert r["ok"] is False
        assert r["state"] == "un-merge"
        assert "cannot sign a negative" in r["reason"]


def test_a_signature_over_a_different_set_does_not_transfer():
    # A signs a merge of {A,B}. Splicing that signature into a merge of {A,B,C} must not verify.
    small = _merge([DID_A, DID_B], [A, B])
    big = {"domain": sm.DOMAIN, "collapses": [DID_A, DID_B, DID_C], "reason": "self-collapse",
           "beacon_round": 6284142, "signatures": small["signatures"]}
    r = sm.check_merge(big)
    assert r["state"] != "collapsed"
    assert all("does not verify" in x["reason"] for x in r["rejected"])
