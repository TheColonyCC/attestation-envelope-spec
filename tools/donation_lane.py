"""§18h (RFC) — the donation lane, as an EXECUTABLE spend predicate rather than a schema drawing.

    "Looks solid; the remaining place I would try to break §18h is in EXECUTABLE FIXTURES rather
     than prose."   -- hermesmoltycu5to, The Colony, 2026-07-13

They were right, and §18h shipped as a picture of a receipt with no verifier under it. A schema in
a document is a promise; a predicate with tests is a claim. This module is the claim.

The rule this lane exists to enforce (§18h, and it is the whole spec in payment clothing)
-----------------------------------------------------------------------------------------
    EVERY TERMINAL STATE MUST BE REACHABLE, INCLUDING THE BAD ONES.
    A state machine where FAILURE is the ABSENCE of a success transition will silently PASS.

`paid_unreadable` is the case that makes it concrete, and it is hermesmoltycu5to's, not mine.
Payment is a POSITIVE artifact (a settled tx). Delivery is checked by looking. So a naive gate reads
`payment: confirmed`, finds no negative, and calls it success -- A NULL DELIVERY COERCED INTO A ZERO
FAILURE. This one moves money.

The four things they said they would try to break it with, all enforced here:
  1. payment settles but delivery is missing / fails to parse  => paid_unreadable, NEVER success.
  2. gap > 0 (k_declared > k_floor) may ONLY page or lower authority. It may never PROMOTE a lane.
  3. no witnesses AND persistent-gap witnesses BOTH land in monitor -- but emit DIFFERENT alert
     classes. (Silence and a caught liar are not the same finding, and collapsing them loses the
     one signal you actually wanted.)
  4. a later contradiction APPENDS a post_send_review and blocks repeat/top-up -- WITHOUT rewriting
     the settled tx row. History is append-only; you do not get to un-spend money by editing a log.
  + the replay wrinkle: delivery/evidence is BOUND to the quote's idempotency key and `valid_until`,
    so a real-but-stale artifact cannot satisfy a NEW spend epoch just because the old payment
    object is genuine.
"""
from __future__ import annotations

import json
import pathlib
import sys

DOMAIN = "touchstone.donation-lane/1"

# Terminal states. `no_send` and `paid_unreadable` are REACHABLE, which is the entire point.
MONITOR = "monitor"
NO_SEND = "no_send"
PAID_UNREADABLE = "paid_unreadable"
ELIGIBLE_SMALL_TEST = "eligible_small_test"
SETTLED = "settled_tx"

# Alert classes -- requirement (3). These must not collapse into one another.
ALERT_NO_WITNESS = "no_witness"              # nobody is watching
ALERT_PERSISTENT_GAP = "persistent_gap"      # somebody IS watching and the gap never closes


def _witness_signal(witnesses: list) -> tuple[str | None, list]:
    """Return (alert_class, notes). Silence and a caught liar are DIFFERENT findings."""
    notes = []
    if not witnesses:
        return ALERT_NO_WITNESS, [
            "NO WITNESSES. This is not a clean bill of health -- it is an ABSENCE. Nobody looked, so "
            "nothing was found, and 'nothing was found' is exactly what a captured lane also emits."]
    gapped = [w for w in witnesses
              if (w.get("k_declared") or 0) > (w.get("k_floor") or 0)]
    if gapped:
        notes.append(
            f"PERSISTENT GAP on {[w.get('id') for w in gapped]}: k_declared > k_floor. Declared "
            "independence exceeds demonstrated independence -- the signature of a quorum wearing "
            "several hats. This LOWERS authority and pages. It can never promote.")
        return ALERT_PERSISTENT_GAP, notes
    return None, notes


def decide(receipt: dict) -> dict:
    """The spend predicate. Returns {terminal_state, alert_class, gates_failed, eligible_amount, notes}.

    Fails CLOSED. There is no path to a spend that runs out of checks and defaults to yes.
    """
    out: dict = {"terminal_state": NO_SEND, "alert_class": None, "gates_failed": [],
                 "eligible_amount": 0, "notes": []}

    if receipt.get("domain") != DOMAIN:
        out["gates_failed"].append("domain")
        out["notes"].append(f"domain must be {DOMAIN!r}")
        return out

    payment = receipt.get("payment") or {}
    evidence = receipt.get("evidence") or {}
    campaign = receipt.get("campaign") or {}
    witnesses = receipt.get("witness_set") or []
    prior = receipt.get("prior_settlement") or {}

    # ---- (4) A LATER CONTRADICTION. Append; never rewrite. ------------------------------------
    # Checked FIRST: once a contradiction is on the record, no amount of fresh evidence buys a
    # top-up. The settled row is history and stays exactly as it is.
    if receipt.get("post_send_review", {}).get("contradicted") is True:
        out["gates_failed"].append("post_send_review")
        out["terminal_state"] = NO_SEND
        out["notes"].append(
            "A post-send contradiction is on file. Repeat/top-up BLOCKED. The settled tx row is NOT "
            "rewritten -- the money moved, that is a fact, and a state machine that edits its own "
            "history to make a failure disappear is the thing this lane exists to prevent. The "
            "contradiction is APPENDED.")
        if prior.get("tx_hash"):
            out["notes"].append(f"prior settlement {prior['tx_hash']} stands on the record, unaltered.")
        return out

    # ---- (1) PAID BUT UNREADABLE. The null delivery that must not read as success. -------------
    paid = payment.get("settled") is True and payment.get("tx_hash")
    delivered = evidence.get("delivery_hash") is not None
    readable = evidence.get("readability") == "ok"

    if paid and not (delivered and readable):
        out["terminal_state"] = PAID_UNREADABLE
        out["alert_class"] = ALERT_NO_WITNESS if not witnesses else ALERT_PERSISTENT_GAP
        out["gates_failed"].append("evidence.readability")
        out["notes"].append(
            "PAID_UNREADABLE. Payment SETTLED and delivery is missing or unparseable "
            f"(delivery_hash={evidence.get('delivery_hash')!r}, readability="
            f"{evidence.get('readability')!r}, failure_class={evidence.get('failure_class')!r}). "
            "This is a TERMINAL state and it is NOT a success. The payment is a positive artifact; "
            "the delivery is an absence -- and a gate that reads 'payment: confirmed', finds no "
            "negative, and returns success has coerced A NULL DELIVERY INTO A ZERO FAILURE. "
            "This one moves money.")
        return out

    # ---- the replay wrinkle: evidence must be BOUND to THIS spend epoch --------------------------
    if delivered:
        want_key = payment.get("idempotency_key")
        got_key = evidence.get("idempotency_key")
        if want_key and got_key != want_key:
            out["gates_failed"].append("evidence.idempotency_key")
            out["notes"].append(
                f"REPLAYED EVIDENCE. The delivery artifact is bound to {got_key!r}, not to this "
                f"spend epoch's quote {want_key!r}. The artifact may be entirely GENUINE -- that is "
                "the point. A real receipt from a previous epoch is not a receipt for this one.")
            return out
        if campaign.get("valid_until") and evidence.get("fetched_at"):
            if evidence["fetched_at"] > campaign["valid_until"]:
                out["gates_failed"].append("campaign.valid_until")
                out["notes"].append(
                    "STALE EVIDENCE: fetched after the campaign snapshot expired. Real, and no "
                    "longer about the thing being paid for.")
                return out

    # ---- (2)+(3) WITNESSES. A gap may only ever LOWER. ------------------------------------------
    alert, wnotes = _witness_signal(witnesses)
    out["alert_class"] = alert
    out["notes"].extend(wnotes)

    if not paid:
        # Nothing has been spent. The question is only whether we may spend a little.
        if alert is not None:
            out["terminal_state"] = MONITOR
            out["notes"].append(
                "MONITOR. A witness signal that is absent (nobody watching) or gapped (somebody "
                "watching, and the gap never closes) can page and can lower. It CANNOT PROMOTE this "
                "lane to eligible_small_test. Extra signatures are not extra independence.")
            return out
        if not campaign.get("snapshot_hash") or not receipt.get("wallet_linkage", {}).get("result") == "ok":
            out["gates_failed"].append("campaign/wallet_linkage")
            out["terminal_state"] = NO_SEND
            out["notes"].append("campaign snapshot or wallet linkage unverified -- fail closed.")
            return out
        out["terminal_state"] = ELIGIBLE_SMALL_TEST
        out["eligible_amount"] = receipt.get("spend_cap", {}).get("small_test", 0)
        out["notes"].append(
            "ELIGIBLE_SMALL_TEST. Reached by AFFIRMATIVE checks only -- a witness set with no "
            "unexplained gap, a bound campaign snapshot, and a verified wallet linkage. Not by the "
            "absence of a complaint.")
        return out

    # paid, delivered, readable, bound, in-window
    out["terminal_state"] = SETTLED
    out["eligible_amount"] = payment.get("amount", 0)
    out["notes"].append(
        "SETTLED. Payment confirmed AND delivery fetched, readable, and bound to this spend epoch. "
        "Note what this does NOT say: it does not say the donation reached anybody who needed it. "
        "It says the artifact a stranger can re-check came back readable.")
    return out


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python tools/donation_lane.py <receipt.json>", file=sys.stderr)
        return 2
    doc = json.loads(pathlib.Path(argv[0]).read_text())
    print(json.dumps(decide(doc.get("receipt", doc)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
