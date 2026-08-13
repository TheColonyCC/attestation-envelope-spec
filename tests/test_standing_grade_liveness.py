"""Tests for the v0.1.9 additions to §12 standing: standing_grade + contest-channel
liveness. Grade is pure/offline; liveness uses an injected http_get (no network).

Requires: pynacl, base58, jsonschema.
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
NOW = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)
ISSUER_ID = CONTESTABLE["issuer"]["id"]


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


# --------------------------------------------------------------------------- #
# standing_grade — named > venue > self > None
# --------------------------------------------------------------------------- #
def test_grade_venue_for_platform_handle_contester():
    # the committed example contests via a platform-handle venue
    assert verify.standing_grade(CONTESTABLE) == "venue"


def test_grade_named_for_did_contester():
    env = copy.deepcopy(CONTESTABLE)
    env["standing"]["contestable_by"] = [
        {"id_scheme": "did:key", "id": "did:key:z6MkNamedReviewer", "display_name": "a keyed reviewer"}
    ]
    assert verify.standing_grade(env) == "named"


def test_grade_named_wins_when_mixed():
    env = copy.deepcopy(CONTESTABLE)
    env["standing"]["contestable_by"].append(
        {"id_scheme": "did:web", "id": "did:web:auditor.example", "display_name": "keyed auditor"}
    )
    assert verify.standing_grade(env) == "named"


def test_grade_self_for_issuer_only():
    env = copy.deepcopy(CONTESTABLE)
    env["standing"]["contestable_by"] = [
        {"id_scheme": "did:key", "id": ISSUER_ID, "display_name": "issuer itself"}
    ]
    assert verify.standing_grade(env) == "self"


def test_grade_none_without_standing():
    env = copy.deepcopy(CONTESTABLE)
    env.pop("standing", None)
    assert verify.standing_grade(env) is None


def test_grade_surfaced_in_verdict():
    v = verify.verify(copy.deepcopy(CONTESTABLE), offline=True, now=NOW)
    assert v["checks"]["standing"]["grade"] == "venue"


# --------------------------------------------------------------------------- #
# contest-channel liveness
# --------------------------------------------------------------------------- #
def test_liveness_live_channel():
    env = copy.deepcopy(CONTESTABLE)  # has a contest_status_uri
    state, notes = verify.check_standing(
        env, now=NOW, offline=False, http_get=lambda u: _Resp(200, {"state": "none"})
    )
    assert state == "contestable"
    assert any("contest channel LIVE" in n for n in notes)


def test_liveness_unreachable_channel_degrades():
    env = copy.deepcopy(CONTESTABLE)
    state, notes = verify.check_standing(
        env, now=NOW, offline=False, http_get=lambda u: _Resp(404)
    )
    assert state == "contestable"  # advisory, not a hard flip
    assert any("UNREACHABLE" in n and "degraded" in n for n in notes)


def test_liveness_open_contest_flagged():
    env = copy.deepcopy(CONTESTABLE)
    _, notes = verify.check_standing(
        env, now=NOW, offline=False, http_get=lambda u: _Resp(200, {"state": "open"})
    )
    assert any("a contest is open" in n for n in notes)


def test_liveness_undeclared_when_no_status_uri():
    env = copy.deepcopy(CONTESTABLE)
    env["standing"].pop("contest_status_uri", None)
    _, notes = verify.check_standing(env, now=NOW, offline=False, http_get=lambda u: _Resp(200))
    assert any("liveness" in n and "UNDECLARED" in n for n in notes)


def test_liveness_skipped_offline():
    _, notes = verify.check_standing(copy.deepcopy(CONTESTABLE), now=NOW, offline=True)
    assert any("SKIPPED (offline)" in n for n in notes)


def test_grade_note_present_on_contestable():
    _, notes = verify.check_standing(copy.deepcopy(CONTESTABLE), now=NOW, offline=True)
    assert any("standing grade:" in n for n in notes)
