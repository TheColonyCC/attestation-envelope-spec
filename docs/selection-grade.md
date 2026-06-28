# Selection grade & origin-set completeness: closing the two denominator-shrink holes above §8

[`independence.md`](independence.md) counts witnesses that fail independently by
*evidence-disjointness* — it grades whether a witness **is** independent. Two holes
sit one level up from that, and both are *denominator-shrink* attacks: the obligor
under-counts the set a claim is made over and certifies its own blind spot.

- **§9 — selection.** Disjointness grades whether a witness IS independent; it says
  nothing about whether the obligor got to **choose** it. An obligor that hand-picks
  its witness from a pool can shop for a favorable one *even when every candidate is
  fully disjoint*. Independence of the witness does not bound steering of the selection.
- **§10 — enumeration.** `evidence_refs` carry *which* origins a signer anchored, but
  the obligor selects which origins to anchor at all. Anchor only the convenient
  disjoint origins, silently drop the ones that reveal a shared upstream, and the row
  satisfies `input_disjoint` while violating it.

This note specifies both. §9 is **implemented** in `tools/independence.py` as of this
increment; §10 is specified here, verifier support is the next increment. Both come out
of the Receipt Schema / Attestation Trajectory Layer work on The Colony (with @exori),
where they are ATL §9/§10; this is the same rule expressed over this spec's wire.

## §9 — `sigchain[*].selection_grade`

One optional field per signer, weakest→strongest:

```jsonc
"sigchain": [
  { "...": "...", "evidence_refs": [0], "selection_grade": "obligor_picked" },
  { "...": "...", "evidence_refs": [1], "selection_grade": "beacon_drawn" }
]
```

- `obligor_picked` — the obligor named the witness. **Steerable; earns nothing toward
  independence even if its evidence is disjoint**, because a pool of disjoint candidates
  can be shopped.
- `public_pool_unverified` — drawn from an eligible set the obligor did not define, but
  the draw is **not reproducible**. Not steering-bounded.
- `beacon_drawn` — witness identity = f(public beacon fixed **after** the row commits,
  committed eligible-set hash). The obligor could neither pre-tune to the witness nor
  re-roll for a favorable one. The eligible set MUST be committed before the beacon, or
  the obligor shrinks the pool to a captured subset (the §10 hole, one level down).
  **The only steering-bounded grade.**

**The counting rule is `min`(selection_grade, evidence-disjointness):** a witness counts
toward independence only if it is **both** evidence-disjoint **and** steering-bounded. An
unsteered draw of a *correlated* witness and a steered pick of a *disjoint* one each
collapse the co-sign. Absent `selection_grade` == `obligor_picked` (**fail closed** —
unstated selection is assumed steered, mirroring how unrefed evidence is assumed
correlated).

`effective_witnesses()` returns `witnesses` (evidence-disjoint, unchanged — backward
compatible) plus `steering_bounded_witnesses` (the §9 count: disjoint clusters with ≥1
`beacon_drawn` signer), `steered` (anchored signers floored by selection), and
`selection_grades`. A v0.1 / v0.1.2 envelope with no `selection_grade` anywhere reports
`steering_bounded_witnesses == 0` — correctly: it proved disjointness but said nothing
about selection, so it has earned no steering-bounded credit until selections are declared.
Worked example: [`independence_selection.v0.1.json`](../examples/independence_selection.v0.1.json)
— 3 sigs → 2 evidence-disjoint witnesses → 1 steering-bounded.

## §10 — origin-set completeness (specified; verifier-next)

§8's `input_disjoint` is computed over the origins a signer *chose* to anchor, and
cherry-picking is undetectable at the row level. The beacon discipline cannot fix this:
a beacon draws from a finite committed battery, but the origin space is open-ended — there
is no denominator to draw from. So **witness the denominator instead of sampling it.**

A trajectory claiming input-disjointness MUST commit an `origin_manifest` — the complete
set of origins the verdict was re-derived from, including inconvenient ones — and
disjointness is computed over the committed manifest, not a hand-picked subset. Where a
counterparty with standing to dispute exists, the manifest MUST be co-signed by that
counterparty (the boundary, not just the favorable members). A row asserting
`input_disjoint` without a committed (and, where a counterparty exists, co-signed)
`origin_manifest` carries `coverage_state = origins_unenumerated` and prices at the floor.

**Completeness is not provable from inside — it is *fireable*.** The `origin_manifest` is a
published, signed denominator anyone can void by naming an excluded load-bearing origin; a
successful fire retroactively voids the row's `input_disjoint` grade. Omission stops being
silent and becomes a repudiable act against a signed artifact.

**The co-signer carries its own `selection_grade` (amendment from review).** Co-signing
only closes the steering if the co-signer is itself steering-bounded — an `obligor_picked`
co-signer rebuilds the captured quorum one level up (fireable-in-principle,
never-fired-in-practice). So §10's weight is `min(co-signer selection_grade, manifest
completeness-bet)`, with a beacon-drawn manifest auditor the only steering-bounded
co-signature. §9 applied recursively to the enumerator.

## Composition

§9 and §10 are weakest-link siblings to §7–8 under one `min`. A row's independence is
`min(§7 axes, §8 evidence-disjointness, §9 selection_grade, §10 coverage_state)`. No axis
rescues another: the obligor must clear all of them to price above the floor. Every fix
that introduces a new party (a co-signer, an auditor) introduces a new denominator that
party can shrink — so each new party carries its own `selection_grade`, until the
selection is beacon-bounded. That recursion *is* the shape of the wall.
