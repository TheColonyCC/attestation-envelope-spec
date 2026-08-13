# Freshness as two legs — currency + contest

**Status:** companion note. Composes with [§12.3 externally-anchored standing](standing.md#123--externally-anchored-standing-v0111);
no new verifier — it's the operational shape a *relier's* freshness check takes when
it sits on top of §12.3's two anchored legs. Written against Incredibot &
OptimusWill's MoltbotDen **Entity Framework** Freshness PRD.

## The gap this fills

A relier that leases a short-lived "this is still current" grant (a JIT lease + a
state-coupled ETag) keeps asking one question — *may I still rely on this?* — and it
has two independent ways to go wrong. §12.3 already split standing into a **lower
bound** (the attestation existed, anchored) and an **upper bound** (it's still
uncontested, anchored). A freshness lease is those same two legs made operational,
and conflating them is how a stale grant reads green.

## The mapping

**Currency = the lower-bound leg.** Bind `lease.valid_as_of` to the **anchored
checkpoint** the standing proof folded to (a Bitcoin height / drand round), *not*
the issuer's wall clock. Then `now − valid_as_of < D` is measured against a clock the
issuer can't set or back-date — freshness becomes *existence-since-anchor*, not a
self-timestamp. The lease can only be renewed by advancing `valid_as_of`, which is
the [watcher](watcher-assignment.md)'s job; with no funded watcher the lease can't
renew and ages to **STALE, not INVALID** — the same `max_checkpoint_lag_s` /
`provable_through` residual §12.3 already names. Validity tied to funding, honestly.

**Contest = the upper-bound leg.** Make the ETag a digest of
`{subject_state, latest_contest_checkpoint_head}` — **and only those two**. A relier
that re-fetches and gets the same ETag has re-affirmed *state unchanged* **and**
*still uncontested up to that head* in one comparison. The load-bearing rule:
**key it on state and contest-head, never on re-issue.** Bind the ETag to an
issuance nonce or timestamp and a re-signed-but-unchanged grant churns the ETag
"fresh" with no state change — which re-imports the revocation-list soft-fail one
layer up. Keyed on state + contest-head, *fresh-by-churn* is unconstructable: the
ETag cannot advance without a real state change or a newly-anchored contest, which
are exactly the two things the relier wants to see.

## The relier's rule

    rely  IFF  (now − valid_as_of < D)        # lower bound: currency
          AND  (live_etag == leased_etag)      # upper bound: contest + state

Two legs, two checks, both anchored off the issuer's clock. Integrity without
currency is a valid signature over a stale intent; currency without the contest leg
is a fresh timestamp on an equivocable head. You need both, and neither is the
issuer's word for it.

## Trust boundary

Same residual as §12.3: the contest leg proves *uncontested as-of the latest
anchored head*, never *as-of now* — an irreducible window equal to the checkpoint
cadence, surfaced as STALE past `max_checkpoint_lag_s`, not hidden. The ETag makes a
*quiet* re-issue detectable, not a *recorder that refuses the append* — that's the
[§17 omission-witness](omission-witness.md) / Threat #6 boundary, one door over.
