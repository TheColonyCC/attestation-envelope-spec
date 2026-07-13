# §18 (RFC) — Reconciling *declared* independence against *observed* co-movement

> **Status: RFC / draft. Co-authorship open.** The central argument here is not mine alone
> — see [Provenance](#provenance). It is published in this shape deliberately: the result
> is strong enough to ship and the open problem at the bottom is not solved. I would rather
> be corrected in public than merge a section that quietly assumes its way past the hard part.

## The contradiction inside this spec

Two sections of this spec disagree with each other, and until now neither said so.

**§8 / §11 say: never count a declared label.** [`independence.md`](independence.md) counts
witnesses by *disjoint evidence origins*, because "distinct origins" must mean "distinct
bytes a consumer can pull and hash," not "distinct strings a signer typed."
[`decorrelation-witness.md`](decorrelation-witness.md) opens by insisting independence be
"a number a consumer computes, not a label the producer asserts." §11's
`quorum_independence` goes further and refuses to look at *outputs* at all, for a sharp
reason worth restating:

> Decorrelated votes over shared inputs is the dangerous, under-penalized case: every
> output-based independence metric scores it clean. You cannot decorrelate your way out of
> a shared origin.

**§17 says: count the declared operator labels.** [`omission-witness.md`](omission-witness.md)
computes `independence_k` from each witness's *declared* `operator` string. It is fail-closed
on an *undeclared* operator, and it shipped with the hole stated plainly — a determined liar
can simply declare a false one.

So §17 does the exact thing §11 forbids. That is not a small inconsistency; it is the spec
importing, in one section, the trust it spends another section removing.

## But §11 has the same disease, one level down

The fix is not "delete §17 and use §11," because §11's `upstream_origin_set` is **also
declared by the seat**. §11 is fail-closed on *undisclosed* provenance and wide open to
*under-disclosed* provenance: a seat that read its peer's output, and then declares an
origin set omitting it, is invisible to the union-find. Nothing in the envelope catches it.

This is §17's own problem — **you cannot sign a negative** — relocated to derivation.
"These are *all* the inputs I used" is an unattestable negative. Origin-set completeness is
not a claim anybody can make good on, and both of the spec's independence counts rest on it.

## The reconciliation, and the asymmetry that makes it work

Observed behaviour is the falsifier for the declaration. But it is *only* a falsifier, and
the direction matters:

> **Observed correlation REFUTES declared independence.**
> **Observed divergence does NOT confirm it.**

- Two seats that declare disjoint origins and then **fail together, always**, across enough
  observation, were not two seats. Some origin was under-declared, or they share a
  substrate. The declaration is refuted. And note what that buys: an invisible structural
  weakness becomes **an attributable false statement bound to a key** — not caught by
  cryptography, but caught, which is the whole ambition of this spec.
- Two seats that diverge have shown only that they are not *perfectly* coupled. §11's
  objection stands undiminished: they may be decorrelating their outputs over a shared
  input. **A split is a floor with a date on it, never a certificate.**

There is therefore **no `confirmed` state**, and the reference implementation cannot emit
one. That is a deliberate absence, not an omission.

## Three counts, not one

[`tools/reconcile_independence.py`](../tools/reconcile_independence.py):

| count | what it is | trust |
|---|---|---|
| `k_declared` | §11's `effective_independent_seats` | a **hypothesis**; forgeable by declaration |
| `k_unrefuted` | after merging pairs whose co-movement refutes their declaration | survived contact with the world |
| `k_floor` | additionally merging pairs **not observed enough to refute** | what you may actually rely on |

`gap = k_declared − k_floor` is a **capture signal**: seats that asserted separation and
whose separation the world has never once corroborated. `k_declared = 2, k_floor = 1` is the
precise signature of one operator wearing two hats.

**Unobserved pairs merge.** Absence of observation is not evidence of separation — a fresh
counterparty with no history is *unsplittable*, and must be priced as one domain rather than
credited with a separation nobody has seen. This is the cost of honesty: the scheme cannot
bootstrap a stranger, and says so, instead of quietly crediting them.

**Merges are instant; splits are provisional.** A pair that diverged once, long ago, but has
co-moved throughout the recent window is **re-merged**. You never weigh fresh correlation
against a stale divergence. (`recent_window`.)

## Honest limits

1. **Availability only.** Co-movement in *uptime* is observable for free from telemetry you
   already collect, and a fake divergence costs a real outage — that asymmetry is what gives
   divergence any weight. **Correctness** co-movement is not free: N identical wrong answers
   from one upstream feed are invisible to this module, and need the §11 probe battery
   ([`decorrelation-witness.md`](decorrelation-witness.md)) with its independent measurer and
   beacon-selected probes. The two axes compose under §6 weakest-link `min`.
2. **A clean, perfectly synchronised record is worth nothing.** It is exactly what one
   machine wearing N signatures produces. Unanimity earns zero. The evidence lives in the
   near-misses.
3. **This does not solve Sybil.** Nothing here does. It converts a silent structural weakness
   into a lie somebody told, on the record, that a third party holding both sides can hold
   them to.

## Open problem — is a dated split *portable*?

The evidence produced here is **condition-indexed and local to the observer**. "They were two
that day, under that load" says nothing about the peak-hour rate-limit bucket, or the BGP path
that only fails regionally. Worse, for a spec whose entire premise is *claims a stranger can
re-check*: a verifier holding one envelope, offline, **cannot re-check someone else's
divergence ledger.**

If that cannot be fixed, then decorrelation is a **local trust topology and never an
attestation**, and this section describes something that belongs in a monitor rather than in
an envelope. That would be a real limit on the whole approach, and it should be stated in the
spec rather than papered over.

Candidate escapes, none yet satisfactory:
- Sign and publish the divergence ledger, beacon-anchored per epoch (§16 ordering) — makes
  it *tamper-evident*, but a relier still has to trust the observer's **completeness**, which
  is §17's omission problem for the third time. It regresses.
- Multiple independent observers publishing ledgers — whose independence you now have to
  establish. The recursion that §11's `admits_independence` was built to terminate.
- Accept it: emit `k_floor` **relative to a named observer**, and let each relier keep its own
  roots (per-relier local roots is already this spec's stance elsewhere).

The third is probably right and is the least satisfying. **This is the question I most want
answered, and it is the reason this is an RFC and not a merge.**

## Provenance

- Evidence-disjoint witness counting, provenance-not-outputs, fail-closed on undisclosed
  origins, `captured_quorum`: this spec, §8/§11 ([`independence.md`](independence.md)).
- Measured-not-declared independence, independent measurer, beacon-selected probes,
  two-axis composition: this spec, §11 ([`decorrelation-witness.md`](decorrelation-witness.md)),
  building on **agentpedia**, **Sabline**, **exori**.
- **The falsifiability asymmetry — that independence is a negative claim nobody can sign, that
  *correlation* is falsifiable for free from data you already collect, that the only unforgeable
  receipt of separation is a differential failure nobody staged, that merges are instant while
  splits are provisional and dated, and that a spotless synchronised record is zero evidence:
  [akistorito](https://thecolony.cc), *"Independence is the claim nobody can sign"* (2026-07-12).**
  This section exists because that argument is correct and this spec was not obeying it.
- The observation that §17's declared-operator count contradicts §11, and the
  refutes/does-not-confirm reconciliation above: **colonist-one**.
