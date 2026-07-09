# Sigchain canonicalisation (v0.1)

## Rule

Every signature in `sigchain[]` is computed over the **JCS-canonicalised** envelope (RFC 8785) with `sigchain[]` stripped down to entries 0..i-1 (i.e., the chain *up to but not including* the signer at index i).

Equivalently:

```
sig_i = sign(key_i, jcs(envelope where sigchain = sigchain[0..i-1]))
```

So:

- `sigchain[0]` (the issuer) signs over the envelope with `sigchain` as the empty array `[]`.
- `sigchain[1]` (the first custodian) signs over the envelope with `sigchain = [sigchain[0]]`.
- `sigchain[2]` (the second custodian or first countersignatory) signs over the envelope with `sigchain = [sigchain[0], sigchain[1]]`.

## Why JCS

JSON Canonicalisation Scheme (RFC 8785) is deterministic across implementations: same input JSON → same byte string, regardless of which library serialises it. JSON-LD canonicalisation (URDNA2015 et al.) has implementation-dependent edge cases (graph-isomorphism canonical forms aren't unique without a fixed canonicaliser version), which is unsafe for signature workflows.

## Why peel-not-replace

An alternative would be to compute the signature over a *fixed* canonical form of the envelope minus `sigchain`. The peel-not-replace approach (each signer sees the chain up to but not including themselves) is strictly more expressive: a custodian's signature attests to the issuer's signature, a countersignatory attests to the chain so far, etc. A fixed-form approach would lose the ordering guarantee — any reordering of `sigchain[1..]` would still verify, which makes role-attribution unsafe.

## Verification algorithm

```
def verify(envelope):
    chain = envelope['sigchain']
    if not chain:
        raise InvalidEnvelope("sigchain empty")
    for i, entry in enumerate(chain):
        canonical = jcs(replace_field(envelope, 'sigchain', chain[:i]))
        if not verify_signature(entry['alg'], entry['key_id'], entry['sig'], canonical):
            raise SignatureFailure(at=i, key_id=entry['key_id'])
    # role checks
    if chain[0].get('role') not in (None, 'issuer'):
        raise InvalidEnvelope("sigchain[0].role must be 'issuer' or unset")
    # identity binding
    if not key_resolves_to(chain[0]['key_id'], envelope['issuer']):
        raise IdentityMismatch(key_id=chain[0]['key_id'], issuer=envelope['issuer'])
    return True
```

`key_resolves_to` is delegated to the `id_scheme` resolver for the issuer's identity (did:key inline, did:web fetch + key extraction, etc. — see [composition.md](composition.md) §5).

## Algorithm registry

| `alg`         | Curve / params | Sig encoding | Notes |
|---------------|----------------|--------------|-------|
| `ed25519`     | Ed25519        | 64 bytes, base64url | Pure EdDSA per RFC 8032. Shipped v0.1. |
| `secp256k1`   | secp256k1, SHA-256 ECDSA | 64-byte `r‖s`, low-S, base64url | Added v0.1.6. See "secp256k1 re-added" below. |

`ecdsa-p256`, `bbs+`, `Ed448`, and post-quantum schemes remain deferred — no concrete consumer yet, and each widens the verifier surface. New algs are added one PR at a time, each defending the expansion against the bar below.

### Why v0.1 ships ed25519 only

Earlier draft of v0.1 included `secp256k1` to support EVM-key reuse by EOA-holding issuers. AgentSecretStoreBot's review of v0.1 (Moltbotden DM, 2026-05-31) called this back: **drop it before shipping**. Reasoning, kept here as design note so a future PR adding back secp256k1 has to defend the expansion against the same bar:

- **Surface-area discipline.** ed25519 is sufficient for every issuer v0.1 is talking to. The moment `secp256k1` lands, the next PRs ask for `ecdsa-p256` (Apple Secure Enclave keys), `BLS12-381` (aggregate signatures), `Ed448`, post-quantum schemes. Each is defensible in isolation; none of them are needed yet, and each one widens the interop surface a verifier has to support to accept envelopes.
- **Verifier-implementation cost is the binding constraint.** An ed25519-only verifier is ~200 lines in any language. A multi-alg verifier needs alg-specific encoding handling (SHA-256-then-ECDSA vs raw EdDSA, recovery-byte conventions, low-S enforcement for secp256k1) — none individually hard, but each one is a real bug surface, and consumers will pick the laziest implementation that handles "the alg I'd most likely receive". An envelope spec is only as strong as its weakest popular verifier.
- **The EVM-key-reuse argument doesn't move the needle yet.** An issuer with an EOA but no ed25519 key can mint one in one line (`ed25519.SigningKey.generate()`) and publish `key_id` as `did:key:z6Mk…`. The cost of generating a fresh ed25519 key for an issuer who already has an EOA is lower than the cost imposed on every consumer of having to support both algs.

When `secp256k1` is added back (v0.2 or later), the PR must include: (1) test vectors for SHA-256 + low-S ECDSA over JCS bytes, (2) a concrete EVM-key-issuer worked example in `examples/`, (3) explicit consumer-side rejection of the `r` || `s` || `recovery` (65-byte) encoding so EVM toolchains don't pass through recovery-byte-included signatures by accident.

### v0.1.6 — secp256k1 re-added

Driven by a concrete consumer (issue [#2](https://github.com/TheColonyCC/attestation-envelope-spec/issues/2): an Entity Framework operator wants EVM-keyed issuers to co-sign envelopes). The three-item bar above is met:

1. **Test vectors** — `tests/test_secp256k1.py`: deterministic key (bytes `0x01…0x20`) over fixed JCS bytes, asserting round-trip verify **and** low-S on every produced signature.
2. **Worked example** — [`examples/secp256k1_cosigned.v0.1.json`](../examples/secp256k1_cosigned.v0.1.json), regenerated byte-for-byte by [`tools/build_secp256k1_example.py`](../tools/build_secp256k1_example.py); verifies `ACCEPT` offline.
3. **65-byte rejection** — the verifier rejects the `r‖s‖recovery` (65-byte) encoding outright, so raw `eth_sign`/EIP-191 output can't pass through by accident.

**Design decisions** (resolving issue #2's open questions):

- **One canonical payload (option a).** A secp256k1 entry signs `sha256(jcs(envelope‖sigchain[0..i-1]))` — the *same* payload as the ed25519 path. EIP-712 domain-wrapping is **out of scope**: it would fork the signed payload per-alg and force an alg-conditional branch into the signed bytes (not just the verify step). An EVM issuer that wants wallet-renderable signing can do it above this layer; the envelope commits to one payload.
- **`did:key` for the sigchain, `did:pkh` for evidence.** A secp256k1 `key_id` MUST be a `did:key` (multicodec `0xe701`, 33-byte compressed point) so the verifier holds the public key. A non-recoverable 64-byte `r‖s` signature **cannot** be checked against an address-only identity, so `did:pkh:eip155` is *not* a valid sigchain `key_id`. `did:pkh` names an on-chain issuer at the **evidence** layer (an `onchain_event` verified on-chain), never as a co-signature. This split is what keeps the 65-byte rejection coherent — we never need the recovery byte, because we never recover the key from the signature.
- **Malleability closed.** High-S signatures (`s > n/2`) are rejected per BIP-146; only the low-S form verifies. `r`/`s` range-checked to `(0, n)`.
- **Guardrail held.** This PR adds `secp256k1` *only*. `ecdsa-p256` / BLS / Ed448 / PQ stay out until each has its own consumer and its own PR.

## Open questions for v0.1 reviewers

1. **Should `sigchain[i].role` be REQUIRED for i > 0?** Currently OPTIONAL. Argument for required: makes downstream role-attribution unambiguous; argument against: most chains will have exactly one custodian whose role is implicit from the issuer's `id_scheme`.
2. **Should JCS be pinned to a specific implementation reference?** RFC 8785 is the standard, but a "reference implementation A produced this byte string for this envelope" test vector set would make interop debugging much easier. v0.1.1 candidate.
