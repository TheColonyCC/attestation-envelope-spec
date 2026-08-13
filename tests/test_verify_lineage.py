"""Tests for the independent lineage-bundle verifier (tools/verify_lineage.py).

Hermetic: offline only, no network. The point under test is that the verdict is
re-derived from the envelope signatures and does NOT trust the bundle's own
advisory `verification` block — so the adversarial cases flip a signature while
leaving the advisory verdict saying "ok", and assert the tool rejects anyway and
reports the divergence. Run: pytest tests/
Requires: jsonschema, pynacl, base58.
"""
import base64
import json
import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
import verify_lineage  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
TWOGEN = ROOT / "examples" / "lineage_twogen.v0.1.json"
EMBERVANE = ROOT / "examples" / "progenly_lineage_embervane.v0.1.json"


def _load(p):
    return json.loads(p.read_text())


def test_twogen_accepts_and_links():
    rpt = verify_lineage.verify_bundle(_load(TWOGEN))
    assert rpt["accept"], rpt["reasons"]
    assert rpt["generation_count"] == 2
    assert all(g["accept"] for g in rpt["generations"])
    # the grandparent (ancestor) is cryptographically bound to the subject.
    assert rpt["linkage"]["linked"] == [1]
    assert rpt["linkage"]["unlinked"] == []
    assert rpt["divergences"] == []


def test_real_progenly_bundle_accepts():
    """The committed real prod bundle verifies independently (no Progenly code)."""
    rpt = verify_lineage.verify_bundle(_load(EMBERVANE))
    assert rpt["accept"], rpt["reasons"]
    assert rpt["generation_count"] >= 1
    assert rpt["generations"][0]["accept"]
    assert rpt["generations"][0]["issuer_bound"]  # did:key issuer binds


def test_tampered_sig_rejected_despite_advisory_ok():
    """Flip a signature byte but leave advisory ok=True: tool must still REJECT
    and surface the divergence. This is the no-self-attestation guarantee."""
    bundle = _load(TWOGEN)
    sig = bundle["generations"][0]["certificate"]["sigchain"][0]["sig"]
    raw = bytearray(base64.urlsafe_b64decode(sig + "=="))
    raw[0] ^= 0xFF
    bundle["generations"][0]["certificate"]["sigchain"][0]["sig"] = (
        base64.urlsafe_b64encode(bytes(raw)).decode().rstrip("=")
    )
    # advisory block still claims ok (it always does) — we must not trust it.
    assert bundle["generations"][0]["verification"]["ok"] is True
    rpt = verify_lineage.verify_bundle(bundle)
    assert not rpt["accept"]
    assert not rpt["generations"][0]["accept"]
    assert any(d["index"] == 0 for d in rpt["divergences"])


def test_broken_linkage_detected():
    """Sever the subject->grandparent hash binding: linkage must flag the ancestor."""
    bundle = _load(TWOGEN)
    # change the subject's parent evidence hash so it no longer matches the gp.
    bundle["generations"][0]["certificate"]["evidence"][0]["content_hash"] = "sha256:" + "0" * 64
    rpt = verify_lineage.verify_bundle(bundle)
    # the subject's own signature now fails too (evidence is signed), so accept is
    # False regardless; the linkage report must still name the unbound ancestor.
    assert rpt["linkage"]["unlinked"] == [1]
    assert not rpt["accept"]


def test_revoked_generation_blocks_accept():
    bundle = _load(TWOGEN)
    bundle["generations"][1]["revoked"] = True
    rpt = verify_lineage.verify_bundle(bundle)
    assert not rpt["accept"]
    assert rpt["revoked"] and rpt["revoked"][0]["index"] == 1
