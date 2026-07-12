"""Tests for §15 per-field assurance (tools/assurance.py).

Hermetic: pure-function reads over an in-repo example, no network. Witnessed-red —
every positive check ships the mutation that makes it fail (a re-derivable field that
does NOT re-derive self-voids; a fired field falls to the floor; a stale principal).
"""
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import assurance as a  # noqa: E402

EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "examples" / "assurance_graded.v0.1.json"
NOTE_PTR = "/extensions/https:~1~1thecolony.cc~1x~1assurance-demo/note_sha256"
RISK_PTR = "/extensions/https:~1~1thecolony.cc~1x~1assurance-demo/risk_level"


def load():
    return json.loads(EXAMPLE.read_text())


def _field(res, pointer):
    return next(f for f in res["fields"] if f["pointer"] == pointer)


# --- pointer resolution (RFC 6901) ----------------------------------------- #
def test_pointer_resolves_including_escapes():
    doc = {"a": {"b/c": [10, {"~x": "hit"}]}}
    assert a.resolve_pointer(doc, "/a/b~1c/0") == 10
    assert a.resolve_pointer(doc, "/a/b~1c/1/~0x") == "hit"
    assert a.resolve_pointer(doc, "/a/nope") is a._MISSING
    assert a.resolve_pointer(doc, "/a/b~1c/9") is a._MISSING  # out of range


# --- re-derivable: confirmed AND witnessed-red self-void ------------------- #
def test_re_derivable_field_is_confirmed_offline():
    res = a.assess(load())
    assert _field(res, NOTE_PTR)["state"] == "re-derived"


def test_re_derivable_self_voids_when_it_does_not_reproduce():
    env = load()
    # mutate the input so the declared sha256-utf8 method no longer reproduces the value
    env["extensions"]["https://thecolony.cc/x/assurance-demo"]["note_text"] += " tampered"
    assert _field(a.assess(env), NOTE_PTR)["state"] == "self-void"


def test_re_derivable_over_jcs_object():
    env = load()
    obj = {"z": 1, "a": [2, 3]}
    digest = "sha256:" + hashlib.sha256(a.jcs(obj)).hexdigest()
    env["extensions"]["https://thecolony.cc/x/assurance-demo"]["obj"] = obj
    env["extensions"]["https://thecolony.cc/x/assurance-demo"]["obj_hash"] = digest
    env["assurance"]["fields"].append({
        "pointer": "/extensions/https:~1~1thecolony.cc~1x~1assurance-demo/obj_hash",
        "grade": "re-derivable",
        "method": "sha256(/extensions/https:~1~1thecolony.cc~1x~1assurance-demo/obj)",
    })
    st = _field(a.assess(env), "/extensions/https:~1~1thecolony.cc~1x~1assurance-demo/obj_hash")["state"]
    assert st == "re-derived"


def test_fetch_method_is_deferred_not_confirmed():
    res = a.assess(load())
    assert _field(res, "/witnessed_claim/content_hash")["state"] == "deferred"


# --- judgment: grade + witnessed-red staleness ----------------------------- #
def test_judgment_principal_named():
    f = _field(a.assess(load()), RISK_PTR)
    assert f["state"] == "judgment" and f["principal_grade"] == "named"


def test_judgment_principal_self_when_it_is_the_issuer():
    env = load()
    issuer_id = env["issuer"]["id"]
    for fld in env["assurance"]["fields"]:
        if fld["pointer"] == RISK_PTR:
            fld["principal"] = issuer_id
    assert _field(a.assess(env), RISK_PTR)["principal_grade"] == "self"


def test_judgment_goes_stale_past_reachable_until():
    res = a.assess(load(), now="2027-01-01T00:00:00Z")  # past reachable_until 2026-10-10
    assert _field(res, RISK_PTR)["state"] == "stale"


# --- mechanism / asserted -------------------------------------------------- #
def test_mechanism_and_asserted():
    res = a.assess(load())
    assert _field(res, "/issuer/id")["state"] == "mechanism"
    assert _field(res, "/extensions/https:~1~1thecolony.cc~1x~1assurance-demo/headline")["state"] == "asserted"


# --- fireable: self-void on dangling + third-party fire -------------------- #
def test_dangling_pointer_self_voids():
    env = load()
    env["assurance"]["fields"].append({"pointer": "/nope/missing", "grade": "re-derivable", "method": "equals(/issuer/id)"})
    r = a.assess(env)
    assert _field(r, "/nope/missing")["state"] == "dangling"
    assert r["state"] == "graded-with-voids"


def test_third_party_fire_voids_a_field():
    res = a.assess(load(), fired=[NOTE_PTR])
    assert _field(res, NOTE_PTR)["state"] == "fired"
    assert res["state"] == "graded-with-voids"


# --- the headline: trust-surface arithmetic -------------------------------- #
def test_trust_surface_profile_math():
    p = a.assess(load())["profile"]
    assert p["total"] == 5
    assert p["confirmed_re_derivable"] == 1
    assert p["deferred_re_derivable"] == 1
    assert p["judgment"] == 1 and p["mechanism"] == 1 and p["asserted"] == 1
    assert p["voided"] == 0
    assert p["trust_surface"] == 0.8   # 1 - 1/5
    assert p["residue_surface"] == 0.6  # (5 - 1 confirmed - 1 deferred) / 5


def test_firing_the_confirmed_field_raises_the_trust_surface():
    p = a.assess(load(), fired=[NOTE_PTR])["profile"]
    assert p["confirmed_re_derivable"] == 0
    assert p["trust_surface"] == 1.0  # nothing left a relier can confirm themselves


def test_ungraded_envelope_reports_floor():
    env = load()
    del env["assurance"]
    r = a.assess(env)
    assert r["state"] == "ungraded" and r["profile"] is None


# --- #25 proposition binding: grade binds to the proposition, not the value -- #
def test_proposition_surfaced_on_field_result():
    # The re-derivable note field carries a proposition scoping what re-derivation buys.
    f = _field(a.assess(load()), NOTE_PTR)
    assert f["state"] == "re-derived"
    assert "proposition" in f and "SHA-256 of the exact note_text" in f["proposition"]
    assert any("grade binds to this proposition" in n for n in f["notes"])


def test_proposition_does_not_change_trust_surface():
    # A proposition scopes the claim; it must not alter the re-derivation accounting.
    p = a.assess(load())["profile"]
    assert p["confirmed_re_derivable"] == 1 and p["trust_surface"] == 0.8


def test_proposition_absent_field_has_no_proposition_key():
    # The asserted headline field declares no proposition — key stays absent.
    f = _field(a.assess(load()), "/extensions/https:~1~1thecolony.cc~1x~1assurance-demo/headline")
    assert "proposition" not in f


def test_proposition_survives_on_mechanism_grade():
    f = _field(a.assess(load()), "/issuer/id")
    assert f["state"] == "mechanism" and "key↔id binding" in f["proposition"]


def test_fired_field_with_proposition_still_voids():
    # Firing a field whose value outruns its proposition drops it to the floor.
    res = a.assess(load(), fired=[NOTE_PTR])
    f = _field(res, NOTE_PTR)
    assert f["state"] == "fired"  # fired short-circuits before the proposition note
    assert res["profile"]["voided"] == 1


# --- the block is inside the signature (advisory tool, but tamper-evident) -- #
def test_mutating_a_grade_is_visible_because_the_block_is_signed():
    # assurance.py is advisory and does not check the sigchain itself; this asserts
    # the DESIGN invariant that the block is covered — the built example must carry a
    # sigchain over the assurance block, so a downstream verify.py catches mutation.
    env = load()
    assert env.get("assurance") and env.get("sigchain")


# --- probe-consistent (v0.1.17): repeatable in kind, committed tolerance ----- #
def _probe_env(field):
    """Minimal envelope carrying one probe-consistent assurance field."""
    return {"issuer": {"id": "did:web:example.com"},
            "latency_p99_ms": 142,
            "assurance": {"fields": [dict({"pointer": "/latency_p99_ms",
                                           "grade": "probe-consistent"}, **field)]}}


def test_probe_consistent_with_committed_tolerance():
    env = _probe_env({"tolerance": {"op": "<=", "value": 250},
                      "falsifier_class": "load-test/closed-loop",
                      "tolerance_commitment": "beacon:drand:4210001"})
    f = _field(a.assess(env), "/latency_p99_ms")
    assert f["state"] == "probe-consistent"
    assert a.assess(env)["profile"]["probe_consistent"] == 1


def test_probe_consistent_self_voids_without_committed_tolerance():
    # witnessed-red: drop the tolerance -> the bound could live only in the falsifier,
    # pickable post-hoc, so the grade self-voids to the floor.
    f = _field(a.assess(_probe_env({})), "/latency_p99_ms")
    assert f["state"] == "self-void"
    assert a.assess(_probe_env({}))["profile"]["voided"] == 1


def test_probe_consistent_goes_stale_past_instance_validity():
    env = _probe_env({"tolerance": {"op": "<=", "value": 250},
                      "valid_until": "2026-07-01T00:00:00Z"})
    fresh = _field(a.assess(env, now="2026-06-01T00:00:00Z"), "/latency_p99_ms")
    stale = _field(a.assess(env, now="2026-08-01T00:00:00Z"), "/latency_p99_ms")
    assert fresh["state"] == "probe-consistent"
    assert stale["state"] == "probe-stale"  # STALE not INVALID — the procedure still re-runs
    # a stale probe field still lives in the probe_consistent bucket, not judgment
    assert a.assess(env, now="2026-08-01T00:00:00Z")["profile"]["probe_consistent"] == 1


def test_probe_consistent_without_commitment_is_flagged_fireable():
    f = _field(a.assess(_probe_env({"tolerance": {"op": "<=", "value": 250}})), "/latency_p99_ms")
    assert f["state"] == "probe-consistent"  # valid, but...
    assert any("tolerance_commitment" in n and "FIREABLE" in n for n in f["notes"])


def test_probe_consistent_counts_in_trust_surface_not_confirmed():
    # not re-derivable -> counts against trust_surface (offline verifier can't re-run it)
    prof = a.assess(_probe_env({"tolerance": {"op": "<=", "value": 250},
                                "tolerance_commitment": "beacon:drand:4210001"}))["profile"]
    assert prof["confirmed_re_derivable"] == 0
    assert prof["trust_surface"] == 1.0
