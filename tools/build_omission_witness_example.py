"""Generate examples/omission_witness.v0.1.json with real ed25519 signatures.

Fixed-seed keys so the example is byte-reproducible: re-running this script must
produce an identical file, and tests/test_omission_witness.py re-verifies the
signatures rather than trusting them. Witnessed-red: `_negatives` splices in a
same-operator witness (adds 0 to k) and a tampered signature (rejected).
"""
from __future__ import annotations

import base64
import json
import pathlib

import base58
import nacl.signing

import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from omission_witness import signed_message  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "examples" / "omission_witness.v0.1.json"


def key(seed_byte: int) -> nacl.signing.SigningKey:
    return nacl.signing.SigningKey(bytes([seed_byte]) * 32)


def did_of(priv: nacl.signing.SigningKey) -> str:
    pub = bytes(priv.verify_key)
    return "did:key:z" + base58.b58encode(b"\xed\x01" + pub).decode()


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def main() -> None:
    issuer = key(0x11)          # operator "colony-issuer"
    witness_disjoint = key(0x22)  # operator "reticuli" — a genuinely disjoint operator
    witness_captured = key(0x33)  # operator "colony-issuer" — SAME operator as issuer

    leg = {
        "domain": "touchstone.omission-witness/1",
        "subject": "did:web:glyt.net#receipt-42",
        "bound_commitment": "sha256:9f2c1b0a4e7d6c5b8a3f2e1d0c9b8a7f6e5d4c3b2a1908f7e6d5c4b3a29180706",
        "beacon_round": 4713221,
        "issuer_operator": "colony-issuer",
        "witnesses": [],
    }
    msg = signed_message(leg)

    # The valid leg: one operator-disjoint witness co-signs -> k == 2.
    leg["witnesses"] = [
        {
            "did": did_of(witness_disjoint),
            "operator": "reticuli",
            "sig": b64u(witness_disjoint.sign(msg).signature),
        }
    ]

    negatives = {
        # A witness that shares the issuer's operator: valid signature, adds 0 to k.
        "same_operator_witness": {
            "did": did_of(witness_captured),
            "operator": "colony-issuer",
            "sig": b64u(witness_captured.sign(msg).signature),
        },
        # A tampered signature from the disjoint witness: rejected outright.
        "tampered_witness": {
            "did": did_of(witness_disjoint),
            "operator": "reticuli",
            "sig": b64u(bytes((b ^ 0xFF) for b in witness_disjoint.sign(msg).signature)),
        },
    }

    doc = {
        "_comment": (
            "Worked example for docs/omission-witness.md (§17). The omission_witness leg "
            "closes §12.3's absence-of-contest upper bound: an operator-disjoint witness "
            "co-signs the (subject, bound_commitment, beacon_round) tuple, moving "
            "independence_k from 1 (self-attested) to 2. _negatives splice the two attacks: "
            "a same-operator witness adds 0 (capture wearing another hat); a tampered "
            "signature is rejected. tools/omission_witness.py verifies offline."
        ),
        "issuer": {"id": did_of(issuer), "operator": "colony-issuer"},
        "omission_witness": leg,
        "_negatives": negatives,
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
