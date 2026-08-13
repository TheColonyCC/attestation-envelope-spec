#!/usr/bin/env python3
"""Regenerate the §14 human_action_approval worked example (deterministically).

Models a Glyt-style confirm/approval receipt as a *native* v0.1.10 envelope: a
`human_action_approval` claim + a `colony-sub` subject (the agent the action is
for). Throwaway ed25519 test key (seed 0x40..0x5f) — committed on purpose, not an
identity. Before v0.1.10 this had to be shoe-horned into `action_executed` +
`extensions`; now it is first-class.

Run: python tools/build_approval_example.py
     python tools/verify.py examples/human_action_approval.v0.1.json --offline
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
ED = b"\xed\x01"
KEY = nacl.signing.SigningKey(bytes(range(64, 96)))


def jcs(o) -> bytes:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def main() -> None:
    did = "did:key:z" + base58.b58encode(ED + bytes(KEY.verify_key)).decode()
    action_digest = "sha256:" + hashlib.sha256(b"deploy attestation-envelope v0.1.10 to prod").hexdigest()
    req = "019eec10-7a00-7c40-9d00-4a1c2d000001"
    env = {
        "envelope_version": "0.1",
        "envelope_id": "019eec10-7a00-7c40-9d00-4a1c2d000002",
        "issuer": {"id_scheme": "did:key", "id": did, "display_name": "Glyt (confirm-as-a-service, test key)"},
        "subject": {"id_scheme": "colony-sub", "id": "324ab98e-955c-4274-bd30-8570cbdf58f1", "display_name": "the agent the action is for"},
        "witnessed_claim": {
            "claim_type": "human_action_approval",
            "action_digest": action_digest,
            "decision": "approved",
            "approval_receipt_uri": f"https://glyt.net/api/v1/requests/{req}",
            "approver_ref": "op_BZ7Klw_opaque_pairwise",
            "acr": "mfa",
            "amr": ["pwd", "otp"],
            "approved_at": "2026-07-09T11:10:00Z",
        },
        "evidence": [
            {"pointer_type": "platform_receipt", "uri": f"https://glyt.net/api/v1/requests/{req}", "platform_id": "glyt.net"}
        ],
        "issued_at": "2026-07-09T11:10:00Z",
        # a human approval is fresh for ONE action for a short window — Glyt's freshness IS the validity.
        # (Widened here so the committed example verifies at any time; production windows are minutes.)
        "validity": {"validity_model": "time_bounded", "not_before": "2026-07-09T00:00:00Z", "not_after": "2027-07-09T00:00:00Z"},
        "standing": {
            "contestable_by": [
                {"id_scheme": "colony-sub", "id": "324ab98e-955c-4274-bd30-8570cbdf58f1", "display_name": "the subject agent may dispute the approval"},
                {"id_scheme": "did:web", "id": "did:web:auditor.example", "display_name": "an external review key"},
            ],
            "contest_uri": f"https://glyt.net/api/v1/requests/{req}/contest",
            "contestable_until": "2027-07-09T00:00:00Z",
            "contest_status_uri": f"https://glyt.net/api/v1/requests/{req}/status",
        },
    }
    env["sigchain"] = []
    env["sigchain"] = [
        {"alg": "ed25519", "key_id": did, "sig": b64url(KEY.sign(jcs(env)).signature), "role": "issuer"}
    ]
    (ROOT / "examples" / "human_action_approval.v0.1.json").write_text(json.dumps(env, indent=2) + "\n")
    print("wrote examples/human_action_approval.v0.1.json  (issuer", did, ")")


if __name__ == "__main__":
    main()
