#!/usr/bin/env python3
"""§16 — verifiable receipt ordering (per-subject prev-hash chain + per-receipt
beacon binding).

An emitter can retract a prior receipt. Order *across* beacon rounds is verifiable
by anchoring emission to a beacon (drand/OTS) — but that leaves two holes an emitter
is incentivised to exploit:

  1. Two receipts in the SAME beacon round are unordered by the beacon, so the
     emitter can reorder retract-vs-emit over one subject after the fact.
  2. A monotone counter the emitter *attests* is no fix — it just picks two counters
     (Threat #1's shape, one layer in).

The fix this checks, at the cost of a hash and a field per receipt:

  - **per-subject prev-hash chain** — each receipt over subject S carries
    `prev = id(prior receipt over S)` (null for the first). Two receipts claiming the
    SAME `prev` over S are a published contradiction: an equivocation *fork* any party
    holding both detects offline. Order becomes structural, not attested.
  - **per-receipt beacon binding** — each receipt commits its OWN `beacon_round`. The
    chain must be monotone in beacon round; a receipt whose round is <= its prev's is a
    detectable *backdate*. Per-receipt, NOT per-chain — else the emitter picks the whole
    chain's anchor and reorders the links underneath it.

TRUST BOUNDARY (the honest residual, generalising Threat #6). This makes equivocation
*fork-evident*; it does not make it *witnessed*. A fork is only caught by a party
holding BOTH conflicting receipts — a same-round equivocation is invisible to a relier
who ever saw only one. So the guarantee is "detectable by anyone holding both," not
"detected." Delivering the two to a common witness needs a gossip/publication layer the
envelope points at but cannot embody (same shape as Threat #6's append-availability).

Advisory + offline: this checks the ordering GRAPH declared across receipts (linkage,
forks, monotonicity). Recomputing each `id` from receipt content is delegated to the
`payload_hash`/JCS machinery, exactly like §12.3 delegates the OTS→Bitcoin leg.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any


def _round_key(r: Any) -> Any:
    """Comparable beacon-round value: int if it parses, else the string itself
    (drand rounds are ints; an OTS/anchor label sorts lexically)."""
    try:
        return (0, int(r))
    except (TypeError, ValueError):
        return (1, str(r))


def check_ordering(receipts: list) -> dict:
    """Fold a list of receipts into a per-subject ordering verdict.

    Each receipt: {id, subject, prev (id|null), beacon_round}. Returns per-subject
    state in {ordered, forked, backdated, broken} plus a rolled-up `state`.
    """
    by_subject: dict = defaultdict(list)
    for r in receipts:
        by_subject[r.get("subject")].append(r)

    subjects = {}
    for subject, rs in by_subject.items():
        ids = {r.get("id") for r in rs}
        notes = []
        state = "ordered"

        # (1) dangling prev — points at no receipt over this subject (self-void link)
        dangling = [r["id"] for r in rs if r.get("prev") is not None and r["prev"] not in ids]
        if dangling:
            state = "broken"
            notes.append(f"prev pointer resolves to no receipt over this subject: {dangling} (self-void link)")

        # (2) FORK — two+ receipts claim the same non-null prev (or two+ claim to be first)
        children = defaultdict(list)
        for r in rs:
            children[r.get("prev")].append(r["id"])
        forks = {p: kids for p, kids in children.items() if len(kids) > 1}
        if forks:
            state = "forked"
            for p, kids in forks.items():
                where = "the same prior receipt" if p is not None else "first-in-chain (null prev)"
                notes.append(f"equivocation fork: {kids} all claim {where} ({p!r}) — a published contradiction")

        # (3) BACKDATE — a receipt's beacon round is not strictly after its prev's
        by_id = {r["id"]: r for r in rs}
        for r in rs:
            p = r.get("prev")
            if p in by_id:
                if _round_key(r.get("beacon_round")) <= _round_key(by_id[p].get("beacon_round")):
                    if state == "ordered":
                        state = "backdated"
                    notes.append(
                        f"backdate: receipt {r['id']} claims prev {p} but beacon_round "
                        f"{r.get('beacon_round')!r} <= prev's {by_id[p].get('beacon_round')!r} "
                        "(the chain is not monotone in beacon round)")

        subjects[subject] = {
            "subject": subject,
            "receipts": len(rs),
            "state": state,
            "notes": notes,
        }

    # roll-up: worst subject state wins; ordered only if every subject is ordered
    order = {"broken": 3, "forked": 3, "backdated": 2, "ordered": 0}
    rolled = "ordered"
    for s in subjects.values():
        if order[s["state"]] > order[rolled]:
            rolled = s["state"]
    return {
        "state": rolled,
        "subjects": list(subjects.values()),
        # the residual is never suppressed: a fork is detectable, not witnessed.
        "trust_boundary": ("fork-evident, not witnessed: a fork is caught only by a party holding "
                           "BOTH receipts; delivering them to a common witness needs a gossip/"
                           "publication layer (see Threat #6 append-availability)."),
    }


def _fmt(res: dict) -> str:
    lines = [f"ORDERING: {res['state']}  ({len(res['subjects'])} subject(s))"]
    for s in res["subjects"]:
        lines.append(f"  [{s['state']:9}] subject={s['subject']!r}  ({s['receipts']} receipts)")
        for n in s["notes"]:
            lines.append(f"       - {n}")
    lines.append(f"  --\n  trust boundary: {res['trust_boundary']}")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: ordering.py <envelope-or-receipt-list.json>", file=sys.stderr)
        sys.exit(2)
    doc = json.loads(open(sys.argv[1]).read())
    receipts = doc.get("receipts", doc) if isinstance(doc, dict) else doc
    res = check_ordering(receipts)
    print(_fmt(res))
    # advisory: forks/backdates/broken links are surfaced, never a hard exit-nonzero here
    sys.exit(0)


if __name__ == "__main__":
    main()
