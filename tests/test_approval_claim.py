"""Tests for the v0.1.10 additions: the `human_action_approval` claim type and the
`colony-sub` subject id_scheme (driven by Glyt as the first real approval issuer).

Requires: pynacl, base58, jsonschema.
"""
import copy
import json
import pathlib
import sys

import jsonschema

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import verify  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "envelope.v0.1.schema.json").read_text())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
EX = json.loads((ROOT / "examples" / "human_action_approval.v0.1.json").read_text())


# --------------------------------------------------------------------------- #
# the worked example verifies
# --------------------------------------------------------------------------- #
def test_example_accepts_offline():
    v = verify.verify(copy.deepcopy(EX), offline=True)
    assert v["accept"], v["reasons"]
    assert EX["witnessed_claim"]["claim_type"] == "human_action_approval"
    assert EX["subject"]["id_scheme"] == "colony-sub"
    assert v["checks"]["standing"]["grade"] == "named"


# --------------------------------------------------------------------------- #
# schema — the claim type
# --------------------------------------------------------------------------- #
def test_schema_accepts_human_action_approval():
    assert not list(VALIDATOR.iter_errors(EX))


def test_schema_rejects_missing_action_digest():
    bad = copy.deepcopy(EX)
    del bad["witnessed_claim"]["action_digest"]
    assert list(VALIDATOR.iter_errors(bad))


def test_schema_rejects_bad_decision_enum():
    bad = copy.deepcopy(EX)
    bad["witnessed_claim"]["decision"] = "maybe"
    assert list(VALIDATOR.iter_errors(bad))


def test_schema_rejects_extra_claim_field():
    bad = copy.deepcopy(EX)
    bad["witnessed_claim"]["operator_name"] = "Jack"  # additionalProperties: false; never a human identity
    assert list(VALIDATOR.iter_errors(bad))


def test_optional_fields_can_be_dropped():
    ok = copy.deepcopy(EX)
    for f in ("approver_ref", "acr", "amr", "approved_at"):
        ok["witnessed_claim"].pop(f, None)
    assert not list(VALIDATOR.iter_errors(ok))


# --------------------------------------------------------------------------- #
# schema — the colony-sub id_scheme
# --------------------------------------------------------------------------- #
def test_colony_sub_valid_as_subject():
    assert EX["subject"]["id_scheme"] == "colony-sub"
    assert not list(VALIDATOR.iter_errors(EX))


def test_unknown_id_scheme_still_rejected():
    bad = copy.deepcopy(EX)
    bad["subject"]["id_scheme"] = "did:evm"  # not in the enum
    assert list(VALIDATOR.iter_errors(bad))


# --------------------------------------------------------------------------- #
# verifier — colony-sub issuer is unbindable (advisory), not a crash
# --------------------------------------------------------------------------- #
def test_colony_sub_issuer_is_unbindable():
    env = copy.deepcopy(EX)
    env["issuer"] = {"id_scheme": "colony-sub", "id": "324ab98e-955c-4274-bd30-8570cbdf58f1"}
    # (signature won't match the new issuer, but binding is computed on the sig-verified path;
    #  here we call the binding check directly.)
    state, notes = verify.check_issuer_binding(env, offline=True)
    assert state == "unbindable"


def test_regression_artifact_published_still_valid():
    ap = json.loads((ROOT / "examples" / "colony_post_published.v0.1.json").read_text())
    assert not list(VALIDATOR.iter_errors(ap))
