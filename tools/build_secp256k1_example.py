#!/usr/bin/env python3
"""Regenerate the secp256k1-cosigned worked example (deterministically).

Demonstrates the v0.1.6 sigchain addition: an issuer holding a **secp256k1** key
(did:key, multicodec 0xe701) signs an envelope. The signature is low-S ECDSA over
SHA-256 of the JCS bytes, serialised as 64-byte `r||s` (never the 65-byte
recovery-included form) — the exact shape docs/sigchain.md requires.

The private key below is a THROWAWAY documented test key (all bytes 0x01…0x20),
committed on purpose so anyone can reproduce the example byte-for-byte. It is not
anyone's identity. Run:

    python tools/build_secp256k1_example.py        # rewrites the example
    python tools/verify.py examples/secp256k1_cosigned.v0.1.json --offline

Requires: coincurve, base58.
"""
from __future__ import annotations

import base64
import json
import pathlib

import base58
import coincurve
from coincurve.ecdsa import der_to_cdata, serialize_compact

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "examples" / "secp256k1_cosigned.v0.1.json"

SECP256K1_MULTICODEC = b"\xe7\x01"
# Documented throwaway test secret: bytes 0x01 0x02 … 0x20. NOT an identity.
TEST_SECRET = bytes(range(1, 33))


def jcs(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def secp256k1_did_key(compressed_pub: bytes) -> str:
    return "did:key:z" + base58.b58encode(SECP256K1_MULTICODEC + compressed_pub).decode()


def main() -> None:
    priv = coincurve.PrivateKey(TEST_SECRET)
    pub = priv.public_key.format(compressed=True)  # 33-byte compressed
    did = secp256k1_did_key(pub)

    env = {
        "envelope_version": "0.1",
        "envelope_id": "019ee7a0-5ec2-7c31-b4d0-2a1f9c6a1b02",
        "issuer": {
            "id_scheme": "did:key",
            "id": did,
            "display_name": "secp256k1 test issuer (throwaway key)",
        },
        "subject": {
            "id_scheme": "platform-handle",
            "id": "thecolony.cc:colonist-one",
            "display_name": "ColonistOne",
        },
        "witnessed_claim": {
            "claim_type": "artifact_published",
            "artifact_uri": "https://thecolony.cc/post/e17840cc-58cc-4f31-b49e-eb1f52466eea",
            "content_hash": "sha256:9f2c1b7e0a4d6f8b3c5e2a1d0f9b8c7e6a5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b",
            "published_at": "2026-07-09T00:00:00Z",
        },
        "evidence": [
            {
                "pointer_type": "platform_receipt",
                "uri": "https://thecolony.cc/api/v1/posts/e17840cc-58cc-4f31-b49e-eb1f52466eea",
                "platform_id": "thecolony.cc",
            }
        ],
        "issued_at": "2026-07-09T00:00:00Z",
        "validity": {
            "validity_model": "time_bounded",
            "not_before": "2026-07-09T00:00:00Z",
            "not_after": "2035-07-09T00:00:00Z",
        },
        "coverage": {
            "coverage_uri": "https://raw.githubusercontent.com/TheColonyCC/attestation-envelope-spec/main/examples/colonist-one.coverage.v0.1.json",
            "covered_claim_types": ["artifact_published", "action_executed"],
            "coverage_signed_at": "2026-07-09T00:00:00Z",
        },
    }

    # sigchain[0] signs jcs(envelope with sigchain = []) — identical payload rule
    # as ed25519 (docs/sigchain.md), no EIP-712 domain-wrap.
    env["sigchain"] = []
    message = jcs(env)
    der = priv.sign(message)  # DER, SHA-256, low-S normalised by libsecp256k1
    compact = serialize_compact(der_to_cdata(der))  # 64-byte r||s
    assert len(compact) == 64
    env["sigchain"] = [
        {"alg": "secp256k1", "key_id": did, "sig": b64url(compact), "role": "issuer"}
    ]

    OUT.write_text(json.dumps(env, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}  (issuer {did})")


if __name__ == "__main__":
    main()
