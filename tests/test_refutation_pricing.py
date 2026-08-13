"""Tests for §18c refutation pricing (tools/refutation_pricing.py).

Witnessed-red. The load-bearing cases are the two halves of the asymmetry that breaks the
recursion:
  - a refutation is accepted FROM ANY SOURCE, including a declared adversary, because it
    self-authenticates and only ever LOWERS;
  - survival is NEVER a count of attempts — 10,000 claimed failed attacks earn exactly zero.
"""
from __future__ import annotations

import base64
import hashlib
import pathlib
import sys

import base58
import nacl.signing

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
import portable_divergence as pd  # noqa: E402
import refutation_pricing as rp  # noqa: E402


def _key(seed: int):
    return nacl.signing.SigningKey(bytes([seed]) * 32)


def _did(priv) -> str:
    return "did:key:z" + base58.b58encode(b"\xed\x01" + bytes(priv.verify_key)).decode()


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _ah(t: str) -> str:
    return "sha256:" + hashlib.sha256(t.encode()).hexdigest()


PSH, PCOUNT = "sha256:battery-v1", 64
A, B = 0x11, 0x22


def _fork_cert(rnd: int, ans_a: str, ans_b: str):
    c = {"domain": pd.DOMAIN, "beacon_round": rnd, "probe_set_hash": PSH, "probe_count": PCOUNT}
    c["challenge_index"] = pd.challenge_index(rnd, PSH, PCOUNT)
    c["responses"] = []
    for seed, ans in ((A, ans_a), (B, ans_b)):
        priv, ah = _key(seed), _ah(ans)
        c["responses"].append({"did": _did(priv), "answer_hash": ah,
                               "sig": _b64u(priv.sign(pd.signed_message(c, ah)).signature)})
    return c


def _survival(rnd: int, seed: int, ans: str):
    priv = _key(seed)
    idx = pd.challenge_index(rnd, PSH, PCOUNT)
    ah = _ah(ans)
    cert = {"domain": pd.DOMAIN, "beacon_round": rnd, "probe_set_hash": PSH, "challenge_index": idx}
    return {"did": _did(priv), "beacon_round": rnd, "challenge_index": idx, "answer_hash": ah,
            "sig": _b64u(priv.sign(pd.signed_message(cert, ah)).signature)}


def _truths(rounds, ans="right"):
    return {str(pd.challenge_index(r, PSH, PCOUNT)): _ah(ans) for r in rounds}


def _claim(**over):
    c = {"domain": rp.DOMAIN, "subject": "did:web:glyt.net#receipt-42",
         "probe_set_hash": PSH, "probe_count": PCOUNT,
         "refutations": [], "survival": [], "ground_truths": {}}
    c.update(over)
    return c


# --- the recursion-breaking half #1: refutations need no independent refuter -----------------

def test_refutation_is_accepted_from_a_declared_adversary():
    # The refuter is literally labelled an adversary. It is STILL upheld: the artifact
    # self-authenticates, and a refutation only LOWERS. Independence is never consulted.
    c = _claim(refutations=[{"type": "fork", "submitted_by": "a-declared-adversary",
                             "certificate": _fork_cert(4713221, "42", "43")}])
    r = rp.price_claim(c)
    assert r["state"] == "refuted"
    assert r["upheld_refutations"][0]["source"] == "a-declared-adversary"
    assert any("independence was NEVER consulted" in n for n in r["notes"])


def test_a_refutation_that_does_not_verify_is_refused():
    # THE mutation: same source, but the "fork" is two identical answers -> no divergence.
    c = _claim(refutations=[{"type": "fork", "submitted_by": "a-declared-adversary",
                             "certificate": _fork_cert(4713221, "42", "42")}])
    r = rp.price_claim(c)
    assert r["state"] != "refuted"
    assert any("does not verify" in x["reason"] for x in r["refused_refutations"])


def test_a_report_can_neither_lower_nor_raise():
    # Anti-grief: an observer's WORD is not an artifact. If reports could refute, an adversary
    # would fabricate co-movement to destroy an honest party's standing.
    c = _claim(refutations=[{"type": "report", "submitted_by": "obs-1",
                             "claim": "I watched them co-move for 90 days"}])
    r = rp.price_claim(c)
    assert r["state"] != "refuted"
    assert any("not self-authenticating" in x["reason"] for x in r["refused_refutations"])


# --- the recursion-breaking half #2: survival is never a count of attempts --------------------

def test_ten_thousand_claimed_attacks_earn_exactly_zero():
    # THE anti-Sybil case. "I attacked and failed" is an unattestable negative.
    c = _claim(attempts_claimed=10_000)
    r = rp.price_claim(c)
    assert r["coverage"] == 0.0
    assert r["state"] == "untested"
    assert any("IGNORED" in n and "Sybil-farmable" in n for n in r["notes"])
    assert any("has been IGNORED" in n for n in r["notes"])  # untested is not a soft pass


def test_coverage_comes_only_from_drawn_signed_correct_answers():
    rounds = [4713221, 4713222, 4713223]
    c = _claim(attempts_claimed=10_000,          # still ignored
               survival=[_survival(r, A, "right") for r in rounds],
               ground_truths=_truths(rounds))
    r = rp.price_claim(c)
    assert r["state"] == "unrefuted"
    assert len(r["covered_probes"]) == 3
    assert r["coverage"] > 0
    assert not r["survival_rejected"]


def test_a_false_survival_certificate_is_a_conviction_not_a_credit():
    # The §18b economics, applied to survival: lying about a probe means SIGNING A WRONG ANSWER.
    rounds = [4713221]
    c = _claim(survival=[_survival(rounds[0], A, "wrong")], ground_truths=_truths(rounds))
    r = rp.price_claim(c)
    assert r["coverage"] == 0.0
    assert any("SIGNED A WRONG ANSWER" in x["reason"] for x in r["survival_rejected"])


def test_prover_cannot_choose_its_own_probe():
    rounds = [4713221]
    s = _survival(rounds[0], A, "right")
    s["challenge_index"] = (s["challenge_index"] + 1) % PCOUNT   # grinding
    c = _claim(survival=[s], ground_truths=_truths(rounds))
    r = rp.price_claim(c)
    assert r["coverage"] == 0.0
    assert any("grinding" in x["reason"] for x in r["survival_rejected"])


def test_unsettleable_probe_proves_nothing():
    # A signed answer to a question with no ground truth is applause, not evidence.
    rounds = [4713221]
    c = _claim(survival=[_survival(rounds[0], A, "right")], ground_truths={})
    r = rp.price_claim(c)
    assert r["coverage"] == 0.0
    assert any("no settled ground truth" in x["reason"] for x in r["survival_rejected"])


def test_duplicate_coverage_of_one_probe_counts_once():
    # 50 signers answering the SAME drawn probe is one probe of coverage, not fifty.
    rounds = [4713221]
    c = _claim(survival=[_survival(rounds[0], seed, "right") for seed in range(0x30, 0x62)],
               ground_truths=_truths(rounds))
    r = rp.price_claim(c)
    assert len(r["covered_probes"]) == 1


def test_refutation_beats_any_amount_of_coverage():
    # Fails closed: one valid artifact refutes, however much survival is piled up.
    rounds = [4713221, 4713222, 4713223]
    c = _claim(survival=[_survival(r, A, "right") for r in rounds],
               ground_truths=_truths(rounds),
               refutations=[{"type": "fork", "submitted_by": "anyone",
                             "certificate": _fork_cert(4713299, "42", "43")}])
    r = rp.price_claim(c)
    assert r["state"] == "refuted"
    assert r["coverage"] == 0.0


def test_no_confirmed_state_exists():
    rounds = [4713221]
    c = _claim(survival=[_survival(rounds[0], A, "right")], ground_truths=_truths(rounds))
    r = rp.price_claim(c)
    assert r["state"] in {"unrefuted", "untested", "refuted", "unsupported"}
    assert any("no 'confirmed' state exists" in n for n in r["notes"])
