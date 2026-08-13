"""§18b (RFC) — portable divergence: making a split re-checkable by a stranger, offline.

The problem this solves
-----------------------
§18 (reconcile_independence.py) can *refute* declared independence from observed co-movement,
but the evidence is not portable: a divergence ledger is condition-indexed and lives with
whoever did the observing. A verifier holding one envelope, offline, cannot re-check someone
else's ledger. Signing the ledger does not help — a signed ledger is a *declaration*, and its
completeness is unattestable (§17 again, third time). So decorrelation looked like a local
trust topology and never an attestation.

The observation that fixes it
-----------------------------
Look at the shape of an observed divergence: **"A failed, B answered."**

- "B answered"  is a POSITIVE — B emitted an artifact. Portable.
- "A did not answer" is a NEGATIVE — and **you cannot sign a negative**.

The non-portability is not a property of *divergence*. It is a property of *silence*. So stop
measuring divergence as a difference in **failure**, and measure it as a disagreement between
signed **positives**:

    A portable divergence is a FORK: two parties returning DIFFERENT signed answers to the
    SAME beacon-selected challenge.

This is exactly §16's primitive with the polarity reversed. There, a fork convicts an emitter
of equivocation. Here, a fork certifies that two signers are not one machine. In both cases it
is, in §16's words, *"a fact, not a claim"* — any party holding both halves detects it offline,
with no observer, no ledger, and no trust in whoever was watching.

What it costs the adversary (the load-bearing part)
---------------------------------------------------
A captured quorum — one operator, N personas — wants `k` high, so it wants divergences. It
cannot forge one: it would have to produce two validly-signed *different* answers. It can only
**actually disagree**. And on a challenge with a settleable ground truth, disagreement means at
least one persona is **wrong, signed, on the record, permanently**.

    Independence is not free. It is PAID FOR IN CORRECTNESS.

akistorito's insight was that staging an availability divergence costs a real outage. This is
the correctness-axis twin: staging a *correctness* divergence costs a real error. Every split a
quorum shows you is a signed error by at least one of its members, and `error_cost` prices it.
A quorum whose independence rests entirely on being wrong a lot is telling you something.

What it does NOT do
-------------------
- **It still does not confirm independence.** §18's asymmetry survives intact: two parties can
  disagree on the probe and agree on the thing that matters. A fork *splits a pair*; it never
  certifies the quorum. Correlation refutes; divergence — even portable divergence — does not
  confirm.
- Same signed answer ⇒ **no information**, not correlation. Two independent correct oracles
  agree. Agreement earns nothing; it also refutes nothing.
- Anti-Potemkin is mandatory (§11 req. 2 / §9 `beacon_drawn`): the challenge MUST be derived
  from a beacon fixed AFTER the responses commit, or a colluding quorum pre-computes a
  disagreement it does not have. `challenge_index` is recomputed here, never trusted.
- A fork proves distinct *derivation*, not distinct *control*. One operator running two genuinely
  different stacks does earn substrate-decorrelation — which is what this axis was ever about.
"""
from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import sys

import base58
import nacl.exceptions
import nacl.signing

DOMAIN = "touchstone.portable-divergence/1"


def jcs(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def challenge_index(beacon_round, probe_set_hash: str, probe_count: int) -> int:
    """Recomputable, un-grindable challenge selection (§9 `beacon_drawn`).

    The issuer does not get to choose which probe is scored: it is a pure function of a public
    beacon fixed AFTER commit. A verifier recomputes this rather than trusting the declared
    index — a declared index is a label, and this spec does not count labels.
    """
    if probe_count <= 0:
        raise ValueError("probe_count must be positive")
    digest = hashlib.sha256(jcs({"domain": DOMAIN, "beacon_round": beacon_round,
                                 "probe_set_hash": probe_set_hash})).digest()
    return int.from_bytes(digest, "big") % probe_count


def signed_message(cert: dict, answer_hash: str) -> bytes:
    """The bytes each responder signs. Domain-separated and bound to the drawn challenge, so a
    signature cannot be replayed onto a different challenge, beacon round, or probe set."""
    return jcs({
        "domain": DOMAIN,
        "beacon_round": cert.get("beacon_round"),
        "probe_set_hash": cert.get("probe_set_hash"),
        "challenge_index": cert.get("challenge_index"),
        "answer_hash": answer_hash,
    })


def _verify(did: str, sig_b64u: str, msg: bytes) -> tuple[bool, str]:
    if not isinstance(did, str) or not did.startswith("did:key:z"):
        return False, "did is not a did:key:z…"
    try:
        raw = base58.b58decode(did[len("did:key:z"):])
    except Exception:
        return False, "did multibase is not valid base58btc"
    if len(raw) != 34 or raw[:2] != b"\xed\x01":
        return False, "did:key is not an ed25519 multicodec key"
    try:
        nacl.signing.VerifyKey(raw[2:]).verify(msg, _b64url_decode(sig_b64u))
    except (nacl.exceptions.BadSignatureError, ValueError, TypeError):
        return False, "signature does not verify over the drawn challenge"
    return True, ""


def check_portable_divergence(cert: dict) -> dict:
    """Verify one divergence certificate offline. No observer, no ledger, no trust.

    Returns {state, splits, clusters, error_cost, rejected, notes}. `splits` are the pairs the
    stranger may treat as NOT one failure domain; everything else stays merged (default
    pessimism — absence of a fork is not evidence of separation).
    """
    out = {"state": "no-divergence", "splits": [], "clusters": [], "error_cost": None,
           "rejected": [], "notes": []}

    if cert.get("domain") != DOMAIN:
        return {**out, "state": "unsupported",
                "notes": [f"domain must be {DOMAIN!r}"]}

    probe_set_hash = cert.get("probe_set_hash")
    probe_count = cert.get("probe_count")
    declared_index = cert.get("challenge_index")
    if not probe_set_hash or not isinstance(probe_count, int):
        return {**out, "state": "unsupported",
                "notes": ["probe_set_hash and probe_count are required (the battery must be pinned)"]}

    # Anti-grinding: RECOMPUTE the drawn challenge. Never trust the declared index.
    try:
        expected = challenge_index(cert.get("beacon_round"), probe_set_hash, probe_count)
    except ValueError as e:
        return {**out, "state": "unsupported", "notes": [str(e)]}
    if declared_index != expected:
        return {**out, "state": "invalid",
                "notes": [f"challenge_index {declared_index} is not f(beacon) = {expected} — "
                          "the issuer chose the probe (grinding); certificate rejected"]}

    # Verify every response. An unsigned or mis-signed answer earns nothing.
    valid = []
    for i, r in enumerate(cert.get("responses", []) or []):
        did, ah, sig = r.get("did"), r.get("answer_hash"), r.get("sig")
        label = did or f"response[{i}]"
        if not ah:
            out["rejected"].append({"responder": label, "reason": "no answer_hash — silence is not a positive"})
            continue
        ok, why = _verify(did, sig or "", signed_message(cert, ah))
        if not ok:
            out["rejected"].append({"responder": label, "reason": why})
            continue
        valid.append({"did": did, "answer_hash": ah})

    if len(valid) < 2:
        out["notes"].append("fewer than two validly-signed answers — nothing to compare")
        return out

    # A FORK is two valid signatures over DIFFERENT answers to the same drawn challenge.
    # Same answer => NO INFORMATION (two independent correct oracles agree). Not correlation.
    splits = []
    for i in range(len(valid)):
        for j in range(i + 1, len(valid)):
            if valid[i]["answer_hash"] != valid[j]["answer_hash"]:
                splits.append(sorted([valid[i]["did"], valid[j]["did"]]))

    # Clusters: parties are merged by default; only a fork splits a pair.
    by_answer: dict = {}
    for v in valid:
        by_answer.setdefault(v["answer_hash"], []).append(v["did"])
    out["clusters"] = [sorted(v) for v in by_answer.values()]
    out["splits"] = sorted(splits)
    out["state"] = "diverged" if splits else "no-divergence"

    # The price. A fork means at least one signer is WRONG — signed, on the record.
    gt = cert.get("ground_truth")
    if gt:
        wrong = [v["did"] for v in valid if v["answer_hash"] != gt]
        out["error_cost"] = len(wrong)
        out["notes"].append(
            f"{len(wrong)} of {len(valid)} signers were WRONG against the settled ground truth — "
            "this is the price of the split: independence is paid for in correctness")
    else:
        out["notes"].append("no ground_truth: the split is portable but UNPRICED — a stranger "
                            "cannot yet see who paid for it")

    out["notes"].append("a fork splits a pair; it never confirms the quorum "
                        "(correlation refutes, divergence does not confirm)")
    return out


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python tools/portable_divergence.py <certificate.json>", file=sys.stderr)
        return 2
    doc = json.loads(pathlib.Path(argv[0]).read_text())
    print(json.dumps(check_portable_divergence(doc.get("divergence_certificate", doc)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
