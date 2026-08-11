# §15 — Per-field assurance (verification modality)

A verifying signature tells a relier the envelope wasn't altered. It does **not**
tell them which parts of the claim they can *check for themselves* and which parts
rest on trusting the issuer. Those are very different kinds of assurance, and a
naïve relier can't see the seam.

`assurance` (optional, top-level) declares, per field, **how a relier gains
assurance about it** — so a stranger can price the trust surface without taking the
issuer's word for any of it.

## The five grades

| grade | meaning | who-said-it matters? |
|---|---|---|
| `re-derivable` | the relier recomputes/verifies the value offline from committed inputs | no — recompute and check |

> **Prior art (added 2026-07-14, after being told to read it):** the `re-derivable` grade is the
> assurance-grading form of the **prover/checker asymmetry** from **proof-carrying authentication**
> — *Appel & Felten, CCS 1999* — and the PCA line that follows it (*Bauer, Schneider & Felten,
> USENIX Security 2002*; *Bauer, PhD thesis, Princeton 2003*). *"We put the burden of proof on the
> requester."* Construction is expensive and falls on the party that wants something; checking is
> cheap, mechanical, and done by the party at risk. **This spec presented that burden-shift as a
> finding for several revisions. It is the founding move of a literature that predates it by 27
> years.** See [prior-art-pca.md](prior-art-pca.md). The same paper's refusal to build `keybind` /
> `controls` into its core logic — they are *participant-supplied definitions a proof must derive
> from, never facts the checker takes on faith* — is the ancestor of this section's
> **`proposition` binding**.
| `probe-consistent` | not re-derivable in instance (the world moved), but the relier re-runs the procedure and checks a **committed `tolerance`** holds — repeatable in *kind* | no — re-run and check the bound |
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

## `probe-consistent`: repeatable in kind, not re-derivable in instance

A lot of real evidence is neither `re-derivable` nor merely `asserted`. A sensor read,
a perturbation/probe test, a load-test result: you can't hand a stranger the inputs and
have them reproduce the *identical* number — the world moved — but they **can** re-run
the *procedure* and get a result of the same kind. Repeatable in kind, not re-derivable
in instance. Laundering these up to `re-derivable` (they feel empirical) or dumping them
down to `asserted` (they're not bit-reproducible) both lie about what a relier can do:
the falsifier here isn't "recompute the value," it's "re-run the probe and check the
bound holds." (Named `probe-consistent` in a Colony thread with hermes-final and
[exori](https://thecolony.cc); this closes the tier's open question.)

The load-bearing rule is **where the tolerance lives**: it MUST be committed **in the
receipt**, as `tolerance` on the field's assurance entry. If the tolerance lives only in
the falsifier's *definition*, the emitter picks a lenient one after seeing the result —
the exact cherry-pick §9's `beacon_drawn` closes for instance-*selection*, reopened for
the *bound*. A `probe-consistent` field with no committed `tolerance` is **self-void** and
falls to the floor, the same way a `re-derivable` field whose method doesn't reproduce the
value is self-void.

Two more fields sharpen it, both **declared + fireable**:

- **`tolerance_commitment`** — evidence the bound was fixed *before* the probe ran (a
  beacon binding, a pre-registration digest). The verifier can't prove pre-commitment
  from inside, so a `probe-consistent` field carrying no `tolerance_commitment` is exactly
  what a relier **fires** for high-stakes reliance: without it, the committed number could
  still have been chosen to fit the result.
- **`falsifier_class`** — names the probe class whose norms the tolerance is judged
  against, so a relier (or policy) can check "is this bound *within* that class's norms?"
  A self-authored tolerance with no class is a lie surface; the class anchors the meaning
  the way `proposition` anchors a re-derived value. Recommended.

A `probe-consistent` field counts in the **trust surface** — the offline verifier can't
re-run the probe, so it is not `confirmed_re_derivable`. But it is strictly stronger than
`asserted`: it ships a concrete, re-runnable falsifier with a committed bound, tracked in
its own `probe_consistent` profile bucket rather than lumped with the issuer's bare word.
Past its instance validity (`reachable_until` / `valid_until`) it reads **STALE, not
INVALID** — the instance expired, the procedure still re-runs (same honest-freshness
stance as `judgment` and §12.3 standing).

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

## Proposition binding (the grade binds to the proposition, not the value)

A method re-derives a *proposition*, which is often narrower than the field's plain
reading. `sha256(fetch(artifact_uri))` establishes *"the bytes at that URI hashed to
this value when fetched"* — integrity-as-fetched — not *"the artifact is authentic"* or
*"the claim it makes is true"*. A counter-signature over a fresh nonce proves *"the
endpoint's key was reachable and willing at T"*, not *"the service was healthy"*. Same
grade (`re-derivable`), wildly different claim. Let a strong-looking field's value be
read as the wider thing and you have laundered trust through a narrow witness.

So a field MAY carry an optional **`proposition`**: the exact claim its `method` /
`verify` establishes, in plain language. The grade binds to *that*, and the verifier
surfaces it verbatim so a relier — or a policy — attaches assurance to the proposition,
not to the value. It changes no arithmetic (a re-derived field still counts as
confirmed); it changes what "confirmed" is allowed to mean.

Like the grade itself, this is **declared + fireable**, never decided: the verifier
cannot know how downstream reads the value, so it does not try to detect
"value outruns proposition." Instead, a field whose value outruns its declared
proposition is exactly what a third party fires (`--fire=/pointer`) — the honesty is
enforced by contestability, not by a decision procedure. Recommended wherever the
method proves less than the value's plain reading might suggest.

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
