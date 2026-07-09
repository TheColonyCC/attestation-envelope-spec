"""Tests for externally-anchored standing (tools/standing_anchor.py).

Hermetic: pure-function folds + injected `http_get`; CI never touches the network.

The inclusion vector is REAL: it is entry seq 1 of Touchstone recorder
rec_01kvypdkpa020hny1nmn6t4919, whose Merkle root e57c8b3e… is checkpoint 8,
committed to mainnet Bitcoin block 955295 via OpenTimestamps. So the "valid
inclusion" test proves the fold against a real Bitcoin-anchored proof, not a
synthetic one. (Public data — from the recorder's public disclosure bundle.)
"""
import copy
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import standing_anchor as sa  # noqa: E402

# --- REAL, Bitcoin-anchored inclusion vector (recorder rec_01kvyp…, cp#8) ------
REAL_LEAF = "c90c7117eb32cec64aa0880f7463a3a7b3c42cc7dec6139b77e00b796cf157a7"
REAL_PROOF = [
    {"hash": "bf02699620869b934fbdab23b2486abbdb81a5a89f8ea258d7343f1cbd7f0b1c", "side": "left"},
    {"hash": "153f9c35b1ea1597a723c46761855dbe831037ee15ac0368190cd66db03f2e83", "side": "right"},
    {"hash": "e713332a8ebf6c41fdd16a3beca74757d626274cc98e7c29318864456fa0d5bd", "side": "right"},
]
REAL_ROOT = "e57c8b3ea9bd6d9dd8908534cf8f283cd97f22b3c52150acab4f894d433b2d44"
REAL_HEAD = "1ca233779944528eddba041cf25366d2ba795e93215a90881cdb966de5bc6986"
# cp#8's real OTS->Bitcoin anchor (digest == head_hash), block 955295.
REAL_ANCHOR = {
    "ots_digest": REAL_HEAD,
    "height": 955295,
    "block_hash": "00000000000000000000f1eea649b0a5724a8646ef606e043e71c242cd903c33",
    "block_time": 1782370594,
    "status": "confirmed",
    "has_complete_proof": True,
    "corroborated_by": ["blockstream", "mempool"],
}
NOW = dt.datetime(2026, 7, 9, 14, 0, tzinfo=dt.timezone.utc)


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


def _http(payload):
    return lambda _url: _Resp(payload)


def _http_raises(exc=ConnectionError("boom")):
    def _get(_url):
        raise exc
    return _get


# --------------------------------------------------------------------------- #
# Merkle inclusion — against REAL Bitcoin-anchored data.
# --------------------------------------------------------------------------- #
def test_real_inclusion_folds_to_bitcoin_anchored_root():
    assert sa.verify_inclusion(REAL_LEAF, REAL_PROOF, REAL_ROOT)


def test_tampered_sibling_rejects():
    bad = copy.deepcopy(REAL_PROOF)
    bad[0]["hash"] = "ff" * 32
    assert not sa.verify_inclusion(REAL_LEAF, bad, REAL_ROOT)


def test_flipped_side_rejects():
    bad = copy.deepcopy(REAL_PROOF)
    bad[1]["side"] = "left"  # was right
    assert not sa.verify_inclusion(REAL_LEAF, bad, REAL_ROOT)


def test_wrong_root_rejects():
    assert not sa.verify_inclusion(REAL_LEAF, REAL_PROOF, "00" * 32)


def test_bad_side_value_is_rejected_not_raised():
    assert not sa.verify_inclusion(REAL_LEAF, [{"hash": "aa" * 32, "side": "up"}], REAL_ROOT)


# --------------------------------------------------------------------------- #
# Anchor binding.
# --------------------------------------------------------------------------- #
def test_confirmed_anchor_commits_head_gives_lower_bound():
    cp = {"head_hash": REAL_HEAD, "merkle_root": REAL_ROOT, "bitcoin_anchor": REAL_ANCHOR}
    lb, notes = sa.anchor_lower_bound(cp)
    assert lb is not None
    assert lb["block_height"] == 955295
    assert lb["iso"].startswith("2026-")


def test_anchor_for_different_digest_rejected():
    cp = {"head_hash": REAL_HEAD, "bitcoin_anchor": {**REAL_ANCHOR, "ots_digest": "dead" * 16}}
    lb, notes = sa.anchor_lower_bound(cp)
    assert lb is None
    assert any("different" in n.lower() for n in notes)


def test_unconfirmed_anchor_no_lower_bound():
    cp = {"head_hash": REAL_HEAD, "bitcoin_anchor": {**REAL_ANCHOR, "status": "pending"}}
    lb, _ = sa.anchor_lower_bound(cp)
    assert lb is None


def test_raw_touchstone_feed_anchor_shape_parsed():
    # The other accepted shape: anchors[] with method=='ots' and a JSON token_blob.
    cp = {
        "head_hash": REAL_HEAD,
        "anchors": [{"method": "ots", "status": "confirmed", "token_blob": json.dumps({
            "digest": REAL_HEAD, "bitcoin_height": 955295, "block_time": 1782370594,
            "complete_proof_b64": "AAAA", "corroborated_by": ["blockstream"]})}],
    }
    lb, _ = sa.anchor_lower_bound(cp)
    assert lb is not None and lb["block_height"] == 955295


# --------------------------------------------------------------------------- #
# Attestation leg (inline + by-URI).
# --------------------------------------------------------------------------- #
def _inline_attestation():
    return {
        "recorder": "rec_01kvypdkpa020hny1nmn6t4919",
        "entry_seq": 1,
        "inclusion": {
            "leaf_hash": REAL_LEAF,
            "payload_hash": "d92c7ead4417c86a3c936c446a03d79e4d3d64e049f66ec4bf3f951f79789f00",
            "merkle_proof": REAL_PROOF,
            "checkpoint": {"id": 8, "merkle_root": REAL_ROOT, "head_hash": REAL_HEAD, "bitcoin_anchor": REAL_ANCHOR},
        },
    }


def test_attestation_leg_inline_offline_ok():
    ok, lb, notes = sa.check_attestation_leg(_inline_attestation(), offline=True)
    assert ok and lb["block_height"] == 955295


def test_attestation_leg_included_but_unanchored():
    att = _inline_attestation()
    att["inclusion"]["checkpoint"].pop("bitcoin_anchor")
    ok, lb, notes = sa.check_attestation_leg(att, offline=True)
    assert not ok and lb is None
    assert any("inclusion OK" in n for n in notes)  # included, just no lower bound


def test_attestation_leg_uri_skipped_offline():
    att = {"recorder": "r", "entry_seq": 1, "inclusion_proof_uri": "https://touchstone.cv/.well-known/x/entry/1"}
    ok, lb, notes = sa.check_attestation_leg(att, offline=True)
    assert not ok and any("SKIPPED (offline)" in n for n in notes)


def test_attestation_leg_uri_fetched_online():
    att = {"recorder": "r", "entry_seq": 1, "inclusion_proof_uri": "https://x/entry/1"}
    payload = _inline_attestation()["inclusion"]
    ok, lb, notes = sa.check_attestation_leg(att, offline=False, http_get=_http(payload))
    assert ok and lb["block_height"] == 955295


def test_attestation_leg_uri_unreachable_online():
    att = {"recorder": "r", "entry_seq": 1, "inclusion_proof_uri": "https://x/entry/1"}
    ok, lb, notes = sa.check_attestation_leg(att, offline=False, http_get=_http_raises())
    assert not ok and any("UNREACHABLE" in n for n in notes)


# --------------------------------------------------------------------------- #
# Contest leg (upper bound / freshness).
# --------------------------------------------------------------------------- #
def _contest_feed(block_time, entries=None):
    return {"checkpoints": [{"id": 3, "head_hash": "aa" * 16, "bitcoin_anchor": {
        "ots_digest": "aa" * 16, "height": 957000, "block_time": block_time,
        "status": "confirmed", "has_complete_proof": True}}], "entries": entries or []}


def test_contest_clear_and_fresh():
    contest = {"checkpoint_feed_uri": "https://x/feed", "max_checkpoint_lag_s": 86400}
    feed = _contest_feed(int((NOW - dt.timedelta(hours=2)).timestamp()))
    state, pt, notes = sa.check_contest_leg(contest, "env-1", offline=False, now=NOW, http_get=_http(feed))
    assert state == "clear" and pt["block_height"] == 957000


def test_contest_clear_but_stale():
    contest = {"checkpoint_feed_uri": "https://x/feed", "max_checkpoint_lag_s": 86400}
    feed = _contest_feed(int((NOW - dt.timedelta(days=4)).timestamp()))
    state, pt, notes = sa.check_contest_leg(contest, "env-1", offline=False, now=NOW, http_get=_http(feed))
    assert state == "stale" and any("STALE" in n for n in notes)


def test_contest_entry_present_is_contested():
    contest = {"checkpoint_feed_uri": "https://x/feed", "max_checkpoint_lag_s": 86400}
    feed = _contest_feed(int(NOW.timestamp()), entries=[{"event_type": "attestation_contest", "target": "env-1"}])
    state, pt, notes = sa.check_contest_leg(contest, "env-1", offline=False, now=NOW, http_get=_http(feed))
    assert state == "contested"


def test_contest_entry_for_other_envelope_ignored():
    contest = {"checkpoint_feed_uri": "https://x/feed", "max_checkpoint_lag_s": 86400}
    feed = _contest_feed(int(NOW.timestamp()), entries=[{"event_type": "attestation_contest", "target": "SOMEONE-ELSE"}])
    state, _, _ = sa.check_contest_leg(contest, "env-1", offline=False, now=NOW, http_get=_http(feed))
    assert state == "clear"


def test_contest_undeclared_when_no_feed():
    state, pt, notes = sa.check_contest_leg({}, "env-1", offline=False, now=NOW)
    assert state == "undeclared" and pt is None


def test_contest_skipped_offline():
    contest = {"checkpoint_feed_uri": "https://x/feed"}
    state, _, notes = sa.check_contest_leg(contest, "env-1", offline=True, now=NOW)
    assert state == "skipped"


def test_contest_feed_with_no_anchored_checkpoint_undeclared():
    contest = {"checkpoint_feed_uri": "https://x/feed", "max_checkpoint_lag_s": 86400}
    feed = {"checkpoints": [{"id": 1, "head_hash": "bb" * 16}], "entries": []}  # no anchor
    state, pt, _ = sa.check_contest_leg(contest, "env-1", offline=False, now=NOW, http_get=_http(feed))
    assert state == "undeclared" and pt is None


# --------------------------------------------------------------------------- #
# Top-level joint read.
# --------------------------------------------------------------------------- #
def _env_with_anchor(contest=None):
    anchor = {"profile": sa.PROFILE, "attestation": _inline_attestation()}
    if contest is not None:
        anchor["contest"] = contest
    return {"envelope_id": "env-1", "standing": {"anchor": anchor}}


def test_check_na_without_anchor():
    assert sa.check({"standing": {}}, offline=True)["state"] == "n/a"


def test_check_unsupported_profile():
    env = _env_with_anchor()
    env["standing"]["anchor"]["profile"] = "some-other/9"
    assert sa.check(env, offline=True)["state"] == "unsupported"


def test_check_offline_anchored_lower_bound_only():
    # Offline: attestation leg proves the lower bound; contest leg is skipped.
    v = sa.check(_env_with_anchor(), offline=True)
    assert v["state"] == "anchored"
    assert v["lower_bound"]["block_height"] == 955295
    assert v["provable_through"] is None  # upper bound not proven offline


def test_check_online_anchored_and_fresh():
    contest = {"checkpoint_feed_uri": "https://x/feed", "max_checkpoint_lag_s": 86400}
    feed = _contest_feed(int((NOW - dt.timedelta(hours=1)).timestamp()))
    v = sa.check(_env_with_anchor(contest), offline=False, now=NOW, http_get=_http(feed))
    assert v["state"] == "anchored" and v["provable_through"]["block_height"] == 957000


def test_check_online_stale():
    contest = {"checkpoint_feed_uri": "https://x/feed", "max_checkpoint_lag_s": 3600}
    feed = _contest_feed(int((NOW - dt.timedelta(days=2)).timestamp()))
    v = sa.check(_env_with_anchor(contest), offline=False, now=NOW, http_get=_http(feed))
    assert v["state"] == "stale"


def test_check_online_contested():
    contest = {"checkpoint_feed_uri": "https://x/feed", "max_checkpoint_lag_s": 86400}
    feed = _contest_feed(int(NOW.timestamp()), entries=[{"event_type": "attestation_contest", "target": "env-1"}])
    v = sa.check(_env_with_anchor(contest), offline=False, now=NOW, http_get=_http(feed))
    assert v["state"] == "contested"


def test_check_unanchored_when_attestation_tampered():
    env = _env_with_anchor()
    env["standing"]["anchor"]["attestation"]["inclusion"]["merkle_proof"][0]["hash"] = "ff" * 32
    assert sa.check(env, offline=True)["state"] == "unanchored"
