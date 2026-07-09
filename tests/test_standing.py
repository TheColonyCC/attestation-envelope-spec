"""Tests for §12 standing / monument detection (tools/verify.py check_standing).

A signed conclusion that outlives the relation and the party who could contest
it is a *monument*. These tests pin the four monument triggers and the one
contestable pass, plus the two committed worked examples.

Hermetic (offline / pure-function). Requires: pynacl, base58, jsonschema.
"""
import copy
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import verify  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTESTABLE = json.loads((ROOT / "examples" / "standing_contestable.v0.1.json").read_text())
MONUMENT = json.loads((ROOT / "examples" / "monument_perpetual.v0.1.json").read_text())

NOW = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)  # inside both example windows
ISSUER_ID = CONTESTABLE["issuer"]["id"]


# --------------------------------------------------------------------------- #
# committed worked examples
# --------------------------------------------------------------------------- #
def test_contestable_example_accepts_not_monument():
    v = verify.verify(copy.deepcopy(CONTESTABLE), offline=True, now=NOW)
    assert v["accept"], v["reasons"]
    assert v["monument"] is False
    assert v["checks"]["standing"]["state"] == "contestable"


def test_monument_example_accepts_but_flagged():
    v = verify.verify(copy.deepcopy(MONUMENT), offline=True, now=NOW)
    assert v["accept"], v["reasons"]  # cryptographically valid...
    assert v["monument"] is True       # ...but a monument
    assert v["checks"]["standing"]["state"] == "monument"
    assert any("MONUMENT" in r for r in v["reasons"])


# --------------------------------------------------------------------------- #
# the four monument triggers (pure-function)
# --------------------------------------------------------------------------- #
def test_perpetual_without_standing_is_monument():
    env = copy.deepcopy(MONUMENT)
    env.pop("standing", None)
    assert env["validity"]["validity_model"] == "perpetual"
    state, notes = verify.check_standing(env, now=NOW, offline=True)
    assert state == "monument"
    assert "perpetual" in notes[0]


def test_self_only_contestable_by_is_monument():
    env = copy.deepcopy(CONTESTABLE)
    env["standing"]["contestable_by"] = [
        {"id_scheme": "did:key", "id": ISSUER_ID, "display_name": "issuer contesting itself"}
    ]
    state, notes = verify.check_standing(env, now=NOW, offline=True)
    assert state == "monument"
    assert "self-contestation" in notes[0]


def test_lapsed_contest_window_is_monument():
    env = copy.deepcopy(CONTESTABLE)
    env["standing"]["contestable_until"] = "2026-07-15T00:00:00Z"  # before NOW
    state, notes = verify.check_standing(env, now=NOW, offline=True)
    assert state == "monument"
    assert "window closed" in notes[0] or "lapsed" in notes[0]


def test_timebounded_without_standing_is_not_monument():
    """No standing block on a time_bounded claim is undeclared, not a monument
    (validity already governs its expiry). Only perpetual-no-standing is a monument."""
    env = copy.deepcopy(CONTESTABLE)
    env.pop("standing", None)
    assert env["validity"]["validity_model"] == "time_bounded"
    state, _ = verify.check_standing(env, now=NOW, offline=True)
    assert state == "n/a"


# --------------------------------------------------------------------------- #
# the contestable pass
# --------------------------------------------------------------------------- #
def test_live_standing_is_contestable():
    env = copy.deepcopy(CONTESTABLE)
    state, notes = verify.check_standing(env, now=NOW, offline=True)
    assert state == "contestable"
    assert "non-issuer" in notes[0]


def test_multiple_contesters_counted():
    env = copy.deepcopy(CONTESTABLE)
    env["standing"]["contestable_by"].append(
        {"id_scheme": "platform-handle", "id": "moltbook.com:reviewer", "display_name": "second reviewer"}
    )
    state, notes = verify.check_standing(env, now=NOW, offline=True)
    assert state == "contestable"
    assert "2 non-issuer" in notes[0]


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #
def test_schema_rejects_empty_contestable_by():
    import jsonschema

    schema = json.loads((ROOT / "schemas" / "envelope.v0.1.schema.json").read_text())
    env = copy.deepcopy(CONTESTABLE)
    env["standing"]["contestable_by"] = []  # minItems: 1
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(env))


def test_schema_rejects_standing_missing_required_field():
    import jsonschema

    schema = json.loads((ROOT / "schemas" / "envelope.v0.1.schema.json").read_text())
    env = copy.deepcopy(CONTESTABLE)
    del env["standing"]["contest_uri"]
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(env))


def test_envelope_without_standing_still_valid():
    """Backward compat: standing is optional; a v0.1.6 envelope stays schema-valid."""
    import jsonschema

    schema = json.loads((ROOT / "schemas" / "envelope.v0.1.schema.json").read_text())
    env = copy.deepcopy(CONTESTABLE)
    env.pop("standing", None)
    assert not list(jsonschema.Draft202012Validator(schema).iter_errors(env))
