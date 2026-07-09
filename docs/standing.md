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

## §12.3 — externally-anchored standing (v0.1.11)

§12.2 confirms a contest channel *resolves*. §12.3 goes further: it lets standing be **checkable by a stranger without trusting the issuer or the log**, by binding it to an external append-only anchor (OpenTimestamps → Bitcoin). Optional `standing.anchor`, verified by [`tools/standing_anchor.py`](../tools/standing_anchor.py). Still advisory — it enriches the verdict, never flips accept/reject.

The design (worked out with reticuli/[Touchstone](https://touchstone.cv)) turns on a distinction:

- **Lower bound — the attestation existed.** Anchoring an attestation entry proves it was live *no later than* a Bitcoin block time. This is a Merkle-inclusion proof against a checkpoint whose root is OTS→Bitcoin-anchored: fold the entry to the checkpoint root, confirm the checkpoint's OTS digest commits its own head. Non-backdatable. Offline-verifiable when the proof is inlined.
- **Upper bound — it is still live (uncontested).** A lower bound can *never* prove the thing standing actually claims: *no contest has since been filed.* Absence of a contest is a negative, and you cannot prove a negative against a channel you don't control. So `standing = live` is unreadable from the attestation's own anchor alone.

**The fix is to anchor the contest channel too.** Standing is live iff (attestation entry included by checkpoint *N*) **and** (no contest entry in the contest recorder up to its latest checkpoint). Both legs Bitcoin-anchored, so absence becomes *evidence* rather than *assertion* — `contest_uri` stops being declarative and points at an append-only anchored recorder a verifier can actually read.

**The honest residual (surfaced, not hidden).** The contest leg proves no-contest only *as-of the latest contest checkpoint*, never *as-of now* — there is an irreducible blind window equal to the checkpoint cadence. So freshness is **not** a boolean `live`. It is a `provable_through` Bitcoin instant plus an issuer-committed `max_checkpoint_lag_s`. If the newest fetchable contest checkpoint is older than that bound, the verifier reads standing **STALE, not INVALID** (advisory, consistent with the rest of the subsystem). You cannot out-run the anchor cadence; you can only bound it and say so.

**Trust boundary** (stated in-module, because a check is only worth what it costs the checked party to fake). It **proves**: Merkle inclusion, that the checkpoint's OTS anchor commits *this* checkpoint's head (not some other digest), checkpoint chain-linkage, and the freshness arithmetic. It **delegates** (documented, not silently skipped): OTS→mainnet confirmation that block *H* is canonical Bitcoin (an SPV / `verify_anchor` pass — offline the state is `anchored`, and the note says mainnet re-derivation is deferred), and the checkpoint `recorder_sig` (verified by the checkpoint feed's own Nostr-mirrored verifier).

Verifier states: `anchored` (lower bound proven, and offline or contest-clear-and-fresh), `stale` (clear but past the lag bound), `contested` (a contest is anchored against this envelope), `unanchored` (anchor present but no lower bound), `unsupported` (unknown `profile`), `n/a` (no anchor).

**Who controls the contest channel (Threat #6).** The absence-of-contest read is only as trustworthy as the party that decides whether a contest *can be recorded*. If the contest recorder is the same recorder that anchors the attestation, absence is self-attested — the issuer can withhold a filed contest and the scan still reads clean. So the verifier also returns `contest_control ∈ {issuer, independent-declared, undeclared}`: `issuer` is the `self` grade for the contestability axis and should be read as *no meaningful upper bound* (just as `standing_grade: self` means no meaningful contestability). Split-view resistance makes *retroactive deletion* of a recorded contest detectable, but not *append-refusal* — that needs an independently-operated recorder, a governance property the envelope points at but can't enforce. Full write-up: [Threat #6](threat-model.md#threat-6--issuer-controlled-contest-channel-absence-of-contest-censorship).

## Why `contestable_until` is not just another expiry

`validity.not_after` says *when the claim stops being asserted.* `contestable_until` says *when the relation stops being re-holdable* — when the last party who could argue with it is no longer owed a hearing. Expiry here is not decay; it is the attestation admitting it was a relation that must be periodically re-held, not a fact that stands alone. A receipt that never lapses is not more permanent than one that does — it is abandoned, wearing a signature.

## Worked examples

- [`examples/standing_contestable.v0.1.json`](../examples/standing_contestable.v0.1.json) — live standing; verifies `ACCEPT`, verdict `contestable`.
- [`examples/monument_perpetual.v0.1.json`](../examples/monument_perpetual.v0.1.json) — perpetual, no standing; verifies `ACCEPT ⚠ MONUMENT`.
- [`examples/standing_bitcoin_anchored.v0.1.json`](../examples/standing_bitcoin_anchored.v0.1.json) — a live standing block carrying a §12.3 `anchor`; verifies `ACCEPT` and reports `standing.anchor = anchored`. The inclusion proof is **real**: entry seq 1 of Touchstone recorder `rec_01kvyp…`, whose Merkle root is checkpoint 8, committed to **mainnet Bitcoin block 955295**.

All three are regenerated byte-for-byte by [`tools/build_standing_examples.py`](../tools/build_standing_examples.py).
