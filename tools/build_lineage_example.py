"""Build examples/lineage_twogen.v0.1.json — a real, verifying TWO-generation
lineage bundle, so the lineage verifier's cross-generation linkage path is
exercised on signed data (the committed Progenly fixture is depth-1).

Shape mirrors what Progenly serves at /births/<id>/lineage.json: a `generations`
list, youngest first, each carrying a full signed attestation envelope plus an
advisory `verification` block (which the independent verifier ignores).

Linkage is genuine: the child (gen 0) lists the grandparent (gen 1) as a parent,
binding it by the grandparent's own child content-hash — exactly how a byte-stable
parent memory re-fed into a descendant merge would bind. Deterministic seeded keys
keep the committed artifact stable. Run: python tools/build_lineage_example.py
"""
import base64
import copy
import hashlib
import json
import pathlib

import base58
import nacl.signing

ROOT = pathlib.Path(__file__).resolve().parent.parent


def jcs(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def did_key(pub: bytes) -> str:
    return "did:key:z" + base58.b58encode(b"\xed\x01" + pub).decode()


def sha(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode()).hexdigest()


def mint(signer: nacl.signing.SigningKey, child_name: str, child_memory: str, parents: list[dict]) -> dict:
    """parents: list of {label, hash} — `hash` is the parent's content-hash."""
    did = did_key(bytes(signer.verify_key))
    env = {
        "envelope_version": "0.1",
        "envelope_id": "019ee0b0-0000-7000-8000-" + hashlib.sha256(child_name.encode()).hexdigest()[:12],
        "issuer": {"id_scheme": "did:key", "id": did, "display_name": "Progenly"},
        "subject": {"id_scheme": "platform-handle", "id": "progenly.com:" + child_name, "display_name": child_name},
        "witnessed_claim": {
            "claim_type": "artifact_published",
            "artifact_uri": "https://progenly.com/child/" + child_name,
            "content_hash": sha(child_memory),
            "published_at": "2026-06-25T00:00:00Z",
        },
        "evidence": [
            {"pointer_type": "immutable_uri", "uri": "progenly:parent/" + p["label"], "content_hash": p["hash"]}
            for p in parents
        ],
        "issued_at": "2026-06-25T00:00:00Z",
        "validity": {"validity_model": "time_bounded", "not_before": "2026-06-01T00:00:00Z", "not_after": "2030-01-01T00:00:00Z"},
    }
    stripped = copy.deepcopy(env)
    stripped["sigchain"] = []
    sig = base64.urlsafe_b64encode(signer.sign(jcs(stripped)).signature).decode().rstrip("=")
    env["sigchain"] = [{"alg": "ed25519", "key_id": did, "sig": sig, "role": "issuer", "evidence_refs": list(range(len(parents)))}]
    return env


def main() -> int:
    signer = nacl.signing.SigningKey(seed=b"\x07" * 32)  # one issuer (Progenly) across generations

    # gen 1 (grandparent): a child of two external agents.
    gp_mem = "grandparent merged memory"
    grandparent = mint(signer, "Forebear", gp_mem,
                       [{"label": "alpha", "hash": sha("alpha mem")}, {"label": "beta", "hash": sha("beta mem")}])
    gp_hash = grandparent["witnessed_claim"]["content_hash"]

    # gen 0 (subject): a child whose parents include the grandparent, re-fed
    # byte-stably -> grandparent's child-hash appears as the subject's parent hash.
    subject = mint(signer, "Scion", "scion merged memory",
                   [{"label": "Forebear", "hash": gp_hash}, {"label": "gamma", "hash": sha("gamma mem")}])

    def gen(env, name, parents, advisory_ok=True, revoked=False):
        return {
            "birth_id": env["envelope_id"], "child_name": name, "parents": parents,
            "born_at": "2026-06-25T00:00:00Z", "revoked": revoked,
            "certificate": env,
            "verification": {"ok": advisory_ok, "issuer_bound": True, "reasons": [], "notes": []},
        }

    bundle = {
        "bundle_version": "0.1",
        "subject_birth_id": subject["envelope_id"],
        "subject_child_name": "Scion",
        "lineage_ok": True,
        "generation_count": 2,
        "generations": [
            gen(subject, "Scion", ["Forebear", "gamma"]),
            gen(grandparent, "Forebear", ["alpha", "beta"]),
        ],
        "note": "Re-verify each generation.certificate offline against its attestation-envelope signature; the verification block is advisory only.",
    }

    out = ROOT / "examples" / "lineage_twogen.v0.1.json"
    out.write_text(json.dumps(bundle, indent=1) + "\n")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
