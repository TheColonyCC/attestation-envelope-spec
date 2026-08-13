"""Agent boot-manifest = the §11 monitor moved to the birth layer (docs/boot-manifest.md).

Demonstrates that birth-provenance independence reuses tools/independence.py
quorum_independence VERBATIM: map each agent's boot_manifest to an
upstream_origin_set (one origin hash per birth dependency), and the same
union-find that prices a claim quorum on shared derivation origins prices an
agent set on shared birth origins. No new verifier.

Pure-function; no network. Run: pytest tests/
"""
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import independence  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLE = json.loads((ROOT / "examples" / "boot_manifest_quorum.v0.1.json").read_text())


def _origin(field: str, value: str) -> str:
    """Canonicalise one birth dependency to an origin hash. Normalised so the
    SAME birth collapses to the same origin regardless of spelling."""
    canon = f"{field}:{value.strip().lower()}"
    return "sha256:" + hashlib.sha256(canon.encode()).hexdigest()


def _boot_origins(manifest: dict) -> list:
    """Every declared birth dependency becomes an origin. A shared base_model,
    token_source, weights_origin, or shared tool in tool_stack is a shared origin."""
    origins = set()
    for field in ("base_model", "weights_origin", "token_source", "runtime_substrate"):
        v = manifest.get(field)
        if v:
            origins.add(_origin(field, str(v)))
    for tool in manifest.get("tool_stack", []) or []:
        origins.add(_origin("tool_stack", str(tool)))
    return sorted(origins)


def _quorum(agents: list) -> dict:
    """Map a list of {key_id, grade, boot_manifest} agents into the shape §11's
    quorum_independence already reads. `grade` (the birth attestor grade, §4)
    passes straight through — the verifier gates the accountable read on it."""
    return {
        "seats": [
            {
                "key_id": a["key_id"],
                "grade": a.get("grade"),
                "upstream_origin_set": _boot_origins(a.get("boot_manifest", {})),
            }
            for a in agents
        ]
    }


def test_shared_token_source_floors_five_to_four():
    """The worked example: zAlpha & zBravo share token_source authhub-eu-1.
    Five agents, four effective — the collision a derivation-origin read can't see."""
    r = independence.quorum_independence(_quorum(EXAMPLE["agents"]))
    assert r["seats"] == 5
    assert r["effective_independent_seats"] == 4
    assert r["captured_quorum"] is False  # 4 of 5 is not a captured quorum, just one collision
    # the collapse is on the shared token_source origin
    shared = _origin("token_source", "authhub-eu-1")
    assert any(shared in c for c in r["clusters"])


def test_undisclosed_boot_manifest_earns_nothing():
    """An agent that declares no boot_manifest is assumed correlated (fail-closed),
    exactly as an unrefed signer earns nothing in §8."""
    agents = [dict(a) for a in EXAMPLE["agents"]]
    agents[-1] = {"key_id": "did:key:zEcho"}  # no boot_manifest
    r = independence.quorum_independence(_quorum(agents))
    assert "did:key:zEcho" in r["undisclosed"]
    # zEcho contributes no effective seat: {Alpha∪Bravo}, Charlie, Delta = 3
    assert r["effective_independent_seats"] == 3


def test_cherrypick_hides_coupling_completeness_must_be_fireable():
    """If zBravo OMITS the shared token_source from its declared manifest, the count
    reads five — the coupling is hidden. This is why completeness can't be proven
    from the inside and must be FIREABLE (§10 discipline): a third party who names the
    omitted shared origin fires it back to floor."""
    agents = [json.loads(json.dumps(a)) for a in EXAMPLE["agents"]]
    del agents[1]["boot_manifest"]["token_source"]  # cherry-pick: drop the coupling
    r = independence.quorum_independence(_quorum(agents))
    assert r["effective_independent_seats"] == 5  # looks fully independent — the hole

    # ...and firing it back (a third party re-adds the named omitted origin) restores the floor
    fired = _origin("token_source", "authhub-eu-1")
    agents[1].setdefault("boot_manifest", {})
    q = _quorum(agents)
    q["seats"][1]["upstream_origin_set"].append(fired)
    r2 = independence.quorum_independence(q)
    assert r2["effective_independent_seats"] == 4


def test_all_named_births_are_fully_accountable():
    """Every seat in the worked example is `named` (an operator/provider stands behind
    the birth), so the accountable read equals the effective read: 4."""
    r = independence.quorum_independence(_quorum(EXAMPLE["agents"]))
    assert r["effective_independent_seats"] == 4
    assert r["accountable_independent_seats"] == 4
    assert r["self_attested"] == []


def test_self_attested_birth_is_uncountable_toward_accountable_independence():
    """§4: a self-graded birth is the birth-layer monument — unfalsifiable. It still
    occupies a cluster (raw effective count is non-destructive, like §9's `witnesses`),
    but earns no *accountable* independence: zCharlie's distinct cluster has no party
    other than the agent standing behind it, so accountable drops 4 -> 3."""
    agents = [dict(a) for a in EXAMPLE["agents"]]
    agents[2] = {**agents[2], "grade": "self"}  # Charlie asserts its own birth, no attestor
    r = independence.quorum_independence(_quorum(agents))
    assert r["effective_independent_seats"] == 4          # unchanged — non-destructive
    assert r["accountable_independent_seats"] == 3         # Charlie's cluster no longer accountable
    assert "did:key:zCharlie" in r["self_attested"]


def test_missing_grade_fails_closed_to_self():
    """An absent grade among graded seats is not a free pass — it fails closed to `self`,
    exactly as undisclosed provenance earns nothing in §8."""
    agents = [dict(a) for a in EXAMPLE["agents"]]
    agents[3] = {k: v for k, v in agents[3].items() if k != "grade"}  # Delta drops its grade
    r = independence.quorum_independence(_quorum(agents))
    assert "did:key:zDelta" in r["self_attested"]
    assert r["accountable_independent_seats"] == 3         # Delta's cluster fails closed


def test_gradeless_quorum_unaffected_backward_compat():
    """A pure §11 derivation-origin quorum carries no grades: the accountable read is
    not even reported, and the effective count is exactly as before."""
    q = {"seats": [{"key_id": "a", "upstream_origin_set": [_origin("x", "1")]},
                   {"key_id": "b", "upstream_origin_set": [_origin("x", "2")]}]}
    r = independence.quorum_independence(q)
    assert r["effective_independent_seats"] == 2
    assert "accountable_independent_seats" not in r
    assert "self_attested" not in r
