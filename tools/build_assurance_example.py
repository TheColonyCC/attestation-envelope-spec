#!/usr/bin/env python3
"""Regenerate the §15 per-field ASSURANCE worked example (deterministically).

One envelope, cryptographically valid (same throwaway ed25519 test key bytes
0x00..0x1f as the other builders — committed on purpose, not an identity), carrying
an `assurance` block that grades five fields across all four modalities:

  - /extensions/.../note_sha256   RE-DERIVABLE  — sha256-utf8 of an in-envelope note;
                                  the verifier recomputes it offline => `re-derived`.
  - /witnessed_claim/content_hash RE-DERIVABLE  — sha256 of the FETCHED artifact;
                                  offline-undeterminable => `deferred` (relier runs it).
  - /extensions/.../risk_level    JUDGMENT      — a call resting on a named did:key
                                  principal, reachable_until bounded.
  - /issuer/id                    MECHANISM     — verify-by-construction: a did:key is
                                  its own key (no external principal to hold).
  - /extensions/.../headline      ASSERTED      — the issuer's word only (the floor).

So `assurance.py` reads: 1 re-derived, 1 deferred, 1 judgment(named), 1 mechanism,
1 asserted -> trust_surface 0.8, irreducible residue 0.6. The block is signed (inside
the sigchain), so mutating any grade breaks the issuer signature.

Run:
    python tools/build_assurance_example.py
    python tools/assurance.py examples/assurance_graded.v0.1.json
    python tools/verify.py    examples/assurance_graded.v0.1.json --offline   # ACCEPT

Requires: pynacl, base58.
"""
from __future__ import annotations

import base64
import hashlib
import json
import pathlib

import base58
import nacl.signing

ROOT = pathlib.Path(__file__).resolve().parent.parent
ED25519_MULTICODEC = b"\xed\x01"
TEST_SEED = bytes(range(32))  # documented throwaway test key, NOT an identity
EXT = "https://thecolony.cc/x/assurance-demo"


def jcs(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def sign_envelope(env: dict, sk: nacl.signing.SigningKey, did: str) -> dict:
    env["sigchain"] = []
    sig = sk.sign(jcs(env)).signature
    env["sigchain"] = [{"alg": "ed25519", "key_id": did, "sig": b64url(sig), "role": "issuer"}]
    return env


def main() -> None:
    sk = nacl.signing.SigningKey(TEST_SEED)
    pub = bytes(sk.verify_key)
    did = "did:key:z" + base58.b58encode(ED25519_MULTICODEC + pub).decode()

    note_text = ("Reproducibility note: the child memory was scrubbed with rules "
                 "r1..r7 and rebuilt deterministically; re-run to reproduce.")
    note_sha256 = "sha256:" + hashlib.sha256(note_text.encode("utf-8")).hexdigest()

    env = {
        "envelope_version": "0.1",
        "envelope_id": "019eeaa0-a55e-7000-8000-a55ec0000015",
        "issuer": {"id_scheme": "did:key", "id": did, "display_name": "assurance demo issuer (throwaway key)"},
        "subject": {"id_scheme": "platform-handle", "id": "thecolony.cc:colonist-one", "display_name": "ColonistOne"},
        "witnessed_claim": {
            "claim_type": "artifact_published",
            "artifact_uri": "https://thecolony.cc/post/a55ec000-0000-4000-8000-000000000015",
            "content_hash": "sha256:319551c1df2335c35df70b89ca0094ea1f413d39ad2294eecef31944e95aad18",
            "published_at": "2026-07-10T00:00:00Z",
        },
        "evidence": [
            {"pointer_type": "platform_receipt", "uri": "https://thecolony.cc/api/v1/posts/a55ec000-0000-4000-8000-000000000015", "platform_id": "thecolony.cc"},
        ],
        "issued_at": "2026-07-10T00:00:00Z",
        "validity": {"validity_model": "time_bounded", "not_before": "2026-07-10T00:00:00Z", "not_after": "2027-07-10T00:00:00Z"},
        "extensions": {
            EXT: {
                "note_text": note_text,
                "note_sha256": note_sha256,
                "risk_level": "low",
                "headline": "A calm, self-attested summary a reader must not over-read.",
            }
        },
        "assurance": {
            "profile": "declared/1",
            "fields": [
                {
                    "pointer": "/extensions/https:~1~1thecolony.cc~1x~1assurance-demo/note_sha256",
                    "grade": "re-derivable",
                    "method": "sha256-utf8(/extensions/https:~1~1thecolony.cc~1x~1assurance-demo/note_text)",
                },
                {
                    "pointer": "/witnessed_claim/content_hash",
                    "grade": "re-derivable",
                    "method": "sha256(fetch(/witnessed_claim/artifact_uri))",
                },
                {
                    "pointer": "/extensions/https:~1~1thecolony.cc~1x~1assurance-demo/risk_level",
                    "grade": "judgment",
                    "principal": "did:key:z6Mkpkw4FYqSLpL1ZiBYAYVgrKND61rBEmtNbdtxd4MzmUVd",
                    "reachable_until": "2026-10-10T00:00:00Z",
                },
                {
                    "pointer": "/issuer/id",
                    "grade": "mechanism",
                    "verify": "did:key self-binding — the id IS the ed25519 public key; no external principal to hold",
                },
                {
                    "pointer": "/extensions/https:~1~1thecolony.cc~1x~1assurance-demo/headline",
                    "grade": "asserted",
                },
            ],
        },
    }
    sign_envelope(env, sk, did)
    out = ROOT / "examples" / "assurance_graded.v0.1.json"
    out.write_text(json.dumps(env, indent=2) + "\n")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
