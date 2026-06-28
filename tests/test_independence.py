"""Tests for effective-independent-witness counting over the sigchain (tools/independence.py).

Pure-function; no network. Run: pytest tests/
"""
import json
import pathlib
import sys

import jsonschema

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import independence  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "envelope.v0.1.schema.json").read_text())
HA = "sha256:" + "a1" * 32
HB = "sha256:" + "b2" * 32


def _env(evidence, sigchain):
    return {"evidence": evidence, "sigchain": sigchain}


def test_disjoint_evidence_two_witnesses():
    env = _env(
        [{"pointer_type": "immutable_uri", "uri": "u0", "content_hash": HA},
         {"pointer_type": "immutable_uri", "uri": "u1", "content_hash": HB}],
        [{"alg": "ed25519", "key_id": "did:key:zA", "sig": "x", "evidence_refs": [0]},
         {"alg": "ed25519", "key_id": "did:key:zB", "sig": "x", "evidence_refs": [1]}],
    )
    assert independence.effective_witnesses(env)["witnesses"] == 2


def test_shared_evidence_one_witness():
    env = _env(
        [{"pointer_type": "immutable_uri", "uri": "u0", "content_hash": HA}],
        [{"alg": "ed25519", "key_id": "did:key:zA", "sig": "x", "evidence_refs": [0]},
         {"alg": "ed25519", "key_id": "did:key:zB", "sig": "x", "evidence_refs": [0]}],
    )
    r = independence.effective_witnesses(env)
    assert r["witnesses"] == 1 and r["signatures"] == 2


def test_no_evidence_refs_earns_nothing():
    env = _env(
        [{"pointer_type": "immutable_uri", "uri": "u0", "content_hash": HA}],
        [{"alg": "ed25519", "key_id": "did:key:zA", "sig": "x", "evidence_refs": [0]},
         {"alg": "ed25519", "key_id": "did:key:zB", "sig": "x"}],  # no refs
    )
    r = independence.effective_witnesses(env)
    assert r["witnesses"] == 1 and r["unanchored"] == ["did:key:zB"]


def test_evidence_without_content_hash_is_unanchored():
    env = _env(
        [{"pointer_type": "platform_receipt", "uri": "u0"}],  # no content_hash
        [{"alg": "ed25519", "key_id": "did:key:zA", "sig": "x", "evidence_refs": [0]}],
    )
    r = independence.effective_witnesses(env)
    assert r["witnesses"] == 0 and r["unanchored"] == ["did:key:zA"]


def test_out_of_range_ref_ignored():
    env = _env(
        [{"pointer_type": "immutable_uri", "uri": "u0", "content_hash": HA}],
        [{"alg": "ed25519", "key_id": "did:key:zA", "sig": "x", "evidence_refs": [0, 7]}],
    )
    assert independence.effective_witnesses(env)["witnesses"] == 1


def test_example_validates_and_counts_two():
    ex = json.loads((ROOT / "examples" / "independence_multiwitness.v0.1.json").read_text())
    jsonschema.validate(ex, SCHEMA, cls=jsonschema.Draft202012Validator)  # schema OK incl. evidence_refs
    r = independence.effective_witnesses(ex)
    assert r["signatures"] == 3 and r["witnesses"] == 2   # 3 sigs, 2 effective witnesses


def test_v01_envelope_without_evidence_refs_counts_zero():
    # backward compatibility: a plain v0.1 envelope (no evidence_refs anywhere) is
    # simply uncounted for independence — the feature is additive and opt-in.
    ex = json.loads((ROOT / "examples" / "colony_post_published.v0.1.json").read_text())
    assert independence.effective_witnesses(ex)["witnesses"] == 0


# --- §9 selection_grade gating -------------------------------------------------

def test_selection_grade_absent_fails_closed():
    # no selection_grade anywhere: 2 evidence-disjoint witnesses, but 0 steering-bounded
    # (absent == obligor_picked == steerable). Backward-compatible: `witnesses` unchanged.
    env = _env(
        [{"pointer_type": "immutable_uri", "uri": "u0", "content_hash": HA},
         {"pointer_type": "immutable_uri", "uri": "u1", "content_hash": HB}],
        [{"alg": "ed25519", "key_id": "did:key:zA", "sig": "x", "evidence_refs": [0]},
         {"alg": "ed25519", "key_id": "did:key:zB", "sig": "x", "evidence_refs": [1]}],
    )
    r = independence.effective_witnesses(env)
    assert r["witnesses"] == 2 and r["steering_bounded_witnesses"] == 0
    assert sorted(r["steered"]) == ["did:key:zA", "did:key:zB"]
    assert all(g == "obligor_picked" for g in r["selection_grades"].values())


def test_beacon_drawn_earns_steering_bounded():
    env = _env(
        [{"pointer_type": "immutable_uri", "uri": "u0", "content_hash": HA},
         {"pointer_type": "immutable_uri", "uri": "u1", "content_hash": HB}],
        [{"alg": "ed25519", "key_id": "did:key:zA", "sig": "x", "evidence_refs": [0],
          "selection_grade": "obligor_picked"},
         {"alg": "ed25519", "key_id": "did:key:zB", "sig": "x", "evidence_refs": [1],
          "selection_grade": "beacon_drawn"}],
    )
    r = independence.effective_witnesses(env)
    # 2 disjoint witnesses; only the beacon-drawn cluster is steering-bounded
    assert r["witnesses"] == 2 and r["steering_bounded_witnesses"] == 1
    assert r["steered"] == ["did:key:zA"]


def test_obligor_picked_disjoint_does_not_count_steering_bounded():
    # a disjoint-but-hand-picked witness earns nothing toward §9 (shoppable pool)
    env = _env(
        [{"pointer_type": "immutable_uri", "uri": "u0", "content_hash": HA},
         {"pointer_type": "immutable_uri", "uri": "u1", "content_hash": HB}],
        [{"alg": "ed25519", "key_id": "did:key:zA", "sig": "x", "evidence_refs": [0],
          "selection_grade": "beacon_drawn"},
         {"alg": "ed25519", "key_id": "did:key:zB", "sig": "x", "evidence_refs": [1],
          "selection_grade": "obligor_picked"}],
    )
    r = independence.effective_witnesses(env)
    assert r["steering_bounded_witnesses"] == 1 and r["steered"] == ["did:key:zB"]


def test_public_pool_is_not_steering_bounded():
    env = _env(
        [{"pointer_type": "immutable_uri", "uri": "u0", "content_hash": HA}],
        [{"alg": "ed25519", "key_id": "did:key:zA", "sig": "x", "evidence_refs": [0],
          "selection_grade": "public_pool_unverified"}],
    )
    r = independence.effective_witnesses(env)
    assert r["witnesses"] == 1 and r["steering_bounded_witnesses"] == 0
    assert r["steered"] == ["did:key:zA"]
    assert r["selection_grades"]["did:key:zA"] == "public_pool_unverified"


def test_unknown_selection_grade_normalizes_to_floor():
    env = _env(
        [{"pointer_type": "immutable_uri", "uri": "u0", "content_hash": HA}],
        [{"alg": "ed25519", "key_id": "did:key:zA", "sig": "x", "evidence_refs": [0],
          "selection_grade": "totally-bogus"}],
    )
    r = independence.effective_witnesses(env)
    assert r["selection_grades"]["did:key:zA"] == "obligor_picked"
    assert r["steering_bounded_witnesses"] == 0


def test_selection_example_validates_and_counts():
    ex = json.loads((ROOT / "examples" / "independence_selection.v0.1.json").read_text())
    jsonschema.validate(ex, SCHEMA, cls=jsonschema.Draft202012Validator)  # selection_grade in schema
    r = independence.effective_witnesses(ex)
    assert r["signatures"] == 3 and r["witnesses"] == 2 and r["steering_bounded_witnesses"] == 1
