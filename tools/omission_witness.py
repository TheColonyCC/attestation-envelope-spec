"""§17 — Operator-disjoint omission witness.

[§12.3 externally-anchored standing](../docs/standing.md) makes *"no contest was
filed"* checkable by anchoring the contest channel. But the anchored
absence-of-contest is only as trustworthy as the party that decides whether a
contest can be **recorded** ([Threat #6](../docs/threat-model.md)): if every
recorder or co-signer the issuer can reach shares the issuer's **operator**,
absence is self-attested — the independence of the omission leg is 1, no matter
how many co-signers stack. This is the residual that both `standing.md` §12.3 and
`watcher-assignment.md` flag as *"needs an independently-operated recorder … a
governance property the envelope points at but can't enforce."*

This module makes the *degree* of that independence a computed number rather than
an assertion. An operator-disjoint **witness** co-signs the omission leg: it signs
the `(subject, bound_commitment, beacon_round)` tuple under its own `did:key`, from
a distinct operator / control domain. `independence_k` = the number of
operator-disjoint signers over the leg (the issuer, plus each witness whose
operator the issuer does not control). A witness sharing the issuer's operator adds
**nothing** — it is capture wearing another hat, the control-axis analogue of
`independence.py`'s shared-origin rule. `k == 1` is self-attested (monument-grade
for the omission upper bound); `k >= 2` means at least one witness outside the
issuer's blast radius co-signed the same tuple.

The signed object is **domain-separated** so a witness signature can't be lifted
onto another leg or claim:

    sig = Ed25519( jcs({domain, subject, bound_commitment, beacon_round}) )
    domain == "touchstone.omission-witness/1"

Advisory and offline, like the rest of §12.

**Trust boundary** (stated in-module, because a check is only worth what it costs
the checked party to fake): this proves each witness signature is valid over *this*
leg and counts operator-disjoint witnesses. It does **not** prove a witness
actually observed the entry out of band (that is the witness's own attestation),
nor does it close append-refusal at a recorder no witness reached. It lowers
*"absence is self-attested"* to *"absence is co-attested by k operator-disjoint
parties"* — fork-evident across operators, not omniscient. Fail-closed throughout:
an undeclared operator (issuer's or a witness's) is assumed correlated, never
independent. Pure verifier over the leg + `did:key` signatures.
"""
from __future__ import annotations

import base64
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from verify import jcs, did_key_to_pubkey  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: E402

DOMAIN = "touchstone.omission-witness/1"


def _b64url_decode(s: str) -> bytes:
    s = str(s)
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def signed_message(leg: dict) -> bytes:
    """The exact bytes a witness signs: JCS over the domain-separated tuple.

    JCS sorts keys, so the field order the emitter used is irrelevant — the four
    fields canonicalise to one byte-string every party re-derives identically.
    """
    return jcs(
        {
            "domain": DOMAIN,
            "subject": leg.get("subject"),
            "bound_commitment": leg.get("bound_commitment"),
            "beacon_round": leg.get("beacon_round"),
        }
    )


def _verify_witness_sig(did: str, sig_b64u: str, message: bytes) -> tuple[bool, str]:
    try:
        pub = did_key_to_pubkey(did)
    except Exception as exc:
        return False, f"unresolvable ed25519 did:key: {exc}"
    try:
        key = Ed25519PublicKey.from_public_bytes(pub)
    except Exception:
        return False, "malformed ed25519 public key"
    try:
        raw = _b64url_decode(sig_b64u)
    except Exception:
        return False, "signature is not base64url"
    try:
        key.verify(raw, message)
    except Exception:
        return False, "signature does not verify over this leg"
    return True, "ok"


def check_omission_witness(leg: dict) -> dict:
    """Verify an omission-witness leg and return its operator-disjoint witness count.

    Returns ``{state, independence_k, grade, valid_witnesses, rejected, notes}``:
      - state: ``co-attested`` (k>=2) / ``self-attested`` (k==1) / ``unsupported``.
      - independence_k: distinct operators co-signing the leg, issuer included.
      - grade: ``named`` (k>=2, a keyed non-issuer witness) / ``self`` (k==1).
    """
    notes: list[str] = []
    if not isinstance(leg, dict):
        return {"state": "unsupported", "independence_k": 0, "grade": "self",
                "valid_witnesses": [], "rejected": [], "notes": ["leg is not an object"]}

    if leg.get("domain") != DOMAIN:
        return {"state": "unsupported", "independence_k": 0, "grade": "self",
                "valid_witnesses": [], "rejected": [],
                "notes": [f"domain is not {DOMAIN!r} — refusing to interpret as an omission-witness leg"]}

    issuer_op = str(leg.get("issuer_operator", "") or "").strip()
    message = signed_message(leg)

    valid_witnesses: list[dict] = []
    rejected: list[dict] = []
    # Operators that co-sign, issuer included. The issuer seeds the k==1 baseline.
    operators: set[str] = set()
    operators.add(issuer_op or "__issuer_undeclared__")

    for w in leg.get("witnesses", []) or []:
        did = str(w.get("did", "") or "")
        op = str(w.get("operator", "") or "").strip()
        sig = w.get("sig", "")
        ok, reason = _verify_witness_sig(did, sig, message)
        if not ok:
            rejected.append({"did": did, "reason": reason})
            continue
        if not op:
            # Undeclared operator == assume correlated (fail closed) — can't credit
            # independence to a witness whose control domain isn't named.
            rejected.append({"did": did, "reason": "operator undeclared (fail-closed: assumed issuer-controlled)"})
            continue
        if issuer_op and op == issuer_op:
            rejected.append({"did": did, "reason": "shares the issuer's operator — capture wearing another hat, adds 0"})
            continue
        valid_witnesses.append({"did": did, "operator": op})
        operators.add(op)

    if not issuer_op:
        # Without the issuer's own operator we cannot certify that any witness is
        # actually disjoint from it — cap at self and say so, rather than credit
        # unverifiable independence.
        notes.append("issuer_operator undeclared — cannot certify witness disjointness; capped at self-attested")
        k = 1
    else:
        k = len(operators)

    state = "co-attested" if k >= 2 else "self-attested"
    grade = "named" if k >= 2 else "self"
    if state == "self-attested":
        notes.append("omission leg is self-attested (k=1): absence-of-contest carries no meaningful upper bound — monument-grade for standing")
    return {
        "state": state,
        "independence_k": k,
        "grade": grade,
        "valid_witnesses": valid_witnesses,
        "rejected": rejected,
        "notes": notes,
    }


if __name__ == "__main__":  # pragma: no cover
    doc = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else json.load(sys.stdin)
    leg = doc.get("omission_witness", doc.get("standing", {}).get("omission_witness", doc))
    res = check_omission_witness(leg)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["state"] != "unsupported" else 2)
