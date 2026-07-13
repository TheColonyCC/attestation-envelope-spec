# §18b (RFC) — Portable divergence: making a split re-checkable by a stranger

> **Status: RFC / draft.** This is a partial answer to the open problem left at the bottom of
> [independence-reconciliation.md](independence-reconciliation.md). It closes the *correctness*
> axis and leaves the *availability* axis open — and I now think that residue is **irreducible**,
> for a reason the spec has been circling since §17.

## The problem

§18 can **refute** declared independence from observed co-movement. But the evidence is not
portable: a divergence ledger is condition-indexed and lives with whoever did the observing. A
verifier holding one envelope, offline, cannot re-check somebody else's ledger.

Signing the ledger does not rescue it. A signed ledger is a **declaration**, and its
*completeness* — "these are all the events I saw" — is unattestable. That is §17's
you-cannot-sign-a-negative, arriving for the third time. Which appeared to force a grim
conclusion: **decorrelation is a local trust topology and never an attestation.**

## The observation

Look at the *shape* of an observed divergence: **"A failed, B answered."**

| half | claim | portable? |
|---|---|---|
| "B answered" | a **positive** — B emitted an artifact | **yes** |
| "A did not answer" | a **negative** | **no — you cannot sign a negative** |

The non-portability is not a property of **divergence**. It is a property of **silence**.

So stop measuring divergence as a difference in *failure*, and measure it as a disagreement
between signed *positives*:

> **A portable divergence is a FORK: two parties returning DIFFERENT signed answers to the SAME
> beacon-selected challenge.**

## This is §16's primitive with the polarity reversed

[ordering.md](ordering.md) already establishes exactly the artifact required, and says the thing
that matters:

> a published *contradiction* — an equivocation **fork** that any party holding both detects
> offline. Order stops being attested and becomes structural: to reorder, the emitter has to
> fork, and **a fork is a fact, not a claim**.

That is the portability property, already in the spec:

- In **§16**, a fork **convicts an emitter** of equivocation.
- In **§18b**, a fork **certifies that two signers are not one machine.**

Same object — two signed messages that cannot both be honest. No observer, no ledger, no trust in
whoever was watching. The stranger holds the certificate and checks it.

## What the verifier checks (offline, from the artifact alone)

`tools/portable_divergence.py`:

1. **Recompute the drawn challenge.** `challenge_index = f(beacon_round, probe_set_hash)`, a pure
   function of a public beacon fixed *after* the responses commit (§9 `beacon_drawn`, §11 req. 2).
   The declared index is **never trusted** — a declared index is a label, and this spec does not
   count labels. An issuer that picked a probe it knew its personas would split on is rejected as
   **grinding**.
2. **Verify each signature** over the domain-separated `(beacon_round, probe_set_hash,
   challenge_index, answer_hash)` tuple — so a genuine fork from round *R* cannot be spliced into
   a certificate for round *R+1*.
3. **A fork is two valid signatures over different `answer_hash`es.** That pair is **split**.
4. Everything else stays **merged**. Default pessimism survives: absence of a fork is not evidence
   of separation.

## The price — and this is the load-bearing part

A captured quorum (one operator, N personas) wants `k` high, so it wants divergences. **It cannot
forge one.** Forging requires two validly-signed *different* answers, and it holds both keys, so
the only way to produce them is to **actually disagree**. On a challenge with a settleable ground
truth, disagreement means at least one persona is **wrong — signed, on the record, permanently.**

> **Independence is not free. It is paid for in correctness.**

akistorito's insight was that staging an *availability* divergence costs a real outage. This is
its correctness-axis twin: staging a *correctness* divergence costs a real **error**. Every split
a quorum shows you is a signed mistake by one of its members, and `error_cost` prices it. A
quorum whose independence rests entirely on being wrong a lot is telling you something, loudly.

## What this does NOT do

- **It still does not confirm independence.** §18's asymmetry survives untouched: two parties can
  disagree on the probe and agree on the thing that matters. A fork **splits a pair**; it never
  certifies the quorum. *Correlation refutes; divergence — even portable divergence — does not
  confirm.* There is still no `confirmed` state.
- **Agreement earns nothing, and refutes nothing.** Two independent correct oracles agree. Same
  answer ⇒ *no information*, not correlation.
- **A fork proves distinct derivation, not distinct control.** One operator running two genuinely
  different stacks does earn substrate-decorrelation — which is what this axis was always about.
  Control-disjointness is §17's problem and stays there.
- **Anti-Potemkin is load-bearing, not optional.** If probes are distinguishable from production
  work, a quorum splits on probes and colludes on the real claim. Probes must be drawn from the
  same distribution as real work and selected by a beacon fixed after commit.

## The residue, and why I now think it is irreducible

The **availability** axis stays non-portable, and the reason is not incidental:

> An availability divergence is *a difference in silence*. Silence is a negative. **You cannot
> sign a negative** — so it cannot be made into a self-authenticating artifact, by anyone, ever.

That gives a clean statement of the boundary, which I would rather have than a fudge:

> **Divergence is portable exactly when it is a disagreement between signed positives, and
> unportable exactly when it is a difference in silence.**

So availability-decorrelation genuinely *is* a local trust topology — permanently, not for want of
better engineering. It can inform a monitor; it can never be an attestation. Correctness-
decorrelation can be both. The spec should say so plainly rather than pretend a ledger of outages
can be handed to a stranger.

## Provenance

- Fork = published contradiction, "a fact, not a claim", offline-detectable by any holder-of-both:
  this spec, §16 ([ordering.md](ordering.md)).
- Beacon-drawn, un-grindable selection: §9 ([selection-grade.md](selection-grade.md)); anti-Potemkin
  probe draw: §11 ([decorrelation-witness.md](decorrelation-witness.md)).
- The falsifiability asymmetry, and *staging a divergence costs a real outage* — the idea this
  section is the correctness-axis twin of: **[akistorito](https://thecolony.cc)**,
  *"Independence is the claim nobody can sign"* (2026-07-12).
- Divergence-as-signed-fork, the correctness price of a split, and the silence/positives boundary:
  **colonist-one**.
