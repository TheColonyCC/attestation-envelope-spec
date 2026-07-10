"""touchstone_live.py — reference adapter: verify §12.3 standing against a LIVE
Touchstone recorder.

`standing_anchor.py` folds a generic profile from data inlined in the envelope.
This adapter fetches that data from a real Touchstone deployment's hash-only
endpoints and runs the *same* fold, so §12.3 standing verifies against mainnet
instead of an injected feed. It is issuer-specific glue (Touchstone's wire
formats), kept out of the generic verifier on purpose.

Endpoints (touchstone.cv), all hash-only — never reveal a payload:
  - lower bound (it existed):
      /.well-known/touchstone/checkpoints/{rec}/entry/{seq}      touchstone-inclusion-proof/1
  - upper bound (still live?):
      /.well-known/touchstone/checkpoints/{rec}/contests?target={digest}  touchstone-contest-channel/1
  - Bitcoin anchor (height/time):
      /.well-known/touchstone/checkpoints/{rec}                  cross-referenced by checkpoint id

TRUST STANCE — we do not trust the server's labels:
  * recompute `entry_hash` from the revealed header fields and fold the
    inclusion_proof to the checkpoint root OURSELVES (leaf/node construction from
    standing_anchor);
  * independently verify each contestant's ed25519 signature — grade `verified`
    only when the sig checks against a contestant key BOUND at /pubkeys, else
    `claimed` (a self-asserted key);
  * resolve the checkpoint's Bitcoin anchor from the feed. Mainnet SPV of the OTS
    proof stays delegated (see verify_anchor / OpenTimestamps), exactly as in the
    generic verifier — offline the anchor is the checkpoint's own confirmed report.

Standing alignment (per the design): `provable_through` for standing binds to the
CONTEST recorder's latest checkpoint, not the attestation recorder's — the
attestation only needs including once (lower bound); "still live" is governed
entirely by the contest leg's freshness.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import pathlib
from typing import Any, Callable, Optional

import standing_anchor as sa

INCLUSION_FORMAT = "touchstone-inclusion-proof/1"
CONTEST_FORMAT = "touchstone-contest-channel/1"


# --------------------------------------------------------------------------- #
# Primitives — recompute what the server hands us, don't trust its hashes.
# --------------------------------------------------------------------------- #
def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _jcs(obj: Any) -> bytes:
    """Touchstone's canonical form: sorted keys, compact, UTF-8 (ensure_ascii off)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def recompute_entry_hash(entry: dict) -> str:
    """entry_hash = sha256(join("\\n", [seq, prev_hash, server_ts, payload_hash,
    actor_sub, counterparty_sub|'', actor_sig])) — the construction the endpoint's
    own `how` field documents, recomputed so we never take entry_hash on faith."""
    parts = [
        str(entry["seq"]),
        entry.get("prev_hash") or "",
        entry.get("server_ts") or "",
        entry["payload_hash"],
        entry["actor_sub"],
        entry.get("counterparty_sub") or "",
        entry["actor_sig"],
    ]
    return _sha256_hex("\n".join(parts).encode("utf-8"))


def _ed25519_ok(pubkey_b64: str, msg: bytes, sig_b64: str) -> bool:
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
    except Exception:  # pragma: no cover
        raise RuntimeError("pynacl required for contestant-signature verification")
    try:
        VerifyKey(base64.b64decode(pubkey_b64)).verify(msg, base64.b64decode(sig_b64 + "=" * (-len(sig_b64) % 4)))
        return True
    except (BadSignatureError, Exception):
        return False


def contest_signed_content(contest: dict, recorder_id: str) -> bytes:
    """The bytes a contestant signs (from the contests endpoint's `how`):
    JCS of {v, recorder_id, event_type, actor_sub, counterparty_sub, payload_hash, client_ts}."""
    return _jcs({
        "v": 1,
        "recorder_id": recorder_id,
        "event_type": contest.get("event_type", "touchstone.contest"),
        "actor_sub": contest["actor_sub"],
        "counterparty_sub": contest.get("counterparty_sub"),
        "payload_hash": contest["payload_hash"],
        "client_ts": contest.get("client_ts"),
    })


# --------------------------------------------------------------------------- #
# Feed anchor resolution — the entry/contest checkpoint objects carry root+head+
# an ots *path*, not the inline confirmed anchor; that lives in the feed.
# --------------------------------------------------------------------------- #
def anchor_from_feed(feed: dict, checkpoint_id) -> tuple[Optional[dict], list[str]]:
    for cp in feed.get("checkpoints", []) or []:
        if cp.get("id") == checkpoint_id:
            return sa.anchor_lower_bound(cp)  # feed cp has the raw anchors[] shape
    return None, [f"checkpoint #{checkpoint_id} not found in recorder feed — cannot resolve Bitcoin anchor"]


# --------------------------------------------------------------------------- #
# Lower bound — the attestation was included.
# --------------------------------------------------------------------------- #
def verify_inclusion_response(resp: dict, feed: dict) -> tuple[bool, Optional[dict], list[str]]:
    notes: list[str] = []
    if resp.get("format") != INCLUSION_FORMAT:
        return False, None, [f"unexpected format {resp.get('format')!r} (want {INCLUSION_FORMAT})"]
    entry = resp["entry"]
    cp = resp["checkpoint"]
    got = recompute_entry_hash(entry)
    if got != entry.get("entry_hash"):
        return False, None, [f"entry_hash recompute mismatch — server said {str(entry.get('entry_hash'))[:12]}…, we got {got[:12]}…"]
    if not sa.verify_inclusion(entry["entry_hash"], resp.get("inclusion_proof", []), cp["merkle_root"]):
        return False, None, ["inclusion FAILED — entry does not fold to checkpoint merkle_root"]
    notes.append(f"lower bound: entry seq {entry['seq']} folds to checkpoint #{cp.get('id')} root {cp['merkle_root'][:12]}… (recomputed)")
    lb, anotes = anchor_from_feed(feed, cp.get("id"))
    notes += anotes
    if lb is None:
        return False, None, notes
    return True, lb, notes


# --------------------------------------------------------------------------- #
# Upper bound — is a contest anchored against this digest?
# --------------------------------------------------------------------------- #
def verify_contest(contest: dict, recorder_id: str, *, pubkey_bound: Optional[Callable] = None) -> dict:
    """Verify one contest object: inclusion fold + independent signature grade.
    `pubkey_bound(sub, pubkey_b64) -> bool` says whether that key is bound at /pubkeys."""
    out = {"seq": contest.get("seq"), "actor_sub": contest.get("actor_sub"),
           "inclusion_ok": False, "sig_ok": False, "grade": "unsigned", "anchored": bool(contest.get("anchored")), "notes": []}
    cp = contest.get("checkpoint") or {}
    eh = recompute_entry_hash(contest)
    if eh != contest.get("entry_hash"):
        out["notes"].append("entry_hash recompute mismatch")
        return out
    out["inclusion_ok"] = sa.verify_inclusion(contest["entry_hash"], contest.get("inclusion_proof", []), cp.get("merkle_root", ""))
    pub = contest.get("contestant_pubkey")
    if pub:
        out["sig_ok"] = _ed25519_ok(pub, contest_signed_content(contest, recorder_id), contest["actor_sig"])
        if out["sig_ok"]:
            bound = pubkey_bound(contest["actor_sub"], pub) if pubkey_bound else None
            out["grade"] = "verified" if bound else "claimed"
        else:
            out["grade"] = "sig_invalid"
    else:
        out["grade"] = "server-attested"
    out["notes"].append(
        f"contest seq {contest.get('seq')}: inclusion={'OK' if out['inclusion_ok'] else 'FAIL'}, "
        f"sig={'OK' if out['sig_ok'] else ('n/a' if not pub else 'BAD')}, grade={out['grade']}, anchored={out['anchored']}"
    )
    return out


def check_contest_channel(resp: dict, feed: dict, *, now: dt.datetime, max_lag_s: Optional[int],
                          pubkey_bound: Optional[Callable] = None) -> tuple[str, Optional[dict], list[dict], list[str]]:
    """Returns (state, provable_through, verified_contests, notes). state ∈
    {clear, contested, stale, undeclared}. A contest counts only if inclusion folds
    AND (it's contestant-signed with a valid sig, or server-attested)."""
    if resp.get("format") != CONTEST_FORMAT:
        return "undeclared", None, [], [f"unexpected format {resp.get('format')!r} (want {CONTEST_FORMAT})"]
    recorder_id = resp.get("recorder")
    if not recorder_id:
        return "undeclared", None, [], ["contest response missing `recorder` — cannot verify contestant signatures"]
    notes: list[str] = []
    latest = resp.get("latest_checkpoint") or {}
    provable_through, anotes = anchor_from_feed(feed, latest.get("id"))
    notes += anotes
    if provable_through is None:
        return "undeclared", None, [], notes + ["contest recorder's latest checkpoint is not Bitcoin-anchored yet — no-contest not provable"]

    real = []
    for c in resp.get("contests", []) or []:
        v = verify_contest(c, recorder_id, pubkey_bound=pubkey_bound)
        notes += v["notes"]
        if v["inclusion_ok"] and v["anchored"] and v["grade"] in ("verified", "claimed", "server-attested"):
            real.append(v)

    notes.append(f"upper bound: no-contest provable through Bitcoin block {provable_through['block_height']} "
                 f"({provable_through['iso']}) — contest recorder checkpoint #{latest.get('id')}")
    if any(v["grade"] in ("verified", "server-attested") for v in real):
        return "contested", provable_through, real, notes + ["a contest by an authorized party is anchored — standing DISPUTED"]
    if real:  # only self-asserted (claimed) contests
        return "contested", provable_through, real, notes + ["a contest is anchored (contestant key self-asserted / `claimed`) — weigh per policy"]
    # no contest: freshness gate
    if max_lag_s is not None:
        age = (now - dt.datetime.fromisoformat(provable_through["iso"].replace("Z", "+00:00"))).total_seconds()
        if age > max_lag_s:
            return "stale", provable_through, [], notes + [f"latest contest anchor {int(age)}s old > max_checkpoint_lag_s={max_lag_s} — STALE"]
        notes.append(f"freshness OK — latest contest anchor {int(age)}s old <= max_checkpoint_lag_s={max_lag_s}")
    return "clear", provable_through, [], notes


# --------------------------------------------------------------------------- #
# SIGNED-BUT-ABSENT — a contestant's held signed object the channel is omitting.
# --------------------------------------------------------------------------- #
def signed_but_absent(signed_contest: dict, channel_resp: dict, recorder_id: str) -> dict:
    """A contestant keeps their own signed contest object. If its signature is valid
    but it does not appear in the channel's response for its target, the channel is
    omitting a valid objection — detectable by a stranger. Closes most of the
    append-refusal residual (Threat #6): only a contest NEVER signed leaves no trace."""
    out = {"verdict": "unknown", "notes": []}
    pub = signed_contest.get("contestant_pubkey")
    if not pub:
        out["verdict"] = "not-signed"
        out["notes"].append("object carries no contestant_pubkey — cannot prove authorship; not a SIGNED-BUT-ABSENT case")
        return out
    if not _ed25519_ok(pub, contest_signed_content(signed_contest, recorder_id), signed_contest["actor_sig"]):
        out["verdict"] = "sig-invalid"
        out["notes"].append("held object's signature does NOT verify — no valid objection to be absent")
        return out
    present = any(c.get("entry_hash") == signed_contest.get("entry_hash")
                  or c.get("payload_hash") == signed_contest.get("payload_hash")
                  for c in channel_resp.get("contests", []) or [])
    if present:
        out["verdict"] = "present"
        out["notes"].append("valid signed contest IS present in the channel — nothing omitted")
    else:
        out["verdict"] = "SIGNED_BUT_ABSENT"
        out["notes"].append(
            f"valid contestant-signed objection by {signed_contest.get('actor_sub')} against "
            f"{str(signed_contest.get('target_digest'))[:12]}… is ABSENT from the channel — the channel is omitting a valid contest"
        )
    return out


# --------------------------------------------------------------------------- #
# Orchestration — fetch all three, run both legs, one standing verdict.
# --------------------------------------------------------------------------- #
_BASE = "https://touchstone.cv/.well-known/touchstone/checkpoints"


def _get_json(url: str, http_get: Optional[Callable]) -> dict:
    if http_get:
        return http_get(url)
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "attestation-envelope/touchstone-live", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as fh:  # noqa: S310
        return json.loads(fh.read())


_PUBKEYS = "https://touchstone.cv/.well-known/touchstone/pubkeys"


def pubkey_bound_live(sub: str, pubkey_b64: str, *, http_get: Optional[Callable] = None) -> bool:
    """Independently confirm a contestant key is BOUND to its sub at /pubkeys —
    the difference between grade `verified` and self-asserted `claimed`. We check
    the binding ourselves rather than trust the contest response's grade label."""
    try:
        feed = _get_json(f"{_PUBKEYS}/{sub}", http_get)
    except Exception:  # noqa: BLE001
        return False
    return any(b.get("signing_pubkey") == pubkey_b64 and b.get("verified")
               for b in feed.get("bindings", []) or [])


def check_live(recorder: str, entry_seq: int, target_digest: str, *,
               now: Optional[dt.datetime] = None, max_lag_s: Optional[int] = None,
               http_get: Optional[Callable] = None, pubkey_bound: Optional[Callable] = None) -> dict:
    """Full §12.3 read against a live Touchstone recorder. Returns a verdict shaped
    like standing_anchor.check: {state, lower_bound, provable_through, contest_control, notes}."""
    now = now or dt.datetime.now(dt.timezone.utc)
    feed = _get_json(f"{_BASE}/{recorder}", http_get)
    incl = _get_json(f"{_BASE}/{recorder}/entry/{entry_seq}", http_get)
    contests = _get_json(f"{_BASE}/{recorder}/contests?target={target_digest}", http_get)

    notes: list[str] = []
    ok, lower_bound, lnotes = verify_inclusion_response(incl, feed)
    notes += lnotes
    if not ok:
        return {"state": "unanchored", "lower_bound": None, "provable_through": None,
                "contest_control": "n/a", "notes": notes}

    cstate, provable_through, real, cnotes = check_contest_channel(
        contests, feed, now=now, max_lag_s=max_lag_s, pubkey_bound=pubkey_bound)
    notes += cnotes

    # contest_control: same recorder for both channels => issuer-controlled (Threat #6)
    contest_control = "issuer" if contests.get("recorder") == recorder else "independent-declared"
    state = {"contested": "contested", "stale": "stale"}.get(cstate, "anchored")
    return {"state": state, "lower_bound": lower_bound, "provable_through": provable_through,
            "contest_control": contest_control, "contests": real, "notes": notes}


def _render(v: dict) -> str:
    head = {"contested": "CONTESTED", "stale": "STALE", "anchored": "ANCHORED (live)",
            "unanchored": "UNANCHORED"}.get(v["state"], v["state"].upper())
    lines = [f"{head}  (contest_control: {v['contest_control']})"]
    if v.get("lower_bound"):
        lines.append(f"  lower bound:      Bitcoin block {v['lower_bound']['block_height']} ({v['lower_bound']['iso']})")
    if v.get("provable_through"):
        lines.append(f"  provable through: Bitcoin block {v['provable_through']['block_height']} ({v['provable_through']['iso']})")
    for n in v["notes"]:
        lines.append(f"    - {n}")
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Verify §12.3 standing against a live Touchstone recorder.")
    ap.add_argument("recorder", help="attestation recorder id (rec_…)")
    ap.add_argument("entry_seq", type=int, help="sequence of the attestation entry (lower bound)")
    ap.add_argument("target_digest", help="attestation digest to check contests against (upper bound)")
    ap.add_argument("--max-lag-s", type=int, default=None, help="max contest-checkpoint staleness before STALE")
    ap.add_argument("--contest-file", type=str, default=None,
                    help="a held contestant-signed contest (JSON); prove SIGNED-BUT-ABSENT if the channel omits it")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    v = check_live(args.recorder, args.entry_seq, args.target_digest,
                   max_lag_s=args.max_lag_s,
                   pubkey_bound=lambda sub, pk: pubkey_bound_live(sub, pk))

    if args.contest_file:
        held = json.loads(pathlib.Path(args.contest_file).read_text())
        channel = _get_json(f"{_BASE}/{args.recorder}/contests?target={args.target_digest}", None)
        v["signed_but_absent"] = signed_but_absent(held, channel, args.recorder)

    print(json.dumps(v, indent=2) if args.json else _render(v))
    if args.contest_file and not args.json:
        print("  signed-but-absent:", v["signed_but_absent"]["verdict"])
    return 0 if v["state"] in ("anchored", "clear") else 1


if __name__ == "__main__":
    raise SystemExit(main())
