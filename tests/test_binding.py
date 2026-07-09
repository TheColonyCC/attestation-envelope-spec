"""Tests for §13 issuer→identity binding (GAP-1) in tools/verify.py.

The binding *logic* is proved here with a resolver injected over the committed
fixture DID documents — no network. Live did:web resolution is exercised only in
full mode (a platform must actually serve the did.json); offline is advisory.

Requires: pynacl, base58, jsonschema.
"""
import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import verify  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
EX = ROOT / "examples"
DIDWEB = json.loads((EX / "issuer_didweb.v0.1.json").read_text())
PWITNESS = json.loads((EX / "issuer_platform_witness.v0.1.json").read_text())
DOMAIN_DOC = json.loads((EX / "artifacts" / "did-web-thecolony.cc.did.json").read_text())
AGENT_DOC = json.loads((EX / "artifacts" / "did-web-thecolony.cc-u-colonist-one.did.json").read_text())

# A resolver over the committed fixtures — this is what a live did:web fetch would return.
FIXTURES = {
    "did:web:thecolony.cc": verify.keys_from_did_document(DOMAIN_DOC),
    "did:web:thecolony.cc:u:colonist-one": verify.keys_from_did_document(AGENT_DOC),
}


def resolver(did):
    if did in FIXTURES:
        return FIXTURES[did]
    raise LookupError(f"no fixture for {did}")


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #
def test_did_web_url_host_only():
    assert verify._did_web_https_url("did:web:thecolony.cc") == "https://thecolony.cc/.well-known/did.json"


def test_did_web_url_with_path():
    assert verify._did_web_https_url("did:web:thecolony.cc:u:colonist-one") == "https://thecolony.cc/u/colonist-one/did.json"


def test_keys_from_did_document_reads_multibase():
    keys = verify.keys_from_did_document(AGENT_DOC)
    assert DIDWEB["sigchain"][0]["key_id"] in keys
    assert all(k.startswith("did:key:z") for k in keys)


# --------------------------------------------------------------------------- #
# did:web issuer binding
# --------------------------------------------------------------------------- #
def test_didweb_issuer_binds_with_resolver():
    state, notes = verify.check_issuer_binding(DIDWEB, offline=False, resolve_did=resolver)
    assert state == "bound", notes


def test_didweb_issuer_unverified_offline():
    state, _ = verify.check_issuer_binding(DIDWEB, offline=True)
    assert state == "unverified"


def test_didweb_issuer_wrong_doc_unverified():
    # DID doc that doesn't list the signing key (return the DOMAIN key set instead)
    state, _ = verify.check_issuer_binding(DIDWEB, offline=False, resolve_did=lambda d: FIXTURES["did:web:thecolony.cc"])
    assert state == "unverified"


# --------------------------------------------------------------------------- #
# platform_witness binding
# --------------------------------------------------------------------------- #
def test_platform_witness_binds_with_resolver():
    state, notes = verify.check_issuer_binding(PWITNESS, offline=False, resolve_did=resolver)
    assert state == "bound", notes
    assert "platform_witness" in notes[0]


def test_platform_witness_not_domain_key_unverified():
    # domain authorises nothing -> the witness is not provably the domain
    state, _ = verify.check_issuer_binding(PWITNESS, offline=False, resolve_did=lambda d: set())
    assert state == "unverified"


def test_platform_handle_without_witness_is_unbindable():
    env = copy.deepcopy(PWITNESS)
    env["sigchain"] = env["sigchain"][:1]  # drop the platform_witness co-signature
    state, notes = verify.check_issuer_binding(env, offline=False, resolve_did=resolver)
    assert state == "unbindable"
    assert "GAP-1" in notes[0]


def test_platform_witness_unverified_offline():
    state, _ = verify.check_issuer_binding(PWITNESS, offline=True)
    assert state == "unverified"


# --------------------------------------------------------------------------- #
# did:key issuer still self-binds offline (unchanged from v0.1)
# --------------------------------------------------------------------------- #
def test_didkey_issuer_binds_offline():
    ed = json.loads((EX / "colony_post_published.v0.1.json").read_text())
    state, _ = verify.check_issuer_binding(ed, offline=True)
    assert state == "bound"


# --------------------------------------------------------------------------- #
# integration through verify(): binding is advisory, examples still ACCEPT
# --------------------------------------------------------------------------- #
def test_examples_accept_offline_with_advisory_binding():
    for ex in (DIDWEB, PWITNESS):
        v = verify.verify(copy.deepcopy(ex), offline=True)
        assert v["accept"], v["reasons"]
        assert v["checks"]["issuer_binding"]["state"] == "unverified"
        assert not v["checks"]["sigchain"]["issuer_bound"]
