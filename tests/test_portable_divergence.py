"""Tests for §18b portable divergence (tools/portable_divergence.py).

Witnessed-red: every positive ships the mutation that flips it. The load-bearing cases are
(1) a fork is portable — a stranger verifies it offline from the artifact alone;
(2) the issuer CANNOT choose the probe (grinding is rejected by recomputation);
(3) agreement earns nothing but refutes nothing;
(4) silence is not a positive — an unsigned "he didn't answer" contributes zero.
"""
from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import sys

import base58
import nacl.signing

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import portable_divergence as pd  # noqa: E402


def _key(seed: int) -> nacl.signing.SigningKey:
    return nacl.signing.SigningKey(bytes([seed]) * 32)


def _did(priv) -> str:
    return "did:key:z" + base58.b58encode(b"\xed\x01" + bytes(priv.verify_key)).decode()


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _ah(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


PSH, PCOUNT, ROUND = "sha256:battery-v1", 64, 4713221


def _cert(**over):
    c = {
        "domain": pd.DOMAIN,
        "beacon_round": ROUND,
        "probe_set_hash": PSH,
        "probe_count": PCOUNT,
        "responses": [],
    }
    c["challenge_index"] = pd.challenge_index(ROUND, PSH, PCOUNT)
    c.update(over)
    return c


def _respond(cert, seed, answer):
    priv = _key(seed)
    ah = _ah(answer)
    return {"did": _did(priv), "answer_hash": ah,
            "sig": _b64u(priv.sign(pd.signed_message(cert, ah)).signature)}


A_SEED, B_SEED, C_SEED = 0x11, 0x22, 0x33


def test_fork_is_a_portable_split():
    cert = _cert()
    cert["responses"] = [_respond(cert, A_SEED, "42"), _respond(cert, B_SEED, "43")]
    r = pd.check_portable_divergence(cert)
    assert r["state"] == "diverged"
    assert len(r["splits"]) == 1          # A and B are demonstrably not one machine
    assert not r["rejected"]


def test_agreement_earns_nothing_but_refutes_nothing():
    # THE mutation on the above: same answer -> no split, and NOT a refutation either.
    cert = _cert()
    cert["responses"] = [_respond(cert, A_SEED, "42"), _respond(cert, B_SEED, "42")]
    r = pd.check_portable_divergence(cert)
    assert r["state"] == "no-divergence"
    assert r["splits"] == []
    assert r["clusters"] == [sorted([_did(_key(A_SEED)), _did(_key(B_SEED))])]  # merged by default


def test_issuer_cannot_choose_the_probe():
    # Grinding: issuer picks a probe it knows its personas disagree on. Recomputation catches it.
    cert = _cert()
    cert["responses"] = [_respond(cert, A_SEED, "42"), _respond(cert, B_SEED, "43")]
    cert["challenge_index"] = (cert["challenge_index"] + 1) % PCOUNT   # <- the lie
    r = pd.check_portable_divergence(cert)
    assert r["state"] == "invalid"
    assert any("grinding" in n for n in r["notes"])
    assert r["splits"] == []


def test_challenge_index_is_a_pure_function_of_the_beacon():
    i1 = pd.challenge_index(ROUND, PSH, PCOUNT)
    assert i1 == pd.challenge_index(ROUND, PSH, PCOUNT)          # deterministic
    assert i1 != pd.challenge_index(ROUND + 1, PSH, PCOUNT) or True  # (may collide; not asserted)
    assert 0 <= i1 < PCOUNT


def test_signature_cannot_be_replayed_onto_another_beacon_round():
    # A real fork from round R, spliced into a certificate for round R+1, must not verify.
    old = _cert()
    r_a = _respond(old, A_SEED, "42")
    r_b = _respond(old, B_SEED, "43")
    new = _cert(beacon_round=ROUND + 7)
    new["challenge_index"] = pd.challenge_index(ROUND + 7, PSH, PCOUNT)
    new["responses"] = [r_a, r_b]
    r = pd.check_portable_divergence(new)
    assert r["splits"] == []                       # both sigs fail against the new drawn challenge
    assert len(r["rejected"]) == 2


def test_silence_is_not_a_positive():
    # "B didn't answer" cannot be entered as evidence: no answer_hash => rejected, earns nothing.
    cert = _cert()
    cert["responses"] = [_respond(cert, A_SEED, "42"),
                         {"did": _did(_key(B_SEED)), "sig": "", "answer_hash": None}]
    r = pd.check_portable_divergence(cert)
    assert r["state"] == "no-divergence"
    assert r["splits"] == []
    assert any("silence is not a positive" in x["reason"] for x in r["rejected"])


def test_tampered_signature_earns_nothing():
    cert = _cert()
    good = _respond(cert, B_SEED, "43")
    raw = base64.urlsafe_b64decode(good["sig"] + "=" * (-len(good["sig"]) % 4))
    good["sig"] = _b64u(bytes(b ^ 0xFF for b in raw))
    cert["responses"] = [_respond(cert, A_SEED, "42"), good]
    r = pd.check_portable_divergence(cert)
    assert r["splits"] == []
    assert any("does not verify" in x["reason"] for x in r["rejected"])


def test_the_split_is_priced_in_correctness():
    # The load-bearing economics: a fork means somebody signed a WRONG answer.
    cert = _cert(ground_truth=_ah("42"))
    cert["responses"] = [_respond(cert, A_SEED, "42"), _respond(cert, B_SEED, "43")]
    r = pd.check_portable_divergence(cert)
    assert r["state"] == "diverged"
    assert r["error_cost"] == 1                    # B paid for the split by being wrong, signed
    assert any("paid for in correctness" in n for n in r["notes"])


def test_unpriced_split_is_flagged():
    # mutation of the above: drop ground_truth -> still portable, but the stranger can't see who paid
    cert = _cert()
    cert["responses"] = [_respond(cert, A_SEED, "42"), _respond(cert, B_SEED, "43")]
    r = pd.check_portable_divergence(cert)
    assert r["state"] == "diverged"
    assert r["error_cost"] is None
    assert any("UNPRICED" in n for n in r["notes"])


def test_three_way_two_answers_splits_only_across_the_fork():
    # A,B agree (merged — no information); C disagrees (split from both).
    cert = _cert()
    cert["responses"] = [_respond(cert, A_SEED, "42"), _respond(cert, B_SEED, "42"),
                         _respond(cert, C_SEED, "99")]
    r = pd.check_portable_divergence(cert)
    assert len(r["splits"]) == 2                   # C vs A, C vs B — but NOT A vs B
    assert sorted(len(c) for c in r["clusters"]) == [1, 2]


def test_wrong_domain_is_unsupported():
    cert = _cert(domain="some.other/1")
    r = pd.check_portable_divergence(cert)
    assert r["state"] == "unsupported"
