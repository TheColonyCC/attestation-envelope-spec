"""Tests for the reference verifier (tools/verify.py).

Hermetic: every test runs in `--offline` mode (or pure-function), so CI never
touches the network. Network evidence/coverage resolution is exercised manually
in the pilot round-trip, not here. Run: pytest tests/
Requires: jsonschema, pynacl, base58.
"""
import base64
import copy
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import verify  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLE = json.loads((ROOT / "examples" / "colony_post_published.v0.1.json").read_text())


def test_example_accepts_offline():
    v = verify.verify(copy.deepcopy(EXAMPLE), offline=True)
    assert v["accept"], v["reasons"]
    assert v["checks"]["sigchain"]["ok"]
    assert v["checks"]["sigchain"]["issuer_bound"]


def test_tampered_body_breaks_sigchain():
    bad = copy.deepcopy(EXAMPLE)
    bad["witnessed_claim"]["content_hash"] = "sha256:" + "0" * 64
    v = verify.verify(bad, offline=True)
    assert not v["accept"]
    assert "sigchain failed" in v["reasons"]


def test_tampered_sig_breaks_sigchain():
    bad = copy.deepcopy(EXAMPLE)
    raw = bytearray(base64.urlsafe_b64decode(bad["sigchain"][0]["sig"] + "=="))
    raw[0] ^= 0xFF
    bad["sigchain"][0]["sig"] = base64.urlsafe_b64encode(bytes(raw)).decode().rstrip("=")
    v = verify.verify(bad, offline=True)
    assert not v["accept"]


def test_expired_envelope_rejected():
    bad = copy.deepcopy(EXAMPLE)
    v = verify.verify(bad, offline=True, now=dt.datetime(2099, 1, 1, tzinfo=dt.timezone.utc))
    assert not v["accept"]
    assert "outside validity window" in v["reasons"]


def test_not_yet_valid_rejected():
    bad = copy.deepcopy(EXAMPLE)
    v = verify.verify(bad, offline=True, now=dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc))
    assert not v["accept"]


def test_schema_violation_short_circuits():
    bad = copy.deepcopy(EXAMPLE)
    del bad["issuer"]
    v = verify.verify(bad, offline=True)
    assert not v["accept"]
    assert not v["checks"]["schema"]["ok"]
    assert "sigchain" not in v["checks"]  # short-circuited before crypto


def test_platform_handle_issuer_is_unbindable():
    """GAP-1: a platform-handle issuer cannot be cryptographically bound in v0.1."""
    bad = copy.deepcopy(EXAMPLE)
    bad["issuer"] = {"id_scheme": "platform-handle", "id": "thecolony.cc:colonist-one"}
    v = verify.verify(bad, offline=True)
    # signature math still passes, but issuer binding is unverified and surfaced
    assert not v["checks"]["sigchain"]["issuer_bound"]
    assert any("UNVERIFIED" in r for r in v["reasons"])


def test_must_claim_without_coverage_fails():
    bad = copy.deepcopy(EXAMPLE)
    bad["witnessed_claim"] = {
        "claim_type": "state_transition",
        "subject_state_before": "instrument",
        "subject_state_after": "agent",
        "transition_witness_uri": "https://example.org/witness/1",
    }
    bad.pop("coverage", None)
    v = verify.verify(bad, offline=True)
    assert v["checks"]["coverage"]["state"] == "fail"
    assert not v["accept"]


def test_did_key_roundtrip():
    import base58
    import nacl.signing

    sk = nacl.signing.SigningKey.generate()
    pub = bytes(sk.verify_key)
    did = "did:key:z" + base58.b58encode(b"\xed\x01" + pub).decode()
    assert verify.did_key_to_pubkey(did) == pub


def test_jcs_is_key_sorted_and_compact():
    assert verify.jcs({"b": 1, "a": 2}) == b'{"a":2,"b":1}'
