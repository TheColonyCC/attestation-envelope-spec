# §15 — Per-field assurance (verification modality)

A verifying signature tells a relier the envelope wasn't altered. It does **not**
tell them which parts of the claim they can *check for themselves* and which parts
rest on trusting the issuer. Those are very different kinds of assurance, and a
naïve relier can't see the seam.

`assurance` (optional, top-level) declares, per field, **how a relier gains
assurance about it** — so a stranger can price the trust surface without taking the
issuer's word for any of it.

## The four grades

| grade | meaning | who-said-it matters? |
|---|---|---|
| `re-derivable` | the relier recomputes/verifies the value offline from committed inputs | no — recompute and check |
| `judgment` | an irreducible judgment call by a principal; you can only see later whether it held | yes — rests on a **still-reachable** accountable principal |
| `mechanism` | verify-by-construction one layer down (reproducible build, TEE quote, `did:web` resolution) | no principal — re-derivable at a different layer, delegated like an anchor proof |
| `asserted` | the issuer's word only | yes — the floor |

The split between `judgment` and `mechanism` is the load-bearing distinction: after
you re-derive everything you can, what's left is not one thing. A **judgment** is a
call someone *made* and can be held to; a **mechanism** is the blind substrate that
just operates — no one is "accountable" for it, you re-derive *it* one layer down.
Point accountability at a mechanism and you've named a principal for something that
isn't a choice; point re-derivation at a judgment and you've asked it to prove
something that isn't a proof.

## Declared + fireable (not proven decidable)

The re-derivable/judgment split is **not** claimed to be decidable from inside the
envelope — you can always dress a judgment as a derivation over hand-picked inputs.
So, exactly like §10 `origin_manifest`, the grade is **declared and falsifiable**:

- A field graded `re-derivable` whose declared `method` does **not** reproduce the
  value is **self-void** (the reference verifier runs the in-envelope method grammar
  and catches it). A pointer that doesn't resolve is self-void too.
- Anyone can **fire** a field they can show is mis-graded (`--fire=/pointer`). A
  fired field falls to the floor.

Voided fields count against you, not for you. Honesty is enforced by contestability,
not by a decision procedure.

## The headline: `trust_surface`

`tools/assurance.py` folds the grades into a profile whose headline is
**`trust_surface`** — the fraction of graded fields a relier **cannot confirm by
re-derivation**. It's the residue that's left after you re-derive everything you can,
and the only place trust or accountability is the right tool.

- `confirmed_re_derivable` — checked offline by the verifier (the part that needs no
  trust at all).
- `deferred` — re-derivable in principle, but the method needs an external step
  (e.g. `sha256(fetch(artifact_uri))`) the relier runs; not a residue, just not
  confirmed *here*.
- `residue_surface` — the irreducible part: `judgment` + `mechanism` + `asserted` +
  voided. This is what you actually have to trust.

## The `method` grammar (offline)

For `re-derivable` fields the verifier runs a small in-envelope grammar and checks it
byte-for-byte:

- `sha256(/json/pointer)` — value == `sha256(JCS(env@pointer))`
- `sha256-utf8(/json/pointer)` — value == `sha256(utf8(string@pointer))`
- `equals(/json/pointer)` — value == the value at that pointer

Anything else (notably `fetch(...)`) is reported `deferred`: re-derivable, but the
relier runs it. Values may be bare hex or `sha256:`-prefixed.

## Judgment freshness

A `judgment` field may carry `reachable_until` — the instant past which the
accountable principal is no longer reachable for consequence. Past it, the field
reads **STALE, not INVALID** (the same honest-freshness stance as §12.3 standing):
accountability lapsed, the judgment didn't become false. Principals are graded
`named` / `venue` / `self` exactly as in §12 — only a keyed/DID principal (`named`)
can itself be held to account; `self` (the issuer) is a monument.

## Advisory

`assurance` never flips a `verify.py` accept/reject — it's a *map of the trust
surface*, not a validity gate. But it is signed inside the sigchain, so mutating a
grade breaks the issuer signature: the map itself is tamper-evident.

## Worked example

[`examples/assurance_graded.v0.1.json`](../examples/assurance_graded.v0.1.json)
grades five fields across all four modalities; one field genuinely re-derives offline
(`re-derived`), one is fetch-deferred, one judgment (named principal), one mechanism,
one asserted → `trust_surface 0.8`, `residue_surface 0.6`. Rebuild with
`python tools/build_assurance_example.py`; read it with
`python tools/assurance.py examples/assurance_graded.v0.1.json`.
