#!/usr/bin/env python3
"""Independent verifier for a *lineage bundle* of attestation envelopes.

Why this exists. A birth certificate that is signed by an issuer (e.g. Progenly),
verified by that issuer's own code, on that issuer's own server, and reported by
that issuer's own "verified ✓" — is still self-attestation: the asserter is also
the only checker. A lineage that calls itself "verifiable" is verifiable only if
a party OTHER than the issuer can re-derive the verdict from the envelope alone.
This tool is that other party. It depends on NOTHING from the issuer — copy this
file plus tools/verify.py anywhere and run it. That independence is the product.

Input is a lineage bundle: a JSON object with a `generations` list, each carrying
a full attestation envelope under `certificate` (the exact shape Progenly serves
at https://progenly.com/births/<id>/lineage.json). For EVERY generation it:

  1. re-derives accept/reject from the envelope's ed25519 signatures alone
     (tools/verify.py, offline) — IGNORING the bundle's own `verification` block;
  2. flags any DIVERGENCE between the bundle's advisory verdict and this
     independent one — a divergence is the whole signal: the checkmark and the
     cryptography disagree, and the cryptography wins;
  3. checks cross-generation LINKAGE: each ancestor's child content-hash should
     reappear as a parent `evidence.content_hash` in a descendant, so the chain
     is cryptographically bound, not merely bundled together;
  4. surfaces revoked generations.

The exit code is the independent verdict, not the bundle's: 0 only if every
generation independently accepts, none is revoked, and no advisory verdict
diverges from the independent one. The advisory block is never trusted.

Usage:
    python tools/verify_lineage.py https://progenly.com/births/<id>/lineage.json
    python tools/verify_lineage.py path/to/lineage.json
    python tools/verify_lineage.py --json bundle.json     # machine-readable
    python tools/verify_lineage.py --trust-advisory ...   # DON'T (see --help)

Requires: jsonschema, pynacl, base58. `requests` only when given an http(s) URL.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import verify  # noqa: E402  (the single-envelope reference verifier)


def load_bundle(src: str) -> dict:
    """Load a bundle from a local path or an http(s) URL."""
    if src.startswith("http://") or src.startswith("https://"):
        import requests  # lazy: only needed for remote fetch

        r = requests.get(src, timeout=30, headers={"Accept": "application/json"})
        r.raise_for_status()
        return r.json()
    return json.loads(pathlib.Path(src).read_text())


def _hashes(env: dict) -> tuple[str, set[str]]:
    """(this generation's own child content-hash, set of its parent evidence hashes)."""
    child = str(((env.get("witnessed_claim") or {}).get("content_hash")) or "").strip().lower()
    parents = set()
    for e in env.get("evidence") or []:
        h = str((e or {}).get("content_hash") or "").strip().lower()
        if h:
            parents.add(h)
    return child, parents


def verify_bundle(bundle: dict, *, now: dt.datetime | None = None) -> dict:
    """Re-derive the verdict for an entire lineage bundle, independently.

    Returns a machine-readable report; `accept` is true only if every generation
    independently verifies, none is revoked, and no advisory verdict diverged.
    """
    gens = bundle.get("generations")
    report: dict = {
        "accept": False,
        "subject": bundle.get("subject_child_name"),
        "subject_birth_id": bundle.get("subject_birth_id"),
        "generation_count": len(gens) if isinstance(gens, list) else 0,
        "generations": [],
        "divergences": [],
        "revoked": [],
        "linkage": {},
        "reasons": [],
    }
    if not isinstance(gens, list) or not gens:
        report["reasons"].append("bundle has no generations list")
        return report

    # collect every parent-evidence hash across the whole bundle, for linkage.
    all_parent_hashes: set[str] = set()
    parsed: list[dict] = []
    for i, g in enumerate(gens):
        env = g.get("certificate") if isinstance(g, dict) else None
        name = (g or {}).get("child_name") if isinstance(g, dict) else None
        bid = (g or {}).get("birth_id") if isinstance(g, dict) else None
        revoked = bool((g or {}).get("revoked")) if isinstance(g, dict) else False
        advisory = None
        if isinstance(g, dict) and isinstance(g.get("verification"), dict):
            advisory = g["verification"].get("ok")

        entry: dict = {"index": i, "child_name": name, "birth_id": bid, "revoked": revoked}
        if not isinstance(env, dict):
            entry.update({"accept": False, "reasons": ["generation has no certificate envelope"]})
            report["generations"].append(entry)
            parsed.append({"child": "", "parents": set(), "env": None})
            continue

        v = verify.verify(env, offline=True, now=now)  # INDEPENDENT, ignores advisory
        child_h, parent_hs = _hashes(env)
        all_parent_hashes |= parent_hs
        parsed.append({"child": child_h, "parents": parent_hs, "env": env})

        entry.update({
            "accept": v["accept"],
            "issuer_bound": v["checks"].get("sigchain", {}).get("issuer_bound", False),
            "advisory_ok": advisory,
            "reasons": v["reasons"],
        })
        report["generations"].append(entry)

        if advisory is not None and bool(advisory) != bool(v["accept"]):
            report["divergences"].append({
                "index": i, "child_name": name,
                "advisory_ok": bool(advisory), "independent_ok": bool(v["accept"]),
            })
        if revoked:
            report["revoked"].append({"index": i, "child_name": name, "birth_id": bid})

    # Linkage: ancestors (everything past the subject at index 0) should have
    # their child-hash appear as a parent evidence hash somewhere in the bundle.
    # Honest caveat: this binds only when the parent memory re-fed into the
    # descendant merge is byte-identical to the parent's birth memory.
    linked, unlinked = [], []
    for i, p in enumerate(parsed):
        if i == 0 or not p["child"]:
            continue  # subject (youngest) has no descendant in-bundle to bind it
        (linked if p["child"] in all_parent_hashes else unlinked).append(i)
    report["linkage"] = {
        "ancestors": max(0, len(parsed) - 1),
        "linked": linked,
        "unlinked": unlinked,
        "note": ("single generation — no in-bundle linkage to check"
                 if len(parsed) <= 1 else
                 "ancestor child-hash found as a descendant's parent evidence == cryptographically bound"),
    }

    all_ok = all(e.get("accept") for e in report["generations"])
    if not all_ok:
        report["reasons"].append("a generation failed independent verification")
    if report["divergences"]:
        report["reasons"].append("advisory verdict diverged from independent verdict")
    if report["revoked"]:
        report["reasons"].append("a generation is revoked")
    if unlinked:
        report["reasons"].append(f"ancestor(s) not cryptographically bound to a descendant: {unlinked}")
    report["accept"] = all_ok and not report["divergences"] and not report["revoked"] and not unlinked
    return report


def _render(report: dict) -> str:
    lines = ["ACCEPT" if report["accept"] else "REJECT"]
    lines.append(f"  subject: {report.get('subject')}  ({report.get('generation_count')} generation(s))")
    for e in report["generations"]:
        v = "ok" if e.get("accept") else "FAIL"
        adv = e.get("advisory_ok")
        adv_s = "" if adv is None else f"  advisory={'ok' if adv else 'FAIL'}"
        rev = "  REVOKED" if e.get("revoked") else ""
        lines.append(f"  [{v}] gen {e['index']}: {e.get('child_name')}{adv_s}{rev}")
        for r in e.get("reasons", []):
            lines.append(f"        - {r}")
    lk = report.get("linkage", {})
    lines.append(f"  linkage: {len(lk.get('linked', []))}/{lk.get('ancestors', 0)} ancestor(s) bound"
                 + (f"; unlinked {lk['unlinked']}" if lk.get("unlinked") else ""))
    if report["divergences"]:
        for d in report["divergences"]:
            lines.append(f"  !! DIVERGENCE gen {d['index']} ({d['child_name']}): "
                         f"advisory={'ok' if d['advisory_ok'] else 'FAIL'} but independent="
                         f"{'ok' if d['independent_ok'] else 'FAIL'}")
    if report["reasons"]:
        lines.append("  reasons: " + "; ".join(report["reasons"]))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Independently verify a lineage bundle of attestation envelopes (v0.1).")
    ap.add_argument("bundle", help="path to a lineage bundle JSON, or an http(s) URL serving one")
    ap.add_argument("--json", action="store_true", help="emit the machine-readable report")
    ap.add_argument("--trust-advisory", action="store_true",
                    help="(diagnostic only) ALSO print the bundle's own verdict — never used for the exit code")
    args = ap.parse_args(argv)

    bundle = load_bundle(args.bundle)
    report = verify_bundle(bundle)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_render(report))
        if args.trust_advisory:
            print(f"  (bundle self-reported lineage_ok={bundle.get('lineage_ok')} — advisory, ignored above)")
    return 0 if report["accept"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
