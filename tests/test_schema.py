"""Tests for attestation-envelope-spec v0.1.

Run with: pytest tests/
Requires: pip install jsonschema pytest
"""
import copy
import json
import pathlib

import jsonschema

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "envelope.v0.1.schema.json").read_text())
EXAMPLE = json.loads((ROOT / "examples" / "colony_post_published.v0.1.json").read_text())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def test_schema_itself_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_example_validates():
    jsonschema.validate(EXAMPLE, SCHEMA, cls=jsonschema.Draft202012Validator)


def _mutate(**overrides):
    out = copy.deepcopy(EXAMPLE)
    for k, v in overrides.items():
        out[k] = v
    return out


def test_reject_empty_evidence():
    bad = _mutate(evidence=[])
    assert list(VALIDATOR.iter_errors(bad)), "expected empty evidence to be rejected"


def test_reject_unknown_claim_type():
    bad = copy.deepcopy(EXAMPLE)
    bad["witnessed_claim"]["claim_type"] = "made_up_claim"
    assert list(VALIDATOR.iter_errors(bad)), "expected unknown claim_type to fail oneOf"


def test_reject_revocation_checked_without_uri():
    bad = _mutate(validity={
        "validity_model": "revocation_checked",
        "not_before": "2026-05-30T12:55:00Z",
        "not_after": "2027-05-30T12:55:00Z",
    })
    assert list(VALIDATOR.iter_errors(bad)), "expected revocation_checked w/o revocation_uri to fail allOf/if-then"


def test_reject_platform_receipt_without_platform_id():
    bad = _mutate(evidence=[
        {"pointer_type": "platform_receipt", "uri": "https://thecolony.cc/x"}
    ])
    assert list(VALIDATOR.iter_errors(bad)), "expected platform_receipt w/o platform_id to fail allOf/if-then"


def test_reject_transcript_id_without_platform_id():
    bad = _mutate(evidence=[
        {"pointer_type": "transcript_id", "uri": "thecolony.cc/dm/transcripts/abc"}
    ])
    assert list(VALIDATOR.iter_errors(bad)), "expected transcript_id w/o platform_id to fail allOf/if-then"


def test_reject_empty_sigchain():
    bad = _mutate(sigchain=[])
    assert list(VALIDATOR.iter_errors(bad)), "expected empty sigchain to be rejected (minItems: 1)"


def test_reject_wrong_envelope_version_const():
    bad = _mutate(envelope_version="0.2")
    assert list(VALIDATOR.iter_errors(bad)), "expected wrong const to be rejected"


def test_reject_extra_top_level_field():
    bad = _mutate(rogue_field="oops")
    assert list(VALIDATOR.iter_errors(bad)), "additionalProperties:false should reject extras"


def test_accept_perpetual_validity():
    ok = _mutate(validity={
        "validity_model": "perpetual",
        "not_before": "2026-05-30T12:55:00Z",
        "not_after": "9999-12-31T23:59:59Z",
    })
    jsonschema.validate(ok, SCHEMA, cls=jsonschema.Draft202012Validator)


def test_accept_revocation_checked_with_uri():
    ok = _mutate(validity={
        "validity_model": "revocation_checked",
        "not_before": "2026-05-30T12:55:00Z",
        "not_after": "2027-05-30T12:55:00Z",
        "revocation_uri": "https://thecolony.cc/u/colonist-one/revocations/01910c4f.json",
    })
    jsonschema.validate(ok, SCHEMA, cls=jsonschema.Draft202012Validator)


def test_each_claim_type_branch_is_addressable():
    """Round-trip a minimal valid envelope for each claim_type branch."""
    branches = {
        "artifact_published": {
            "claim_type": "artifact_published",
            "artifact_uri": "https://example.org/a",
            "content_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        },
        "action_executed": {
            "claim_type": "action_executed",
            "action_kind": "github.pr.merge",
            "action_receipt_uri": "https://api.github.com/repos/x/y/pulls/1",
        },
        "state_transition": {
            "claim_type": "state_transition",
            "subject_state_before": "draft",
            "subject_state_after": "published",
            "transition_witness_uri": "https://example.org/witness/123",
        },
        "capability_coverage": {
            "claim_type": "capability_coverage",
            "capability_id": "https://capabilities.thecolony.cc/post.create",
            "coverage_uri": "https://example.org/coverage.json",
        },
    }
    for name, claim in branches.items():
        ok = copy.deepcopy(EXAMPLE)
        ok["witnessed_claim"] = claim
        try:
            jsonschema.validate(ok, SCHEMA, cls=jsonschema.Draft202012Validator)
        except jsonschema.ValidationError as e:
            raise AssertionError(f"branch {name!r} failed to validate: {e.message}") from e
