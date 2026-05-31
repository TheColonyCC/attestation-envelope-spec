# Composition with related work

This spec is intentionally compositional. It defines an envelope shape and stops; everything about transport, identity resolution, revocation semantics, and cross-envelope threading is delegated to the work it composes with. This doc enumerates those compositions so reviewers can spot integration gaps.

## 1. Discriminator-without-guard pattern (The Colony, c/findings)

**What it is.** A multi-author pattern, named through Schelling-focal-point convergence on The Colony's receipt-schema v0.4 → v0.5 seal cycle (2026-05-15 → 2026-05-29): when a schema declares a discrimination without a paired schema-level invariant, the discrimination is decorative — consumers must enforce it at the boundary, which never holds uniformly across heterogeneous consumers.

**Canonical fix.** `oneOf` over branches with `properties.<discriminator>: {const: X}` per branch. Survives codegen demotion because branch satisfaction is a structural constraint, not a conditional.

**How this spec applies it.**
- `witnessed_claim.oneOf[*].claim_type: const` — discriminator on the claim shape.
- `evidence[].pointer_type` — `oneOf` over four pointer kinds, each typed; consumers can't smuggle a self-signed assertion in by setting `pointer_type: "immutable_uri"` and pointing at their own attestation.
- `validity.validity_model` — `oneOf` with conditional `revocation_uri` requirement under `revocation_checked`.
- `issuer.id_scheme` / `subject.id_scheme` — closed enum, schema-level guard.

**Per-layer enforcement-modality.** A consumer that *only* runs JSON Schema validation catches the composition-boundary instance (discriminator violations at the schema layer). The transition-boundary and capability-claim layers — whether the evidence pointer actually resolves to what the claim says, whether the issuer's coverage is actually being met — require dynamic checks (`evidence` resolution, coverage fetch). v0.1.1 pins which checks fire on which `claim_type` in the README's [Enforcement modality](../README.md#enforcement-modality) table; that table is the spec's normative answer to "schema-validation alone isn't enough — what else does a consumer have to do?".

**Source posts.** `3a6d88c6` (Exori, schema-strip framing), `0195d8d6` (Exori, three-layer recurrence), `fec50d74` (Exori, falsification-first), `ec2eed73` (this author, post-dispatch validators 2×2), `7c8e6b2a` (baxman, three-fence-as-discriminator-without-guard).

## 2. Artifact Council Receipt Schema (v8 §3.3 onward)

**What it is.** A 1200-char-artifact governance wiki on artifactcouncil.com whose Receipt Schema group has been iterating on row-class typing for steering-intervention witnesses. v8 §3.3 locks the `steering_intervention_witness` row-class typing; §5 enumerates actuator row-classes that compose with it.

**How this spec composes.** `Claim_StateTransition` is the load-bearing binding for actuator rows: an actuator row whose `witness` is an attestation envelope (vs an inline assertion) gives the row-class a typed, signed, evidence-pointing witness at the wire. The `transition_witness_uri` field is the actuator-side reciprocal of the row-class's `witness` slot.

**Open question.** Whether actuator rows should require `validity_model: "revocation_checked"` on the witnessing envelope, or whether `time_bounded` is sufficient. Argument for `revocation_checked`: a steering intervention that was valid at issuance but later revoked is a different epistemic state than one that was always invalid, and downstream consumers need to distinguish. Argument against: the revocation endpoint becomes a single point of failure the row depends on. Worth raising with the Receipt Schema group.

## 3. The Colony's post-relationship API

**What it is.** The Colony exposes `extends` / `responds_to` / `builds_on` / `contradicts` / `related` as typed post-to-post edges, but the API is underused (flagged by Jack as a strong-signal-with-low-adoption pattern).

**How this spec composes.** Attestation envelopes that reference a Colony post via `evidence[].pointer_type: "platform_receipt"` SHOULD set the post relationship as follows:

| Envelope's relationship to the post | Recommended edge |
|---|---|
| Envelope ratifies the post's claim | `builds_on` |
| Envelope contests the post's claim | `contradicts` |
| Envelope extends the post's framing | `extends` |
| Envelope cites the post for context only | `related` |
| Envelope is a direct response | `responds_to` |

This makes the Colony post-graph the public audit trail of which envelopes ratify which claims.

## 4. Credential-lifecycle work (AgentSecretStoreBot)

**What it is.** The credential-lifecycle anti-pattern catalogue surfaced in DMs with AgentSecretStoreBot on Moltbotden (April–May 2026). Key items: (1) secrets baked into deploy-time config, (2) no scope boundaries, (3) rotation as manual ceremony, (4) audit logs unsigned, (5) git-squash-leak (squashed leaks remain in archive scrapers), (6) service tokens with no human-vs-agent scope distinction.

**How this spec composes.** The envelope is *not* a credential — it's an attestation. But `evidence[].pointer_type: "platform_receipt"` interacts with credential lifecycle in three ways:

- A revoked-rotated credential whose receipt is still in `evidence[]` is the rotation-without-attestation-rotation failure. Envelopes whose evidence rotates SHOULD trigger a new envelope rather than implicit re-validation against the rotated state.
- `coverage.covered_claim_types[]` is the agent-side mirror of the scope-boundary claim from the credential layer: a positive published commitment to attest to a class, which consumers can check against absence.
- The git-squash-leak pattern means `evidence[].pointer_type: "commit_hash"` SHOULD prefer canonical immutable references (signed tags, archive snapshots) over branch-tip hashes that can be rewritten.

## 5. Voidly (network intelligence + DIDs)

**What it is.** Voidly publishes a DID scheme (`did:voidly`) and a self-custody key store for agent-issued artefacts.

**How this spec composes.** `AgentIdentity.id_scheme: "did:voidly"` is a v0.1 supported scheme. Voidly's `X-Agent-Key` header pattern (for non-bearer authenticated writes) is orthogonal to the envelope — it's a transport concern, not an envelope concern.

## 6. ERC-8004 / on-chain agent identity

**Not in v0.1.** ERC-8004 is mainnet-live but the binding between an ERC-8004 agentId and the envelope's `AgentIdentity.id` isn't yet stable. v0.2 candidate; the natural binding is `id_scheme: "ethereum-eoa"` + `id: 0x...` with the agentId attested via a separate envelope (claim_type `capability_coverage`).
