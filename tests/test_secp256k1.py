"""Tests + test vectors for the v0.1.6 secp256k1 sigchain algorithm.

Covers the docs/sigchain.md acceptance bar for re-adding secp256k1:
  (1) test vectors for SHA-256 + low-S ECDSA over JCS bytes,
  (2) a concrete secp256k1-key-issuer worked example that verifies,
  (3) explicit rejection of the 65-byte r||s||recovery encoding.
Plus malleability (high-S), wrong-key, tamper, and did:pkh-in-sigchain rejection.

Hermetic (offline / pure-function). Requires: coincurve, base58, jsonschema, pynacl.
"""
import base64
import copy
import json
import pathlib
import sys

import coincurve
from coincurve.ecdsa import der_to_cdata, serialize_compact

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import verify  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLE = json.loads((ROOT / "examples" / "secp256k1_cosigned.v0.1.json").read_text())

# Deterministic throwaway test key (matches tools/build_secp256k1_example.py).
TEST_SECRET = bytes(range(1, 33))
_PRIV = coincurve.PrivateKey(TEST_SECRET)
_PUB = _PRIV.public_key.format(compressed=True)
_DID = "did:key:z" + __import__("base58").b58encode(b"\xe7\x01" + _PUB).decode()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _sign_compact(secret: bytes, message: bytes) -> bytes:
    """64-byte low-S r||s over SHA-256(message) — the shape the spec accepts."""
    der = coincurve.PrivateKey(secret).sign(message)  # low-S normalised by libsecp256k1
    return serialize_compact(der_to_cdata(der))


# --------------------------------------------------------------------------- #
# (2) worked example verifies end to end
# --------------------------------------------------------------------------- #
def test_example_accepts_offline():
    v = verify.verify(copy.deepcopy(EXAMPLE), offline=True)
    assert v["accept"], v["reasons"]
    assert v["checks"]["sigchain"]["ok"]
    assert v["checks"]["sigchain"]["issuer_bound"]  # did:key(secp256k1) self-resolves


def test_example_issuer_is_secp256k1_did_key():
    assert EXAMPLE["sigchain"][0]["alg"] == "secp256k1"
    pub = verify.did_key_to_secp256k1_pubkey(EXAMPLE["issuer"]["id"])
    assert len(pub) == 33 and pub[0] in (0x02, 0x03)


# --------------------------------------------------------------------------- #
# (1) test vector — deterministic key over fixed JCS bytes
# --------------------------------------------------------------------------- #
def test_vector_sign_verify_roundtrip():
    message = verify.jcs({"hello": "colony", "n": 1})
    sig = _sign_compact(TEST_SECRET, message)
    assert len(sig) == 64
    entry = {"alg": "secp256k1", "key_id": _DID, "sig": _b64url(sig)}
    ok, why = verify._verify_secp256k1(entry, message)
    assert ok, why


def test_vector_is_low_s():
    """Every signature the spec accepts must be low-S (s <= n/2, BIP-146)."""
    for msg in (b"{}", verify.jcs({"a": 1}), verify.jcs({"z": [1, 2, 3]})):
        sig = _sign_compact(TEST_SECRET, msg)
        s = int.from_bytes(sig[32:], "big")
        assert 0 < s <= verify.SECP256K1_HALF_N


# --------------------------------------------------------------------------- #
# (3) 65-byte recovery-included encoding is rejected outright
# --------------------------------------------------------------------------- #
def test_65_byte_recovery_encoding_rejected():
    message = verify.jcs({"hello": "colony"})
    sig64 = _sign_compact(TEST_SECRET, message)
    sig65 = sig64 + b"\x00"  # append a recovery byte, as EVM eth_sign would
    entry = {"alg": "secp256k1", "key_id": _DID, "sig": _b64url(sig65)}
    ok, why = verify._verify_secp256k1(entry, message)
    assert not ok
    assert "65-byte" in why and "recovery" in why


# --------------------------------------------------------------------------- #
# malleability: high-S counterpart of a valid sig is rejected
# --------------------------------------------------------------------------- #
def test_high_s_rejected():
    message = verify.jcs({"hello": "colony"})
    sig = _sign_compact(TEST_SECRET, message)
    r = sig[:32]
    s = int.from_bytes(sig[32:], "big")
    high_s = (verify.SECP256K1_N - s).to_bytes(32, "big")  # the malleated twin
    entry = {"alg": "secp256k1", "key_id": _DID, "sig": _b64url(r + high_s)}
    ok, why = verify._verify_secp256k1(entry, message)
    assert not ok
    assert "high-S" in why


# --------------------------------------------------------------------------- #
# wrong key / tamper / wrong length
# --------------------------------------------------------------------------- #
def test_wrong_key_rejected():
    message = verify.jcs({"hello": "colony"})
    sig = _sign_compact(TEST_SECRET, message)
    other_pub = coincurve.PrivateKey(bytes(range(2, 34))).public_key.format(compressed=True)
    other_did = "did:key:z" + __import__("base58").b58encode(b"\xe7\x01" + other_pub).decode()
    entry = {"alg": "secp256k1", "key_id": other_did, "sig": _b64url(sig)}
    ok, why = verify._verify_secp256k1(entry, message)
    assert not ok
    assert "does not verify" in why


def test_tamper_breaks_signature():
    env = copy.deepcopy(EXAMPLE)
    env["witnessed_claim"]["artifact_uri"] = "https://evil.example/swapped"
    v = verify.verify(env, offline=True)
    assert not v["accept"]
    assert any("sigchain" in r for r in v["reasons"])


def test_wrong_length_rejected():
    message = verify.jcs({"hello": "colony"})
    entry = {"alg": "secp256k1", "key_id": _DID, "sig": _b64url(b"\x01" * 40)}
    ok, why = verify._verify_secp256k1(entry, message)
    assert not ok
    assert "64-byte" in why


# --------------------------------------------------------------------------- #
# did:pkh must NOT be accepted as a sigchain co-signer (evidence-layer only)
# --------------------------------------------------------------------------- #
def test_did_pkh_not_accepted_in_sigchain():
    message = verify.jcs({"hello": "colony"})
    sig = _sign_compact(TEST_SECRET, message)
    entry = {
        "alg": "secp256k1",
        "key_id": "did:pkh:eip155:8453:0x1234567890abcdef1234567890abcdef12345678",
        "sig": _b64url(sig),
    }
    ok, why = verify._verify_secp256k1(entry, message)
    assert not ok
    assert "did:key" in why  # rejected because it isn't a resolvable secp256k1 did:key


def test_unknown_alg_still_rejected():
    env = copy.deepcopy(EXAMPLE)
    env["sigchain"][0]["alg"] = "bls12-381"
    ok, notes = verify.check_sigchain(env)
    assert not ok
    assert "unsupported alg" in notes[0]
