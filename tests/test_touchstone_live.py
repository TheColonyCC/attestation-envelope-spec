"""Tests for tools/touchstone_live.py — the live Touchstone adapter.

Hermetic: the fixtures under tests/fixtures/ are REAL responses captured from
touchstone.cv's demo recorder rec_ed8e540a54dd07db (attestation digest
324138f3…, checkpoint #42 → mainnet Bitcoin block 957323, one contestant-signed
contest). So these exercise the fold + the contestant-signature verification
against genuine bytes, with zero network. `python -m pytest` only.
"""
import copy
import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import touchstone_live as tl  # noqa: E402

FX = ROOT / "tests" / "fixtures"
REC = "rec_ed8e540a54dd07db"
DIGEST = "324138f3515ae98a7872f020a5d4dda7f38e19408cf3188d019aac8579929916"
NOW = dt.datetime(2026, 7, 10, 2, 0, tzinfo=dt.timezone.utc)


def _incl():
    return json.loads((FX / "ts_inclusion_entry1.json").read_text())


def _contests():
    return json.loads((FX / "ts_contests_target.json").read_text())


def _feed():
    return json.loads((FX / "ts_feed_cp42.json").read_text())


def _bound(_sub, _pk):  # pretend the contestant key is bound at /pubkeys
    return True


# --- lower bound (inclusion) ----------------------------------------------- #
def test_entry_hash_recomputes_from_header_fields():
    e = _incl()["entry"]
    assert tl.recompute_entry_hash(e) == e["entry_hash"]


def test_entry_hash_recompute_catches_tamper():
    e = _incl()["entry"]
    e = copy.deepcopy(e)
    e["payload_hash"] = "0" * 64
    assert tl.recompute_entry_hash(e) != e["entry_hash"]


def test_inclusion_folds_to_bitcoin_anchored_root():
    ok, lb, notes = tl.verify_inclusion_response(_incl(), _feed())
    assert ok and lb["block_height"] == 957323


def test_inclusion_tampered_proof_rejects():
    bad = _incl()
    bad["inclusion_proof"][0]["hash"] = "ff" * 32
    ok, lb, _ = tl.verify_inclusion_response(bad, _feed())
    assert not ok and lb is None


def test_inclusion_forged_entry_hash_rejects():
    bad = _incl()
    bad["entry"]["entry_hash"] = "ab" * 32  # recompute won't match
    ok, _, notes = tl.verify_inclusion_response(bad, _feed())
    assert not ok and any("recompute mismatch" in n for n in notes)


def test_inclusion_wrong_format_rejects():
    bad = _incl()
    bad["format"] = "something-else/1"
    ok, _, _ = tl.verify_inclusion_response(bad, _feed())
    assert not ok


def test_anchor_unresolvable_when_checkpoint_absent_from_feed():
    ok, lb, notes = tl.verify_inclusion_response(_incl(), {"checkpoints": []})
    assert not ok and any("not found in recorder feed" in n for n in notes)


# --- contestant signature (the trust-nothing check) ------------------------ #
def test_real_contestant_signature_verifies_and_grades_verified():
    c = _contests()["contests"][0]
    v = tl.verify_contest(c, REC, pubkey_bound=_bound)
    assert v["inclusion_ok"] and v["sig_ok"] and v["grade"] == "verified"


def test_claimed_grade_when_key_not_bound():
    c = _contests()["contests"][0]
    v = tl.verify_contest(c, REC, pubkey_bound=lambda s, p: False)
    assert v["sig_ok"] and v["grade"] == "claimed"


def test_tampered_signature_breaks_entry_hash_binding():
    # entry_hash commits actor_sig, so swapping the sig alone is caught by the
    # recompute guard before the sig-check even runs — a stronger binding.
    c = copy.deepcopy(_contests()["contests"][0])
    c["actor_sig"] = "A" * 86 + "=="  # garbage signature, entry_hash now stale
    v = tl.verify_contest(c, REC, pubkey_bound=_bound)
    assert not v["sig_ok"] and v["grade"] != "verified"
    assert any("recompute mismatch" in n for n in v["notes"])


def test_sig_invalid_grade_when_signature_bad():
    # Isolate the signature-check branch: swap the sig AND recompute a matching
    # entry_hash so the binding guard passes; the sig itself must then fail.
    c = copy.deepcopy(_contests()["contests"][0])
    c["actor_sig"] = "A" * 86 + "=="
    c["entry_hash"] = tl.recompute_entry_hash(c)  # make the binding guard pass
    v = tl.verify_contest(c, REC, pubkey_bound=_bound)
    assert not v["sig_ok"] and v["grade"] == "sig_invalid"


def test_contest_signed_over_wrong_recorder_id_rejects():
    c = _contests()["contests"][0]
    v = tl.verify_contest(c, "rec_WRONG", pubkey_bound=_bound)
    assert not v["sig_ok"]  # signing input includes recorder_id


# --- upper bound (contest channel) ----------------------------------------- #
def test_contest_channel_reads_contested():
    state, pt, real, notes = tl.check_contest_channel(_contests(), _feed(), now=NOW, max_lag_s=None, pubkey_bound=_bound)
    assert state == "contested" and pt["block_height"] == 957323 and len(real) == 1


def test_contest_channel_clear_when_no_contests():
    resp = _contests()
    resp["contests"] = []
    resp["count"] = 0
    state, pt, real, _ = tl.check_contest_channel(resp, _feed(), now=NOW, max_lag_s=86400, pubkey_bound=_bound)
    assert state == "clear" and not real


def test_contest_channel_stale_when_past_lag():
    resp = _contests()
    resp["contests"] = []
    # NOW is far past block 957323's time (2026-07-09T16:06) with a 1h lag
    state, pt, _, notes = tl.check_contest_channel(resp, _feed(), now=NOW, max_lag_s=3600, pubkey_bound=_bound)
    assert state == "stale" and any("STALE" in n for n in notes)


def test_contest_channel_undeclared_when_latest_cp_unanchored():
    state, pt, _, _ = tl.check_contest_channel(_contests(), {"checkpoints": []}, now=NOW, max_lag_s=None)
    assert state == "undeclared" and pt is None


# --- SIGNED BUT ABSENT ------------------------------------------------------ #
def test_signed_but_absent_detects_omission():
    held = _contests()["contests"][0]           # a real, valid signed contest
    empty_channel = {"format": tl.CONTEST_FORMAT, "recorder": REC, "contests": []}  # channel omits it
    r = tl.signed_but_absent(held, empty_channel, REC)
    assert r["verdict"] == "SIGNED_BUT_ABSENT"


def test_signed_but_absent_present_when_channel_includes_it():
    held = _contests()["contests"][0]
    r = tl.signed_but_absent(held, _contests(), REC)
    assert r["verdict"] == "present"


def test_signed_but_absent_rejects_forged_held_object():
    held = copy.deepcopy(_contests()["contests"][0])
    held["actor_sig"] = "A" * 86 + "=="
    r = tl.signed_but_absent(held, {"contests": []}, REC)
    assert r["verdict"] == "sig-invalid"


# --- full orchestration ----------------------------------------------------- #
def _fake_get(feed, incl, contests):
    def get(url):
        if url.rstrip("/").endswith(REC):
            return feed
        if "/entry/1" in url:
            return incl
        if "contests?target=" in url:
            return contests
        raise AssertionError(f"unexpected url {url}")
    return get


def test_check_live_full_read_contested():
    v = tl.check_live(REC, 1, DIGEST, now=NOW, max_lag_s=86400,
                      http_get=_fake_get(_feed(), _incl(), _contests()), pubkey_bound=_bound)
    assert v["state"] == "contested"
    assert v["lower_bound"]["block_height"] == 957323
    assert v["provable_through"]["block_height"] == 957323
    assert v["contest_control"] == "issuer"  # demo reuses one recorder for both channels


def test_check_live_unanchored_on_bad_inclusion():
    bad = _incl()
    bad["inclusion_proof"][0]["hash"] = "ff" * 32
    v = tl.check_live(REC, 1, DIGEST, now=NOW,
                      http_get=_fake_get(_feed(), bad, _contests()), pubkey_bound=_bound)
    assert v["state"] == "unanchored"
