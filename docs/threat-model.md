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

**Residual risk.** The consumer needs to actively check coverage; the envelope doesn't force this. Worth a v0.2 enforcement-modality column in the README that says "for X claim type, consumers MUST fetch coverage_uri before relying".

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

## Out-of-scope threats

- **Compromised issuer key.** Sigchain is only as good as the issuer's key custody. Defended by key rotation + revocation, not by this spec.
- **Compromised platform receipt.** If the platform issuing a receipt is itself compromised, `platform_receipt` evidence becomes worthless. Defended by reputation + multi-source evidence (`evidence[].minItems: 1` is the floor; real envelopes SHOULD include ≥2 evidence pointers from distinct sources for high-stakes claims).
- **Denial-of-service against revocation endpoints.** A `revocation_uri` that's intermittently unreachable creates the same indeterminate state as OCSP soft-fail. Defended by client-side fail-closed policy, not by this spec.
