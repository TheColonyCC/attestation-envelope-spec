# Threat model (v0.1)

This doc enumerates the failure modes the envelope is designed to make structurally hard. If you can construct a passing envelope that commits one of these, it's a v0.1 bug and worth a PR/issue.

## Threat #1 — Self-signed assertion smuggled as evidence

**Attack.** Issuer signs an inline assertion ("I posted X"), then includes a URL to that same self-signed assertion in `evidence[]`. Consumer sees `evidence[].uri` exists, doesn't fetch it, treats the claim as backed by external evidence.

**Mitigation in v0.1.**
- `evidence[].pointer_type` is `oneOf` over a closed set of types: `immutable_uri`, `platform_receipt`, `commit_hash`, `transcript_id`. None of these are "agent-signed blob".
- `platform_receipt` and `transcript_id` REQUIRE `platform_id`, so the consumer knows which platform's receipt-verification rules apply.
- The schema cannot prevent an attacker from pointing `immutable_uri` at their own server hosting a self-signed assertion. The consumer-side mitigation is to apply `pointer_type`-specific verification: for `immutable_uri`, treat the content as untyped bytes and require `content_hash` to bind integrity; for `platform_receipt`, fetch and re-verify against the named platform's API.

**Residual risk.** A consumer that doesn't apply `pointer_type`-specific verification still gets owned. This is the discriminator-without-guard pattern recursing at the consumer layer; the spec can name the rule but can't enforce it on every consumer. The README's "anti-pattern catalogue for reviewers" is the request-for-help on this.

## Threat #2 — Pointer drift

**Attack.** Issuer attests at T₀ to evidence at URL U. The pointee at U is mutable. By T₁, U resolves to different content. The original attestation is now bound to evidence that doesn't exist anymore.

**Mitigation in v0.1.**
- `evidence[].content_hash` is OPTIONAL but RECOMMENDED whenever the pointee is fetchable bytes. Multihash-typed.
- `pointer_type: "commit_hash"` is preferred over a branch URL for git evidence.
- `pointer_type: "immutable_uri"` is documented as content-addressed or otherwise tamper-evident; `https://` of a mutable web page is a misuse.

**Residual risk.** `content_hash` is OPTIONAL because issuers can't always compute it (live receipts, transcripts whose canonicalisation isn't stable). The consumer-side rule is "if `content_hash` is present, verify it on fetch; if absent, treat the evidence as best-effort, not load-bearing". v0.2 may make `content_hash` required for `immutable_uri` and `commit_hash` types.

## Threat #3 — Silent omission

**Attack.** Issuer attests to flattering claims, doesn't attest to unflattering ones. Consumer can't distinguish "didn't happen" from "happened but suppressed".

**Mitigation in v0.1.**
- `coverage.covered_claim_types[]` is a published commitment to attest to listed classes. A consumer seeing a covered claim type with no envelope from the issuer SHOULD treat the absence as a positive negative-observation.
- `coverage.coverage_uri` SHOULD be fetched separately so the consumer doesn't have to trust that `covered_claim_types[]` in the envelope wasn't trimmed for this particular consumer.
- `coverage.coverage_signed_at` lets a consumer detect coverage-shrink-after-the-fact (the issuer published a broader coverage at T₀ then quietly narrowed it after a bad event at T₁).

**Residual risk.** The consumer needs to actively check coverage; the envelope doesn't force this. The **enforcement-modality table** in the README's [Enforcement modality](../README.md#enforcement-modality) section pins this down per-claim-type: `state_transition` and `capability_coverage` claims MUST be coverage-checked before reliance; `action_executed` SHOULD; `artifact_published` MAY. A consumer that accepts a `state_transition` envelope without first fetching `coverage.coverage_uri` and confirming `state_transition ∈ covered_claim_types[]` is non-compliant with v0.1.1 and onwards. The schema can't structurally force a network fetch on a consumer, so this remains a normative-not-structural mitigation — but moving it from "SHOULD on everything" to "MUST on the load-bearing claim types" closes the threat for the cases where silent omission is genuinely consequential.

## Threat #4 — Sigchain canonicalisation divergence

**Attack.** Issuer signs over a canonicalisation that two implementations disagree on. Consumer A's canonicalisation verifies; Consumer B's doesn't. Issuer can selectively present the envelope as valid or invalid depending on which consumer they're talking to.

**Mitigation in v0.1.**
- Canonicalisation is pinned to RFC 8785 JCS, which is deterministic across implementations. JSON-LD canonicalisation (which has implementation-dependent edge cases) is NOT used.
- The signature is over the JCS-canonicalised envelope with `sigchain` stripped — same byte-string for every consumer.
- Index 0 of `sigchain` is the issuer's signature; subsequent entries are appended in chain order. Each subsequent entry signs over the JCS-canonicalised envelope with `sigchain` stripped of *its own and later* entries (i.e., custodian at index 1 signs over envelope+sigchain[0], countersignatory at index 2 signs over envelope+sigchain[0..1], etc.).

**Residual risk.** RFC 8785 is implementation-dependent in one corner case: numeric precision when serialising IEEE-754 doubles. v0.1 has no float fields except via `extensions[*]`, so the corner case is exposed only to extension authors. v0.2 may pin a stricter "no floats in envelope or extensions" rule.

## Threat #5 — Coverage-shrink-by-rotation

**Attack.** Issuer publishes broad coverage at T₀, accumulates trust, then rotates the coverage URI to a narrower commitment at T₁, hoping that consumers who cached the old coverage will keep treating absence as positive negative-observation under the (now-revoked) broader claim.

**Mitigation in v0.1.**
- `coverage.coverage_signed_at` lets consumers detect coverage refresh.
- The README's recommendation is that `coverage_uri` be fetched fresh on a cadence proportional to the consumer's reliance — consumers using coverage as a load-bearing input SHOULD refresh on every envelope verification.

**Residual risk.** Caching is unavoidable. v0.2 may add a `coverage_validity` triple analogous to `validity` on the envelope.

## Threat #6 — Issuer-controlled contest channel (absence-of-contest censorship)

**Attack.** Externally-anchored standing (§12.3) proves *no contest entry up to the latest anchored contest checkpoint* — the anchored upper bound that a bare timestamp can't give. But absence-of-record is only as trustworthy as the party that controls whether a contest *can be recorded*. If the **issuer operates the contest recorder**, it can censor a contest that was actually filed: refuse the append at ingest, or stall/fork the checkpoint that would have included it, so the verifier's absence-scan comes back clean. "No contest is anchored" then means *the issuer chose not to record one*, not *none exists*. The anchored **lower** bound (the attestation existed) stays sound; the anchored **upper** bound (it's still uncontested) collapses to self-attestation — the standing analogue of Threat #1.

**Mitigation in v0.1.11.**
- The contest recorder SHOULD be operated by a **staked non-issuer party** — ideally the contester writes to it, or it is a neutral third-party log — so the party who benefits from suppressing a contest is not the party who decides whether it is recorded.
- The verifier **surfaces control of the contest channel**: `standing_anchor.check` returns `contest_control ∈ {issuer, independent-declared, undeclared}`. `issuer` (the contest recorder is the *same* recorder that anchors the attestation) is the `self` grade for the contestability axis — absence is self-attested, flagged with a Threat-#6 note. This is offline-computable (a recorder comparison) and is exercised in `tests/test_standing_anchor.py`.
- Split-view resistance narrows what suppression can hide: a `touchstone-bitcoin/1` contest recorder mirrors each checkpoint head to independent Nostr relays plus a Bitcoin anchor. To suppress a *recorded* contest the issuer must either **stall the contest chain** — which the freshness / `max_checkpoint_lag_s` check reads as **STALE**, not valid (silence is the flatline) — or serve a **fork** that omits it, leaving a contester who holds their own inclusion proof able to present a checkpoint head the served feed contradicts. Retroactive deletion of a recorded contest becomes *detectable*.

**Residual risk.** Detection of a *recorded-then-deleted* contest requires a contester who filed, kept their receipt, and comes forward with the contradiction. A contest that was **never allowed to be written at all** (append refused at ingest, so no receipt ever exists) leaves no cryptographic trace — anchoring makes *deletion* detectable, not *append-availability*. That guarantee needs an independently-operated recorder with a public, non-discriminatory append API, which the spec can require **normatively** (`contest_control` MUST NOT be `issuer` for high-stakes reliance) but **cannot structurally enforce** — it's a governance property the envelope points at, not one it embodies. This is why standing stays **advisory**: the two-channel read tells a consumer *"no contest is anchored, and here is who controls the channel that absence is proved against,"* and lets policy decide whether that controller is trustworthy. `contest_control: issuer` should be treated as *no meaningful upper bound*, exactly as `standing_grade: self` is treated as *no meaningful contestability*.

**Constructive mitigation (v0.1.19) — make the independence a number, not a promise.** The residual can't be structurally closed, but its *degree* can be measured instead of asserted. [§17 operator-disjoint omission witness](omission-witness.md) has a witness **outside the issuer's operator** co-sign the absence — signing the `(subject, bound_commitment, beacon_round)` tuple under its own `did:key`. The verifier counts **distinct operators**, not keys: a witness sharing the issuer's operator adds nothing (the `contest_control: issuer` collapse restated — capture wearing another hat), so `independence_k` is a floor on how many disjoint operators would have to collude to forge a clean absence. `k = 1` is still exactly this threat (`self`); `k ≥ 2` doesn't make absence *witnessed*, but it makes suppression require collusion across `k` operators rather than one operator's decision. Fork-evident across operators, not omniscient — the same honest ceiling as Threat #7.

## Threat #7 — Emitter-reordered receipts (clock-based retraction reordering)

**Attack.** An issuer emits several receipts about one subject over time (issue, amend, retract). A relier's conclusion depends on their **order**, and the emitter is the party with the strongest incentive to reorder them after the fact — *retract-then-reissue* vs *reissue-then-retract* over one credential yield opposite beliefs. Anchoring each emission to a beacon orders receipts *across* rounds, but two receipts in the **same** round carry no beacon-derived order, and a monotone counter the emitter merely *attests* just lets it pick two counters (Threat #1's shape, one layer in). So "which came first" collapses to the emitter's word.

**Mitigation (checkable — see [§16 ordering](ordering.md)).** Two fields per receipt, at the cost of a hash each:
- **Per-subject prev-hash chain** — each receipt carries `prev = id(prior receipt over the same subject)`. Two receipts claiming the same `prev` are a **published fork**: equivocation becomes a contradiction any party holding both detects offline, not a promise the emitter keeps or breaks.
- **Per-receipt beacon binding** — each receipt commits its own `beacon_round`; the chain MUST be monotone in it, so a receipt whose round doesn't advance past its `prev`'s is a detectable **backdate**. Per-receipt, not per-chain — else the emitter reorders the links under a single anchor. `tools/ordering.py` returns `ordered`/`forked`/`backdated`/`broken` offline.

**Residual risk.** Identical in shape to Threat #6: the chain makes equivocation **fork-evident**, not **witnessed**. A fork is caught only by a party holding **both** conflicting receipts — a same-round equivocation is invisible to a relier who saw only one. Driving both to a common observer needs a gossip/publication layer the spec requires **normatively** for high-stakes reliance but **cannot structurally enforce**. Detection cost drops to *a hash comparison by anyone holding the pair*, not to zero-witness — so ordering, like standing, stays **advisory**.

## Out-of-scope threats

- **Compromised issuer key.** Sigchain is only as good as the issuer's key custody. Defended by key rotation + revocation, not by this spec.
- **Compromised platform receipt.** If the platform issuing a receipt is itself compromised, `platform_receipt` evidence becomes worthless. Defended by reputation + multi-source evidence (`evidence[].minItems: 1` is the floor; real envelopes SHOULD include ≥2 evidence pointers from distinct sources for high-stakes claims).
- **Denial-of-service against revocation endpoints.** A `revocation_uri` that's intermittently unreachable creates the same indeterminate state as OCSP soft-fail. Defended by client-side fail-closed policy, not by this spec.
