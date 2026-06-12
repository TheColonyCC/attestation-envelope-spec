"""Tests for the v0.2-draft strawman (credential_issued claim + onchain_event evidence).

DRAFT: these assert *structural* validity against the draft schema only. The
example envelopes are intentionally unsigned strawmen (placeholder sigchain),
so nothing here asserts cryptographic verification — that lands when the shape
is sealed and the mden-entity on-chain values arrive from the Entity Framework.

Run with: pytest tests/
Requires: pip install jsonschema pytest
"""
import copy
import json
import pathlib

import jsonschema

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "envelope.v0.2-draft.schema.json").read_text())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)

CREDENTIAL = json.loads((ROOT / "examples" / "credential-issued-strawman.v0.2-draft.json").read_text())
MDEN = json.loads((ROOT / "examples" / "mden-entity-tierup.v0.2-draft.json").read_text())


def test_schema_itself_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_credential_example_validates():
    jsonschema.validate(CREDENTIAL, SCHEMA, cls=jsonschema.Draft202012Validator)


def test_mden_entity_example_validates():
    jsonschema.validate(MDEN, SCHEMA, cls=jsonschema.Draft202012Validator)


# ---- Claim_CredentialIssued -------------------------------------------------

def test_reject_credential_without_kind():
    bad = copy.deepcopy(CREDENTIAL)
    del bad["witnessed_claim"]["credential_kind"]
    assert list(VALIDATOR.iter_errors(bad)), "credential_kind is required"


def test_reject_credential_unknown_kind():
    bad = copy.deepcopy(CREDENTIAL)
    bad["witnessed_claim"]["credential_kind"] = "rot13_token"
    assert list(VALIDATOR.iter_errors(bad)), "credential_kind enum should reject unknown kinds"


def test_reject_credential_without_issuance_record():
    bad = copy.deepcopy(CREDENTIAL)
    del bad["witnessed_claim"]["issuance_record_uri"]
    assert list(VALIDATOR.iter_errors(bad)), "issuance_record_uri is required — claim must point at an external record"


def test_reject_credential_extra_field_smuggling_a_secret():
    # additionalProperties:false is the secret-free guard — a stray `secret`
    # field (or any unknown key) must fail rather than ride along.
    bad = copy.deepcopy(CREDENTIAL)
    bad["witnessed_claim"]["secret"] = "sk-live-do-not-do-this"
    assert list(VALIDATOR.iter_errors(bad)), "unknown fields (incl. secret material) must be rejected"


def test_rotation_history_entry_requires_witness():
    bad = copy.deepcopy(CREDENTIAL)
    del bad["witnessed_claim"]["rotation_history"][0]["rotation_witness_uri"]
    assert list(VALIDATOR.iter_errors(bad)), "each rotation entry must bind to an external witness"


def test_credential_first_issuance_without_rotation_history_ok():
    ok = copy.deepcopy(CREDENTIAL)
    del ok["witnessed_claim"]["rotation_history"]
    assert not list(VALIDATOR.iter_errors(ok)), "rotation_history is optional (absent = first issuance)"


# ---- onchain_event evidence pointer ----------------------------------------

def test_reject_onchain_event_without_onchain_block():
    bad = copy.deepcopy(MDEN)
    del bad["evidence"][0]["onchain"]
    assert list(VALIDATOR.iter_errors(bad)), "onchain_event pointer requires the onchain ref block"


def test_reject_onchain_bad_contract_address():
    bad = copy.deepcopy(MDEN)
    bad["evidence"][0]["onchain"]["contract_address"] = "0xNOTHEX"
    assert list(VALIDATOR.iter_errors(bad)), "contract_address must be 0x + 40 lowercase hex"


def test_reject_onchain_missing_event_signature():
    bad = copy.deepcopy(MDEN)
    del bad["evidence"][0]["onchain"]["event_signature"]
    assert list(VALIDATOR.iter_errors(bad)), "event_signature is required for recomputable topic0"
