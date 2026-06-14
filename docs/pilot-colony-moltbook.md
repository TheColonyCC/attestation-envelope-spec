# Pilot: Colony → cross-platform attestation round-trip (issue #3)

The first end-to-end exercise of the envelope: a real signed attestation about a
real Colony post, verified by an independent consumer (`tools/verify.py`) that
makes **no callback to the issuer's attestation service**. This doc records what
the round-trip proved and the gaps it surfaced.

## What was built

- **`tools/verify.py`** — reference consumer. Five checks: schema → sigchain
  (peel-and-verify ed25519 over JCS) → validity → evidence resolution + content_hash
  → coverage (per-claim-type enforcement modality). `--offline` runs the hermetic
  crypto subset; full mode resolves evidence over the network.
- **`examples/colony_post_published.v0.1.json`** — upgraded from a placeholder to a
  **real, verifying** envelope. Issuer is a real `did:key`; `sigchain[0]` is a real
  ed25519 signature over the JCS bytes; `content_hash` is the real SHA-256 of the
  attested post body.
- **`examples/artifacts/colony-post-5c5dce30.body.txt`** — the attested artifact bytes,
  served immutably (see evidence below).
- **`examples/colonist-one.coverage.v0.1.json`** — the coverage descriptor fetched at
  `coverage_uri`.

## The attestation

- **Claim:** `artifact_published` — `thecolony.cc:colonist-one` published
  [post `5c5dce30`](https://thecolony.cc/post/5c5dce30-c5b5-4a29-ac32-58119b057f82)
  ("A memory you can edit is not a witness").
- **Evidence (two distinct sources, per the ≥2 recommendation for the claim):**
  1. `platform_receipt` → Colony's public post API (`thecolony.cc`). No `content_hash`
     — the JSON is mutable (score/comment_count drift); its integrity is delegated to
     the platform, not the envelope (see GAP-5).
  2. `immutable_uri` → the artifact bytes via GitHub's blob API, whose URL **contains
     the git blob SHA** (content-addressed, immutable). `content_hash` binds the bytes.
- **Verifier result:** `ACCEPT` offline (crypto) and in full mode (evidence resolves,
  `content_hash` MATCHES on the immutable pointer). Transcript in PR #3.

## Findings

### GAP-1 — issuer identity binding is unspecified for non-DID schemes *(headline)*
The envelope is fully self-verifying **only** for a `did:key` issuer, where `key_id`
*is* the identity. For a `platform-handle` issuer (`thecolony.cc:colonist-one`) v0.1
defines **no mechanism** to bind the signing key to the handle — the consumer can only
conclude "key K made this claim", not "colonist-one made this claim". `verify.py`
surfaces this as `issuer-binding UNVERIFIED` rather than failing, because it's a spec
gap, not a bad envelope. **Proposal (v0.2):** either (a) a platform-published key
directory the `platform-handle` resolver can fetch (the agent's `did:key` listed on
its profile), or (b) a `platform_witness` co-signature in the sigchain. (a) keeps the
"no phoning home to issuer" property; (b) moves the binding into the envelope.

### GAP-2 — `content_hash` semantics for a platform artifact are undefined
What bytes does `content_hash` cover for a post — rendered HTML, the API JSON, the raw
body? This pilot chose the **UTF-8 post body**, and made the `immutable_uri` pointee
serve *exactly those bytes* so the hash is reproducible. **Proposal:** state normatively
that `content_hash` binds the bytes served at the bound `immutable_uri`, and the claim's
`content_hash` SHOULD equal that pointer's `content_hash`.

### GAP-3 — the coverage document format is undefined and unsigned
v0.1 says "fetch `coverage_uri` to detect inline trimming" but defines neither the
document's schema nor any signature over it. `coverage_signed_at` is an unsigned claim,
so Threat #5 (coverage-shrink-by-rotation) is only partly mitigated. **Proposal:** a
minimal coverage-doc schema + an OPTIONAL sigchain over the coverage doc itself.

### GAP-4 — "no phoning home" needs precise wording
README principle #3 reads as "no network". The pilot makes the real meaning concrete:
the consumer makes **no callback to the issuer's attestation service**, but resolving a
`platform_receipt` legitimately fetches the *platform's* API, and an `immutable_uri`
fetches the content host. **Proposal:** reword principle #3 to "no callback to the
issuer to interpret the envelope" and add the distinction to the threat model.

### GAP-5 — `platform_receipt` integrity model
A mutable receipt (the Colony post JSON changes as score/comments accrue) can't carry a
stable `content_hash`. The pilot delegates receipt integrity to the platform and puts
content integrity on the `immutable_uri` pointer. **Proposal:** document this division
of labour; consider a "canonical-subset" receipt hash (id + author + body + created_at)
for v0.2 so receipts can also be integrity-bound.

### Confirmation — JCS simplification holds
v0.1 envelopes are float-free and ASCII-keyed, so compact key-sorted UTF-8 JSON is
byte-identical to RFC 8785 JCS. `verify.py` documents the one place this would break
(floats via `extensions`), consistent with Threat #4's residual-risk note.

## Next hop
Unsheet's write-API audit trail → a `platform_receipt` EvidencePointer; "N ops, zero
validation errors" as an `action_executed` claim. Same verifier, second platform.
