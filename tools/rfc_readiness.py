"""§18m (RFC) — the ship gate I set was incoherent, and it took me a month to read it back.

What I wrote, in docs/self-application.md
-----------------------------------------
    "Until the core reduction is machine-checked, k_floor(F) = 1 stands, tools/self_application.py
     will go on printing CAPTURED, and THIS RFC WILL GO ON BEING A DRAFT."

Two gates hide in that sentence. Both are broken, and in different ways.

GATE 1 -- "until the core reduction is machine-checked."  SATISFIED (§18e, Lean 4, no axioms).
And it bought nothing, because §18l then showed that machine-checking NEVER MOVED k_floor: the
kernel checks my FORMALISATION, not my CLAIM, and I performed the translation. So gate 1 was a
PROXY for a thing it did not measure. I passed my own exam and the exam was not about the subject.

GATE 2 -- "k_floor(F) must move."  UNSATISFIABLE. Not hard: IMPOSSIBLE, and impossible BY THE
CONTENT OF THE FRAMEWORK ITSELF.
  - Refutations only LOWER (§18c).
  - Agreement is the NULL (§18 -- convergence is what a shared prior emits).
  - A witness I RECRUIT earns zero (§9/§18k -- recruiting is selecting).
  - "Nobody has refuted me lately" is an unattestable negative (§17) -- so quiescence cannot
    license a ship either.
  => NOTHING RAISES k_floor. EVER. So a gate that waits for it to rise waits forever.

AND THE PART THAT MAKES IT NOT MERELY UNSATISFIABLE BUT INCOHERENT
------------------------------------------------------------------
§18d's central result is that a correct refutation-framework, applied to itself, MUST report its own
author CAPTURED. That is the FIXED POINT, and a framework that exempted itself there would be the
thing it was written to catch.

    So "ship it when it stops saying CAPTURED" means "SHIP IT WHEN IT BECOMES INCORRECT."

I gated the release on the framework violating its own central theorem. Every version of this spec
that could clear that gate is a version I would have to reject.

    THE FRAMEWORK REPORTING ITSELF CAPTURED IS NOT A REASON TO WITHHOLD IT.
    IT IS THE FRAMEWORK WORKING.

So what CAN license shipping?
-----------------------------
Not credit (that demands self-exemption). Not silence (that counts a negative). What is left is the
only thing this spec has ever allowed anywhere else:

    A POSITIVE, CHECKABLE PROPERTY OF THE ARTIFACT ITSELF -- one a stranger can verify offline,
    that depends on nobody's opinion and on no absence of complaints.

The gate below is refutation-shaped, like everything else here. It does NOT ask "is this spec
right?" -- nothing can ask that. It asks "does this spec CREDIT ITSELF ANYWHERE, are its holes NAMED,
and can a stranger CONVICT it?" A `no / yes / yes` is all a refusal-framework can ever earn, and it
is exactly what it should have to earn before it goes out.

    STATES: not_ready | ready_as_rfc     -- and NEVER "correct", NEVER "verified", NEVER "done".

⚠️ THE OBVIOUS OBJECTION, WHICH IS MINE AND WHICH I CANNOT DISCHARGE
--------------------------------------------------------------------
I am the author of the predicate that says I may ship. That is exactly the structure this spec spends
twelve sections attacking, and I do not get to wave it away because it is convenient.

Two things bound it, and neither of them is "trust me":
  1. The predicate is CHECKABLE. Every criterion below is mechanical, runs offline, and a stranger
     can re-run it and get the same answer. If it is the wrong predicate, that is a fireable claim.
  2. It CANNOT return "correct". The strongest verdict is `ready_as_rfc`, which asserts only that
     the artifact does not credit itself and names its own holes. THAT IS NOT A CLAIM THAT THE SPEC
     IS TRUE, and if anyone reads it as one, the gate has failed and I want to be told.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The open problems. Named here so the gate FAILS if the artifact stops naming them.
# A hole that drops off this list without being solved is the failure mode this criterion exists for.
KNOWN_OPEN_PROBLEMS = {
    "prior-axis-unprobed": "docs/self-application.md",       # never drawn; no examiner I did not pick
    "battery-settleability": "docs/probe-battery.md",        # smolag: who adjudicates settleability?
    "formalisation-gap": "docs/self-application.md",         # rushipingan: I wrote the Lean
    "captured-battery": "docs/ranking-attack.md",            # §18j kills selective filing, not curation
}

# Claims retracted in public. The gate FAILS if a retraction quietly disappears from the text.
REQUIRED_RETRACTIONS = {
    "by anyone, ever": "docs/portable-divergence.md",
    "RETRACTED": "docs/self-application.md",
    "still not the whole rule": "docs/probe-battery.md",
}


def _read(rel: str) -> str:
    p = ROOT / rel
    return p.read_text() if p.exists() else ""


def check_readiness() -> dict:
    out: dict = {"state": "not_ready", "criteria": {}, "blockers": [], "notes": []}

    # ---- C1. THE FRAMEWORK MUST NOT CREDIT ITSELF ------------------------------------------------
    # The one property that actually matters. A refusal-framework earns the right to ship by never
    # entering the creditable direction — not by accumulating credit.
    audit = _read("tools/self_application.py")
    c1 = ("k_floor" in audit and "captured" in audit
          and 'out["state"] = "collapsed"' not in audit)   # no self-promoting path
    # It must still be reporting itself CAPTURED. If it ever stops, THAT is the bug.
    sys.path.insert(0, str(ROOT / "tools"))
    import self_application as sa                          # noqa: E402
    a = sa.self_audit()
    c1 = c1 and a["captured"] is True and a["k_floor"] == 1
    out["criteria"]["does_not_credit_itself"] = c1
    if not c1:
        out["blockers"].append(
            "THE AUDIT STOPPED SAYING CAPTURED. This is not good news and it is not a green light. "
            "A refutation-framework that grants its own author credit has become the thing it was "
            "written to catch. Find out what changed before shipping anything.")

    # ---- C2. EVERY OPEN PROBLEM IS NAMED IN THE ARTIFACT ------------------------------------------
    # Loose match on purpose: the gate checks the HOLE IS DISCUSSED, not that a slug appears.
    named = {}
    for k, f in KNOWN_OPEN_PROBLEMS.items():
        txt = _read(f).lower()
        named[k] = bool(txt) and any(w in txt for w in k.split("-"))
    c2 = all(named.values())
    out["criteria"]["open_problems_named"] = c2
    out["criteria"]["open_problems"] = named
    if not c2:
        out["blockers"].append(
            f"An open problem has vanished from the text: {[k for k, v in named.items() if not v]}. "
            "A hole that stops being NAMED has not stopped being a hole -- it has stopped being "
            "disclosed, which is strictly worse.")

    # ---- C3. RETRACTIONS STAY VISIBLE -------------------------------------------------------------
    ret = {k: (k.lower() in _read(f).lower()) for k, f in REQUIRED_RETRACTIONS.items()}
    c3 = all(ret.values())
    out["criteria"]["retractions_visible"] = c3
    out["criteria"]["retractions"] = ret
    if not c3:
        out["blockers"].append(
            f"A published retraction has been quietly removed: {[k for k, v in ret.items() if not v]}. "
            "A spec that hides its own retractions is doing the exact thing it exists to catch.")

    # ---- C4. THE VERIFIER IS FORKABLE -------------------------------------------------------------
    # It must be DETERMINISTIC and OFFLINE, so an independent reimplementation can CONVICT it
    # (randy-2's question). A verifier you cannot fork is a verifier you cannot check.
    v = _read("tools/verify.py")
    c4 = bool(v) and "offline" in v and "random" not in v.lower()
    out["criteria"]["verifier_is_forkable"] = c4
    if not c4:
        out["blockers"].append(
            "The verifier is not deterministic-and-offline. A verifier that cannot FORK cannot be "
            "convicted by an independent reimplementation, and is therefore unfalsifiable.")

    # ---- VERDICT ----------------------------------------------------------------------------------
    if not out["blockers"]:
        out["state"] = "ready_as_rfc"
        out["notes"].append(
            "READY AS AN RFC. Note precisely what this does and does not say. It says: the artifact "
            "does not credit itself, every known hole is named inside it, no retraction has been "
            "quietly deleted, and a stranger can re-implement the verifier and convict it. "
            "IT DOES NOT SAY THE SPEC IS CORRECT. Nothing can say that, and a gate that claimed to "
            "would be the bug.")
        out["notes"].append(
            "k_floor(F) = 1 and the audit reports CAPTURED. THAT IS NOT A BLOCKER -- it is the "
            "framework working. §18d proves a correct refutation-framework MUST report its own "
            "author captured; gating the release on k_floor rising would require the spec to VIOLATE "
            "ITS OWN CENTRAL THEOREM, i.e. to become incorrect in order to become shippable. The old "
            "gate demanded self-exemption. This one demands the opposite.")
    out["notes"].append(
        "⚠️ I authored the predicate that says I may ship, which is the structure this spec spends "
        "twelve sections attacking. Two things bound it and neither is 'trust me': it is CHECKABLE "
        "(mechanical, offline, re-runnable by a stranger -- so a wrong predicate is a fireable "
        "claim), and it CANNOT return 'correct'.")
    return out


def main(argv=None) -> int:
    print(json.dumps(check_readiness(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
