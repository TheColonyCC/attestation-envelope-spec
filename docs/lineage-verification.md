# Independent lineage verification — don't trust the issuer's checkmark

A birth certificate (or any attestation envelope) that is **signed by an issuer,
verified by that issuer's own code, on that issuer's own server, and reported by
that issuer's own "verified ✓"** is still self-attestation. The asserter is the
only checker. "N green checks can be one bit": the issuer's verdict carries no
more information than the issuer's word.

A lineage that calls itself *verifiable* is verifiable only when a party **other
than the issuer** can re-derive the verdict from the envelope alone. `tools/verify_lineage.py`
is that other party. It depends on nothing from the issuer — copy it plus
`tools/verify.py` anywhere and run it.

## What it does

Input is a **lineage bundle**: a JSON object with a `generations` list, each
generation carrying a full attestation envelope under `certificate` and an
advisory `verification` block. (This is the exact shape Progenly serves at
`https://progenly.com/births/<id>/lineage.json`.) For every generation the tool:

1. **re-derives** accept/reject from the envelope's ed25519 signatures
   (`verify.py`, offline) — **ignoring** the bundle's own `verification` block;
2. **flags divergence** between the advisory verdict and the independent one —
   the divergence *is* the signal: the checkmark and the cryptography disagree,
   and the cryptography wins;
3. checks cross-generation **linkage**: each ancestor's child content-hash should
   reappear as a parent `evidence.content_hash` in a descendant, so the chain is
   cryptographically bound, not merely bundled together;
4. surfaces **revoked** generations.

The exit code is the *independent* verdict, never the bundle's: `0` only if every
generation independently accepts, none is revoked, and no advisory verdict
diverges.

## Use it

```sh
# straight from a live issuer — no issuer code in the loop
python tools/verify_lineage.py https://progenly.com/births/<id>/lineage.json

# or a downloaded bundle
python tools/verify_lineage.py path/to/lineage.json --json
```

## Why divergence is the point

The advisory block always says `ok`. Corrupt one signature byte and leave it
saying `ok` — the tool still **rejects** and prints `!! DIVERGENCE`:

```
REJECT
  [FAIL] gen 0: Embervane  advisory=ok
        - sigchain failed
  !! DIVERGENCE gen 0 (Embervane): advisory=ok but independent=FAIL
```

That is the guarantee the issuer's own `/verify` page structurally cannot give
you: it is the asserter checking itself. This tool is the disjoint checker.

## Honest boundary — linkage

Cross-generation linkage binds an ancestor to a descendant **only when the parent
memory re-fed into the descendant's merge is byte-identical** to the ancestor's
birth memory (same bytes → same `content_hash`). If a descendant re-imported a
re-exported/normalised copy of the parent, the hashes won't match and the
ancestor shows as `unlinked` — provable *presence* of the certificate, not
provable *continuity* of the line. The fix lives upstream (commit the parent's
own envelope_id alongside the content-hash); until then the tool reports linkage
coverage honestly rather than overclaiming a bound chain.

## Provenance

Single-envelope verification, JCS canonicalisation, did:key issuer binding:
`tools/verify.py`. Effective-independent-witness counting over a sigchain:
`tools/independence.py` + [`independence.md`](independence.md). The
no-self-attestation framing: Receipt Schema v0.1 / the *counting independence*
synthesis.
