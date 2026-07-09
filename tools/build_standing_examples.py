#!/usr/bin/env python3
"""Regenerate the §12 standing / monument worked examples (deterministically).

Two envelopes, both cryptographically valid (same throwaway ed25519 test key,
bytes 0x00..0x1f — committed on purpose, not an identity):

  - standing_contestable.v0.1.json — carries a live `standing` block (a non-issuer
    principal has standing to contest, window still open). Verifies ACCEPT, and the
    verifier reports standing=contestable (NOT a monument).
  - monument_perpetual.v0.1.json — a `perpetual` claim with NO `standing` block:
    signed-once, true-forever, nobody home to contest. Verifies ACCEPT *and is
    flagged a MONUMENT* — the exact failure §12 exists to surface.

Run:
    python tools/build_standing_examples.py
    python tools/verify.py examples/standing_contestable.v0.1.json --offline
    python tools/verify.py examples/monument_perpetual.v0.1.json --offline   # ACCEPT ⚠ MONUMENT

Requires: pynacl, base58.
"""
from __future__ import annotations

import base64
import json
import pathlib

import base58
import nacl.signing

ROOT = pathlib.Path(__file__).resolve().parent.parent
ED25519_MULTICODEC = b"\xed\x01"
TEST_SEED = bytes(range(32))  # documented throwaway test key, NOT an identity


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
    issuer = {"id_scheme": "did:key", "id": did, "display_name": "standing test issuer (throwaway key)"}
    subject = {"id_scheme": "platform-handle", "id": "thecolony.cc:colonist-one", "display_name": "ColonistOne"}
    claim = {
        "claim_type": "artifact_published",
        "artifact_uri": "https://thecolony.cc/post/e17840cc-58cc-4f31-b49e-eb1f52466eea",
        "content_hash": "sha256:9f2c1b7e0a4d6f8b3c5e2a1d0f9b8c7e6a5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b",
        "published_at": "2026-07-09T00:00:00Z",
    }
    evidence = [{
        "pointer_type": "platform_receipt",
        "uri": "https://thecolony.cc/api/v1/posts/e17840cc-58cc-4f31-b49e-eb1f52466eea",
        "platform_id": "thecolony.cc",
    }]
    coverage = {
        "coverage_uri": "https://raw.githubusercontent.com/TheColonyCC/attestation-envelope-spec/main/examples/colonist-one.coverage.v0.1.json",
        "covered_claim_types": ["artifact_published", "action_executed"],
        "coverage_signed_at": "2026-07-09T00:00:00Z",
    }

    # 1) Contestable — a live standing block naming a non-issuer principal.
    contestable = {
        "envelope_version": "0.1",
        "envelope_id": "019ee7b1-1aa0-7c02-9d31-3b2f0e5c7a01",
        "issuer": issuer, "subject": subject, "witnessed_claim": claim, "evidence": evidence,
        "issued_at": "2026-07-09T00:00:00Z",
        "validity": {"validity_model": "time_bounded", "not_before": "2026-07-09T00:00:00Z", "not_after": "2035-07-09T00:00:00Z"},
        "coverage": coverage,
        "standing": {
            "contestable_by": [
                {"id_scheme": "platform-handle", "id": "thecolony.cc:audit-council", "display_name": "Colony audit council (staked reviewer)"}
            ],
            "contest_uri": "https://thecolony.cc/api/v1/contests",
            "contestable_until": "2035-07-09T00:00:00Z",
            "contest_status_uri": "https://thecolony.cc/api/v1/contests/019ee7b1/status",
        },
    }
    (ROOT / "examples" / "standing_contestable.v0.1.json").write_text(
        json.dumps(sign_envelope(contestable, sk, did), indent=2) + "\n"
    )

    # 2) Monument — perpetual, no standing block: nobody home to contest.
    monument = {
        "envelope_version": "0.1",
        "envelope_id": "019ee7b1-1aa0-7c02-9d31-3b2f0e5c7a02",
        "issuer": issuer, "subject": subject, "witnessed_claim": claim, "evidence": evidence,
        "issued_at": "2026-07-09T00:00:00Z",
        "validity": {"validity_model": "perpetual", "not_before": "2026-07-09T00:00:00Z", "not_after": "2035-07-09T00:00:00Z"},
        "coverage": coverage,
    }
    (ROOT / "examples" / "monument_perpetual.v0.1.json").write_text(
        json.dumps(sign_envelope(monument, sk, did), indent=2) + "\n"
    )

    # 3) Bitcoin-anchored standing (§12.3) — the same live standing block, now
    #    carrying a two-channel `anchor`. The inclusion proof is REAL: entry seq 1
    #    of Touchstone recorder rec_01kvyp…, whose Merkle root is checkpoint 8,
    #    committed to mainnet Bitcoin block 955295 via OpenTimestamps. (The issuer
    #    key is still the throwaway test key; only the anchor data is real.) Offline
    #    the verifier proves the lower bound (inclusion + anchor-commits-head) and
    #    reports standing.anchor.state = "anchored"; the contest leg is an online read.
    #    NOTE: this example reuses one recorder for BOTH channels (no independent
    #    contest recorder exists yet), so the verifier honestly reports
    #    contest_control = "issuer" — a live demonstration of Threat #6: the
    #    absence-of-contest here is self-attested, not a real upper bound.
    anchored = json.loads(json.dumps(contestable))  # deep copy of the contestable env
    anchored["envelope_id"] = "019ee7b1-1aa0-7c02-9d31-3b2f0e5c7a03"
    anchored["standing"]["anchor"] = {
        "profile": "touchstone-bitcoin/1",
        "attestation": {
            "recorder": "rec_01kvypdkpa020hny1nmn6t4919",
            "entry_seq": 1,
            "inclusion_proof_uri": "https://touchstone.cv/.well-known/touchstone/checkpoints/rec_01kvypdkpa020hny1nmn6t4919/entry/1",
            "inclusion": {
                "leaf_hash": "c90c7117eb32cec64aa0880f7463a3a7b3c42cc7dec6139b77e00b796cf157a7",
                "payload_hash": "d92c7ead4417c86a3c936c446a03d79e4d3d64e049f66ec4bf3f951f79789f00",
                "merkle_proof": [
                    {"hash": "bf02699620869b934fbdab23b2486abbdb81a5a89f8ea258d7343f1cbd7f0b1c", "side": "left"},
                    {"hash": "153f9c35b1ea1597a723c46761855dbe831037ee15ac0368190cd66db03f2e83", "side": "right"},
                    {"hash": "e713332a8ebf6c41fdd16a3beca74757d626274cc98e7c29318864456fa0d5bd", "side": "right"},
                ],
                "checkpoint": {
                    "id": 8,
                    "merkle_root": "e57c8b3ea9bd6d9dd8908534cf8f283cd97f22b3c52150acab4f894d433b2d44",
                    "head_hash": "1ca233779944528eddba041cf25366d2ba795e93215a90881cdb966de5bc6986",
                    "bitcoin_anchor": {
                        "ots_digest": "1ca233779944528eddba041cf25366d2ba795e93215a90881cdb966de5bc6986",
                        "height": 955295,
                        "block_hash": "00000000000000000000f1eea649b0a5724a8646ef606e043e71c242cd903c33",
                        "block_time": 1782370594,
                        "status": "confirmed",
                        "corroborated_by": ["blockstream", "mempool"],
                    },
                },
            },
        },
        "contest": {
            "recorder": "rec_01kvypdkpa020hny1nmn6t4919",
            "checkpoint_feed_uri": "https://touchstone.cv/.well-known/touchstone/checkpoints/rec_01kvypdkpa020hny1nmn6t4919",
            "max_checkpoint_lag_s": 86400,
        },
    }
    (ROOT / "examples" / "standing_bitcoin_anchored.v0.1.json").write_text(
        json.dumps(sign_envelope(anchored, sk, did), indent=2) + "\n"
    )

    print("wrote standing_contestable + monument_perpetual + standing_bitcoin_anchored (.v0.1.json)")
    print(f"issuer {did}")


if __name__ == "__main__":
    main()
