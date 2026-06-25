"""Build examples/independence_multiwitness.v0.1.json — a real, verifying envelope
whose 3 signatures resolve to 2 effective-independent witnesses.

issuer + countersignatory-B both re-derived from evidence[0]; countersignatory-C
re-derived from evidence[1]. So len(sigchain)==3 but effective_witnesses()==2 —
the point the example exists to make. Deterministic keys (seeded) so the committed
example is stable and re-buildable. Run: python tools/build_independence_example.py
"""
import base64
import copy
import json
import pathlib

import base58
import nacl.signing

ROOT = pathlib.Path(__file__).resolve().parent.parent


def jcs(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def did_key(pub: bytes) -> str:
    return "did:key:z" + base58.b58encode(b"\xed\x01" + pub).decode()


def main() -> int:
    # deterministic keys so the committed artifact is stable
    keys = [nacl.signing.SigningKey(seed=bytes([i + 1]) * 32) for i in range(3)]
    dids = [did_key(bytes(k.verify_key)) for k in keys]

    Ha = "sha256:" + "a1" * 32
    Hb = "sha256:" + "b2" * 32

    env = {
        "envelope_version": "0.1",
        "envelope_id": "019ee0a0-0000-7000-8000-00000000d101",
        "issuer": {"id_scheme": "did:key", "id": dids[0], "display_name": "Release publisher"},
        "subject": {"id_scheme": "platform-handle", "id": "pkg:demo/widget", "display_name": "demo/widget v2"},
        "witnessed_claim": {
            "claim_type": "artifact_published",
            "artifact_uri": "https://example.test/demo/widget/2.0.0",
            "content_hash": Ha,
            "published_at": "2026-06-25T00:00:00Z",
        },
        "evidence": [
            {"pointer_type": "immutable_uri", "uri": "https://example.test/builds/A", "content_hash": Ha},
            {"pointer_type": "immutable_uri", "uri": "https://example.test/builds/B", "content_hash": Hb},
        ],
        "issued_at": "2026-06-25T00:00:00Z",
        "validity": {
            "validity_model": "time_bounded",
            "not_before": "2026-06-01T00:00:00Z",
            "not_after": "2030-01-01T00:00:00Z",
        },
        "coverage": {
            "coverage_uri": "https://example.test/publisher/coverage.json",
            "covered_claim_types": ["artifact_published"],
            "coverage_signed_at": "2026-06-25T00:00:00Z",
        },
    }

    # issuer & B both re-derived from evidence[0] (one witness); C from evidence[1] (a second).
    plan = [("issuer", [0]), ("countersignatory", [0]), ("countersignatory", [1])]
    chain: list = []
    for i, (role, refs) in enumerate(plan):
        stripped = copy.deepcopy(env)
        stripped["sigchain"] = copy.deepcopy(chain)
        sig = base64.urlsafe_b64encode(keys[i].sign(jcs(stripped)).signature).decode().rstrip("=")
        chain.append({"alg": "ed25519", "key_id": dids[i], "sig": sig, "role": role, "evidence_refs": refs})
    env["sigchain"] = chain

    out = ROOT / "examples" / "independence_multiwitness.v0.1.json"
    out.write_text(json.dumps(env, indent=1) + "\n")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
