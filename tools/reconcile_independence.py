"""§18 (RFC) — reconciling *declared* independence (§8/§11) against *observed* co-movement.

The gap this closes
-------------------
§11 (`quorum_independence`) prices independence on disjoint **derivation origins** and
refuses to look at outputs, for a good reason: *decorrelated votes over shared inputs*
is the dangerous case, and every output-based metric scores it clean. You cannot
decorrelate your way out of a shared origin.

But §11's `upstream_origin_set` is **declared by the seat**. §11 is fail-closed on
*undisclosed* provenance and wide open to *under-disclosed* provenance: a seat that read
its peer's output and then declares a disjoint origin set is invisible to the union-find.
That is the spec's own omission problem (§17), relocated to derivation — **nobody can sign
"these are all the inputs I used."** Origin-set completeness is an unattestable negative.

The reconciliation
------------------
Observed behaviour is the falsifier for the declaration:

    Observed correlation REFUTES declared independence.
    Observed divergence does NOT confirm it.

The asymmetry is the whole point, and it is why this module never returns "confirmed":

- Two seats that declare disjoint origins and then **fail together, always**, across
  enough observation, were not two seats. Some origin was under-declared, or they share a
  substrate. The declaration is refuted — and, unlike a silent correlation, it is now an
  *attributable false statement* bound to a key.
- Two seats that diverge have shown only that they are not *perfectly* coupled. §11's
  argument still stands: they may be decorrelating outputs over a shared input. A split is
  a **floor with a date on it**, never a certificate.

Hence three counts, not one:

- ``k_declared``  — §11's `effective_independent_seats`. A hypothesis. Forgeable.
- ``k_unrefuted`` — after merging pairs whose co-movement refutes their declaration.
- ``k_floor``     — additionally merging pairs we have **not observed enough to refute**.
  Pessimistic default, after the "one failure domain until a divergence splits it" rule:
  absence of observation is not evidence of separation.

``gap = k_declared - k_floor`` is a **capture signal**: seats that asserted separation and
whose separation the world has never once corroborated.

Temporal discipline: **merges are instant, splits are provisional.** A pair that diverged
long ago but has co-moved throughout the recent window is re-merged — you never weigh fresh
correlation against a stale divergence. `recent_window` is that horizon, in epochs.

Honest limits (do not paper over these):
- Availability co-movement is cheap to observe and cheap-ish to *stage in reverse* only by
  taking a real outage — that asymmetry is what gives divergence any weight at all.
  Correctness co-movement is NOT free; it needs the §11 probe battery
  (`docs/decorrelation-witness.md`). This module scores the availability axis only.
- **The evidence is not portable.** A divergence ledger is condition-indexed and lives with
  whoever did the observing. A verifier holding one envelope, offline, cannot re-check
  someone else's ledger. See docs/independence-reconciliation.md "Open problem".
"""
from __future__ import annotations

import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from independence import quorum_independence  # noqa: E402

# An observation epoch records, per seat key_id, whether it FAILED (True) or answered (False).
# Seats absent from an epoch are simply unobserved in it.


def _pairs(keys: list) -> list:
    return [(keys[i], keys[j]) for i in range(len(keys)) for j in range(i + 1, len(keys))]


def _declared_cluster_of(quorum: dict) -> dict:
    """Map key_id -> declared cluster index, using §11's union-find over origins."""
    seats = quorum.get("seats", []) or []
    origin_owner: dict = {}
    cluster: dict = {}
    nxt = 0
    for i, seat in enumerate(seats):
        kid = str(seat.get("key_id") or f"seat{i}")
        origins = {str(h).strip().lower() for h in (seat.get("upstream_origin_set") or []) if str(h).strip()}
        if not origins:
            continue  # undisclosed: §11 already gives it zero; it cannot be a declared-disjoint party
        hit = next((origin_owner[o] for o in origins if o in origin_owner), None)
        if hit is None:
            hit = nxt
            nxt += 1
        cluster[kid] = hit
        for o in origins:
            origin_owner.setdefault(o, hit)
    return cluster


def _covectors(observations: list, a: str, b: str, recent_window: int | None):
    """Epochs where BOTH seats were observed -> (n_common, n_differential)."""
    obs = sorted(observations, key=lambda e: e.get("epoch", 0))
    if recent_window is not None:
        obs = obs[-recent_window:]
    n_common = n_diff = 0
    for e in obs:
        o = e.get("outcome", {}) or {}
        if a in o and b in o:
            n_common += 1
            if bool(o[a]) != bool(o[b]):
                n_diff += 1
    return n_common, n_diff


def reconcile(quorum: dict, observations: list | None = None, min_epochs: int = 3,
              recent_window: int | None = None) -> dict:
    """Reconcile §11's declared independence against observed co-movement.

    `observations`: [{"epoch": int, "outcome": {key_id: failed_bool, ...}}, ...]
    `min_epochs`:   common epochs required before a pair is even *refutable*.
    `recent_window`: only the last N epochs count — merges are instant, splits provisional.

    Returns k_declared / k_unrefuted / k_floor / gap / per-pair verdicts. Never "confirmed".
    """
    observations = observations or []
    base = quorum_independence(quorum)
    k_declared = base["effective_independent_seats"]

    cluster = _declared_cluster_of(quorum)
    keys = sorted(cluster)

    # Union-find over the DECLARED clusters; we only ever merge, never split.
    parent: dict = {c: c for c in set(cluster.values())}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    verdicts = []
    refuted_merges, unobserved_merges = [], []
    for a, b in _pairs(keys):
        if cluster[a] == cluster[b]:
            continue  # §11 already merged them; nothing declared to refute
        n, d = _covectors(observations, a, b, recent_window)
        if n < min_epochs:
            v = "unobserved"          # cannot refute — and MUST NOT credit
            unobserved_merges.append([a, b])
        elif d == 0:
            v = "refuted"             # declared disjoint; never once diverged => one domain
            refuted_merges.append([a, b])
        else:
            v = "unrefuted"           # a dated split. A floor, not a certificate.
        verdicts.append({"pair": [a, b], "verdict": v, "common_epochs": n, "differential_failures": d})

    # k_unrefuted: merge only the pairs the world actively contradicted.
    for a, b in refuted_merges:
        union(cluster[a], cluster[b])
    k_unrefuted = len({find(c) for c in parent})

    # k_floor: additionally merge pairs we simply have not watched long enough to refute.
    # "One failure domain until an observed divergence splits it" — absence of observation
    # is not evidence of separation.
    for a, b in unobserved_merges:
        union(cluster[a], cluster[b])
    k_floor = len({find(c) for c in parent})

    return {
        "k_declared": k_declared,
        "k_unrefuted": k_unrefuted,
        "k_floor": k_floor,
        "gap": k_declared - k_floor,
        "captured": k_declared >= 2 and k_floor <= 1,
        "verdicts": verdicts,
        "undisclosed": base.get("undisclosed", []),
        "notes": [
            "correlation refutes; divergence does not confirm — no 'confirmed' state exists",
            "k_floor treats unobserved pairs as one domain (absence of observation != separation)",
            "availability axis only; correctness co-movement needs the §11 probe battery",
        ],
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python tools/reconcile_independence.py <doc.json>", file=sys.stderr)
        print("  doc: {quorum: {seats:[...]}, observations: [{epoch, outcome:{key_id: failed}}]}", file=sys.stderr)
        return 2
    doc = json.loads(pathlib.Path(argv[0]).read_text())
    res = reconcile(doc.get("quorum", {}), doc.get("observations", []),
                    min_epochs=doc.get("min_epochs", 3),
                    recent_window=doc.get("recent_window"))
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
