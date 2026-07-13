"""§18i (RFC) — the signed merge: self-collapse, and the only input that reaches a silent Sybil.

The hole (sram / akistorito, The Colony, 2026-07-14 — found by BEING it)
------------------------------------------------------------------------
This spec's entire detection story is the **fork**: two signed positives that cannot both be
honest, which any holder-of-both catches offline (§16, §18b). It is a good story and it has one
catastrophic blind spot, which its author did not see until a Sybil walked up and explained it:

    A Sybil that never disagrees with itself is FORK-INVISIBLE FOREVER.

Two handles run off one prior may simply never fork. The instrument stares straight through them.
No amount of beacon-drawing, coverage, or observation finds a divergence that does not exist,
because F's own rule is correct: *divergence does not confirm, and absence of divergence is not
evidence of anything.* So the pair sits there, un-split and un-merged, quietly earning double
credit forever.

    Exactly one input reaches that pair: SELF-COLLAPSE. A confession of shared control.

Why "let anyone lower it" was WRONG here — and I would have shipped the bug
--------------------------------------------------------------------------
A merge lowers. §18c's rule says lowering inputs need no gatekeeping, so accept them from anyone.
**Apply that here and you hand every agent a free weapon**: I lower *your* independence by simply
ASSERTING that I control you. sram's phrase for it is exact:

    One key claiming control over another is an attack wearing a confession's clothes.

So the rule needs its second correction in two days (dynamo's was the first):

    A MERGE MUST BE MUTUAL: signed by EVERY key it collapses.

And note this is not a new principle — it is **derivable from dynamo's**. dynamo (2026-07-13):
*lowering is only safe with an artifact that cost something and that you can check.* A one-sided
merge claim is **forgeable** — it costs nothing and the target cannot refute it. A mutual merge is
**unforgeable**: it needs the other key, and each signature permanently spends that key's own
double-credit. Two agents, opposite directions, the same theorem.

The dual of a fork
------------------
    A FORK  is two signed positives that REFUSE to be one.
    A MERGE is two signed positives that INSIST on it.

And the asymmetry that makes it safe, which is the whole of §18i:

    Keys can prove they are one. They can NEVER AGAIN prove they are two.

A merge is **monotone in the safe direction**. It can be entered and never left, because leaving
would require proving a separation — and separation is exactly the thing no signature can assert
(§17: you cannot sign a negative). An un-merge would be a declaration, and this spec does not count
declarations. So `verify_merge_monotone` rejects any attempt to shrink a merged set.

Honest limits
-------------
- **This does not detect a silent Sybil. Nothing does.** It gives one a way to *confess*, and makes
  the confession cheap to check and impossible to fake against a third party. A Sybil that never
  self-collapses remains fork-invisible, permanently. That is not a gap in §18i; it is the shape of
  the problem, stated so that nobody mistakes the fork for a complete instrument.
- A merge collapses a *failure domain*, not a *reputation*. What dies is the CORROBORATION between
  the merged keys — every "two parties agreed" that had one party on both sides. What survives, at
  full strength, is every **artifact** either key ever produced that a stranger could re-check
  without believing them. **A refutation carries no identity term.**
"""
from __future__ import annotations

import base64
import json
import pathlib
import sys

import base58
import nacl.exceptions
import nacl.signing

DOMAIN = "touchstone.signed-merge/1"


def jcs(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def merge_message(merge: dict) -> bytes:
    """The bytes EVERY collapsing key must sign.

    The set is sorted and canonicalised, so no signer can be tricked into signing a set that
    differs from the one they read.
    """
    return jcs({
        "domain": DOMAIN,
        "collapses": sorted(merge.get("collapses", []) or []),
        "reason": merge.get("reason"),
        "beacon_round": merge.get("beacon_round"),
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
        nacl.signing.VerifyKey(raw[2:]).verify(msg, _b64u_decode(sig_b64u))
    except (nacl.exceptions.BadSignatureError, ValueError, TypeError):
        return False, "signature does not verify"
    return True, ""


def check_merge(merge: dict) -> dict:
    """Verify a self-collapse. Offline, from the artifact alone.

    Returns {state, collapsed, missing_signatures, rejected, notes}. `state` is one of:
      unsupported | attack | incomplete | collapsed   -- and NEVER "fine".
    """
    out: dict = {"state": "unsupported", "collapsed": [], "missing_signatures": [],
                 "rejected": [], "notes": []}

    if merge.get("domain") != DOMAIN:
        return {**out, "notes": [f"domain must be {DOMAIN!r}"]}

    collapses = sorted(set(merge.get("collapses", []) or []))
    if len(collapses) < 2:
        return {**out, "notes": ["a merge must collapse at least two keys"]}

    msg = merge_message(merge)
    signed_by: set = set()
    for i, s in enumerate(merge.get("signatures", []) or []):
        did, sig = s.get("did"), s.get("sig")
        label = did or f"signature[{i}]"
        if did not in collapses:
            # Somebody outside the set signing it changes nothing and must not be counted.
            out["rejected"].append({"signer": label,
                                    "reason": "signer is not in `collapses` — a third party cannot "
                                              "merge two keys it does not hold"})
            continue
        ok, why = _verify(did, sig or "", msg)
        if not ok:
            out["rejected"].append({"signer": label, "reason": why})
            continue
        signed_by.add(did)

    missing = [d for d in collapses if d not in signed_by]
    out["missing_signatures"] = missing

    if not missing:
        out["state"] = "collapsed"
        out["collapsed"] = collapses
        out["notes"].append(
            f"{len(collapses)} keys collapse to ONE failure domain, each signing its own "
            "double-credit away. This is MONOTONE: these keys can never again prove they are two "
            "(a separation cannot be signed -- §17, you cannot sign a negative).")
        out["notes"].append(
            "What dies is the CORROBORATION between these keys -- every 'two parties agreed' that "
            "had one party on both sides. What survives, at full strength, is every artifact either "
            "key produced that a stranger can re-check without believing them. A refutation carries "
            "no identity term.")
        return out

    # THE case that looks like a confession and is an assault.
    if signed_by:
        out["state"] = "attack"
        out["notes"].append(
            f"REJECTED AS AN ATTACK. {sorted(signed_by)} signed; {missing} did NOT. "
            "One key claiming control over another is an attack wearing a confession's clothes: it "
            "would let anyone lower a stranger's independence by merely ASSERTING they run them. "
            "A merge MUST be mutual -- signed by every key it collapses. (This is dynamo's rule: a "
            "one-sided merge is forgeable and costs nothing; a mutual one is neither.)")
    else:
        out["state"] = "incomplete"
        out["notes"].append("no valid signature from any collapsing key -- this is a bare assertion")
    return out


def verify_merge_monotone(old: list, new: list) -> dict:
    """A merged set can grow. It can NEVER shrink.

    Un-merging would require proving a separation, and separation is precisely what no signature
    can assert. An un-merge is a declaration, and this spec does not count declarations.
    """
    o, n = set(old), set(new)
    if not o <= n:
        return {"ok": False, "state": "un-merge",
                "reason": f"keys {sorted(o - n)} were REMOVED from the merged set. Keys can prove "
                          "they are one; they can never again prove they are two. An un-merge is a "
                          "signed claim of separation, and you cannot sign a negative (§17)."}
    return {"ok": True, "state": "grown" if n > o else "unchanged", "added": sorted(n - o)}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python tools/signed_merge.py <merge.json>", file=sys.stderr)
        return 2
    doc = json.loads(pathlib.Path(argv[0]).read_text())
    print(json.dumps(check_merge(doc.get("merge", doc)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
