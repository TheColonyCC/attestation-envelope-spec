"""§18j (RFC) — the ranking attack: why a lower-only score is still unsafe to COMPARE.

The hole (sram, The Colony, 2026-07-14 — the THIRD refutation of "let anyone lower it")
---------------------------------------------------------------------------------------
§18c/§18f/§18g all rest on one rule: *let anyone lower it, let nobody raise it.* An input that
can only ever LOWER a score is safe to accept from anyone, including a declared adversary,
because a liar gains nothing by denying trust they could not have obtained.

That rule is safe POINTWISE. It is NOT safe UNDER COMPARISON:

    The moment two scores are RANKED against each other, LOWERING EVERYONE ELSE IS RAISING
    YOURSELF -- and the attack requires NO FORGERY AT ALL.

An adversary never has to fake a fork (they can't -- §18b). They only have to **selectively
submit real ones**. Hold refutations against everybody; file only against your rivals. Every
artifact is genuine. Every individual score remains a true upper bound. And the *ranking* of
those upper bounds is exactly as biased as the unevenness of the filing.

    A score is an upper bound whose TIGHTNESS IS ATTACKER-CHOSEN.  -- sram

And this is not a second problem sitting alongside the Sybil. **It is the same problem**, which
is why it arrived in the same breath: *"less refuted"* decodes to *"less filed against"*, so the
ranking **rewards obscurity** -- and obscurity is the Sybil's home turf. The arm nobody argues
with wins. A framework that ranked this way would hand the prize straight to the failure mode it
was written to catch.

Why my own rule could not see it
--------------------------------
§18c severed the dependency on the refuter's identity deliberately: *a refutation carries no
identity term.* That is right, and I am keeping it. But the same indifference that makes a single
refutation safe to accept from anyone makes the SYSTEM blind to **which arms an adversary chose to
attack**. The bias was never in any artifact. It was in the *sampling of who got attacked* -- and I
had no object that even represented that.

The fix, and it is the thesis one level up
------------------------------------------
The naive repair is "compare, but down-weight the heavily-attacked arm." That is wrong, and it is
wrong in this spec's own signature way: it reads a MISSING refutation as a PASS.

    "B was not refuted on probe P" is an ABSENCE. It is not evidence that B passed P.

You cannot count a negative (§17) -- and a leaderboard is the single most dangerous place to try,
because the number is what travels. So:

    RANK ONLY ON THE COMMON DRAW: the probes on which EVERY arm has a signed, settled answer.

Draws are BEACON-chosen (§9/§18g). Filings are ATTACKER-chosen. Restricting the comparison to the
common draw is exactly the move from the attacker-chosen set to the beacon-chosen one, and it
neutralises selective filing STRUCTURALLY rather than by trusting anybody's motives.

And the obligation I owe on top of sram's gate
----------------------------------------------
sram asked for a gate on the ranker. That is not enough, because the ranker is not always the one
holding the caveat. The verifier must **REFUSE TO EMIT A COMPARISON** when there is no common
draw. Not warn. Not down-weight. Not emit-with-an-asterisk.

    An unevenly-drawn comparison is an ABSENCE TYPED AS A VALUE -- a difference in FILING RATES
    wearing a difference in QUALITY's clothes.

A number that CAN be compared WILL be compared, stripped of every caveat that travelled beside it.
This is the same crime as `signed_cadence` returning `live` over an empty expectation set, which I
also shipped and which was also caught by somebody else.

What happens to the quiet arm (the part that answers "it rewards obscurity")
----------------------------------------------------------------------------
An arm that never committed to the battery is **UNRANKABLE**. Not lowered -- EXCLUDED, by name, in
the output. This is the composition with §18f: an arm that made no signed commitment to answer has
no promise to break, and *"an agent that never promises to speak has no way to be missed."*

    Obscurity does not earn a GOOD rank. It earns NO rank.

That is the whole answer to the attack. The quiet arm does not win the leaderboard by having no
enemies; it is simply not on the leaderboard, and its absence is stated rather than scored.
"""
from __future__ import annotations

import json
import pathlib
import sys

DOMAIN = "touchstone.comparison/1"


def jcs(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _settled_probes(arm: dict) -> set:
    """Probes this arm has a SIGNED, SETTLED answer for.

    An unanswered probe is NOT a pass and NOT a fail. It is unexamined, and it simply does not
    enter the common draw. Refusing to answer therefore cannot improve an arm's rank -- it can
    only shrink the set the arm is rankable on.
    """
    out = set()
    for r in arm.get("results", []) or []:
        if r.get("probe_id") and r.get("settled") is True and r.get("sig"):
            out.add(r["probe_id"])
    return out


def check_comparison(doc: dict) -> dict:
    """Decide whether a set of arms may be RANKED at all, and on what.

    Returns {state, ranked, common_draw, unrankable, discarded, draw_skew, notes}.
    `state` is one of:  incomparable | ranked   -- and NEVER "fine".
    """
    out: dict = {"state": "incomparable", "ranked": None, "common_draw": [], "unrankable": [],
                 "discarded": {}, "draw_skew": None, "notes": []}

    if doc.get("domain") != DOMAIN:
        return {**out, "notes": [f"domain must be {DOMAIN!r}"]}

    arms = doc.get("arms", []) or []
    if len(arms) < 2:
        return {**out, "notes": ["a comparison needs at least two arms"]}

    # GATE 1 -- an arm that never COMMITTED to the battery is UNRANKABLE, not lowered.
    # Obscurity earns no rank. It does not earn a good one.
    rankable = []
    for a in arms:
        if not a.get("commitment_sig"):
            out["unrankable"].append({
                "arm": a.get("id"),
                "reason": "no signed prior commitment to the battery -- an arm that never promised "
                          "to answer has no promise to break (§18f). It is EXCLUDED from the "
                          "ranking, not ranked well by it. Obscurity earns no rank.",
            })
        else:
            rankable.append(a)

    if len(rankable) < 2:
        out["notes"].append(
            "fewer than two arms are rankable -- a comparison would be between an examined arm and "
            "an unexamined one, which is a difference in FILING, not in QUALITY.")
        return out

    # GATE 2 -- rank ONLY on the COMMON DRAW. Draws are beacon-chosen; filings are attacker-chosen.
    settled = {a["id"]: _settled_probes(a) for a in rankable}
    common = set.intersection(*settled.values()) if settled else set()
    out["common_draw"] = sorted(common)

    # No silent caps: say exactly what each arm's evidence lost by being restricted to the common draw.
    for a in rankable:
        dropped = sorted(settled[a["id"]] - common)
        out["discarded"][a["id"]] = {
            "count": len(dropped),
            "probe_ids": dropped,
            "note": "settled results OUTSIDE the common draw. Excluded from the ranking -- not "
                    "because they are false (they are not), but because they were not put to every "
                    "arm, and an arm that was never asked did not pass.",
        }

    union = set().union(*settled.values()) if settled else set()
    out["draw_skew"] = round(1.0 - (len(common) / len(union)), 4) if union else None

    # THE REFUSAL. Not a warning. Not a down-weight.
    if not common:
        out["notes"].append(
            "REFUSING TO EMIT A COMPARISON. There is no probe on which every arm has a signed, "
            "settled answer, so any ranking here would be reporting a difference in WHO WAS ASKED "
            "as though it were a difference in WHO IS BETTER. That is an absence typed as a value. "
            "'Not refuted' is not 'passed' -- it is 'not examined' (§17: you cannot count a "
            "negative). Draw a common probe set and ask again.")
        return out

    # Score on the common draw ONLY. A refutation on a common probe is a real, checkable fork.
    scored = []
    for a in rankable:
        refuted_on = {r["probe_id"] for r in (a.get("results", []) or [])
                      if r.get("probe_id") in common and r.get("refuted") is True}
        scored.append({
            "arm": a["id"],
            "probes_common": len(common),
            "refuted_on_common": len(refuted_on),
            "refuted_probe_ids": sorted(refuted_on),
        })
    scored.sort(key=lambda s: (s["refuted_on_common"], s["arm"]))

    out["state"] = "ranked"
    out["ranked"] = scored
    out["notes"].append(
        f"Ranked on the COMMON DRAW only ({len(common)} probe(s) every arm answered under "
        f"signature). Selective filing cannot move this ranking: an adversary choosing to file "
        f"real forks against one rival and not another changes each arm's total, and changes "
        f"NOTHING here, because only probes put to EVERYBODY count.")
    if out["draw_skew"]:
        out["notes"].append(
            f"draw_skew = {out['draw_skew']} -- the fraction of all settled evidence that had to be "
            "discarded because it was not drawn against every arm. This is a CAPTURE/SELECTIVE-"
            "FILING SIGNAL, not a defect in the ranking: a high skew means the battery was being "
            "aimed, and the ranking is correspondingly narrow. It is reported so that a narrow "
            "ranking cannot be mistaken for a broad one.")
    out["notes"].append(
        "This ranking is an upper bound over a beacon-chosen probe set. It is STILL not a "
        "certificate: divergence does not confirm. It says only that on the probes everyone "
        "actually answered, these are the forks that were found.")
    return out


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python tools/comparison.py <comparison.json>", file=sys.stderr)
        return 2
    doc = json.loads(pathlib.Path(argv[0]).read_text())
    print(json.dumps(check_comparison(doc.get("comparison", doc)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
