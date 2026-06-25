"""Effective-independent-witness counting over an attestation envelope's sigchain.

A sigchain with N signatures is not N independent witnesses. Two signers that
re-derived their signature from the same evidence are one witness wearing two
hats, no matter how distinct their keys look — the coincident-failure problem at
the attestation layer. This module counts the witnesses that actually fail
independently, by causally-disjoint evidence.

The convergence: the envelope already carries the *wire* — content-hashed
`evidence[]` pointers and a multi-signer `sigchain` — it just doesn't bind the two
or count them. `sigchain[*].evidence_refs` (v0.1.2, optional) binds each signer to
the `evidence[]` entries it independently re-derived from; this tool applies the
counting rule from TheColonyCC/verify-before-bump (`evidence_witnesses`):

  - a signer's *origins* are the `content_hash` values of its referenced evidence;
  - union-find over signers by shared origin — same `content_hash` => same witness;
  - a signer with no `evidence_refs`, or refs only to evidence lacking a
    `content_hash`, earns NOTHING (undeclared provenance == assume correlated), so
    it cannot manufacture an independent witness from an unverifiable label.

`witnesses` is the number of distinct substantiated origin-clusters — the honest
denominator for "how independent is this attestation," which a consumer can
recompute from the envelope alone. Consumption-liveness (a disjoint challenger
re-deriving each signer's vote) is the next layer; see verify-before-bump's
challenge protocol. Pure stdlib.
"""
from __future__ import annotations
import json
import sys


def _origins(signer: dict, evidence: list) -> set:
    """The set of evidence content_hashes this signer re-derived from. An
    evidence_ref out of range, or to an entry without a content_hash, contributes
    nothing — only a fetchable, content-addressed artifact can anchor independence."""
    out = set()
    for idx in signer.get("evidence_refs", []) or []:
        if not isinstance(idx, int) or idx < 0 or idx >= len(evidence):
            continue
        ch = str(evidence[idx].get("content_hash", "") or "").strip().lower()
        if ch:
            out.add(ch)
    return out


def effective_witnesses(envelope: dict) -> dict:
    """Count effective-independent witnesses over an envelope's sigchain.

    Returns ``{"witnesses": int, "signatures": int, "anchored": [key_id…],
    "unanchored": [key_id…], "clusters": [[content_hash…]…]}`` where `unanchored`
    signers cited no usable (content-addressed) evidence and contribute nothing.
    """
    evidence = envelope.get("evidence", []) or []
    chain = envelope.get("sigchain", []) or []

    parent: dict = {}
    def find(x):
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root
    def union(a, b):
        parent[find(a)] = find(b)

    anchored, unanchored = [], []
    origin_owner: dict = {}
    sig_origins: dict = {}
    for i, signer in enumerate(chain):
        kid = str(signer.get("key_id") or f"sig{i}")
        origins = _origins(signer, evidence)
        if not origins:
            unanchored.append(kid)
            continue
        anchored.append(kid)
        sig_origins[("sig", i)] = origins
        node = ("sig", i)
        find(node)
        for o in origins:
            if o in origin_owner:
                union(node, origin_owner[o])
            else:
                origin_owner[o] = node

    roots: dict = {}
    for node, origins in sig_origins.items():
        roots.setdefault(find(node), set()).update(origins)
    return {
        "witnesses": len(roots),
        "signatures": len(chain),
        "anchored": anchored,
        "unanchored": unanchored,
        "clusters": [sorted(o) for o in roots.values()],
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python tools/independence.py <envelope.json>", file=sys.stderr)
        return 2
    env = json.loads(open(argv[0]).read())
    r = effective_witnesses(env)
    print(f"{r['signatures']} signature(s) -> {r['witnesses']} effective-independent witness(es)")
    for c in r["clusters"]:
        print(f"  witness: {c}")
    if r["unanchored"]:
        print(f"  unanchored (no content-addressed evidence, earns nothing): {r['unanchored']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
