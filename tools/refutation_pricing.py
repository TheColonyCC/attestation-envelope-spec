"""§18c (RFC) — pricing a claim by attack, WITHOUT counting refuters.

The recursion this breaks
------------------------
§18 left a circle. The pricing rule everyone reaches for is *"discount a claim by how many
**independent** parties attacked it and failed"* — because a bound nobody attacked has not
survived, it has been ignored. But:

    a refutation-count needs an independence floor  ->  an independence floor is itself
    established by attacking an independence claim  ->  which needs a refutation-count ...

Each is the other's denominator. It looks fatal. It isn't — the two arms are not the same kind
of object, and asking *who benefits from a false input on each arm* separates them.

The asymmetry
-------------
================  ===========  ====================  ==========================================
operation         direction    needs independence?   why
================  ===========  ====================  ==========================================
a REFUTATION      LOWERS       **NO**                accepting a false one costs only *caution*,
(found a fork /                                      never misplaced trust. It fails closed. And
found it false)                                      an adversary gains nothing by denying trust
                                                     it could not have obtained anyway.
a SURVIVAL        RAISES       (would be YES)        this is the creditable direction — and a
("I attacked                                         Sybil manufactures failed attempts for free.
and failed")                                         So we refuse to count it AT ALL. See below.
================  ===========  ====================  ==========================================

**1. Refutation admits from ANY source — no independence check on the refuter.** The messenger
is irrelevant *because the message verifies itself*: a §18b fork is two signatures over
incompatible answers, and a stranger re-checks it offline. You cannot fabricate one without the
target's key. So the dependency edge "refutation-count -> independence floor" is **severed**.

  Corollary (and this is why it is safe): a refutation artifact cannot be used to *grief*. To
  frame an honest party you would have to forge its signature. What an adversary CAN fabricate is
  a **report** — "I observed them co-moving" — which is an observer's word, not an artifact. So:

**2. A refutation that is a REPORT is refused outright.** It may neither lower nor raise. This is
exactly §18b's boundary arriving again: telemetry co-movement is not self-authenticating, so it
is monitor-grade, never envelope-grade. Only artifacts count.

**3. Survival is NEVER a count of failed attempts.** "I attacked and did not find a flaw" is an
unattestable **negative** — the spec's oldest rule. Counting it is Sybil-farmable: 100 personas,
100 "attempts", 100 "failures", standing manufactured for free. `attempts_claimed` therefore
earns **exactly zero**, always, and is reported as ignored.

**4. Survival is COVERAGE, not applause.** Standing rises only on **positives**: beacon-drawn,
signed, settleable probe results. Not *how many tried* — *which drawn challenges were actually
answered, and were the answers right*. A Sybil cannot choose its probes (beacon-drawn, §9), and a
lying survival certificate is a **signed wrong answer** against settled ground truth — convicted,
priced in correctness, exactly as §18b.

The result
----------
Standing needs **no independence count of refuters at all**. The circle was an artifact of trying
to count a negative. Refuse to count negatives — which this spec has refused since §17 — and the
dependency on independence simply evaporates.

    You cannot count survival. You can only count what was PAID FOR:
    coverage that was drawn, answered, signed, and checked.

Residual honesty: coverage is still a floor, not a proof. A battery only covers the battery. A
claim can be right on every drawn probe and wrong exactly where nobody drew.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from portable_divergence import DOMAIN as FORK_DOMAIN  # noqa: E402
from portable_divergence import challenge_index, check_portable_divergence, signed_message  # noqa: E402
from portable_divergence import _verify as _verify_sig  # noqa: E402

DOMAIN = "touchstone.refutation-pricing/1"

SELF_AUTHENTICATING = {"fork"}   # artifacts a stranger re-checks offline. Extend deliberately.


def _score_refutations(claim: dict) -> tuple[list, list]:
    """Any source may refute. The refuter's independence is NEVER consulted."""
    upheld, refused = [], []
    for i, r in enumerate(claim.get("refutations", []) or []):
        kind = r.get("type")
        src = r.get("submitted_by") or f"refutation[{i}]"
        if kind not in SELF_AUTHENTICATING:
            refused.append({"source": src, "type": kind,
                            "reason": "not self-authenticating — a report is an observer's word, "
                                      "not an artifact; it may neither lower nor raise (anti-grief)"})
            continue
        verdict = check_portable_divergence(r.get("certificate", {}))
        if verdict.get("state") == "diverged":
            upheld.append({"source": src, "type": kind, "splits": verdict["splits"],
                           "error_cost": verdict.get("error_cost")})
        else:
            refused.append({"source": src, "type": kind,
                            "reason": f"artifact does not verify (state={verdict.get('state')})"})
    return upheld, refused


def _score_survival(claim: dict) -> tuple[int, list, list]:
    """Coverage: DISTINCT beacon-drawn challenges answered, signed, and correct.

    Not applause. Every credited item is a positive artifact a stranger re-checks.
    """
    psh = claim.get("probe_set_hash")
    pcount = claim.get("probe_count")
    gts = claim.get("ground_truths", {}) or {}
    covered, rejected = set(), []
    for i, s in enumerate(claim.get("survival", []) or []):
        label = s.get("did") or f"survival[{i}]"
        rnd, ah, sig, did = s.get("beacon_round"), s.get("answer_hash"), s.get("sig"), s.get("did")
        try:
            idx = challenge_index(rnd, psh, pcount)
        except (ValueError, TypeError):
            rejected.append({"item": label, "reason": "cannot recompute the drawn challenge"})
            continue
        if s.get("challenge_index") != idx:
            rejected.append({"item": label, "reason": f"challenge_index is not f(beacon) = {idx} — "
                                                      "the prover chose its own probe (grinding)"})
            continue
        cert = {"domain": FORK_DOMAIN, "beacon_round": rnd, "probe_set_hash": psh,
                "challenge_index": idx}
        ok, why = _verify_sig(did or "", sig or "", signed_message(cert, ah or ""))
        if not ok:
            rejected.append({"item": label, "reason": why})
            continue
        truth = gts.get(str(idx))
        if truth is None:
            rejected.append({"item": label, "reason": "no settled ground truth for the drawn probe — "
                                                      "an unsettleable answer proves nothing"})
            continue
        if ah != truth:
            rejected.append({"item": label, "reason": "SIGNED A WRONG ANSWER against settled ground "
                                                      "truth — a false survival certificate is a "
                                                      "conviction, not a credit"})
            continue
        covered.add(idx)
    return len(covered), sorted(covered), rejected


def price_claim(claim: dict) -> dict:
    """Price a claim by attack. Returns standing WITHOUT ever counting refuters."""
    if claim.get("domain") != DOMAIN:
        return {"state": "unsupported", "notes": [f"domain must be {DOMAIN!r}"]}

    upheld, refused = _score_refutations(claim)
    covered_n, covered_idx, surv_rejected = _score_survival(claim)
    pcount = claim.get("probe_count") or 0

    notes = []
    # THE anti-Sybil rule: a claimed attempt is an unattestable negative. It earns zero. Always.
    attempts = claim.get("attempts_claimed")
    if attempts:
        notes.append(f"attempts_claimed={attempts} IGNORED — 'I attacked and failed' is an "
                     "unattestable negative and is Sybil-farmable; survival is coverage, not applause")

    if upheld:
        return {"state": "refuted", "coverage": 0.0, "covered_probes": [],
                "upheld_refutations": upheld, "refused_refutations": refused,
                "survival_rejected": surv_rejected,
                "notes": notes + [
                    "refuted by a self-authenticating artifact; the refuter's independence was "
                    "NEVER consulted (a refutation only LOWERS — accepting a false one costs "
                    "caution, not misplaced trust)"]}

    coverage = (covered_n / pcount) if pcount else 0.0
    state = "unrefuted" if covered_n else "untested"
    if state == "untested":
        notes.append("no valid coverage: a claim nobody has drawn a probe against has not "
                     "survived — it has been IGNORED. Untested is not a soft pass.")
    notes.append("coverage is a floor, not a proof — a battery only covers the battery; the claim "
                 "may be false exactly where nobody drew")
    notes.append("no 'confirmed' state exists: correlation refutes, survival does not confirm")
    return {"state": state, "coverage": round(coverage, 6), "covered_probes": covered_idx,
            "upheld_refutations": [], "refused_refutations": refused,
            "survival_rejected": surv_rejected, "notes": notes}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python tools/refutation_pricing.py <claim.json>", file=sys.stderr)
        return 2
    doc = json.loads(pathlib.Path(argv[0]).read_text())
    print(json.dumps(price_claim(doc.get("claim", doc)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
