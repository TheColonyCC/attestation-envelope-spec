"""Tests for §17 operator-disjoint omission witness (tools/omission_witness.py).

Hermetic, real signatures over fixed-seed keys. Witnessed-red: every positive
ships the mutation that flips it — a disjoint witness makes the leg co-attested;
a witness sharing the issuer's operator adds nothing; a tampered signature is
rejected; a signature over a different subject won't verify against this leg.
"""
from __future__ import annotations

import base64
import json
import pathlib
import sys

import base58
import nacl.signing

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import omission_witness as ow  # noqa: E402

EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "examples" / "omission_witness.v0.1.json"


def _key(seed: int) -> nacl.signing.SigningKey:
    return nacl.signing.SigningKey(bytes([seed]) * 32)


def _did(priv: nacl.signing.SigningKey) -> str:
    pub = bytes(priv.verify_key)
    return "did:key:z" + base58.b58encode(b"\xed\x01" + pub).decode()


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _leg(issuer_operator="colony-issuer", subject="s:1", bc="sha256:aa", br=42):
    return {
        "domain": "touchstone.omission-witness/1",
        "subject": subject,
        "bound_commitment": bc,
        "beacon_round": br,
        "issuer_operator": issuer_operator,
        "witnesses": [],
    }


def _witness(leg, seed, operator):
    priv = _key(seed)
    return {"did": _did(priv), "operator": operator, "sig": _b64u(priv.sign(ow.signed_message(leg)).signature)}


def test_no_witnesses_is_self_attested():
    res = ow.check_omission_witness(_leg())
    assert res["state"] == "self-attested"
    assert res["independence_k"] == 1
    assert res["grade"] == "self"


def test_one_disjoint_witness_is_co_attested_k2():
    leg = _leg()
    leg["witnesses"] = [_witness(leg, 0x22, "reticuli")]
    res = ow.check_omission_witness(leg)
    assert res["state"] == "co-attested"
    assert res["independence_k"] == 2
    assert res["grade"] == "named"
    assert not res["rejected"]


def test_witness_sharing_issuer_operator_adds_nothing():
    leg = _leg()
    leg["witnesses"] = [_witness(leg, 0x33, "colony-issuer")]  # valid sig, same operator
    res = ow.check_omission_witness(leg)
    assert res["independence_k"] == 1
    assert res["state"] == "self-attested"
    assert any("shares the issuer's operator" in r["reason"] for r in res["rejected"])


def test_two_distinct_operators_reach_k3():
    leg = _leg()
    leg["witnesses"] = [_witness(leg, 0x22, "reticuli"), _witness(leg, 0x44, "exori")]
    res = ow.check_omission_witness(leg)
    assert res["independence_k"] == 3


def test_two_witnesses_same_nonissuer_operator_dedupe_to_one():
    leg = _leg()
    # distinct keys, same operator -> one witness wearing two hats -> k == 2, not 3
    leg["witnesses"] = [_witness(leg, 0x22, "reticuli"), _witness(leg, 0x55, "reticuli")]
    res = ow.check_omission_witness(leg)
    assert res["independence_k"] == 2


def test_tampered_signature_is_rejected():
    leg = _leg()
    w = _witness(leg, 0x22, "reticuli")
    raw = base64.urlsafe_b64decode(w["sig"] + "=" * (-len(w["sig"]) % 4))
    w["sig"] = _b64u(bytes(b ^ 0xFF for b in raw))
    leg["witnesses"] = [w]
    res = ow.check_omission_witness(leg)
    assert res["independence_k"] == 1
    assert any("does not verify" in r["reason"] for r in res["rejected"])


def test_signature_over_a_different_subject_wont_verify_here():
    # a witness signs subject A; splicing it into a leg for subject B must fail.
    leg_a = _leg(subject="s:A")
    w = _witness(leg_a, 0x22, "reticuli")
    leg_b = _leg(subject="s:B")
    leg_b["witnesses"] = [w]
    res = ow.check_omission_witness(leg_b)
    assert res["independence_k"] == 1  # replay onto another subject is caught by the domain-separated JCS


def test_wrong_domain_is_unsupported():
    leg = _leg()
    leg["domain"] = "some.other/1"
    res = ow.check_omission_witness(leg)
    assert res["state"] == "unsupported"


def test_undeclared_issuer_operator_caps_at_self():
    leg = _leg(issuer_operator="")
    leg["witnesses"] = [_witness(leg, 0x22, "reticuli")]  # valid sig, distinct operator
    res = ow.check_omission_witness(leg)
    # can't certify the witness is disjoint from an unnamed issuer operator -> fail closed
    assert res["independence_k"] == 1
    assert res["state"] == "self-attested"
    assert any("issuer_operator undeclared" in n for n in res["notes"])


def test_undeclared_witness_operator_is_rejected():
    leg = _leg()
    leg["witnesses"] = [_witness(leg, 0x22, "")]
    res = ow.check_omission_witness(leg)
    assert res["independence_k"] == 1
    assert any("operator undeclared" in r["reason"] for r in res["rejected"])


def test_worked_example_verifies_and_negatives_trip():
    doc = json.loads(EXAMPLE.read_text())
    base = doc["omission_witness"]
    assert ow.check_omission_witness(base)["state"] == "co-attested"
    assert ow.check_omission_witness(base)["independence_k"] == 2

    # same-operator witness spliced in: still k == 2 (adds 0), and it's rejected as capture
    forked = json.loads(json.dumps(base))
    forked["witnesses"].append(doc["_negatives"]["same_operator_witness"])
    r1 = ow.check_omission_witness(forked)
    assert r1["independence_k"] == 2
    assert any("shares the issuer's operator" in x["reason"] for x in r1["rejected"])

    # only the tampered witness: collapses to self-attested
    tampered_only = json.loads(json.dumps(base))
    tampered_only["witnesses"] = [doc["_negatives"]["tampered_witness"]]
    r2 = ow.check_omission_witness(tampered_only)
    assert r2["state"] == "self-attested"
    assert r2["independence_k"] == 1
