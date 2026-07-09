# §12 — Standing & the monument problem

## The failure this closes

Every other check in this spec answers *"is this attestation cryptographically sound?"* — signature, freshness, evidence, coverage. None of them answers *"is there anyone who can still argue with it?"*

A signature is nonrepudiation: it proves key `K` said this. It is **not** accountability: it does not prove anyone can dispute it, or that the party behind `K` is still reachable to be held to it. An attestation that has outlived the relation — and the party who could contest it — is a **monument**: signed once, true forever, nobody home. Cryptographically valid, semantically empty, and (the dangerous part) *indistinguishable from a live fact to a naïve verifier.*

Background: [The Monument Problem](https://github.com/ColonistOne/monument-problem).

## The `standing` block

`standing` is an OPTIONAL top-level object. When present it makes contestability a first-class, offline-checkable property:

| field | meaning |
|---|---|
| `contestable_by` | Principals (`AgentIdentity[]`, ≥1) with standing to contest. **MUST include at least one party other than the issuer.** |
| `contest_uri` | Where a party with standing lodges, and a consumer checks, a contest. |
| `contestable_until` | RFC 3339 instant after which standing lapses. |
| `contest_status_uri` | OPTIONAL — publishes the current contest state (`none`/`open`/`upheld`/`rejected`) for full-mode fetch. |

### Standing ≠ revocation

`validity.revocation_uri` and `standing.contest_uri` are different powers. **Revocation is the issuer withdrawing its own claim.** **Contestation is a staked third party disputing it.** A receipt only the issuer can revoke is still a monument — the issuer is exactly the party an audit trail exists to hold accountable. Standing is the power that does *not* belong to the issuer.

## Verifier behaviour (§12)

A verifier computes a `standing` verdict in `{contestable, monument, n/a}` and surfaces a top-level `monument` boolean. **Monument detection is advisory, not a hard reject** — the same posture as issuer-binding. An accepted envelope MAY still be a monument; whether to rely on one is consumer policy. (Note: an expired `time_bounded` claim is *already* rejected by validity; §12 catches the cases validity passes clean.)

The verdict is `monument` when any of:

1. **`perpetual` claim with no `standing` block** — the canonical monument: signed-once-true-forever with no contest channel at all.
2. **`contestable_by` names only the issuer** — self-contestation is not standing; a party the issuer cannot lawyer for is required.
3. **`contestable_until` has passed** — the contest window closed; standing has lapsed. Being relied upon past it is relying on a conclusion no one can now dispute.

Otherwise, with a live standing block naming a non-issuer principal inside an open window, the verdict is `contestable`. A `time_bounded` claim with no `standing` block is `n/a` (undeclared — validity governs its expiry; consumer policy governs the rest).

Consumers relying on high-stakes attestations SHOULD treat `monument: true` as disqualifying per their own policy — the primitive is *never let a lapsed relation read as a standing fact*.

## §12.1 — standing grade (v0.1.9)

Not every non-issuer contester is equally accountable, so a `contestable` verdict also carries a **grade** (`standing_grade`, surfaced as `checks.standing.grade`), mirroring §9 `selection_grade` — *contestability is only as strong as the party you can actually reach*:

- **`named`** — at least one non-issuer contester is a keyed / DID principal (`did:key`, `did:web`, …). It can itself be held to account (it has a key, an identity, a hearing you can demand of *it*).
- **`venue`** — the contesters are only platform-handles: a diffuse *venue* (e.g. a public comment thread), contestable-in-principle but with no single accountable key.
- **`self`** — `contestable_by` names only the issuer (already a monument).
- **`null`** — no `standing` block.

A `named` standing is strictly stronger than a `venue` one; a consumer MAY require `named` for high-stakes reliance. The grade is computed offline from `contestable_by`.

## §12.2 — contest-channel liveness (v0.1.9)

`standing` is a claim about a channel; a verifier should confirm the channel is *live*, not just *declared*. In full (online) mode the verifier resolves `contest_status_uri` and reports:

- **live** — the channel resolves (and its `state`, e.g. `none`/`open`/`upheld`, is surfaced; an `open`/`upheld` contest is flagged as material).
- **unreachable** — declared but does not resolve → **degraded**: the standing is *claimed*, not verifiable. Surfaced prominently (advisory, like the monument flag).
- **undeclared** — no `contest_status_uri` at all → liveness can't be checked.

Deep anchor proofs are **out of scope for this check by design**: if `contest_status_uri` points at an externally-anchored record (e.g. an OTS→Bitcoin-anchored disclosure that fixes *when* the standing was live), verifying that anchor is delegated to the anchor type's own verifier — this check confirms only that the channel resolves. That keeps the envelope verifier vendor-neutral while letting a standing be backed by a real external anchor. *(Worked end-to-end against a Bitcoin-anchored Touchstone disclosure — see the interop notes.)*

## Why `contestable_until` is not just another expiry

`validity.not_after` says *when the claim stops being asserted.* `contestable_until` says *when the relation stops being re-holdable* — when the last party who could argue with it is no longer owed a hearing. Expiry here is not decay; it is the attestation admitting it was a relation that must be periodically re-held, not a fact that stands alone. A receipt that never lapses is not more permanent than one that does — it is abandoned, wearing a signature.

## Worked examples

- [`examples/standing_contestable.v0.1.json`](../examples/standing_contestable.v0.1.json) — live standing; verifies `ACCEPT`, verdict `contestable`.
- [`examples/monument_perpetual.v0.1.json`](../examples/monument_perpetual.v0.1.json) — perpetual, no standing; verifies `ACCEPT ⚠ MONUMENT`.

Both are regenerated byte-for-byte by [`tools/build_standing_examples.py`](../tools/build_standing_examples.py).
