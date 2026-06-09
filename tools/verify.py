#!/usr/bin/env python3
"""Reference consumer / verifier for attestation-envelope-spec v0.1.

This is the *consumer* side of the envelope: given an envelope JSON, decide
`accept | reject` and say why. It implements the four checks a compliant
consumer owes (README "Enforcement modality" + docs/threat-model.md):

  1. schema      — Draft 2020-12 structural validation
  2. sigchain    — peel-and-verify each signature over JCS(envelope|sigchain[0..i-1])
  3. validity    — time_bounded / perpetual / revocation_checked
  4. evidence    — resolve each pointer; if content_hash present, verify it
  5. coverage    — per-claim-type enforcement modality (MAY/SHOULD/MUST)

Network checks (evidence resolution, coverage fetch, revocation) only run in
full mode. `--offline` runs the cryptographically-meaningful, hermetic subset
(schema + sigchain + validity + structural coverage) so CI never touches the
network — see tests/test_verify.py.

Usage:
    python tools/verify.py examples/colony_post_published.v0.1.json
    python tools/verify.py --offline path/to/envelope.json
    python tools/verify.py --json envelope.json     # machine-readable verdict

Requires: jsonschema, pynacl, base58, requests (requests only for full mode).
"""
from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import hashlib
import json
import pathlib

import jsonschema

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "envelope.v0.1.schema.json").read_text())

# Per-claim-type coverage enforcement modality (README "Enforcement modality").
# MUST  -> a missing/failed coverage check is a rejection.
# SHOULD/MAY -> advisory; surfaced as a warning, not a rejection.
COVERAGE_MODALITY = {
    "artifact_published": "MAY",
    "action_executed": "SHOULD",
    "state_transition": "MUST",
    "capability_coverage": "MUST",
}

ED25519_MULTICODEC = b"\xed\x01"


# --------------------------------------------------------------------------- #
# Canonicalisation
# --------------------------------------------------------------------------- #
def jcs(obj) -> bytes:
    """RFC 8785 JCS canonical bytes.

    v0.1 envelopes are float-free (the one RFC 8785 corner case is IEEE-754
    number formatting; see docs/threat-model.md Threat #4), and all object keys
    are ASCII, so compact key-sorted UTF-8 JSON is byte-identical to a full JCS
    implementation for this schema. If `extensions` ever carries floats this
    must be swapped for a real RFC 8785 serialiser.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# --------------------------------------------------------------------------- #
# Identity / key resolution
# --------------------------------------------------------------------------- #
def did_key_to_pubkey(did: str) -> bytes:
    """Extract the raw 32-byte ed25519 public key from a did:key string."""
    import base58

    if not did.startswith("did:key:z"):
        raise ValueError(f"not a base58btc did:key: {did!r}")
    decoded = base58.b58decode(did[len("did:key:") + 1 :])  # strip 'did:key:' and the multibase 'z'
    if decoded[:2] != ED25519_MULTICODEC:
        raise ValueError("did:key multicodec is not ed25519 (0xed01)")
    pub = decoded[2:]
    if len(pub) != 32:
        raise ValueError(f"ed25519 pubkey must be 32 bytes, got {len(pub)}")
    return pub


def key_resolves_to(key_id: str, issuer: dict) -> tuple[bool, str]:
    """Does the signing key_id bind to the issuer identity?

    v0.1 can only *cryptographically* close this for did:key issuers, where the
    key_id IS the identity. For platform-handle / ethereum-eoa issuers there is
    no defined key-publication mechanism in v0.1 — the binding is UNBINDABLE and
    the consumer must treat the attestation as "key K made this claim", not
    "issuer I made this claim". This is the headline gap the pilot surfaces.
    """
    scheme = issuer.get("id_scheme")
    if scheme == "did:key":
        if key_id == issuer["id"]:
            return True, "did:key issuer: key_id == issuer.id (self-resolving)"
        return False, f"did:key issuer but key_id {key_id!r} != issuer.id {issuer['id']!r}"
    return False, (
        f"id_scheme={scheme!r}: no key-publication binding defined in v0.1 "
        "(UNBINDABLE — see GAP-1)"
    )


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #
def check_schema(env) -> list[str]:
    v = jsonschema.Draft202012Validator(SCHEMA)
    return [f"{'/'.join(map(str, e.path))}: {e.message}" for e in v.iter_errors(env)]


def check_sigchain(env) -> tuple[bool, list[str]]:
    import nacl.exceptions
    import nacl.signing

    notes: list[str] = []
    chain = env.get("sigchain") or []
    if not chain:
        return False, ["sigchain empty"]
    for i, entry in enumerate(chain):
        if entry.get("alg") != "ed25519":
            return False, [f"sigchain[{i}]: unsupported alg {entry.get('alg')!r} (v0.1 = ed25519 only)"]
        stripped = copy.deepcopy(env)
        stripped["sigchain"] = chain[:i]
        message = jcs(stripped)
        try:
            pub = did_key_to_pubkey(entry["key_id"])
        except ValueError as exc:
            return False, [f"sigchain[{i}]: key_id not a resolvable ed25519 did:key: {exc}"]
        try:
            sig = base64.urlsafe_b64decode(entry["sig"] + "=" * (-len(entry["sig"]) % 4))
            nacl.signing.VerifyKey(pub).verify(message, sig)
        except (nacl.exceptions.BadSignatureError, ValueError) as exc:
            return False, [f"sigchain[{i}]: signature does not verify ({type(exc).__name__})"]
        notes.append(f"sigchain[{i}] ({entry.get('role','?')}) verified against {entry['key_id'][:24]}…")
    # role + identity binding on the issuer signature
    if chain[0].get("role") not in (None, "issuer"):
        return False, [f"sigchain[0].role must be 'issuer' or unset, got {chain[0].get('role')!r}"]
    bound, why = key_resolves_to(chain[0]["key_id"], env["issuer"])
    notes.append(("issuer-binding OK: " if bound else "issuer-binding UNVERIFIED: ") + why)
    return True, notes  # signature math passed; binding result is surfaced in notes (see verdict)


def check_validity(env, *, now: dt.datetime | None = None, offline: bool) -> tuple[bool, list[str]]:
    v = env["validity"]
    model = v["validity_model"]
    now = now or dt.datetime.now(dt.timezone.utc)
    nb = dt.datetime.fromisoformat(v["not_before"].replace("Z", "+00:00"))
    na = dt.datetime.fromisoformat(v["not_after"].replace("Z", "+00:00"))
    if model == "time_bounded":
        if now < nb:
            return False, [f"not yet valid (not_before {v['not_before']})"]
        if now > na:
            return False, [f"expired (not_after {v['not_after']})"]
        return True, [f"time_bounded: within [{v['not_before']}, {v['not_after']}]"]
    if model == "perpetual":
        return True, ["perpetual: not_after is informational"]
    if model == "revocation_checked":
        if offline:
            return True, ["revocation_checked: SKIPPED in offline mode (would fetch revocation_uri)"]
        import requests

        try:
            r = requests.get(v["revocation_uri"], timeout=15)
            revoked = r.status_code == 200 and r.json().get("revoked") is True
            return (not revoked), [
                "revoked per revocation_uri" if revoked else "not revoked per revocation_uri"
            ]
        except Exception as exc:  # fail-closed (README out-of-scope: client policy)
            return False, [f"revocation endpoint unreachable, failing closed: {exc}"]
    return False, [f"unknown validity_model {model!r}"]


def check_evidence(env, *, offline: bool) -> tuple[bool, list[str]]:
    notes: list[str] = []
    hard_fail = False
    for i, ev in enumerate(env["evidence"]):
        ptype = ev["pointer_type"]
        if offline:
            notes.append(f"evidence[{i}] {ptype}: resolution SKIPPED (offline)")
            continue
        import requests

        try:
            r = requests.get(ev["uri"], timeout=20, headers={"User-Agent": "attestation-verify/0.1", "Accept": "*/*"})
            r.raise_for_status()
            raw = r.content
            # GitHub blob API returns base64-wrapped content; unwrap so content_hash
            # binds the *artifact* bytes, not the API envelope.
            if "api.github.com" in ev["uri"] and r.headers.get("content-type", "").startswith("application/json"):
                payload = r.json()
                if payload.get("encoding") == "base64":
                    raw = base64.b64decode(payload["content"])
            if "content_hash" in ev:
                alg, _, want = ev["content_hash"].partition(":")
                got = hashlib.new(alg, raw).hexdigest()
                if got == want:
                    notes.append(f"evidence[{i}] {ptype}: resolved, content_hash {alg} MATCHES")
                else:
                    hard_fail = True
                    notes.append(f"evidence[{i}] {ptype}: content_hash MISMATCH (pointer drift/tamper)")
            else:
                notes.append(f"evidence[{i}] {ptype}: resolved ({len(raw)} bytes, no content_hash to bind)")
        except Exception as exc:
            notes.append(f"evidence[{i}] {ptype}: unreachable ({exc}) — best-effort, not load-bearing")
    return (not hard_fail), notes


def check_coverage(env, *, offline: bool) -> tuple[str, list[str]]:
    """Returns ('ok'|'warn'|'fail', notes) per the claim's enforcement modality."""
    claim_type = env["witnessed_claim"]["claim_type"]
    modality = COVERAGE_MODALITY.get(claim_type, "SHOULD")
    cov = env.get("coverage")
    if not cov:
        msg = f"no coverage block; modality for {claim_type} is {modality}"
        return ("fail" if modality == "MUST" else "warn"), [msg]
    inline = set(cov.get("covered_claim_types", []))
    in_inline = claim_type in inline
    notes = [f"{claim_type} {'∈' if in_inline else '∉'} inline covered_claim_types (modality {modality})"]
    if offline:
        if not in_inline and modality == "MUST":
            return "fail", notes + ["MUST claim type not covered"]
        return ("ok" if in_inline else "warn"), notes + ["coverage_uri fetch SKIPPED (offline)"]
    import requests

    try:
        r = requests.get(cov["coverage_uri"], timeout=15, headers={"User-Agent": "attestation-verify/0.1"})
        r.raise_for_status()
        published = set(r.json().get("covered_claim_types", []))
        if inline - published:
            return "fail", notes + [f"inline coverage claims {inline - published} NOT in published coverage (trim attack)"]
        notes.append("coverage_uri fetched; inline ⊆ published (no trim)")
        covered = claim_type in published
        if not covered and modality == "MUST":
            return "fail", notes + ["MUST claim type not in published coverage"]
        return ("ok" if covered else "warn"), notes
    except Exception as exc:
        return ("fail" if modality == "MUST" else "warn"), notes + [f"coverage_uri unreachable: {exc}"]


# --------------------------------------------------------------------------- #
# Top-level
# --------------------------------------------------------------------------- #
def verify(env, *, offline: bool = False, now: dt.datetime | None = None) -> dict:
    verdict = {"accept": False, "checks": {}, "reasons": []}

    schema_errors = check_schema(env)
    verdict["checks"]["schema"] = {"ok": not schema_errors, "notes": schema_errors or ["valid Draft 2020-12"]}
    if schema_errors:
        verdict["reasons"].append("schema invalid")
        return verdict  # everything else assumes a well-formed envelope

    sig_ok, sig_notes = check_sigchain(env)
    issuer_bound = any(n.startswith("issuer-binding OK") for n in sig_notes)
    verdict["checks"]["sigchain"] = {"ok": sig_ok, "issuer_bound": issuer_bound, "notes": sig_notes}
    if not sig_ok:
        verdict["reasons"].append("sigchain failed")

    val_ok, val_notes = check_validity(env, now=now, offline=offline)
    verdict["checks"]["validity"] = {"ok": val_ok, "notes": val_notes}
    if not val_ok:
        verdict["reasons"].append("outside validity window")

    ev_ok, ev_notes = check_evidence(env, offline=offline)
    verdict["checks"]["evidence"] = {"ok": ev_ok, "notes": ev_notes}
    if not ev_ok:
        verdict["reasons"].append("evidence content_hash mismatch")

    cov_state, cov_notes = check_coverage(env, offline=offline)
    verdict["checks"]["coverage"] = {"state": cov_state, "notes": cov_notes}
    if cov_state == "fail":
        verdict["reasons"].append("coverage check failed (MUST claim type)")

    verdict["accept"] = sig_ok and val_ok and ev_ok and cov_state != "fail"
    # The issuer-binding gap is NOT a hard reject in v0.1 (it's UNBINDABLE for
    # platform-handle issuers by design); it's surfaced so consumers can apply
    # their own policy. did:key issuers do bind.
    if not issuer_bound:
        verdict["reasons"].append("issuer-binding UNVERIFIED (advisory; see GAP-1)")
    return verdict


def _render(verdict: dict) -> str:
    lines = [("ACCEPT" if verdict["accept"] else "REJECT")]
    for name, c in verdict["checks"].items():
        head = c.get("state", "ok" if c.get("ok") else "FAIL")
        lines.append(f"  [{head}] {name}")
        for n in c["notes"]:
            lines.append(f"        - {n}")
    if verdict["reasons"]:
        lines.append("  reasons: " + "; ".join(verdict["reasons"]))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verify an attestation envelope (v0.1).")
    ap.add_argument("envelope", type=pathlib.Path)
    ap.add_argument("--offline", action="store_true", help="skip all network checks (hermetic subset)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable verdict")
    args = ap.parse_args(argv)

    env = json.loads(args.envelope.read_text())
    verdict = verify(env, offline=args.offline)
    print(json.dumps(verdict, indent=2) if args.json else _render(verdict))
    return 0 if verdict["accept"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
