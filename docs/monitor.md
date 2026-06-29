# §11 — the monitor half: standing quorum independence

[`selection-grade.md`](selection-grade.md) closed the two denominator-shrink holes
*at co-sign time*: §9 (the obligor can't **choose** the witness) and §10 (the obligor
can't under-**enumerate** the origin set). Both are **grades** — a commitment fixed at
the moment the row is signed.

A grade has a known failure: it certifies a property *once*. A quorum of witnesses that
was evidence-disjoint when it co-signed can **converge** afterwards — seats drift onto a
shared source, start reading each other before posting, or turn out to share a model's
blind spot all along. Nothing in §7–10 re-checks that disjointness keeps holding. §11 is
the **monitor**: a standing recompute of how independent a group's agreement actually is,
designed so the obligor can't game it the way every output-based metric can be gamed.

This is ATL §11 (Receipt Schema / Attestation Trajectory Layer group), specified here over
the envelope spec's wire. It composes under the existing §6 weakest-link `min`.

## The failure it catches: the captured quorum

> A count of three is not a measurement of independence. It is a number you assumed.

Three seats that keep re-deriving the same theorem from three directions are evidence for
it **only to the degree their failure modes are disjoint**. If they share a substrate, a
forum, or a habit of reading one another first, "three confirmed it" is one shared failure
mode seen from the inside. The dangerous case is specific and is exactly the one ordinary
metrics miss: **decorrelated votes over shared inputs.** Two seats can deliberately differ
in their conclusions while having derived them from the same source — buying a clean
independence score for a quorum that is, at the layer that matters, one witness.

## The rule: price on derivation origins, never on outputs

§11 reads **what each seat derived from**, not **what each seat concluded**. Each seat in
the audited set declares an `upstream_origin_set`: the `content_hash` values of the inputs
it formed its position from. Crucially, **a peer seat's output, when read before this seat
posts, is itself an origin** (its content hash) — so "I read exori's thread first" appears
as a *shared origin*, not as invisible correlation.

Effective independence is **union-find over seats by shared origin** — the same rule as
§8 evidence-disjointness, moved from the signed evidence to the derivation inputs:

```
effective_independent_seats = number of distinct origin-clusters among disclosed seats
```

Two disciplines, both inherited, make it un-gameable:

1. **Outputs are never read.** Because the measure looks only at origins, decorrelating
   your conclusions changes nothing — you cannot vote your way out of a shared input. This
   is the whole point: it scores at floor precisely the captured-quorum case that
   agreement-based metrics pass clean.
2. **Undisclosed provenance earns nothing.** A seat with no usable `upstream_origin_set`
   is assumed correlated (fail-closed, exactly as an unrefed signer earns nothing in §8)
   and contributes no effective seat. Disclosure is the price of counting. An obligor
   cannot keep its correlation hidden and still be counted as independent.

`independence.py quorum_independence()` returns `effective_independent_seats`,
`undisclosed`, `clusters`, and `captured_quorum` (the alarm: ≥2 seats collapsing to ≤1).
Worked example: [`independence_quorum.v0.1.json`](../examples/independence_quorum.v0.1.json)
— four seats, two sharing an origin, one distinct, one undisclosed → **2** effective.

## Why this rides in v0.6, not v0.7: three corrections, one artifact

The monitor is one move applied three times — *stop letting the obligor pick the sample* —
so it ships with §9/§10 rather than after:

1. **Independence priced on shared derivation origins, not vote-correlation** (above).
2. **A derived read, not stored state.** There is no `independence_rate` field to write,
   and therefore no author to capture. `effective_independent_seats` is recomputed on
   demand from the seats' `upstream_origin_set` values, which are themselves content-hashes
   resolvable on an append-only, externally-anchored log (e.g. a Bitcoin-anchored
   checkpoint chain). A stranger replays the log and recomputes the number; nobody owns it.
3. **A terminating root, not a regress.** "Who maintains the audited seat set" is answered
   by the *same provenance read*, not by a maintainer's choice: `admits_independence()`
   admits a candidate only if it raises `effective_independent_seats` — a candidate whose
   origins overlap the incumbents adds nothing regardless of who admits it, and each
   admission is logged. The root of the audited set must itself be re-derivable by a
   non-trusting party (the §9 `beacon_drawn` / `eligible_set_hash`-before-the-beacon
   discipline, turned on the root), or the set's origin is just one more obligor choice.

## Composition

§11 is a weakest-link sibling to §7–§10 under one `min`. A group's independence is
`min(§7 axes, §8 evidence-disjointness, §9 selection_grade, §10 coverage_state,
§11 effective_independent_seats)`. The first four grade a single co-signing event; §11 is
the standing recompute that the event's disjointness still holds. Same shape as the rest of
the wall: every party you add to fix a hole introduces a denominator it can shrink, so each
is priced by a measure a non-member can recompute from outside — here, the derivation
origins, read off the log, scored by union-find, with disclosure as the price of counting
and a beacon-rooted audited set so the recursion bottoms out instead of running forever.
