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

# §9 selection_grade — whether the OBLIGOR got to choose the witness, weakest→strongest.
# Evidence-disjointness (§8) grades whether a witness IS independent; selection_grade
# grades whether you got to PICK it. Independence credit is min of the two: a witness
# counts only if it is BOTH evidence-disjoint AND steering-bounded, because an obligor
# that hand-picks from a pool can shop for a disjoint-looking witness. Only `beacon_drawn`
# is steering-bounded (fixed after commit, no re-roll). Absent == obligor_picked (fail closed).
SELECTION_TIERS = {"obligor_picked": 0, "public_pool_unverified": 1, "beacon_drawn": 2}
STEERING_BOUNDED = "beacon_drawn"


def _selection_grade(signer: dict) -> str:
    g = str(signer.get("selection_grade", "") or "").strip().lower()
    return g if g in SELECTION_TIERS else "obligor_picked"


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

    anchored, unanchored, steered = [], [], []
    selection_grades: dict = {}
    origin_owner: dict = {}
    sig_origins: dict = {}
    node_bounded: dict = {}   # node -> is this signer steering-bounded (beacon_drawn)
    for i, signer in enumerate(chain):
        kid = str(signer.get("key_id") or f"sig{i}")
        grade = _selection_grade(signer)
        selection_grades[kid] = grade
        origins = _origins(signer, evidence)
        if not origins:
            unanchored.append(kid)
            continue
        anchored.append(kid)
        # §9: an anchored signer that isn't steering-bounded earns nothing toward
        # the §9 count — the obligor could have shopped a disjoint-looking witness.
        if grade != STEERING_BOUNDED:
            steered.append(kid)
        sig_origins[("sig", i)] = origins
        node = ("sig", i)
        node_bounded[node] = grade == STEERING_BOUNDED
        find(node)
        for o in origins:
            if o in origin_owner:
                union(node, origin_owner[o])
            else:
                origin_owner[o] = node

    roots: dict = {}
    root_bounded: dict = {}
    for node, origins in sig_origins.items():
        r = find(node)
        roots.setdefault(r, set()).update(origins)
        root_bounded[r] = root_bounded.get(r, False) or node_bounded.get(node, False)
    # §9 count: an evidence-disjoint cluster earns independence only if at least one
    # of its signers is steering-bounded (min(selection_grade, disjointness)).
    steering_bounded_witnesses = sum(1 for r in roots if root_bounded.get(r))
    return {
        "witnesses": len(roots),
        "steering_bounded_witnesses": steering_bounded_witnesses,
        "signatures": len(chain),
        "anchored": anchored,
        "unanchored": unanchored,
        "steered": steered,
        "selection_grades": selection_grades,
        "clusters": [sorted(o) for o in roots.values()],
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python tools/independence.py <envelope.json>", file=sys.stderr)
        return 2
    env = json.loads(open(argv[0]).read())
    r = effective_witnesses(env)
    print(f"{r['signatures']} signature(s) -> {r['witnesses']} evidence-disjoint witness(es)"
          f" -> {r['steering_bounded_witnesses']} steering-bounded (§9) witness(es)")
    for c in r["clusters"]:
        print(f"  witness: {c}")
    if r["steered"]:
        print(f"  steered (anchored but not beacon_drawn, earns nothing toward §9): {r['steered']}")
    if r["unanchored"]:
        print(f"  unanchored (no content-addressed evidence, earns nothing): {r['unanchored']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
