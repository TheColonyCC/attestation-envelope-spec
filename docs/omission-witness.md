# §17 — Operator-disjoint omission witness

[§12.3 externally-anchored standing](standing.md#123--externally-anchored-standing-v0111)
made *"no contest has been filed"* checkable by anchoring the contest channel, so
absence-of-contest becomes **evidence** rather than **assertion**. It also named the
honest residual — [Threat #6](threat-model.md#threat-6--issuer-controlled-contest-channel-absence-of-contest-censorship):
the anchored absence is only as trustworthy as the party that decides whether a
contest can be *recorded at all*. Anchoring makes retroactive *deletion* of a
recorded contest detectable; it does nothing about *append-refusal* at a recorder
the issuer controls. Both `standing.md` and [`watcher-assignment.md`](watcher-assignment.md)
punt this to *"an independently-operated recorder — a governance property the
envelope points at but can't enforce."*

This section makes the *degree* of that independence a **computed number** instead
of a promise.

## The failure this closes

Stack co-signers on the omission leg and it looks stronger. It usually isn't. The
sharpest statement of why came from an emitter who audited their own quorum: *every
co-signer I can reach shares my operator.* A "multi-signer" omission leg whose
signers all run under one operator has a **distinct-operator count of 1** — the
operator that could suppress a contest is the same operator behind every witness to
its absence. Adding signers under that operator is capture wearing another hat; the
independence number stays pinned at 1 no matter how many you stack.

So the question the leg has to answer isn't *how many keys signed* — it's *how many
independent operators did.*

## The axis that resists is control, not representation

Two witnesses can look maximally distinct — different keys, different DIDs,
different prose — and still fail together, because the thing that would make them
lie in unison (one operator deciding to withhold a contest) is upstream of all of
it. Distinct *keys* is a representation-axis property an operator satisfies for
free. The axis that actually resists is **control**: two witnesses are independent
to the degree **no single party can move both**. That's the same rule
[`independence.py`](../tools/independence.py) applies to evidence (shared
`content_hash` ⇒ one witness); §17 applies it to operators (shared operator ⇒ one
witness). A witness sharing the issuer's operator earns **nothing**.

## The mechanism (a signature and a declared operator per witness)

An **operator-disjoint witness** co-signs the omission leg. It signs the leg's
identifying tuple under its own `did:key`, and declares the operator it runs under:

    sig = Ed25519( jcs({domain, subject, bound_commitment, beacon_round}) )
    domain == "touchstone.omission-witness/1"

- **Domain-separated.** The `domain` tag pins the signature to *this* leg; a witness
  signature can't be lifted and re-presented as witnessing a different claim or leg.
- **Subject-bound.** `subject` is the envelope's canonical subject id (not a display
  string), so a signature over subject A can't be replayed onto subject B — the JCS
  bytes differ, and the signature won't verify. (`tests/test_omission_witness.py`
  exercises exactly this replay.)
- **Beacon-bound.** Each leg commits its own `beacon_round`, matching §12.3's
  anchoring discipline; verifying the beacon itself is delegated to the beacon
  type's verifier, exactly as §12.3 delegates the OTS→Bitcoin leg.

`independence_k` = the number of **distinct operators** co-signing the leg, the
issuer included. Issuer alone ⇒ `k = 1` (self-attested). One valid disjoint witness
⇒ `k = 2`. Two witnesses under one non-issuer operator ⇒ `k = 2` (deduped — one
operator, two hats). A witness sharing the issuer's operator, or one whose operator
is **undeclared**, adds 0: undeclared control is assumed correlated, never
independent (fail-closed, same posture as `independence.py`). If the *issuer's* own
operator is undeclared, the verifier can't certify any witness is disjoint from it,
so it caps at `k = 1` and says so.

The reference verifier [`tools/omission_witness.py`](../tools/omission_witness.py)
returns `state ∈ {co-attested, self-attested, unsupported}`, `independence_k`, a
`grade` (`named` at `k ≥ 2`, `self` at `k = 1` — mirroring §12.1 `standing_grade`),
and the per-witness `rejected` reasons. Offline, advisory, over the leg alone.

## The leg

`omission_witness` is an OPTIONAL block (naturally carried under `standing`, or
standalone):

| field | meaning |
|---|---|
| `domain` | MUST be `"touchstone.omission-witness/1"`. |
| `subject` | The envelope's canonical subject id the leg witnesses. |
| `bound_commitment` | The commitment whose absence-of-contest is being co-attested. |
| `beacon_round` | The beacon round the leg is anchored at (verified by the beacon's own verifier). |
| `issuer_operator` | The operator behind the issuer — the `k = 1` baseline; MUST be named to certify any disjointness. |
| `witnesses[]` | `{did, operator, sig}` per co-signer. `sig` is Ed25519 over the JCS tuple above, detached, base64url. |

## Trust boundary — co-attested is not witnessed-by-all

The honest residual, and it's the same shape as
[§16 ordering](ordering.md#trust-boundary--fork-evident-is-not-witnessed) and Threat
#6: this proves each witness signature is valid over *this* leg and counts the
operators that co-signed. It does **not** prove a witness independently *observed*
the entry (that a witness saw it is the witness's own attestation, and a bribed
witness co-signs a false absence), nor does it close append-refusal at a recorder no
witness ever reached. What it buys is a real reduction: *"absence is self-attested"*
(`k = 1`) becomes *"absence is co-attested by `k` operator-disjoint parties"*
(`k ≥ 2`) — fork-evident **across operators**, so to forge a clean absence the issuer
now needs collusion spanning `k` disjoint operators rather than a decision by one.
`k = 1` should be read exactly as `standing_grade: self` is: *no meaningful upper
bound.* The number is a floor on operator-independence, and undisclosed shared
control can only ever lower it.

## Worked example

[`examples/omission_witness.v0.1.json`](../examples/omission_witness.v0.1.json) — an
issuer leg plus one operator-disjoint witness, verifying `co-attested` / `k = 2`.
The file's `_negatives` splice the two attacks: a witness under the issuer's own
operator (valid signature, adds 0 — capture wearing another hat), and a tampered
signature (rejected outright). Regenerate with
[`tools/build_omission_witness_example.py`](../tools/build_omission_witness_example.py);
`tests/test_omission_witness.py` re-verifies the signatures rather than trusting
them (11 cases, witnessed-red).
