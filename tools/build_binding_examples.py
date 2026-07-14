#!/usr/bin/env python3
"""Regenerate the §13 issuer-binding worked examples + their fixture DID docs.

Two throwaway ed25519 test keys (committed on purpose; not identities):
  - AGENT key  (seed 0x00..0x1f) — the issuer's signing key.
  - DOMAIN key (seed 0x20..0x3f) — a platform's key, published in its did:web doc.

Produces:
  - examples/artifacts/did-web-thecolony.ai.did.json
        the DID document a verifier fetches for did:web:thecolony.ai — authorises DOMAIN.
  - examples/artifacts/did-web-thecolony.ai-u-colonist-one.did.json
        the DID document for did:web:thecolony.ai:u:colonist-one — authorises AGENT.
  - examples/issuer_didweb.v0.1.json
        issuer id_scheme did:web; signing key AGENT is authorised by its DID doc -> BOUND.
  - examples/issuer_platform_witness.v0.1.json
        issuer platform-handle thecolony.ai:colonist-one; a platform_witness co-signs with
        DOMAIN, which did:web:thecolony.ai authorises -> BOUND via the domain's co-signature.

Live verification needs the platform to actually serve those did.json files; offline the
verifier reports issuer_binding=unverified (advisory). tests/test_binding.py proves the
binding with an injected resolver that reads these committed fixtures.

Run: python tools/build_binding_examples.py
Requires: pynacl, base58.
"""
from __future__ import annotations

import base64
import json
import pathlib

import base58
import nacl.signing

ROOT = pathlib.Path(__file__).resolve().parent.parent
ED = b"\xed\x01"
AGENT = nacl.signing.SigningKey(bytes(range(32)))
DOMAIN = nacl.signing.SigningKey(bytes(range(32, 64)))


def jcs(o) -> bytes:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def multibase(sk: nacl.signing.SigningKey) -> str:
    return "z" + base58.b58encode(ED + bytes(sk.verify_key)).decode()


def did_key(sk: nacl.signing.SigningKey) -> str:
    return "did:key:" + multibase(sk)


def did_document(did: str, sk: nacl.signing.SigningKey) -> dict:
    vm_id = did + "#key-1"
    return {
        "@context": ["https://www.w3.org/ns/did/v1"],
        "id": did,
        "verificationMethod": [
            {"id": vm_id, "type": "Ed25519VerificationKey2020", "controller": did, "publicKeyMultibase": multibase(sk)}
        ],
        "assertionMethod": [vm_id],
    }


def sign(env: dict, entries: list[tuple[nacl.signing.SigningKey, str, str]]) -> dict:
    """entries: [(key, did, role)]; peel-and-sign each over the chain so far."""
    env["sigchain"] = []
    for sk, did, role in entries:
        sig = sk.sign(jcs(env)).signature
        env["sigchain"].append({"alg": "ed25519", "key_id": did, "sig": b64url(sig), "role": role})
    return env


def base_envelope(env_id: str, issuer: dict) -> dict:
    return {
        "envelope_version": "0.1",
        "envelope_id": env_id,
        "issuer": issuer,
        "subject": {"id_scheme": "platform-handle", "id": "thecolony.ai:colonist-one", "display_name": "ColonistOne"},
        "witnessed_claim": {
            "claim_type": "artifact_published",
            "artifact_uri": "https://thecolony.ai/post/e17840cc-58cc-4f31-b49e-eb1f52466eea",
            "content_hash": "sha256:4c91c74b14111d2fd86309eaae923f4fad424b24ba416f3770b3e62ec14b92a3",
            "published_at": "2026-07-09T03:57:38Z",
        },
        "evidence": [{"pointer_type": "platform_receipt", "uri": "https://thecolony.ai/api/v1/posts/e17840cc-58cc-4f31-b49e-eb1f52466eea", "platform_id": "thecolony.ai"}],
        "issued_at": "2026-07-09T07:00:00Z",
        "validity": {"validity_model": "time_bounded", "not_before": "2026-07-09T00:00:00Z", "not_after": "2027-07-09T00:00:00Z"},
    }


def main() -> None:
    art = ROOT / "examples" / "artifacts"
    (art / "did-web-thecolony.ai.did.json").write_text(
        json.dumps(did_document("did:web:thecolony.ai", DOMAIN), indent=2) + "\n"
    )
    (art / "did-web-thecolony.ai-u-colonist-one.did.json").write_text(
        json.dumps(did_document("did:web:thecolony.ai:u:colonist-one", AGENT), indent=2) + "\n"
    )

    # A) did:web issuer, signed by AGENT (authorised by the issuer's own DID doc).
    a = base_envelope("019ee9a0-1000-7c00-8a00-000000000001",
                      {"id_scheme": "did:web", "id": "did:web:thecolony.ai:u:colonist-one", "display_name": "ColonistOne"})
    sign(a, [(AGENT, did_key(AGENT), "issuer")])
    (ROOT / "examples" / "issuer_didweb.v0.1.json").write_text(json.dumps(a, indent=2) + "\n")

    # B) platform-handle issuer + a platform_witness co-signature by DOMAIN
    #    (authorised by did:web:thecolony.ai).
    b = base_envelope("019ee9a0-1000-7c00-8a00-000000000002",
                      {"id_scheme": "platform-handle", "id": "thecolony.ai:colonist-one", "display_name": "ColonistOne"})
    sign(b, [(AGENT, did_key(AGENT), "issuer"), (DOMAIN, did_key(DOMAIN), "platform_witness")])
    (ROOT / "examples" / "issuer_platform_witness.v0.1.json").write_text(json.dumps(b, indent=2) + "\n")

    print("wrote 2 DID-doc fixtures + issuer_didweb + issuer_platform_witness examples")
    print("AGENT ", did_key(AGENT))
    print("DOMAIN", did_key(DOMAIN))


if __name__ == "__main__":
    main()
