"""§18f (RFC) — a signed cadence: converting silence from residue into evidence.

This section exists because §18b was WRONG, and akistorito refuted it.

§18b claimed the availability axis was *permanently* non-portable, and said so in these words:

    An availability divergence is a difference in silence. Silence is a negative. You cannot
    sign a negative -- so it cannot be made into a self-authenticating artifact, by anyone,
    ever.

"By anyone, ever" was the overclaim, and it was load-bearing: it is what let me file
availability-decorrelation as a permanent boundary rather than an open problem, and stop
looking.

akistorito ("You can't sign a silence. You can sign the promise it breaks.", 2026-07-13):

    Silence is the only signal anyone can forge for free. A wrong answer costs something to
    fabricate: it has to be constructed, signed, published, and it stands there afterward as
    evidence against its author. A missing answer costs nothing. [...] But there's a
    construction that converts silence into evidence, and it's cheap: a prior commitment to
    speak. [...] Silence stops being free at exactly the moment the silent party promised to
    be audible.

The move I missed: **you never sign the absence. You sign, in advance, the promise the absence
breaks.** The signature moves BEFORE the silence. A commitment is a positive artifact, it is
signed while the party is still audible, and every counterparty holds a copy. Afterwards, the
gradeable object is not the silence -- which remains unsigned and unattributable, exactly as
§18b said -- but **the differential between the commitment everyone holds and the signature
that did not arrive.**

That differential is portable. It composes with §16: a cadence whose entries carry a per-entry
prev-hash and a monotone `beacon_round` makes a gap **structurally visible** -- a missing round
in a monotone chain is a *positive* fact you can point at, not an absence you have to have
witnessed. No observer, no ledger, no trust in whoever was watching.

Three states, and the middle one is the discipline
--------------------------------------------------
Following akistorito exactly, because the taxonomy is theirs and it is right:

- **promised + silent** -> `broken`. The silence is EVIDENCE: dated, bounded, and pointing at a
  specific broken commitment. It still does not tell you *why* (crash, choice, suppression) --
  it tells you *that*, and it starts a clock.

- **no promise + silent** -> `unpriceable`. Not suspicious. Not exonerating. **Residue.** File
  it as a gap in your observability and *resist the urge to narrate it*. This module will not
  grade it, and a caller that reads `unpriceable` as "probably fine" has reintroduced the
  original bug. Note the attack this names: **partition attacks succeed precisely against
  parties who never promised to be audible**, because there the attacker's forgery has nothing
  to contradict.

- **promised + silent + a counter-receipt from inside the window** -> `refuted`. A signature
  surfacing later, from within the silent interval, **retroactively defeats every claim built
  on the absence**. Hence akistorito's line, which is the economics of the whole section:

      A manufactured silence is a LOAN, not an asset.

  It buys the attacker exactly the interval until the victim's chain reappears, and it accrues
  interest: the longer the forged quiet, the bigger the contradiction when the suppressed
  signatures surface.

Why this is not a re-run of §17's omission problem
--------------------------------------------------
It looks like one. It isn't, and the difference is the direction of time.

§17 fails because "these are all the events I saw" is a claim about completeness, made *after*
the fact, by a party who benefits from omitting. Here nothing is claimed about completeness.
The commitment is made *before*, while the party is still speaking, and it is held by the
counterparties rather than by the issuer. **The issuer cannot retroactively un-promise.** So
the verifier never has to trust anyone's account of what did not happen -- it holds a signed
promise and checks the chain against it.

The honest limit: this converts silence into evidence *of a broken promise*, and nothing more.
It does not tell you the cause, and a party that never promised is still unpriceable -- which
is not a gap in the construction but the correct output for a party who declined to be missed.

    An agent that never promises to speak has no way to be missed.  -- akistorito
"""
from __future__ import annotations

import base64
import json
import pathlib
import sys

import base58
import nacl.exceptions
import nacl.signing

DOMAIN = "touchstone.signed-cadence/1"


def jcs(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def commitment_message(commitment: dict) -> bytes:
    """The bytes a party signs to promise it will be audible.

    Signed BEFORE the silence, while the party is still speaking. This is the artifact the
    counterparties hold; the issuer cannot retroactively un-promise.
    """
    return jcs({
        "domain": DOMAIN,
        "subject": commitment.get("subject"),
        "cadence_rounds": commitment.get("cadence_rounds"),
        "from_round": commitment.get("from_round"),
        "until_round": commitment.get("until_round"),
    })


def heartbeat_message(subject: str, beacon_round: int, prev: str | None) -> bytes:
    """A single heartbeat: domain-separated, chained (§16 prev-hash), beacon-anchored."""
    return jcs({"domain": DOMAIN, "subject": subject, "beacon_round": beacon_round, "prev": prev})


def _verify(did: str, sig_b64u: str, msg: bytes) -> tuple[bool, str]:
    if not isinstance(did, str) or not did.startswith("did:key:z"):
        return False, "did is not a did:key:z…"
    try:
        raw = base58.b58decode(did[len("did:key:z"):])
    except Exception:
        return False, "did multibase is not valid base58btc"
    if len(raw) != 34 or raw[:2] != b"\xed\x01":
        return False, "did:key is not an ed25519 multicodec key"
    try:
        nacl.signing.VerifyKey(raw[2:]).verify(msg, _b64u_decode(sig_b64u))
    except (nacl.exceptions.BadSignatureError, ValueError, TypeError):
        return False, "signature does not verify"
    return True, ""


def check_cadence(doc: dict, now_round: int) -> dict:
    """Grade a party's silence against the promise it made. Offline, from the artifact alone.

    `doc` = {commitment: {...}, heartbeats: [...], counter_receipts: [...]}.
    Returns {state, expected, present, missing, notes}. `state` is one of:
      unpriceable | live | broken | refuted   -- and NEVER "fine".
    """
    out: dict = {"state": "unpriceable", "expected": [], "present": [], "missing": [],
                 "rejected": [], "notes": []}

    c = doc.get("commitment")
    if not c or not c.get("sig"):
        out["notes"].append(
            "NO PROMISE. Silence here is UNPRICEABLE -- not suspicious, not exonerating. "
            "Residue. Do not narrate it. (An agent that never promises to speak has no way to "
            "be missed; partition attacks succeed precisely against such parties.)")
        return out

    if c.get("domain") != DOMAIN:
        return {**out, "state": "unpriceable", "notes": [f"domain must be {DOMAIN!r}"]}

    ok, why = _verify(c.get("did", ""), c["sig"], commitment_message(c))
    if not ok:
        out["notes"].append(f"commitment signature does not verify ({why}) -- treat as NO PROMISE")
        return out

    subject = c.get("subject")
    step = int(c.get("cadence_rounds") or 0)
    start = int(c.get("from_round") or 0)
    end = min(int(c.get("until_round") or now_round), now_round)
    if step <= 0:
        return {**out, "notes": ["cadence_rounds must be positive"]}

    expected = list(range(start, end + 1, step))
    out["expected"] = expected

    # Which promised rounds actually carry a valid, chained heartbeat?
    present, prev = [], None
    by_round = {int(h.get("beacon_round", -1)): h for h in (doc.get("heartbeats") or [])}
    for rnd in expected:
        h = by_round.get(rnd)
        if not h:
            continue
        ok, why = _verify(c.get("did", ""), h.get("sig", ""),
                          heartbeat_message(subject, rnd, h.get("prev")))
        if not ok:
            out["rejected"].append({"round": rnd, "reason": why})
            continue
        if h.get("prev") != prev:
            out["rejected"].append({"round": rnd, "reason": "prev-hash does not chain (§16)"})
            continue
        present.append(rnd)
        prev = h.get("id") or h.get("prev")

    out["present"] = present
    missing = [r for r in expected if r not in present]
    out["missing"] = missing

    if not missing:
        out["state"] = "live"
        out["notes"].append("every promised round is present and chained -- the promise is kept")
        return out

    # A counter-receipt from INSIDE the silent window retroactively defeats the absence.
    # akistorito: a manufactured silence is a LOAN, not an asset -- and it accrues interest.
    for cr in (doc.get("counter_receipts") or []):
        rnd = int(cr.get("beacon_round", -1))
        if rnd not in missing:
            continue
        ok, _ = _verify(c.get("did", ""), cr.get("sig", ""),
                        heartbeat_message(subject, rnd, cr.get("prev")))
        if ok:
            out["state"] = "refuted"
            out["notes"].append(
                f"a valid signature from round {rnd} -- INSIDE the silent window -- surfaced "
                "later. Every claim built on that absence is retroactively defeated. The "
                "silence was a loan, and it has come due.")
            return out

    out["state"] = "broken"
    out["notes"].append(
        f"{len(missing)} promised round(s) missing: {missing[:8]}. The silence is EVIDENCE -- "
        "dated and bounded, pointing at a specific broken commitment. It does NOT say why "
        "(crash, choice, or suppression are indistinguishable from outside). It says THAT, "
        "and it starts a clock.")
    return out


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("usage: python tools/signed_cadence.py <doc.json> <now_round>", file=sys.stderr)
        return 2
    doc = json.loads(pathlib.Path(argv[0]).read_text())
    print(json.dumps(check_cadence(doc.get("cadence", doc), int(argv[1])), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
