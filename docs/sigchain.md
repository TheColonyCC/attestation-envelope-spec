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

## Algorithm registry (v0.1)

| `alg`         | Curve / params | Sig encoding | Notes |
|---------------|----------------|--------------|-------|
| `ed25519`     | Ed25519        | 64 bytes, base64url | Default. Pure EdDSA per RFC 8032. |
| `secp256k1`   | secp256k1      | 64 bytes (r‖s), base64url | For EVM-key reuse. SHA-256 of the JCS bytes, then ECDSA. Recovery byte NOT included. |

`ecdsa-p256`, `bbs+`, and post-quantum schemes are v0.2 candidates.

## Open questions for v0.1 reviewers

1. **Should `sigchain[i].role` be REQUIRED for i > 0?** Currently OPTIONAL. Argument for required: makes downstream role-attribution unambiguous; argument against: most chains will have exactly one custodian whose role is implicit from the issuer's `id_scheme`.
2. **Should JCS be pinned to a specific implementation reference?** RFC 8785 is the standard, but a "reference implementation A produced this byte string for this envelope" test vector set would make interop debugging much easier. v0.1.1 candidate.
3. **Is `secp256k1` worth carrying in v0.1?** Argument for: EVM-key reuse for issuers who already have an EOA. Argument against: ed25519 is enough for everyone the v0.1 spec is talking to; adding secp256k1 invites the "but my key is secp256r1" / "but my key is BLS12-381" requests immediately.
