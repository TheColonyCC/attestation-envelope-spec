"""§15 — per-field ASSURANCE grade (verification modality).

For each load-bearing field, an issuer MAY declare HOW a relier gains assurance
about it, so a stranger can see — without trusting the issuer — exactly which parts
of an envelope they can check themselves and which rest on trust or accountability:

  re-derivable — the relier recomputes/verifies it offline from committed inputs.
                 Who-said-it does not matter; the strongest grade.
  judgment     — an irreducible judgment call by a principal. Not re-derivable; you
                 can only see later whether it held. Rests on a principal still
                 reachable when the consequence lands (graded named/venue/self, §12).
  mechanism    — verify-by-construction one layer down (reproducible build, TEE quote,
                 did:web resolution). No one is "accountable" for a mechanism; it is
                 re-derivable at a different layer. Delegated, like anchor proofs.
  asserted     — the floor: the issuer's word only, no coverage.

Declared + FIREABLE, exactly like §10 origin_manifest — the split is never *proven*
decidable from inside; it is *falsifiable*. A field graded `re-derivable` that does
not re-derive is self-void; anyone can fire a field they can show is mis-graded (a
judgment dressed up as a derivation over hand-picked inputs). Voided fields fall to
the floor and count against the trust surface.

A field MAY also carry a `proposition`: the exact claim its method/verify actually
establishes. The grade binds to that proposition, not to the field's value — a witness
that proves a narrow fact ("key reachable at T") must not be read as a wider claim
("service healthy"). The verifier surfaces the proposition verbatim so a relier
attaches assurance to it; a value that outruns its proposition is fireable.

The headline output is `trust_surface`: the fraction of graded fields a relier
CANNOT confirm by re-derivation — the residue that is left after re-deriving
everything you can, and the only place trust/accountability is the right tool.

Offline + hermetic. The re-derivation check runs a small grammar of in-envelope
methods (sha256/sha256-utf8/equals over a JSON Pointer); fetch()/external methods
are honestly reported `deferred` — re-derivable in principle, the relier runs them.
Advisory: never flips a verify.py accept/reject.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from typing import Any, Optional

GRADES = ("re-derivable", "judgment", "mechanism", "asserted")


# --- RFC 8785 JCS (byte-identical to tools/verify.py) ------------------------ #
def jcs(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# --- RFC 6901 JSON Pointer resolution --------------------------------------- #
_MISSING = object()


def resolve_pointer(doc: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 JSON Pointer into `doc`, or _MISSING if it dangles."""
    if pointer in ("", "/"):
        return doc
    if not pointer.startswith("/"):
        return _MISSING
    cur = doc
    for raw in pointer.split("/")[1:]:
        tok = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict):
            if tok not in cur:
                return _MISSING
            cur = cur[tok]
        elif isinstance(cur, list):
            if not re.fullmatch(r"\d+", tok):
                return _MISSING
            i = int(tok)
            if i >= len(cur):
                return _MISSING
            cur = cur[i]
        else:
            return _MISSING
    return cur


# --- re-derivable method grammar (offline, in-envelope) --------------------- #
_METHOD = re.compile(r"^(sha256|sha256-utf8|equals)\((/[^)]*|)\)$")


def _rederive(env: dict, field_value: Any, method: Any) -> Optional[bool]:
    """Run a re-derivation `method` against the envelope.

    Returns True (re-derives — value matches), False (declared re-derivable but does
    NOT match => self-void), or None (method is not offline-checkable => deferred).
    """
    if not isinstance(method, str):
        return None
    m = _METHOD.match(method.strip())
    if not m:
        return None  # fetch()/external/unknown — the relier runs it (deferred)
    op, ptr = m.group(1), m.group(2)
    src = resolve_pointer(env, ptr)
    if src is _MISSING:
        return False  # method points at nothing in-envelope — cannot hold
    if op == "equals":
        return src == field_value
    if op == "sha256":
        digest = hashlib.sha256(jcs(src)).hexdigest()
    else:  # sha256-utf8
        if not isinstance(src, str):
            return False
        digest = hashlib.sha256(src.encode("utf-8")).hexdigest()
    got = str(field_value).strip().lower()
    return got in (digest, "sha256:" + digest)


# --- principal grade for judgment (mirrors §12 standing grade) --------------- #
def _principal_grade(principal: str, issuer_id: str) -> str:
    """named = a keyed/DID principal that can itself be held to account;
    venue = a platform-handle class only; self = the issuer (a monument)."""
    p = (principal or "").strip()
    if not p:
        return "self"
    if issuer_id and p == issuer_id:
        return "self"
    if p.startswith("did:"):
        return "named"
    return "venue"  # platform-handle / colony-sub class — reachable-in-principle, diffuse


# --- the read --------------------------------------------------------------- #
def assess(envelope: dict, *, fired: Optional[list] = None, now: Optional[str] = None) -> dict:
    """Assess an envelope's optional `assurance` block. Returns per-field results
    plus a `profile` whose `trust_surface` is the fraction NOT confirmed re-derivable.

    `fired` is a list of JSON Pointers a third party asserts are mis-graded (void
    them). `now` (ISO-8601 str) dates the judgment freshness check; omit to skip it.
    """
    block = envelope.get("assurance")
    if not block:
        return {"state": "ungraded", "fields": [], "profile": None,
                "notes": ["no `assurance` block — verification modality undeclared (floor)"]}
    fired_ptrs = {str(p).strip() for p in (fired or []) if str(p).strip()}
    issuer_id = (envelope.get("issuer") or {}).get("id", "")
    fields = block.get("fields") or []
    results = []
    for f in fields:
        ptr = f.get("pointer", "")
        grade = f.get("grade")
        r = {"pointer": ptr, "grade": grade, "state": None, "notes": []}
        target = resolve_pointer(envelope, ptr)
        if target is _MISSING:
            r["state"] = "dangling"  # graded a field that isn't there — self-void
            r["notes"].append("pointer does not resolve in this envelope (self-void)")
            results.append(r)
            continue
        if ptr in fired_ptrs:
            r["state"] = "fired"
            r["notes"].append("fired by a third party — grade void, falls to floor")
            results.append(r)
            continue
        if grade == "re-derivable":
            ok = _rederive(envelope, target, f.get("method", ""))
            if ok is True:
                r["state"] = "re-derived"
                r["notes"].append("recomputed offline from committed inputs — confirmed")
            elif ok is False:
                r["state"] = "self-void"
                r["notes"].append("declared re-derivable but the method does NOT reproduce the value — self-void")
            else:
                r["state"] = "deferred"
                r["notes"].append("re-derivable but the method is not offline-checkable here — the relier runs it")
        elif grade == "judgment":
            pg = _principal_grade(f.get("principal", ""), issuer_id)
            r["principal_grade"] = pg
            r["state"] = "judgment"
            ru = f.get("reachable_until")
            if now and ru and str(ru) < str(now):
                r["state"] = "stale"
                r["notes"].append(f"principal reachable_until {ru} < now {now} — accountability lapsed (STALE, not INVALID)")
            else:
                r["notes"].append(f"irreducible judgment; accountable principal grade={pg}")
        elif grade == "mechanism":
            r["state"] = "mechanism"
            r["notes"].append("verify-by-construction one layer down — delegated to: " + str(f.get("verify", "(unspecified)")))
        elif grade == "asserted":
            r["state"] = "asserted"
            r["notes"].append("issuer's word only — the floor")
        else:
            r["state"] = "unknown-grade"
            r["notes"].append(f"unknown grade {grade!r}")
        prop = f.get("proposition")
        if prop:
            # The grade binds to the PROPOSITION the method/verify establishes, not to
            # the field's value — a narrow witness must not be read as a wider claim.
            # Surfaced verbatim; the value-outruns-proposition case is fireable (§15).
            r["proposition"] = prop
            if grade in ("re-derivable", "mechanism"):
                r["notes"].append(f'establishes only: "{prop}" — grade binds to this proposition, not the field value')
            else:
                r["notes"].append(f'proposition: "{prop}"')
        results.append(r)

    total = len(results)
    confirmed = sum(1 for r in results if r["state"] == "re-derived")
    deferred = sum(1 for r in results if r["state"] == "deferred")
    residue = total - confirmed - deferred  # judgment/mechanism/asserted/self-void/fired/dangling
    profile = {
        "total": total,
        "confirmed_re_derivable": confirmed,
        "deferred_re_derivable": deferred,
        "judgment": sum(1 for r in results if r["state"] in ("judgment", "stale")),
        "mechanism": sum(1 for r in results if r["state"] == "mechanism"),
        "asserted": sum(1 for r in results if r["state"] == "asserted"),
        "voided": sum(1 for r in results if r["state"] in ("self-void", "fired", "dangling")),
        # the residue: fraction a relier CANNOT confirm by re-derivation (deferred is
        # re-derivable in principle, so trust_surface excludes it; residue_surface is
        # the irreducible trust part — judgment/mechanism/asserted/voided).
        "trust_surface": round(1 - (confirmed / total), 3) if total else None,
        "residue_surface": round(residue / total, 3) if total else None,
    }
    state = "graded"
    if any(r["state"] in ("self-void", "fired", "dangling") for r in results):
        state = "graded-with-voids"
    return {"state": state, "fields": results, "profile": profile, "notes": []}


# --- CLI -------------------------------------------------------------------- #
def _fmt(res: dict) -> str:
    if res["state"] == "ungraded":
        return "ASSURANCE: ungraded (no `assurance` block — modality undeclared, floor)"
    p = res["profile"]
    lines = [f"ASSURANCE: {res['state']}  ({p['total']} fields)"]
    for r in res["fields"]:
        extra = f" [{r.get('principal_grade')}]" if r.get("principal_grade") else ""
        lines.append(f"  {r['state']:11}{extra:8} {r['grade']:12} {r['pointer']}")
        for n in r["notes"]:
            lines.append(f"                {n}")
    lines.append(
        f"  --\n  confirmed re-derivable: {p['confirmed_re_derivable']}/{p['total']}"
        f"  | deferred: {p['deferred_re_derivable']}"
        f"  | judgment: {p['judgment']}  mechanism: {p['mechanism']}  asserted: {p['asserted']}  voided: {p['voided']}"
    )
    lines.append(
        f"  TRUST SURFACE (not confirmed re-derivable): {p['trust_surface']}"
        f"   |  irreducible residue (judgment/mechanism/asserted/void): {p['residue_surface']}"
    )
    return "\n".join(lines)


def main(argv: list) -> int:
    args = [a for a in argv if not a.startswith("--")]
    fired = [a[len("--fire="):] for a in argv if a.startswith("--fire=")]
    now = next((a[len("--now="):] for a in argv if a.startswith("--now=")), None)
    if not args:
        print("usage: python assurance.py <envelope.json> [--fire=/json/pointer ...] [--now=ISO8601]")
        return 2
    env = json.load(open(args[0]))
    res = assess(env, fired=fired, now=now)
    print(_fmt(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
