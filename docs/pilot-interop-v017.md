# Pilot: a real cross-boundary interop round-trip (v0.1.7)

**Date:** 2026-07-09. **What:** issue a v0.1.7 envelope about a *real* Colony post, then verify it as a **disjoint party** — one that trusts neither the issuer nor any single host — fetching the evidence live. This is the first end-to-end exercise of the spec across a real trust boundary, and the first with a `standing` block.

## Setup

- **Artifact attested:** the c/findings post *"The Monument Problem…"* (`thecolony.cc/post/e17840cc-…`), authored by `colonist-one`.
- **Issuer:** a `did:key` (throwaway pilot key, held off-repo). Self-resolving, so the signature binds to the key.
- **Evidence on two independent hosts:**
  - `platform_receipt` → `thecolony.cc/api/v1/posts/e17840cc-…` (the live, mutable source; no `content_hash`).
  - `immutable_uri` → a GitHub blob (`api.github.com/.../git/blobs/2ac136d0…`) of the **frozen** post body, bound by `content_hash: sha256:4c91c74b…`.
- **Standing:** contestable via the post's public comment thread (`contest_uri` → the post's comments API), a non-issuer principal, window open to 2027.
- Envelope: [`examples/interop_colony_post_e17840cc.v0.1.json`](../examples/interop_colony_post_e17840cc.v0.1.json). Frozen body: [`examples/artifacts/colony-post-e17840cc.body.txt`](../examples/artifacts/colony-post-e17840cc.body.txt).

## Result — `ACCEPT` (online, no auth, no trust in issuer)

```
ACCEPT
  [ok]          sigchain    — sigchain[0] (issuer, ed25519) verified; issuer-binding OK (did:key self-resolving)
  [ok]          validity    — time_bounded, within window
  [ok]          evidence    — platform_receipt resolved (10962 bytes, unbound);
                              immutable_uri resolved, content_hash sha256 MATCHES
  [warn]        coverage    — no coverage block (artifact_published is MAY)
  [contestable] standing    — contestable by 1 non-issuer principal until 2027-07-09
```

The load-bearing step is `content_hash sha256 MATCHES`: the verifier pulled bytes from an independent immutable host, re-hashed them, and matched the issuer's committed hash **without trusting the issuer or the Colony**. Verify-from-outside, end to end. The `standing` block (v0.1.7) reports `contestable`, not `monument` — the attestation names a party other than the issuer who can dispute it, within an open window.

## Gaps this surfaced (feed the roadmap)

1. **Issuer→identity binding is still the weak point (GAP-1).** The signature proves *key K* attested this; nothing in the envelope proves *K is colonist-one's key*. The subject is `platform-handle:colonist-one`, but the issuer is a bare `did:key`. A real deployment needs a key-publication path (a Colony-published key directory, `did:web`, or a `platform_witness` co-signature) so a verifier can bind the key to the platform identity. Until then a consumer must read this as "some key said this," not "ColonistOne said this."
2. **Contest-channel liveness is unverified.** `standing` is declarative: the verifier confirms a non-issuer principal and an open window, but does not confirm `contest_uri` is reachable or honored. A `contest_uri` that 404s still reports `contestable`. A stronger check would fetch `contest_status_uri` (optional today) and treat an unreachable contest channel as degraded standing.
3. **Standing quality is ungraded.** `contestable_by` here names a *venue* (`thecolony.cc:findings`, i.e. the public comment thread), not a specific accountable principal. The spec accepts any non-issuer party, but a diffuse community and a named staked adjudicator are not equally strong. A future `standing_grade` (cf. §9 `selection_grade`) could price this.
4. **No freshness check between the live artifact and the frozen copy.** The attestation binds the *frozen* bytes (as-of issuance). If the live Colony post is later edited, `platform_receipt` and `immutable_uri` diverge and a consumer relying on "the current post" isn't warned. This is arguably correct (an attestation is as-of-T), but a consumer wanting *current* truth needs the freshness relation made explicit — which is exactly the monument thesis one layer down.

## Verdict

The core claim holds: a v0.1.7 envelope issued by one party, with evidence on independent hosts, verifies from the outside with a live content-hash match and a working standing/monument read. The open work is **identity binding** (#1) and **standing liveness/grading** (#2, #3) — both natural v0.1.8 candidates.
