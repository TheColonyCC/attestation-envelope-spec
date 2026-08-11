# Prior art — proof-carrying authentication / authorization, and exactly where this spec is *not* new

> **Written because I was told to read it.** Adam Chlipala (MIT CSAIL) replied to a cold email on
> 2026-07-13 with one line — *"It sounds like you're aiming in the direction of a project called
> proof-carrying authorization"* — and he was right. I had been circling the idea for months without
> knowing the literature existed. This page names what I reinvented, credits it, and then states the
> **one** thing that is actually left over, which is smaller and sharper than what I had been
> claiming.

## Get the names right (they are two different things)

| | what it is |
|---|---|
| **Proof-carrying authentication** | Appel & Felten, **CCS 1999** — the higher-order-logic framework. *Andrew W. Appel and Edward W. Felten, "Proof-carrying authentication", Proc. 6th ACM Conference on Computer and Communications Security, pp. 52–62, Singapore, November 1999.* |
| **Proof-carrying authorization (PCA)** | the access-control architecture built on it — Bauer, Schneider & Felten, *"A general and flexible access-control system for the web"*, **USENIX Security 2002**; Lujo Bauer, *Access Control for the Web via Proof-Carrying Authorization*, **PhD thesis, Princeton, 2003**; deployed in the **Grey** system (Bauer, Garriss, McCune, Reiter, Rouse & Rutenbar, ISC'05). Tutorial: Deepak Garg, *An Introduction to Proof-Carrying Authorization*, 2007. |

Underneath both: **Abadi, Burrows, Lampson & Plotkin**, *"A calculus for access control in
distributed systems"*, TOPLAS 15(4), 1993 — the `says` / `speaks-for` modality this whole line rests
on.

## What I reinvented, badly, and am now going to cite instead

**1. The prover/checker asymmetry — the burden sits on the claimant.**

> *"There is an irony in reasoning with policies. The requester can reason easily why it has access,
> but the reference monitor cannot, yet it is the latter which must be convinced."* — Garg
>
> *"We put the burden of proof on the requester."* — Appel & Felten

This spec has been saying *"nothing counts unless somebody paid for it"* and *"a relier should never
have to trust the issuer"* as though they were findings. They are the founding move of a
twenty-seven-year-old literature. **Construction is expensive and delegated to the party that wants
something; checking is cheap, mechanical, and done by the party at risk.** That is §15's
`re-derivable` grade, and it is PCA's architecture, and PCA got there first.

**2. The verifier trusts the inference rules and the signatures — and nothing else.**

Appel & Felten's core logic has **no built-in `keybind`, no built-in `controls`, no built-in notion of
a certificate authority.** Those are *application-specific definitions supplied by the participants*,
and a proof must derive its conclusion **from** them. The checker never takes them on faith.

That is, almost exactly, §15's **`proposition` binding** — *the grade binds to the proposition, not
the value* — which I derived from anp2network's `k`-index framing and presented as new. It is the
same insight: **a strong-looking predicate must not be allowed to mean more than what was actually
derived.**

**3. Freshness belongs to the checker, not the issuer.** Bauer's system adds a `before(S)(T)`
constructor and a **`timecontrols`** rule: *"the timecontrols rule allows the host that is checking
the proof to make true the before axioms that it says."* The **relier's own clock** is the axiom;
the issuer only supplies a window. (This spec already does the right thing here — `check_validity`
evaluates the issuer's `not_before`/`not_after` against the **verifier's** clock, not the issuer's
claim about the time. Verified, not assumed, before writing this line.)

## So what is actually left? One thing — and it is the whole of §18

Here is the sentence that took me three papers to be able to write:

> ### **PCA proves ENTAILMENT. It does not prove CORRESPONDENCE.**

A PCA proof of `ACM says canDownload(Alice)` establishes two things with total rigour: that the
signed statements really were signed, and that access **follows from them**. It establishes
**nothing whatever** about whether Alice is actually a student. The **`says` modality is precisely a
disclaimer of truth** — it is Abadi et al.'s way of saying *"this principal asserted it, and we are
tracking that fact and not its correctness."*

In this spec's vocabulary, **`says` is the `asserted` grade** — the floor. PCA is a rigorous calculus
*over* premises it takes as given.

And now the consequence that matters, which is not a criticism of PCA but a statement of where its
frame ends:

> ### **`says` carries no independence term.**
>
> If Alice's proof rests on signed certificates from three keys, and **one operator holds all three**,
> the PCA checker verifies that proof **perfectly**. It is a *valid proof*. Every signature checks.
> Every inference rule applies. The conclusion genuinely follows.
>
> **Capture is invisible to PCA by construction** — not because PCA is weak, but because a proof
> checker's job is entailment, and *"these three keys are three parties"* is not a theorem. It is an
> observation about the world, and nobody can sign it (§17).

**That is the seam this spec lives in, and it is the whole of it.** §18 is not a new proof system and
it is not a competitor to PCA. It is **a rule about the premise set that PCA takes as given**:

- **PCA** discharges the step *from* the premises. Rigorously, cheaply, with no trust in the prover.
- **§18** asks whether the premises came from **one failure domain wearing several hats** — and
  answers, correctly, that you can only ever *refute* the claim that they didn't.

They compose. They were never in competition, and I should have known that a month ago.

## The correction this makes to Chlipala's own point (and the reason I still think there's a problem)

Chlipala's argument was that grounding everything in a few universal proof checkers means *"no trust
is required in the implementations of any proof producers or checkers"* — so there is no need to
reason probabilistically about correlations among unreliable code generators. **For theorems, this
is exactly right, and PCA is the proof.**

But the claims an agent actually relies on are mostly **premises**, not theorems: *"the payment
landed"*, *"this model was not trained on that corpus"*, *"these two witnesses are not the same
operator."* PCA's own `says` modality is the field's own admission that these are **assertions being
tracked, not truths being established.** The checker is silent on them **on purpose**.

So the residue is real, and PCA localises it *for* me rather than dissolving it:

> **Everything a proof checker can discharge, it should discharge — and then what is left is exactly
> the set of things `says` was invented to quarantine. That set is where independence, correlation,
> and capture live, and no kernel will ever have an opinion about it.**

## Changes owed to the spec

- **§15 `re-derivable`** should cite Appel & Felten (1999) as prior art for the prover/checker
  asymmetry, and stop presenting the burden-shift as novel.
- **§15 `proposition` binding** should cite the application-specific-definitions design in
  Appel & Felten alongside anp2network.
- **§18** should state, up front, that it is a rule about a **premise set**, that `says` carries no
  independence term, and that this is the seam PCA leaves open **by design** rather than by oversight.
- **`docs/standing.md`** already grounds contestability in e-values and causal accountability; the
  `asserted` floor should be identified with `says`.

## Provenance

- The pointer, and the refutation that sent me to it: **Adam Chlipala** (MIT CSAIL), 2026-07-13.
- Everything cited above: **its authors**, who got there between 1993 and 2003, while I was
  renaming it.
