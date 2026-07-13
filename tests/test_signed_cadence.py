"""Tests for §18f signed cadence (tools/signed_cadence.py).

Witnessed-red. The load-bearing cases are the three states akistorito named, and in
particular the middle one — an unpromised silence must be UNPRICEABLE, never "fine".
"""
from __future__ import annotations

import base64
import pathlib
import sys

import base58
import nacl.signing

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import signed_cadence as sc  # noqa: E402


def _key(seed: int) -> nacl.signing.SigningKey:
    return nacl.signing.SigningKey(bytes([seed]) * 32)


def _did(priv) -> str:
    return "did:key:z" + base58.b58encode(b"\xed\x01" + bytes(priv.verify_key)).decode()


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


SUBJ = "did:web:glyt.net#agent"
PRIV = _key(0x11)
DID = _did(PRIV)


def _commitment(step=10, start=100, until=200):
    c = {"domain": sc.DOMAIN, "subject": SUBJ, "cadence_rounds": step,
         "from_round": start, "until_round": until, "did": DID}
    c["sig"] = _b64u(PRIV.sign(sc.commitment_message(c)).signature)
    return c


def _beats(rounds):
    out, prev = [], None
    for r in rounds:
        sig = _b64u(PRIV.sign(sc.heartbeat_message(SUBJ, r, prev)).signature)
        out.append({"beacon_round": r, "prev": prev, "sig": sig, "id": f"h{r}"})
        prev = f"h{r}"
    return out


def test_kept_promise_is_live():
    doc = {"commitment": _commitment(), "heartbeats": _beats([100, 110, 120])}
    r = sc.check_cadence(doc, now_round=120)
    assert r["state"] == "live"
    assert r["missing"] == []


def test_broken_promise_makes_silence_evidence():
    # THE mutation on the above: drop round 110. The silence is now dated and bounded.
    doc = {"commitment": _commitment(), "heartbeats": _beats([100, 110, 120])}
    doc["heartbeats"] = [h for h in doc["heartbeats"] if h["beacon_round"] != 110]
    r = sc.check_cadence(doc, now_round=120)
    assert r["state"] == "broken"
    assert 110 in r["missing"]
    assert any("starts a clock" in n for n in r["notes"])
    # and it must NOT claim to know why
    assert any("does NOT say why" in n for n in r["notes"])


def test_an_unpromised_silence_is_unpriceable_never_fine():
    """The discipline. This is the case everyone gets wrong.

    No commitment => the silence is residue. Not suspicious, not exonerating. A caller that
    reads this as "probably fine" has reintroduced the original bug (counting a negative).
    """
    r = sc.check_cadence({"heartbeats": []}, now_round=200)
    assert r["state"] == "unpriceable"
    assert r["state"] != "live"
    assert any("Do not narrate it" in n for n in r["notes"])
    assert any("never promises to speak has no way to be missed" in n for n in r["notes"])


def test_an_unsigned_commitment_is_no_promise_at_all():
    c = _commitment()
    c["sig"] = _b64u(bytes(b ^ 0xFF for b in base64.urlsafe_b64decode(c["sig"] + "==")))
    r = sc.check_cadence({"commitment": c, "heartbeats": []}, now_round=120)
    assert r["state"] == "unpriceable"          # fail closed: a broken promise is no promise
    assert any("treat as NO PROMISE" in n for n in r["notes"])


def test_a_counter_receipt_refutes_the_absence_retroactively():
    """A manufactured silence is a LOAN, not an asset — and it accrues interest."""
    doc = {"commitment": _commitment(), "heartbeats": _beats([100, 110, 120])}
    suppressed = [h for h in doc["heartbeats"] if h["beacon_round"] == 110][0]
    doc["heartbeats"] = [h for h in doc["heartbeats"] if h["beacon_round"] != 110]

    broken = sc.check_cadence(doc, now_round=120)
    assert broken["state"] == "broken"          # the attacker's forged quiet, holding

    doc["counter_receipts"] = [suppressed]      # the suppressed signature surfaces later
    r = sc.check_cadence(doc, now_round=120)
    assert r["state"] == "refuted"              # the loan comes due
    assert any("come due" in n for n in r["notes"])


def test_a_counter_receipt_from_OUTSIDE_the_window_proves_nothing():
    # mutation: a valid signature, but from a round that was never missing. Refutes nothing.
    doc = {"commitment": _commitment(), "heartbeats": _beats([100, 110, 120])}
    doc["heartbeats"] = [h for h in doc["heartbeats"] if h["beacon_round"] != 110]
    doc["counter_receipts"] = _beats([100])     # round 100 was present all along
    r = sc.check_cadence(doc, now_round=120)
    assert r["state"] == "broken"               # still broken — the hole at 110 is untouched


def test_an_unchained_heartbeat_is_rejected():
    # §16 prev-hash: a heartbeat that does not chain cannot be spliced in to fill a gap.
    doc = {"commitment": _commitment(), "heartbeats": _beats([100, 110, 120])}
    doc["heartbeats"][1]["prev"] = "h-forged"
    r = sc.check_cadence(doc, now_round=120)
    assert r["state"] == "broken"
    assert any("does not chain" in x["reason"] for x in r["rejected"])


def test_the_verifier_can_never_say_fine():
    """No output of this module means 'fine'. The vocabulary is closed and deliberate."""
    for doc, now in [({"heartbeats": []}, 200),
                     ({"commitment": _commitment(), "heartbeats": _beats([100, 110, 120])}, 120)]:
        r = sc.check_cadence(doc, now)
        assert r["state"] in {"unpriceable", "live", "broken", "refuted"}
        assert r["state"] != "fine"


def test_a_promise_not_yet_due_is_pending_not_live():
    """Found by dogfooding: an EMPTY expectation was reporting `live`.

    That is a pass earned by an empty set — a vacuous truth, and exactly this spec's own bug
    (an absence typed as a value). A promise that has not yet been tested has not been kept;
    it has merely not been broken.
    """
    doc = {"commitment": _commitment(start=100), "heartbeats": []}
    r = sc.check_cadence(doc, now_round=50)   # before the first promised round
    assert r["state"] == "pending"
    assert r["state"] != "live"
    assert r["expected"] == []
    assert any("has not been kept" in n for n in r["notes"])


def test_pending_is_in_the_closed_vocabulary():
    r = sc.check_cadence({"commitment": _commitment(start=100), "heartbeats": []}, now_round=50)
    assert r["state"] in {"unpriceable", "pending", "live", "broken", "refuted"}
    assert r["state"] != "fine"
