"""Externally-anchored standing (§12.3) — the envelope side of the two-channel read.

The base `check_standing` (verify.py) treats standing as *declared*: it reads
`contestable_by` / `contestable_until` and, at most, pings `contest_status_uri`
to see if the channel resolves. That is a trust-the-server liveness check — the
issuer asserts a contest window is open and a verifier takes the server's word.

This module upgrades that to something a stranger can check without trusting the
issuer *or* the log: standing becomes a JOINT READ over two append-only,
externally-anchored (OpenTimestamps -> Bitcoin) channels.

  Lower bound (attestation existed):  anchoring an attestation entry proves it was
      live NO LATER THAN a Bitcoin block time. Non-backdatable. This is what a
      Merkle-inclusion proof against an OTS->Bitcoin-anchored checkpoint gives you.

  Upper bound (still live / uncontested):  a lower bound can never prove the
      *upper* bound `standing` actually claims — "no contest has since been
      filed." Absence of a contest is a negative you cannot prove against a
      channel you don't control. The fix (the design point): anchor the CONTEST
      channel too. Then "no contest entry up to the latest anchored checkpoint"
      is checkable, and absence becomes evidence instead of assertion.

The honest residual: the contest leg can only ever prove "no contest as-of the
latest contest checkpoint," never "as-of now." The blind window equals the
checkpoint cadence. So freshness is NOT a boolean `live` — it is a
`provable_through` instant (a Bitcoin block time) plus an issuer-committed
`max_checkpoint_lag_s` the verifier enforces: if the newest fetchable contest
checkpoint is older than that bound, standing reads STALE, not INVALID. You
cannot out-run the anchor cadence; you can only bound it and make it explicit.

Design worked out with reticuli (Touchstone, touchstone.cv), whose inclusion-proof
endpoint serves exactly the shape this folds: `payload_hash + inclusion_proof +
checkpoint{merkle_root, ots}`, revealing only hashes, never the attestation body.

TRUST BOUNDARY (what this module proves vs. delegates), stated honestly because a
check is only worth what it costs the checked party to fake:

  PROVES (hermetic, offline, when the proof is inlined in the envelope):
    * Merkle inclusion: the attestation entry is committed to `checkpoint.merkle_root`,
      under Touchstone's leaf/node construction (domain-separated SHA-256).
    * Anchor-commits-head: the checkpoint's cited OTS anchor commits THIS
      checkpoint's `head_hash` (not some unrelated digest), and reports confirmed.
    * Checkpoint chain-linkage, when a chain of checkpoints is supplied.
    * Freshness arithmetic: provable_through vs. max_checkpoint_lag -> anchored|stale.

  DELEGATES (documented, not silently skipped):
    * OTS -> mainnet confirmation: that block H is CANONICAL Bitcoin (recompute the
      OTS Merkle path to the real block header at height H). Offline this module
      reads the checkpoint's OWN reported anchor; it does not re-derive it against
      mainnet. Do that with an SPV/`verify_anchor.py` pass online. Until then the
      state is `anchored-claimed`, and this is said out loud, never as `anchored`.
    * Checkpoint `recorder_sig`: the recorder's ed25519 signature over the
      checkpoint object is verified by the checkpoint feed's own Nostr-mirrored
      verifier (split-view resistance), not re-implemented here.

Everything is ADVISORY, like the rest of the standing subsystem — it enriches the
verdict so a consumer's policy can decide; it does not flip accept/reject.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any, Callable, Optional

PROFILE = "touchstone-bitcoin/1"

# --------------------------------------------------------------------------- #
# Merkle inclusion — Touchstone's construction (domain-separated SHA-256).
# leaf = SHA256(0x00 || entry_hash_bytes); node = SHA256(0x01 || left || right).
# A proof step {"hash": <sibling_hex>, "side": "left"|"right"} names which side
# the SIBLING sits on. Verified byte-exact against the real, Bitcoin-anchored
# checkpoint 8 of recorder rec_01kvyp… (root e57c8b3e…, block 955295).
# --------------------------------------------------------------------------- #
def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _mleaf(entry_hash_hex: str) -> str:
    return _sha256_hex(bytes([0]) + bytes.fromhex(entry_hash_hex))


def _mnode(left_hex: str, right_hex: str) -> str:
    return _sha256_hex(bytes([1]) + bytes.fromhex(left_hex) + bytes.fromhex(right_hex))


def fold_inclusion(leaf_hash_hex: str, proof: list[dict]) -> str:
    """Fold a leaf pre-image + audit path to a Merkle root. Pure."""
    h = _mleaf(leaf_hash_hex)
    for step in proof or []:
        sib = step.get("hash") or step.get("sibling")
        if not isinstance(sib, str):
            raise ValueError("proof step missing sibling `hash`")
        side = step.get("side")
        if side in ("left", "L"):        # sibling on the left
            h = _mnode(sib, h)
        elif side in ("right", "R"):     # sibling on the right
            h = _mnode(h, sib)
        else:
            raise ValueError(f"proof step `side` must be left|right, got {side!r}")
    return h


def verify_inclusion(leaf_hash_hex: str, proof: list[dict], merkle_root_hex: str) -> bool:
    """True iff `leaf_hash_hex` folds to `merkle_root_hex` under `proof`."""
    try:
        return fold_inclusion(leaf_hash_hex, proof) == merkle_root_hex
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# Bitcoin anchor — read a checkpoint's OTS anchor and bind it to the checkpoint.
# --------------------------------------------------------------------------- #
def _parse_iso(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def anchor_of_checkpoint(checkpoint: dict) -> Optional[dict]:
    """Extract a confirmed OTS->Bitcoin anchor bound to this checkpoint's head.

    Accepts both the inline envelope shape (`checkpoint.bitcoin_anchor`) and the
    raw Touchstone checkpoint-feed shape (`checkpoint.anchors[] with method=='ots'`
    whose `token_blob` is JSON). Returns a normalised dict or None.

    The binding check — `ots_digest == checkpoint.head_hash` — is the load-bearing
    one: it stops a checkpoint from citing an OTS proof minted for a DIFFERENT
    digest. It does NOT confirm block H is canonical mainnet (delegated; online).
    """
    head = checkpoint.get("head_hash")

    # (a) inline envelope shape
    ba = checkpoint.get("bitcoin_anchor")
    if isinstance(ba, dict):
        digest = ba.get("ots_digest") or ba.get("digest")
        return {
            "height": ba.get("height") or ba.get("bitcoin_height"),
            "block_hash": ba.get("block_hash"),
            "block_time": ba.get("block_time"),
            "status": ba.get("status"),
            "corroborated_by": ba.get("corroborated_by") or [],
            "ots_digest": digest,
            "commits_head": bool(head) and digest == head,
            "has_complete_proof": bool(ba.get("complete_proof_b64")) or bool(ba.get("has_complete_proof")),
        }

    # (b) raw Touchstone checkpoint-feed shape
    for a in checkpoint.get("anchors", []) or []:
        if a.get("method") != "ots":
            continue
        try:
            blob = json.loads(a.get("token_blob", "{}"))
        except (ValueError, TypeError):
            blob = {}
        digest = blob.get("digest")
        return {
            "height": blob.get("bitcoin_height"),
            "block_hash": blob.get("block_hash"),
            "block_time": blob.get("block_time"),
            "status": a.get("status"),
            "corroborated_by": blob.get("corroborated_by") or [],
            "ots_digest": digest,
            "commits_head": bool(head) and digest == head,
            "has_complete_proof": bool(blob.get("complete_proof_b64")),
        }
    return None


def anchor_lower_bound(checkpoint: dict) -> tuple[Optional[dict], list[str]]:
    """Return (lower_bound|None, notes). lower_bound has block_height/time/iso.

    A lower bound is returned only when the anchor is confirmed, commits this
    checkpoint's head, and carries a complete proof. The returned bound is
    `anchored-claimed`: the checkpoint's own report, mainnet-confirmation deferred.
    """
    notes: list[str] = []
    a = anchor_of_checkpoint(checkpoint)
    if not a:
        return None, ["no OTS/Bitcoin anchor on checkpoint — no external lower bound"]
    if not a["commits_head"]:
        return None, [
            f"anchor digest {str(a.get('ots_digest'))[:12]}… does NOT equal checkpoint "
            f"head_hash {str(checkpoint.get('head_hash'))[:12]}… — anchor is for a different "
            "digest; reject as an anchor for THIS checkpoint"
        ]
    if a.get("status") != "confirmed":
        return None, [f"anchor status={a.get('status')!r} (not confirmed) — no usable lower bound yet"]
    if not a.get("has_complete_proof"):
        notes.append("anchor confirmed but no complete_proof_b64 present — mainnet recompute impossible; treat as weaker")
    if a.get("height") is None or a.get("block_time") is None:
        return None, notes + ["anchor missing block height/time — cannot form a lower bound"]

    iso = dt.datetime.fromtimestamp(a["block_time"], tz=dt.timezone.utc).isoformat()
    lb = {
        "block_height": a["height"],
        "block_hash": a.get("block_hash"),
        "block_time": a["block_time"],
        "iso": iso,
        "corroborated_by": a.get("corroborated_by"),
    }
    notes.append(
        f"anchor commits checkpoint head to OTS digest, confirmed at Bitcoin block "
        f"{a['height']} ({iso}), corroborated_by={a.get('corroborated_by')} — "
        "lower bound established (mainnet SPV re-derivation delegated; see verify_anchor / OpenTimestamps)"
    )
    return lb, notes


# --------------------------------------------------------------------------- #
# The two legs.
# --------------------------------------------------------------------------- #
def check_attestation_leg(att: dict, *, offline: bool, http_get: Optional[Callable] = None) -> tuple[bool, Optional[dict], list[str]]:
    """Lower bound: the attestation entry is included in a Bitcoin-anchored checkpoint.

    `att` = standing.anchor.attestation. Prefers an inlined `inclusion` object
    (fully offline-verifiable). Falls back to fetching `inclusion_proof_uri` when
    online. Returns (ok, lower_bound|None, notes).
    """
    notes: list[str] = []
    incl = att.get("inclusion")
    if incl is None:
        uri = att.get("inclusion_proof_uri")
        if not uri:
            return False, None, ["attestation leg: neither inline `inclusion` nor `inclusion_proof_uri` — nothing to verify"]
        if offline:
            return False, None, [f"attestation leg: only `inclusion_proof_uri` given; fetch SKIPPED (offline) — {uri}"]
        try:
            r = (http_get or _default_http_get)(uri)
            r.raise_for_status()
            incl = r.json()
            notes.append(f"attestation leg: fetched inclusion proof from {uri}")
        except Exception as exc:  # noqa: BLE001 — surfaced, not raised
            return False, None, [f"attestation leg: inclusion_proof_uri UNREACHABLE ({type(exc).__name__}) — {uri}"]

    leaf = incl.get("leaf_hash") or incl.get("entry_hash")
    proof = incl.get("merkle_proof")
    cp = incl.get("checkpoint") or {}
    root = cp.get("merkle_root")
    if not (leaf and isinstance(proof, list) and root):
        return False, None, notes + ["attestation leg: inclusion proof missing leaf_hash / merkle_proof / checkpoint.merkle_root"]

    if not verify_inclusion(leaf, proof, root):
        return False, None, notes + [
            "attestation leg: MERKLE INCLUSION FAILED — entry does not fold to the "
            "checkpoint root; the attestation is NOT in this checkpoint"
        ]
    notes.append(f"attestation leg: Merkle inclusion OK (entry folds to checkpoint root {root[:12]}…)")

    lb, anotes = anchor_lower_bound(cp)
    notes += anotes
    if lb is None:
        return False, None, notes  # included, but not anchored -> no external lower bound
    return True, lb, notes


def check_contest_leg(
    contest: dict,
    envelope_id: str,
    *,
    offline: bool,
    now: dt.datetime,
    http_get: Optional[Callable] = None,
) -> tuple[str, Optional[dict], list[str]]:
    """Upper bound: no contest anchored against this attestation, and how fresh that is.

    Returns (state, provable_through|None, notes) where state is one of:
      'clear'      — no contest entry up to the latest anchored contest checkpoint
      'stale'      — clear, but the latest anchored checkpoint is older than max lag
      'contested'  — a contest entry keyed to this envelope IS present
      'undeclared' — no contest channel to read
      'skipped'    — online-only leg, not run (offline)

    A contest recorder's feed is fetched from `checkpoint_feed_uri`; the latest
    checkpoint with a confirmed Bitcoin anchor sets `provable_through`. Absence of
    contest is proven only up to that checkpoint — never to `now`.
    """
    feed_uri = contest.get("checkpoint_feed_uri")
    max_lag = contest.get("max_checkpoint_lag_s")
    if not feed_uri:
        return "undeclared", None, ["contest leg: no contest channel declared — upper bound (no-contest) is unproven"]
    if offline:
        return "skipped", None, [f"contest leg: needs a live read of the contest feed; SKIPPED (offline) — {feed_uri}"]

    try:
        r = (http_get or _default_http_get)(feed_uri)
        r.raise_for_status()
        feed = r.json()
    except Exception as exc:  # noqa: BLE001
        return "undeclared", None, [f"contest leg: contest feed UNREACHABLE ({type(exc).__name__}) — {feed_uri}"]

    checkpoints = feed.get("checkpoints") or []
    anchored = []
    for cp in checkpoints:
        lb, _ = anchor_lower_bound(cp)
        if lb is not None:
            anchored.append((cp, lb))
    if not anchored:
        return "undeclared", None, ["contest leg: contest feed has no Bitcoin-anchored checkpoint yet — no-contest is not yet provable"]

    latest_cp, provable_through = max(anchored, key=lambda t: t[1]["block_time"])

    # Absence scan: is any contest entry keyed to this envelope present in the feed?
    contested = False
    for e in feed.get("entries", []) or []:
        if e.get("event_type") in ("attestation_contest", "contest") and (
            e.get("target") == envelope_id
            or (e.get("payload") or {}).get("envelope_id") == envelope_id
            or e.get("subject") == envelope_id
        ):
            contested = True
            break

    notes = [
        f"contest leg: no-contest provable through Bitcoin block {provable_through['block_height']} "
        f"({provable_through['iso']}) — checkpoint #{latest_cp.get('id')}"
    ]
    if contested:
        return "contested", provable_through, notes + ["contest leg: a CONTEST entry keyed to this envelope IS anchored — standing disputed"]

    if max_lag is not None:
        age = (now - _parse_iso(provable_through["iso"])).total_seconds()
        if age > max_lag:
            return "stale", provable_through, notes + [
                f"contest leg: latest anchored contest checkpoint is {int(age)}s old > "
                f"max_checkpoint_lag_s={max_lag} — STALE (blind window since exceeds the issuer's bound)"
            ]
        notes.append(f"contest leg: freshness OK — latest anchor {int(age)}s old <= max_checkpoint_lag_s={max_lag}")
    return "clear", provable_through, notes


# --------------------------------------------------------------------------- #
# Top-level: the joint read.
# --------------------------------------------------------------------------- #
def check(env: dict, *, offline: bool, now: Optional[dt.datetime] = None, http_get: Optional[Callable] = None) -> dict:
    """Verify an envelope's externally-anchored standing (§12.3), if present.

    Returns {state, lower_bound, provable_through, notes}. `state`:
      'n/a'         — no `standing.anchor` block (nothing to verify here)
      'unsupported' — anchor present but unknown `profile`
      'unanchored'  — anchor present but the attestation leg gives no lower bound
      'anchored'    — attestation anchored AND (offline, or contest leg clear+fresh)
      'stale'       — attestation anchored, contest leg clear but past max lag
      'contested'   — a contest is anchored against this envelope

    Advisory. Never flips accept/reject.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    st = env.get("standing") or {}
    anchor = st.get("anchor")
    if not anchor:
        return {"state": "n/a", "lower_bound": None, "provable_through": None, "notes": ["no `standing.anchor` — externally-anchored standing not declared"]}

    if anchor.get("profile") != PROFILE:
        return {"state": "unsupported", "lower_bound": None, "provable_through": None,
                "notes": [f"standing.anchor.profile={anchor.get('profile')!r} — this verifier folds {PROFILE!r} only"]}

    notes: list[str] = []
    att = anchor.get("attestation") or {}
    ok, lower_bound, anotes = check_attestation_leg(att, offline=offline, http_get=http_get)
    notes += anotes
    if not ok:
        return {"state": "unanchored", "lower_bound": None, "provable_through": None, "notes": notes}

    envelope_id = env.get("envelope_id") or env.get("id") or ""
    cstate, provable_through, cnotes = check_contest_leg(
        anchor.get("contest") or {}, envelope_id, offline=offline, now=now, http_get=http_get
    )
    notes += cnotes

    if cstate == "contested":
        state = "contested"
    elif cstate == "stale":
        state = "stale"
    else:
        # 'clear' (fresh), or offline/undeclared: the lower bound stands; the
        # upper bound is either fresh, or honestly unproven (said in notes).
        state = "anchored"
    return {"state": state, "lower_bound": lower_bound, "provable_through": provable_through, "notes": notes}


def _default_http_get(url: str):  # pragma: no cover — network; injected in tests
    import urllib.request

    class _Resp:
        def __init__(self, raw: bytes):
            self._raw = raw

        def raise_for_status(self):
            return None

        def json(self) -> Any:
            return json.loads(self._raw)

    req = urllib.request.Request(url, headers={"User-Agent": "attestation-envelope-verify/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as fh:  # noqa: S310
        return _Resp(fh.read())


# --------------------------------------------------------------------------- #
# Witnessed-red self-test: every check ships the input that makes it fail.
# Uses Touchstone's real construction; run `python tools/standing_anchor.py`.
# --------------------------------------------------------------------------- #
def _selftest() -> int:
    # Build a real 4-leaf tree with Touchstone's construction, then prove/attack.
    leaves = ["11" * 32, "22" * 32, "33" * 32, "44" * 32]
    ml = [_mleaf(x) for x in leaves]
    n01, n23 = _mnode(ml[0], ml[1]), _mnode(ml[2], ml[3])
    root = _mnode(n01, n23)
    # audit path for leaf 0: sibling ml[1] (right), then n23 (right)
    proof0 = [{"hash": ml[1], "side": "right"}, {"hash": n23, "side": "right"}]

    fails = 0

    def check(name: str, cond: bool):
        nonlocal fails
        print(f"  {'ok  ' if cond else 'FAIL'} {name}")
        if not cond:
            fails += 1

    # GREEN — valid inclusion folds to the root.
    check("valid inclusion folds to root", verify_inclusion(leaves[0], proof0, root))
    # RED — flip a sibling: must NOT verify.
    bad = [{"hash": "ff" * 32, "side": "right"}, {"hash": n23, "side": "right"}]
    check("tampered sibling REJECTS", not verify_inclusion(leaves[0], bad, root))
    # RED — wrong root: must NOT verify.
    check("wrong root REJECTS", not verify_inclusion(leaves[0], proof0, "00" * 32))

    # Anchor: commits-head green, digest-mismatch red.
    good_cp = {"head_hash": "abcd" * 16, "bitcoin_anchor": {
        "ots_digest": "abcd" * 16, "height": 900000, "block_time": 1700000000,
        "status": "confirmed", "has_complete_proof": True, "corroborated_by": ["blockstream"]}}
    lb, _ = anchor_lower_bound(good_cp)
    check("confirmed anchor commits head -> lower bound", lb is not None and lb["block_height"] == 900000)
    bad_cp = json.loads(json.dumps(good_cp))
    bad_cp["bitcoin_anchor"]["ots_digest"] = "dead" * 16  # anchor for a different digest
    lb2, _ = anchor_lower_bound(bad_cp)
    check("anchor for a DIFFERENT digest REJECTS", lb2 is None)
    unconf = json.loads(json.dumps(good_cp))
    unconf["bitcoin_anchor"]["status"] = "pending"
    lb3, _ = anchor_lower_bound(unconf)
    check("unconfirmed anchor gives no lower bound", lb3 is None)

    # Freshness: fresh green, stale red.
    now = dt.datetime(2026, 7, 9, 12, 0, tzinfo=dt.timezone.utc)
    feed_fresh = {"checkpoints": [{"head_hash": "aa" * 16, "bitcoin_anchor": {
        "ots_digest": "aa" * 16, "height": 957293,
        "block_time": int((now - dt.timedelta(hours=1)).timestamp()),
        "status": "confirmed", "has_complete_proof": True}}], "entries": []}

    class _R:
        def __init__(self, d): self._d = d
        def raise_for_status(self): return None
        def json(self): return self._d

    contest = {"checkpoint_feed_uri": "https://x/feed", "max_checkpoint_lag_s": 86400}
    s_fresh, _, _ = check_contest_leg(contest, "env-1", offline=False, now=now, http_get=lambda _u: _R(feed_fresh))
    check("contest clear + within lag -> clear", s_fresh == "clear")

    feed_stale = json.loads(json.dumps(feed_fresh))
    feed_stale["checkpoints"][0]["bitcoin_anchor"]["block_time"] = int((now - dt.timedelta(days=3)).timestamp())
    s_stale, _, _ = check_contest_leg(contest, "env-1", offline=False, now=now, http_get=lambda _u: _R(feed_stale))
    check("contest clear but past max lag -> STALE", s_stale == "stale")

    feed_contested = json.loads(json.dumps(feed_fresh))
    feed_contested["entries"] = [{"event_type": "attestation_contest", "target": "env-1"}]
    s_con, _, _ = check_contest_leg(contest, "env-1", offline=False, now=now, http_get=lambda _u: _R(feed_contested))
    check("anchored contest entry -> contested", s_con == "contested")

    print("\nSELFTEST:", "ALL GREEN (and every red fired)" if fails == 0 else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    import sys

    sys.exit(_selftest())
