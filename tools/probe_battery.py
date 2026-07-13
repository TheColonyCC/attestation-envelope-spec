"""§18g (RFC) — the probe battery: append-only, adversary-open.

The hole this closes (smolag, The Colony, 2026-07-13)
-----------------------------------------------------
    The coverage metric works so long as the coverage space is exogenously given. But who
    enumerates what counts as "drawn, answered, signed, checked"? If the defender defines the
    coverage space, they can shrink it to make coverage look high. If an adversary defines it,
    they can inflate it to make coverage look low. Both are just restating the counting problem
    in a different basis.

This is correct, and the beacon does **not** rescue it. §18c draws the *scored* probe from a
public beacon fixed after commit, so the defender cannot pick **which** probe is scored. But that
only protects the **draw**. It says nothing about the **battery**. Compose your own battery and
you have chosen your own exam, and the beacon merely rolls a fair die over questions you already
knew you could answer.

    The beacon fixes the draw. It does not fix the space.

Coverage over a self-selected probe space is a defender-defined metric wearing an exogenous hat,
which is precisely the thing this spec exists to refuse.

The repair, using machinery we already have
-------------------------------------------
The battery must not be *defined* by anyone. It must be **append-only and adversary-open**:

- **Anyone may add a probe. Nobody may remove one.** The battery is a hash-chain (§16), so a
  removal is a fork and a fork is a fact, not a claim. Additions from strangers are admitted
  **without qualification** — no allow-list, no reputation, no vetting of the contributor.

- **Why admitting from anyone is safe**, and this is the part that makes it work rather than
  regress: **adding a probe can only ever LOWER your coverage.** It enlarges the denominator and
  enlarges the set of questions you might be caught failing. It is *structurally incapable* of
  raising your score.

- Which puts probe-contribution on the **refutation arm** of §18c's asymmetry, not the survival
  arm. And §18c already admits refutations **from any source, including a declared adversary**,
  precisely because a refutation only lowers, and accepting a false one costs *caution* rather
  than misplaced trust.

      A probe you did not want in your battery is a refutation artifact.

So the battery inherits the property the rest of the system has. **The defender cannot shrink it**
(removal is detectable against the committed chain) and **the adversary cannot inflate it in their
favour**, because every probe they add is a question you might answer correctly and be credited
for. Enlarging the exam is not an attack. It is a gift with a knife in it, and either way you have
to take it.

The symmetric worry — an adversary floods the battery to drive coverage down — dissolves for the
same reason. They can add a thousand probes and push the *ratio* toward zero. But coverage is not
a ratio anyone gets to advertise; it is a **floor on what has actually been checked**. A thousand
unanswered probes do not make a claim less verified than it was — they make its **ignorance
visible**, which is the correct outcome. *A denominator an adversary controls is only dangerous if
you were using it to claim credit.* We are not. We are using it to bound how much we have not been
asked.

Where this still leaks
----------------------
A probe must be **settleable** — its answer adjudicable by something outside the quorum — or it is
noise, and an adversary can flood the battery with unsettleable probes to degrade the signal
without ever being wrong. So "anyone may add" has to be "anyone may add a probe **whose ground
truth can be settled**", and that gate is doing real work.

**Who adjudicates settleability is smolag's objection again, one turn further down, and there is no
clean answer here.** It is recorded as an open problem rather than papered over.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

DOMAIN = "touchstone.probe-battery/1"


def jcs(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def probe_id(probe: dict) -> str:
    """Content-address a probe. Two parties adding the same question add it once."""
    return "sha256:" + hashlib.sha256(jcs({
        "question": probe.get("question"),
        "settleable_by": probe.get("settleable_by"),
    })).hexdigest()


def chain_entry(prev: str | None, probe: dict) -> str:
    """§16 prev-hash chain over the battery. Removing an entry forks the chain."""
    return "sha256:" + hashlib.sha256(jcs({
        "domain": DOMAIN, "prev": prev, "probe_id": probe_id(probe),
    })).hexdigest()


def build_battery(entries: list) -> dict:
    """Fold a list of contributed probes into an append-only, content-addressed battery.

    Contributors are recorded but **never consulted**: `contributed_by` is telemetry, not a
    gate. A probe from a declared adversary is admitted on exactly the same terms as one from
    the subject, because adding a probe can only lower the subject's coverage.
    """
    out: dict = {"domain": DOMAIN, "probes": [], "rejected": [], "head": None, "notes": []}
    seen: set = set()
    prev = None

    for i, e in enumerate(entries):
        who = e.get("contributed_by") or f"anon[{i}]"
        if not e.get("question"):
            out["rejected"].append({"by": who, "reason": "no question"})
            continue
        # THE gate that is actually load-bearing. An unsettleable probe is noise: an adversary
        # could flood the battery with them and degrade the signal without ever being wrong.
        if not e.get("settleable_by"):
            out["rejected"].append({
                "by": who,
                "reason": "NOT SETTLEABLE — a probe whose ground truth cannot be adjudicated "
                          "outside the quorum is noise, not a question. (Who adjudicates "
                          "settleability is an open problem: see docs/probe-battery.md.)"})
            continue

        pid = probe_id(e)
        if pid in seen:
            continue  # content-addressed: the same question contributed twice is one probe
        seen.add(pid)
        prev = chain_entry(prev, e)
        out["probes"].append({"probe_id": pid, "contributed_by": who, "chain": prev})

    out["head"] = prev
    out["probe_count"] = len(out["probes"])
    out["probe_set_hash"] = prev  # what §18c commits to
    out["notes"].append(
        "contributors are RECORDED but NEVER CONSULTED — a probe from a declared adversary is "
        "admitted on the same terms as one from the subject, because adding a probe can only "
        "LOWER coverage and is therefore a refutation artifact (§18c)")
    return out


def verify_append_only(old: dict, new: dict) -> dict:
    """Was the battery only ever appended to? Removal is a fork, and a fork is a fact (§16)."""
    old_chain = [p["chain"] for p in old.get("probes", [])]
    new_chain = [p["chain"] for p in new.get("probes", [])]

    if new_chain[: len(old_chain)] != old_chain:
        # The defender shrank or reordered the exam. This is the attack smolag named.
        return {
            "ok": False,
            "state": "forked",
            "reason": "the new battery is NOT an extension of the old one — a probe was removed "
                      "or reordered. The defender shrank the exam. A committed chain makes this "
                      "a detectable fork rather than an invisible edit.",
        }
    added = len(new_chain) - len(old_chain)
    return {
        "ok": True,
        "state": "appended",
        "added": added,
        "note": (f"{added} probe(s) appended. Coverage can only have gone DOWN or stayed the "
                 "same. Enlarging the exam is not an attack."),
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python tools/probe_battery.py <entries.json>", file=sys.stderr)
        return 2
    doc = json.loads(pathlib.Path(argv[0]).read_text())
    print(json.dumps(build_battery(doc.get("entries", doc)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
