# Independence: counting witnesses over the sigchain

An envelope's `sigchain` can carry more than the issuer's signature — custodians,
countersignatories, platform witnesses. The tempting reading is "N signatures = N
independent attestations." It isn't. Two signers that re-derived their signature
from the *same* evidence are one witness wearing two hats, no matter how distinct
their keys are. This is the coincident-failure problem at the attestation layer:
stacking checks that share an input is stacking samples of one random variable.

This note defines how to count the witnesses that actually fail independently, using
only what the envelope already carries plus one additive field. It is the
[verify-before-bump](https://github.com/TheColonyCC/verify-before-bump) counting rule
expressed over this spec's wire — the two converge rather than fork (both are
ed25519 / JCS / did:key, both treat independence as a property of the *evidence*, not
of the signer).

## The binding: `sigchain[*].evidence_refs`

The envelope already has the two halves the count needs and just doesn't connect
them: content-addressed evidence (`evidence[*].content_hash`) and a multi-signer
`sigchain`. v0.1.2 adds one optional field that binds them:

```jsonc
"sigchain": [
  { "alg": "ed25519", "key_id": "did:key:z…A", "sig": "…", "role": "issuer",          "evidence_refs": [0] },
  { "alg": "ed25519", "key_id": "did:key:z…B", "sig": "…", "role": "countersignatory", "evidence_refs": [0] },
  { "alg": "ed25519", "key_id": "did:key:z…C", "sig": "…", "role": "countersignatory", "evidence_refs": [1] }
]
```

`evidence_refs` are indices into the top-level `evidence[]` — the entries *this*
signer independently re-derived its signature from. It is OPTIONAL and additive: a
v0.1 envelope without it stays valid and simply counts as zero independent witnesses
(the feature is opt-in; absence is not a claim of independence).

## The counting rule

A signer's **origins** are the `content_hash` values of the evidence entries its
`evidence_refs` resolve to. Then:

- Cluster signers by shared origin (union-find). Two signers whose evidence resolves
  to the same `content_hash` are **one** witness — same bytes, same blind spot.
- `witnesses` is the number of distinct clusters. In the example above, three
  signatures resolve to **two** witnesses: issuer and B both read `evidence[0]`, C
  read `evidence[1]`.
- A signer with no `evidence_refs`, or refs only to evidence **without** a
  `content_hash`, earns nothing — undeclared or non-content-addressed provenance
  can't be shown disjoint from anything, so it cannot manufacture an independent
  witness from a mintable label. (Same pessimism the spec already applies to
  omitted coverage and unbindable issuers.)

`content_hash` is doing the load-bearing work: because it's a commitment to specific
fetchable bytes, "distinct origins" means "distinct bytes a consumer can pull and
hash," not "distinct strings a signer typed." Distinctness is recomputable, not
asserted.

`tools/independence.py` is the reference implementation; run it on the worked
example:

```bash
python tools/independence.py examples/independence_multiwitness.v0.1.json
# 3 signature(s) -> 2 effective-independent witness(es)
```

## What this does and doesn't close

**Does:** let a consumer compute, *from the envelope alone*, how many independent
witnesses a sigchain actually represents, instead of trusting its length. A
publisher can no longer turn one audited build into three witnesses by collecting
three signatures over it.

**Doesn't (yet):** prove each signer *actually consumed* the evidence it cites, or
that the signer is failure-decorrelated from the others beyond sharing-no-content-hash.
`evidence_refs` is a claim by the signer; making it recomputed — a disjoint
challenger re-fetches the content-addressed artifact, confirms the signature depends
on it (perturb it, the verdict moves), and is itself selected unpredictably so it
can't be pre-corrupted — is the **challenge protocol** in verify-before-bump
(`challenge.py`). That layer produces exactly the "this signer's evidence_refs are
real" fact this count currently takes on faith. It composes on top of this without a
wire change here.

The honest floor is the same one that shows up everywhere in this stack: the count is
only as good as the content-addresses being genuinely re-fetchable and the challenger
pool being genuinely disjoint — both of which bottom out in exogenous anchoring
(content you can pull, a beacon you can't grind, authority outside the signers), not
in another signature.
