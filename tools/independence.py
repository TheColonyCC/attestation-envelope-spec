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


def _evidence_origins(envelope: dict) -> set:
    """Every content_hash anchored in evidence[]."""
    out = set()
    for e in envelope.get("evidence", []) or []:
        ch = str(e.get("content_hash", "") or "").strip().lower()
        if ch:
            out.add(ch)
    return out


def origin_coverage(envelope: dict, fired_origins=None) -> dict:
    """§10 origin-set completeness over an envelope's committed `origin_manifest`.

    Disjointness (§8) is computed over the origins the obligor *chose* to anchor;
    cherry-picking (anchor the convenient-disjoint origins, drop the ones that reveal
    a shared upstream) is undetectable at the row level. §10 closes it by witnessing
    the denominator: a committed `origin_manifest` lists the COMPLETE origin set, so
    omission becomes visible-as-absence rather than silent.

    Returns ``{coverage_state, manifest_origins, cosigner_grade,
    steering_bounded_coverage, fired, self_missing}`` where ``coverage_state`` is:
      - ``origins_unenumerated`` — no manifest (floor); evidence[] may be a subset.
      - ``manifest_incomplete`` — an anchored evidence origin is absent from the
        committed manifest => the manifest is incomplete on its face (self-fire, void).
      - ``fired`` — a third party named (``fired_origins``) a load-bearing origin
        absent from the manifest (the fireable case: completeness isn't proven, it's
        falsifiable). Void.
      - ``origins_enumerated`` — manifest present and consistent.
    Completeness is never *proven* from inside; the manifest is a signed denominator
    anyone can fire. The co-signer carries its own selection_grade (§9 applied to the
    enumerator): coverage is steering-bounded only when enumerated AND the co-signer is
    ``beacon_drawn`` — an obligor_picked co-signer rebuilds the captured quorum a level up.
    """
    manifest = envelope.get("origin_manifest")
    ev_origins = _evidence_origins(envelope)
    fired = [str(h).strip().lower() for h in (fired_origins or []) if str(h).strip()]
    if not manifest:
        return {"coverage_state": "origins_unenumerated", "manifest_origins": 0,
                "cosigner_grade": None, "steering_bounded_coverage": False,
                "fired": [], "self_missing": []}
    declared = {str(h).strip().lower() for h in (manifest.get("origins") or []) if str(h).strip()}
    self_missing = sorted(ev_origins - declared)
    fired_hits = sorted(h for h in fired if h not in declared)
    cosigner = manifest.get("cosigner") or {}
    cosigner_grade = _selection_grade(cosigner) if cosigner.get("key_id") else None
    if self_missing:
        state = "manifest_incomplete"
    elif fired_hits:
        state = "fired"
    else:
        state = "origins_enumerated"
    return {
        "coverage_state": state,
        "manifest_origins": len(declared),
        "cosigner_grade": cosigner_grade,
        "steering_bounded_coverage": state == "origins_enumerated" and cosigner_grade == STEERING_BOUNDED,
        "fired": fired_hits,
        "self_missing": self_missing,
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python tools/independence.py <envelope.json> [--fire <content_hash>…]", file=sys.stderr)
        return 2
    fired = []
    if "--fire" in argv:
        i = argv.index("--fire")
        fired = argv[i + 1:]
        argv = argv[:i]
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
    cov = origin_coverage(env, fired_origins=fired)
    print(f"§10 origin coverage: {cov['coverage_state']}"
          + (f" (manifest: {cov['manifest_origins']} origins, co-signer {cov['cosigner_grade']},"
             f" steering-bounded={cov['steering_bounded_coverage']})" if cov['manifest_origins'] else ""))
    if cov["self_missing"]:
        print(f"  manifest incomplete — anchored evidence absent from manifest: {cov['self_missing']}")
    if cov["fired"]:
        print(f"  FIRED — named origins absent from committed manifest: {cov['fired']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
