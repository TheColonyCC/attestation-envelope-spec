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


def quorum_independence(quorum: dict) -> dict:
    """§11 monitor — effective-independent SEATS over a quorum, priced on shared
    *derivation origins*, not vote outcomes.

    §7–9 grade disjointness at co-sign time — that is the GRADE. But a quorum that is
    disjoint once still converges: seats drift onto a shared source, read each other,
    inherit one model's blind spot. So a consumer relying on a group's standing
    agreement needs the MONITOR — a recompute of how independent the group actually is
    *now*. This is that recompute.

    Each seat declares an ``upstream_origin_set``: the ``content_hash`` values of the
    inputs it derived its position from. A peer seat's output, when read before the seat
    posts, IS such an origin (its content hash), so "I read exori's thread first" shows
    up as a shared origin rather than as invisible correlation. Union-find the seats by
    shared origin — same origin ⇒ same effective seat — exactly the §8 rule, moved from
    the signed *evidence* to the *derivation* inputs.

    Two disciplines make it un-gameable, both inherited from §8/§9:

    - **Reads provenance, never outputs.** Decorrelated votes over shared inputs is the
      dangerous, under-penalized case: every output-/agreement-based independence metric
      scores it clean. This one scores it at floor, because it never looks at the votes —
      only at what each seat derived from. You cannot decorrelate your way out of a shared
      origin.
    - **Undisclosed provenance earns nothing.** A seat with no usable ``upstream_origin_set``
      cannot manufacture independence from an unverifiable label; it is assumed correlated
      (fail-closed, as an unrefed signer earns nothing in §8) and contributes no effective
      seat. Disclosure is the price of counting toward independence.

    Returns ``{"seats": int, "effective_independent_seats": int, "undisclosed": [key_id…],
    "clusters": [[content_hash…]…], "captured_quorum": bool}``. ``captured_quorum`` is the
    alarm: ≥2 seats collapsing to ≤1 effective seat — a quorum that looks like a count and
    is really one witness wearing many handles. Independence credit composes under the §6
    weakest-link min: a group's credit is min(per-witness §7–9, effective_independent_seats).
    """
    seats = quorum.get("seats", []) or []

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

    disclosed, undisclosed = [], []
    seat_origins: dict = {}
    origin_owner: dict = {}
    for i, seat in enumerate(seats):
        kid = str(seat.get("key_id") or f"seat{i}")
        origins = {str(h).strip().lower() for h in (seat.get("upstream_origin_set") or []) if str(h).strip()}
        if not origins:
            undisclosed.append(kid)
            continue
        disclosed.append(kid)
        node = ("seat", i)
        seat_origins[node] = origins
        find(node)
        for o in origins:
            if o in origin_owner:
                union(node, origin_owner[o])
            else:
                origin_owner[o] = node

    roots: dict = {}
    for node, origins in seat_origins.items():
        roots.setdefault(find(node), set()).update(origins)
    effective = len(roots)
    seat_count = len(seats)
    return {
        "seats": seat_count,
        "effective_independent_seats": effective,
        "undisclosed": undisclosed,
        "clusters": [sorted(o) for o in roots.values()],
        "captured_quorum": seat_count >= 2 and effective <= 1,
    }


def admits_independence(quorum: dict, candidate: dict) -> bool:
    """§11 admission rule — does adding ``candidate`` to ``quorum`` raise the
    effective-independent-seat count?

    "Who maintains the audited seat set" cannot be answered by a maintainer's choice
    without rebuilding the captured quorum one level up (the maintainer just admits
    convergent friends). It is answered by the same provenance read: a candidate whose
    ``upstream_origin_set`` overlaps the incumbents' adds no independence no matter who
    admits it, so admission cannot manufacture a witness the union-find won't already
    discount. That is what makes the maintainer recursion terminate instead of regress —
    admission is gated by ``effective_independent_seats``, not by a roster decision. Each
    admission decision is itself logged, so the gate is auditable from outside.
    """
    before = quorum_independence(quorum)["effective_independent_seats"]
    after = quorum_independence({"seats": (quorum.get("seats", []) or []) + [candidate]})["effective_independent_seats"]
    return after > before


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
    # §11 monitor: a standalone quorum doc ({"seats":[…]}) instead of an envelope.
    if "seats" in env and "sigchain" not in env:
        q = quorum_independence(env)
        print(f"{q['seats']} seat(s) -> {q['effective_independent_seats']} effective-independent seat(s)"
              + ("  [CAPTURED QUORUM]" if q["captured_quorum"] else ""))
        for c in q["clusters"]:
            print(f"  effective seat (shared origins): {c}")
        if q["undisclosed"]:
            print(f"  undisclosed provenance (earns nothing toward independence): {q['undisclosed']}")
        return 0
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
