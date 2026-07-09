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

Requires: jsonschema, pynacl, base58, coincurve (secp256k1 sigchains),
requests (requests only for full mode).
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
    "human_action_approval": "SHOULD",
}

ED25519_MULTICODEC = b"\xed\x01"
SECP256K1_MULTICODEC = b"\xe7\x01"
# Order of the secp256k1 group; low-S canonicalisation requires s <= n//2 (BIP-146).
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_HALF_N = SECP256K1_N // 2


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
def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


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


def did_key_to_secp256k1_pubkey(did: str) -> bytes:
    """Extract the 33-byte *compressed* secp256k1 public key from a did:key string.

    A secp256k1 sigchain entry MUST name its key as a `did:key` (multicodec
    0xe701) so the verifier holds the public key: a non-recoverable 64-byte
    r||s signature cannot be checked against an address-only identity. That is
    the deliberate split — `did:pkh:eip155` names an on-chain issuer at the
    *evidence* layer (verified on-chain), never as a sigchain co-signature. See
    docs/sigchain.md.
    """
    import base58

    if not did.startswith("did:key:z"):
        raise ValueError(f"not a base58btc did:key: {did!r}")
    decoded = base58.b58decode(did[len("did:key:") + 1 :])
    if decoded[:2] != SECP256K1_MULTICODEC:
        raise ValueError("did:key multicodec is not secp256k1 (0xe701)")
    pub = decoded[2:]
    if len(pub) != 33 or pub[0] not in (0x02, 0x03):
        raise ValueError(
            f"secp256k1 pubkey must be 33-byte compressed (0x02/0x03 prefix), got {len(pub)} bytes"
        )
    return pub


def _verify_ed25519(entry: dict, message: bytes) -> tuple[bool, str]:
    import nacl.exceptions
    import nacl.signing

    try:
        pub = did_key_to_pubkey(entry["key_id"])
    except ValueError as exc:
        return False, f"key_id not a resolvable ed25519 did:key: {exc}"
    try:
        nacl.signing.VerifyKey(pub).verify(message, _b64url_decode(entry["sig"]))
    except (nacl.exceptions.BadSignatureError, ValueError) as exc:
        return False, f"signature does not verify ({type(exc).__name__})"
    return True, "ok"


def _verify_secp256k1(entry: dict, message: bytes) -> tuple[bool, str]:
    """Low-S ECDSA over SHA-256 of the JCS bytes; 64-byte r||s encoding only.

    Three defences make the acceptance bar (docs/sigchain.md) enforceable:
      - the 65-byte `r||s||recovery` encoding is rejected outright, so EVM
        toolchains can't pass eth_sign/EIP-191 output through by accident;
      - high-S signatures (s > n/2) are rejected — malleability closed per BIP-146;
      - the payload is `jcs(envelope|sigchain[0..i-1])`, identical to the ed25519
        path (no EIP-712 domain-wrap), so there is one canonical signed payload.
    """
    import coincurve
    from coincurve.ecdsa import cdata_to_der, deserialize_compact

    try:
        pub = did_key_to_secp256k1_pubkey(entry["key_id"])
    except ValueError as exc:
        return False, f"key_id not a resolvable secp256k1 did:key: {exc}"
    try:
        sig = _b64url_decode(entry["sig"])
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        return False, f"sig not valid base64url ({exc})"
    if len(sig) == 65:
        return False, (
            "65-byte r||s||recovery encoding rejected — strip the trailing recovery "
            "byte; raw EVM eth_sign/EIP-191 output is not accepted (docs/sigchain.md)"
        )
    if len(sig) != 64:
        return False, f"secp256k1 signature must be 64-byte r||s, got {len(sig)} bytes"
    r = int.from_bytes(sig[:32], "big")
    s = int.from_bytes(sig[32:], "big")
    if not (0 < r < SECP256K1_N):
        return False, "invalid signature: r out of range"
    if not (0 < s <= SECP256K1_HALF_N):
        return False, "non-canonical signature: high-S (s > n/2) rejected — low-S required (BIP-146)"
    try:
        der = cdata_to_der(deserialize_compact(sig))
        ok = coincurve.PublicKey(pub).verify(der, message)  # coincurve hashes with SHA-256
    except Exception as exc:  # malformed pubkey / sig
        return False, f"signature does not verify ({type(exc).__name__})"
    return (ok, "ok" if ok else "signature does not verify")


_SIG_VERIFIERS = {"ed25519": _verify_ed25519, "secp256k1": _verify_secp256k1}


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
# Issuer→identity binding (§13, closes GAP-1)
# --------------------------------------------------------------------------- #
def _did_web_https_url(did: str) -> str:
    """did:web:host[:path...] -> the HTTPS URL of its DID document (W3C did:web)."""
    if not did.startswith("did:web:"):
        raise ValueError(f"not a did:web: {did!r}")
    parts = [p.replace("%3A", ":") for p in did[len("did:web:") :].split(":")]
    host = parts[0]
    if len(parts) == 1:
        return f"https://{host}/.well-known/did.json"
    return f"https://{host}/{'/'.join(parts[1:])}/did.json"


def keys_from_did_document(doc: dict) -> set[str]:
    """The set of `did:key` identifiers a DID document authorises to sign.

    Reads `verificationMethod[*]`: a `publicKeyMultibase` becomes `did:key:<mb>`
    (a did:key IS that multibase), and an `id`/`publicKeyDidKey` already in did:key
    form is taken as-is. Other key encodings are ignored — a verifier only binds
    what it can turn into a did:key it already checks signatures against.
    """
    keys: set[str] = set()
    for vm in doc.get("verificationMethod", []) or []:
        if not isinstance(vm, dict):
            continue
        mb = vm.get("publicKeyMultibase")
        if isinstance(mb, str) and mb.startswith("z"):
            keys.add("did:key:" + mb)
        for field in ("id", "publicKeyDidKey"):
            v = vm.get(field)
            if isinstance(v, str) and v.startswith("did:key:z"):
                keys.add(v.split("#", 1)[0])
    return keys


def _default_http_get(url: str):
    import requests

    return requests.get(url, timeout=15, headers={"User-Agent": "attestation-verify/0.1"})


def resolve_did_web(did: str, *, http_get=None) -> set[str]:
    """Fetch a did:web DID document and return the did:key set it authorises."""
    fetch = http_get or _default_http_get
    r = fetch(_did_web_https_url(did))
    r.raise_for_status()
    return keys_from_did_document(r.json())


def check_issuer_binding(env, *, offline: bool, resolve_did=None) -> tuple[str, list[str]]:
    """Bind the issuer's signing key to the issuer *identity* (§13, GAP-1).

    Returns (state, notes), state in {'bound','unverified','unbindable'}. Advisory
    — as in v0.1, a failure to bind is surfaced, not a hard reject. `resolve_did`
    maps a did:web DID to its authorised did:key set (injected in tests; defaults
    to a live fetch). Offline mode skips every network resolution.

    Mechanisms (both were the GAP-1 proposals in docs/pilot-colony-moltbook.md):
      - did:key issuer  — key_id IS the identity (self-resolving; offline).
      - did:web issuer  — sigchain[0].key_id must be authorised by the DID document
                          the issuer's own domain publishes.
      - platform-handle — a `platform_witness` co-signer whose key is authorised by
                          the DID document of the SAME domain (`did:web:<domain>`)
                          vouches that this issuer key speaks for the handle. The
                          binding lives in the envelope; the trust root is the domain.
    """
    resolve_did = resolve_did or resolve_did_web
    issuer = env["issuer"]
    scheme = issuer.get("id_scheme")
    chain = env.get("sigchain") or []
    if not chain:
        return "unbindable", ["no sigchain to bind an issuer key from"]
    issuer_key = chain[0]["key_id"]

    if scheme == "did:key":
        ok, why = key_resolves_to(issuer_key, issuer)
        return ("bound" if ok else "unbindable"), [why]

    if scheme == "did:web":
        if offline:
            return "unverified", ["did:web issuer: DID-document resolution SKIPPED (offline)"]
        try:
            authorised = resolve_did(issuer["id"])
        except Exception as exc:
            return "unverified", [f"did:web issuer: DID document unresolvable ({exc})"]
        if issuer_key in authorised:
            return "bound", [f"did:web issuer: signing key authorised by {issuer['id']} DID document"]
        return "unverified", [f"did:web issuer: signing key {issuer_key!r} NOT in the DID document"]

    if scheme == "platform-handle":
        domain = str(issuer.get("id", "")).split(":", 1)[0]
        witnesses = [e for e in chain if e.get("role") == "platform_witness"]
        if not witnesses:
            return "unbindable", [
                f"platform-handle issuer {issuer.get('id')!r}: no platform_witness co-signature and "
                "no did:web — key cannot be bound to the handle (GAP-1)"
            ]
        if offline:
            return "unverified", ["platform_witness present; domain DID-document resolution SKIPPED (offline)"]
        try:
            domain_keys = resolve_did(f"did:web:{domain}")
        except Exception as exc:
            return "unverified", [f"platform_witness: domain DID document (did:web:{domain}) unresolvable ({exc})"]
        for w in witnesses:
            if w.get("key_id") in domain_keys:
                return "bound", [
                    f"bound via platform_witness: {domain} (did:web) authorises the witness key, which "
                    f"co-signed this envelope binding {issuer_key} to {issuer['id']!r}"
                ]
        return "unverified", [
            f"platform_witness key(s) not authorised by did:web:{domain} — the witness is not the domain"
        ]

    return "unbindable", [f"id_scheme={scheme!r}: no binding mechanism (GAP-1)"]


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #
def check_schema(env) -> list[str]:
    v = jsonschema.Draft202012Validator(SCHEMA)
    return [f"{'/'.join(map(str, e.path))}: {e.message}" for e in v.iter_errors(env)]


def check_sigchain(env) -> tuple[bool, list[str]]:
    notes: list[str] = []
    chain = env.get("sigchain") or []
    if not chain:
        return False, ["sigchain empty"]
    for i, entry in enumerate(chain):
        alg = entry.get("alg")
        verifier = _SIG_VERIFIERS.get(alg)
        if verifier is None:
            return False, [
                f"sigchain[{i}]: unsupported alg {alg!r} (supported: {', '.join(sorted(_SIG_VERIFIERS))})"
            ]
        stripped = copy.deepcopy(env)
        stripped["sigchain"] = chain[:i]
        message = jcs(stripped)
        ok, why = verifier(entry, message)
        if not ok:
            return False, [f"sigchain[{i}] ({alg}): {why}"]
        notes.append(
            f"sigchain[{i}] ({entry.get('role','?')}, {alg}) verified against {entry['key_id'][:24]}…"
        )
    # role check on the issuer signature; identity binding is a separate check (§13).
    if chain[0].get("role") not in (None, "issuer"):
        return False, [f"sigchain[0].role must be 'issuer' or unset, got {chain[0].get('role')!r}"]
    return True, notes


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


def standing_grade(env) -> str | None:
    """Grade the *strength* of an envelope's standing (§12.1): 'named' > 'venue' > 'self'.

    Not every non-issuer contester is equally accountable. A keyed/DID principal
    ('named') can itself be held to account; a platform-handle names a diffuse
    *venue* ('venue', e.g. a public comment thread) with no single accountable key;
    an issuer-only list is 'self' (a monument). None => no standing block. Mirrors
    the §9 selection_grade idea: contestability is only as strong as the party you
    can actually reach. Pure/offline — computed from `contestable_by`.
    """
    st = env.get("standing")
    if not st:
        return None
    issuer_id = env["issuer"].get("id")
    non_issuer = [c for c in st.get("contestable_by", []) if c.get("id") != issuer_id]
    if not non_issuer:
        return "self"
    if any(isinstance(c.get("id_scheme"), str) and c["id_scheme"].startswith("did:") for c in non_issuer):
        return "named"
    return "venue"


def check_standing(env, *, now: dt.datetime | None = None, offline: bool, http_get=None) -> tuple[str, list[str]]:
    """Contestability = standing (§12). Returns ('contestable'|'monument'|'n/a', notes).

    A signed conclusion that outlives the relation — and the party who could
    contest it — is a *monument*: cryptographically valid, semantically empty.
    This check makes the monument visible. It is **advisory** (like issuer-binding),
    not a hard reject: whether to rely on a monument is consumer policy. Note that
    an expired `time_bounded` claim already rejects via `check_validity`; this check
    catches the cases validity passes clean — a `perpetual` claim with no contest
    channel, a lapsed contest window, or issuer-only ("self") contestability.

    v0.1.9 adds a **grade** (see `standing_grade`) and a **contest-channel liveness**
    check: a `contest_status_uri` that is declared but unreachable is surfaced as
    degraded — a standing whose contest channel a verifier can't reach isn't really
    contestable, only *claimed* so. `http_get` is injectable for tests.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    st = env.get("standing")
    if not st:
        if env["validity"]["validity_model"] == "perpetual":
            return "monument", [
                "perpetual claim with no `standing` block — signed-once, true-forever, "
                "nobody home to contest (the monument case; see docs/standing.md)"
            ]
        return "n/a", ["no `standing` block; relation-contestability undeclared (consumer policy)"]

    until = dt.datetime.fromisoformat(st["contestable_until"].replace("Z", "+00:00"))
    issuer_id = env["issuer"].get("id")
    non_issuer = [c for c in st["contestable_by"] if c.get("id") != issuer_id]
    if not non_issuer:
        return "monument", [
            "`contestable_by` names only the issuer — self-contestation is not standing "
            "(a party the issuer cannot lawyer for is required)"
        ]
    if now > until:
        return "monument", [
            f"contest window closed ({st['contestable_until']}) — standing has lapsed; "
            "a signed conclusion no one can now contest"
        ]

    grade = standing_grade(env)
    notes = [
        f"contestable by {len(non_issuer)} non-issuer principal(s) until {st['contestable_until']}",
        f"standing grade: {grade} (a keyed/DID principal is 'named'; a platform-handle class is 'venue'; "
        "issuer-only is 'self' = monument)",
    ]

    # Contest-channel liveness (§12.2). A declared-but-unreachable channel is degraded:
    # standing is *claimed*, not verifiable. Deep anchor proofs (e.g. an OTS→Bitcoin-anchored
    # disclosure at contest_status_uri) are delegated to that anchor type's own verifier —
    # this check confirms only that the channel resolves.
    status_uri = st.get("contest_status_uri")
    if not status_uri:
        notes.append("liveness: no contest_status_uri — channel liveness UNDECLARED (a verifier can't confirm it's live)")
    elif offline:
        notes.append("liveness: contest_status_uri present; check SKIPPED (offline)")
    else:
        try:
            r = (http_get or _default_http_get)(status_uri)
            r.raise_for_status()
            try:
                state = (r.json() or {}).get("state", "resolved")
            except Exception:
                state = "resolved"
            notes.append(f"liveness: contest channel LIVE (contest_status_uri resolved; state={state})")
            if state in ("open", "upheld"):
                notes.append(f"a contest is {state} — material; consumer SHOULD weigh before relying")
        except Exception as exc:
            notes.append(
                f"liveness: contest channel UNREACHABLE ({type(exc).__name__}) — standing is DECLARED but "
                "not verifiable; treat as degraded"
            )
    return "contestable", notes


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
    if sig_ok:
        bind_state, bind_notes = check_issuer_binding(env, offline=offline)
    else:
        bind_state, bind_notes = "unbindable", ["sigchain did not verify — binding is moot"]
    issuer_bound = bind_state == "bound"
    verdict["checks"]["sigchain"] = {"ok": sig_ok, "issuer_bound": issuer_bound, "notes": sig_notes}
    verdict["checks"]["issuer_binding"] = {"state": bind_state, "notes": bind_notes}
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

    standing_state, standing_notes = check_standing(env, now=now, offline=offline)
    verdict["checks"]["standing"] = {
        "state": standing_state,
        "grade": standing_grade(env),
        "notes": standing_notes,
    }
    verdict["monument"] = standing_state == "monument"

    verdict["accept"] = sig_ok and val_ok and ev_ok and cov_state != "fail"
    # The issuer-binding gap is NOT a hard reject in v0.1 (it's UNBINDABLE for
    # platform-handle issuers by design); it's surfaced so consumers can apply
    # their own policy. did:key issuers do bind.
    if not issuer_bound:
        verdict["reasons"].append(f"issuer-binding {bind_state} (advisory; see docs/binding.md / GAP-1)")
    # Monument detection (§12) is advisory too: an accepted envelope can still be
    # a monument (a conclusion no live party can contest). Surfaced, not rejected.
    if verdict["monument"]:
        verdict["reasons"].append("MONUMENT: relied-on conclusion with no live standing to contest (advisory; see docs/standing.md)")
    return verdict


def _render(verdict: dict) -> str:
    head = "ACCEPT" if verdict["accept"] else "REJECT"
    if verdict.get("monument"):
        head += "  ⚠ MONUMENT"
    lines = [head]
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
