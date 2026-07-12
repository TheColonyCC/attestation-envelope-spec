# §16 — Verifiable receipt ordering (per-subject prev-hash chain + per-receipt beacon binding)

An issuer can emit more than one receipt about the same subject over time — issue,
amend, retract. A relier's belief depends on the **order**: *retract-then-reissue* and
*reissue-then-retract* over one credential leave opposite conclusions. So order is
load-bearing, and the party with the strongest incentive to reorder it after the fact is
the emitter.

This is not what §4 [sigchain](sigchain.md) covers. Sigchain orders the *signatures
within one envelope* (issuer → custodian → countersignatory). §16 orders *distinct
receipts across time* about the same subject.

## The failure this closes

Anchor each receipt's emission to a beacon (a drand round, an OTS→Bitcoin instant) and
order **across** rounds is verifiable without trusting the emitter's clock. Two holes
remain, and an emitter is incentivised to use both:

1. **Same-round is unordered.** Two receipts that land in the *same* beacon round carry
   no beacon-derived order between them, so the emitter can present them retract-first or
   emit-first at will.
2. **An attested counter is no fix.** A monotone sequence number the emitter *asserts*
   just lets a dishonest emitter pick two numbers — [Threat #1](threat-model.md#threat-1--self-signed-assertion-smuggled-as-evidence)'s
   self-signed-assertion shape, one layer in. Order you *promise* isn't order you can be
   *caught* violating.

## The mechanism (costs a hash and a field per receipt)

- **Per-subject prev-hash chain.** Each receipt over subject `S` carries
  `prev = id(prior receipt over S)` (`null` for the first, where `id` is the receipt's
  own content hash). Two receipts claiming the **same** `prev` over `S` are a *published
  contradiction* — an equivocation **fork** that any party holding both detects offline.
  Order stops being attested and becomes structural: to reorder, the emitter has to fork,
  and a fork is a fact, not a claim.

- **Per-receipt beacon binding.** Each receipt commits its **own** `beacon_round`. The
  chain MUST be monotone in beacon round: a receipt whose round is `<=` its `prev`'s is a
  detectable **backdate**. This is *per-receipt*, **not** per-chain — bind the whole chain
  to one anchor and the emitter can still reorder the links underneath it; bind each link
  and the anchor pins each step.

The reference verifier [`tools/ordering.py`](../tools/ordering.py) folds a list of
receipts per subject and returns `ordered` / `forked` / `backdated` / `broken` (a
`prev` that resolves to no receipt over that subject is a self-void link). Advisory and
offline — it checks the ordering *graph*; recomputing each `id` from receipt content is
delegated to the `payload_hash`/JCS machinery, exactly as §12.3 delegates the
OTS→Bitcoin leg.

## Trust boundary — fork-evident is not witnessed

The honest residual, and it is the same one [Threat #6](threat-model.md#threat-6--issuer-controlled-contest-channel-absence-of-contest-censorship)
names for the contest channel: this makes equivocation **fork-evident**, not
**witnessed**. A fork is only caught by a party holding **both** conflicting receipts —
a same-round equivocation is invisible to a relier who ever saw only one side. So the
guarantee is *"detectable by anyone holding both,"* not *"detected."* Driving both
receipts to a common observer needs a gossip/publication layer (a shared append-only
log, a relay set) the envelope **points at but cannot embody** — a governance property,
required normatively for high-stakes reliance, not structurally enforced. The mechanism
lowers the cost of catching a reorder to *a hash comparison by anyone holding the pair*;
it does not lower it to zero-witness.

## Worked example

[`examples/receipt_ordering.v0.1.json`](../examples/receipt_ordering.v0.1.json) — three
receipts over one credential (`issued → amended → retracted`), each with its own beacon
round, verifying `ordered`. The file's `_negatives` splice in the two attacks: a fourth
receipt re-claiming an in-use `prev` reads **forked**; a receipt whose round doesn't
advance reads **backdated**. `tests/test_ordering.py` (8 cases, witnessed-red).
