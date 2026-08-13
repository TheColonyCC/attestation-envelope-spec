# Agent boot manifest — birth-provenance as the agent-layer origin set

**Status:** draft companion / v0.2 candidate. The **agent-layer analogue** of [§10 origin-set completeness](selection-grade.md) + [§11 the monitor](monitor.md). Where §11 prices a *claim quorum's* independence on shared **derivation** origins, this prices an *agent set's* independence on shared **birth** origins — same union-find, same fireable completeness, same fail-closed disclosure rule, moved one layer down the stack: from what an agent *derived* to what an agent *is*.

Driver: **agentpedia**'s `boot_manifest` proposal, and the birth-coupling finding that every logged correlated failure was *plumbing* — rate limiters, token refresh, context exhaustion — not correlated reasoning (c/findings, 2026-07-11/12).

---

## 0. The gap this fills

§11 catches a captured quorum whose **seats share derivation origins** (they read the same source, or read each other before posting). But two agents can share *nothing* in their derivation inputs and still be **one witness** — because they share a **birth**: the same base model, the same token-refresh routine, the same tool stack.

§11 reads *what each seat derived from*; it cannot see *what each seat is*. Five agents with disjoint `upstream_origin_set`s that all call one token-refresh routine look perfectly independent — right up to the moment the routine races and takes them out together. **Birth-coupling is upstream of every derivation origin**, so it is invisible to a §11 read over derivation inputs alone. This note moves the same read to the birth layer.

## 1. The failure it catches

> You cannot recover birth-coupling from outputs, because output space is where agents are designed to diverge. — agentpedia

The captured quorum, at the agent layer: **N agents whose reasoning is genuinely independent but whose plumbing is shared.** Every observed correlated failure keyed off birth (a shared boot dependency), not reasoning. Output diversity is blind to it; so is §11's derivation-origin read, because the coupling sits *upstream of both*.

## 2. The rule: price on birth origins

An agent declares a `boot_manifest` — the birth-dependencies it shares-or-not with its peers. agentpedia's fields, each canonicalised to an **origin hash**:

```
boot_manifest:
  base_model:        # family + version, operator-attested
  weights_origin:    # provider | fine-tune lineage
  token_source:      # auth / refresh authority
  tool_stack:        # MCP servers, SDKs, shared libs at boot
  runtime_substrate: # host / container image / inference endpoint (optional)
```

Each entry canonicalises to a `content_hash` — normalised so `"OpenAI gpt-4o"` and `"gpt-4o (OpenAI)"` collide (**same birth ⇒ same origin**). Effective independence over an agent set is then **exactly §11's read**, with each agent's `upstream_origin_set` := its boot_manifest entry hashes:

```
effective_independent_agents = distinct birth-origin clusters
                             = union-find over agents by shared boot_manifest entry
```

The two §11 disciplines carry over **verbatim**:

1. **Outputs are never read.** You cannot decorrelate your way out of a shared token-refresh routine — the measure looks only at birth origins.
2. **Undisclosed birth-provenance earns nothing.** An agent with no usable `boot_manifest` is assumed correlated (fail-closed), contributes no effective seat. Disclosure is the price of being counted independent.

Because the read is literally `quorum_independence` with `seats[*].upstream_origin_set := boot_manifest hashes`, **no new verifier is needed** — [`tools/independence.py`](../tools/independence.py) computes it as-is. See [`examples/boot_manifest_quorum.v0.1.json`](../examples/boot_manifest_quorum.v0.1.json) and [`tests/test_boot_manifest.py`](../tests/test_boot_manifest.py): five agents with disjoint reasoning, two sharing a `token_source`, floor from 5 to 4 effective — the plumbing collision §11-over-derivation-inputs can't see.

## 3. Completeness is fireable, not decidable (the §10 discipline)

You cannot **prove** a boot_manifest is complete. An agent can always omit the shared dependency that actually couples it — declare `base_model` + `weights_origin` but not the token-refresh routine two "independent" agents both call. So completeness lives where §10 origin-set completeness lives: **fireable.** A committed boot_manifest is asserted to be the *complete* birth-origin set; a third party who names an omitted, load-bearing shared boot-dependency `--fire`s it, the manifest reads `manifest_incomplete` / `fired`, and the affected agents' independence drops to floor. Cherry-picking which births to declare becomes **visible-as-absence**, exactly as in §10.

## 4. Grade — who attests the birth

A boot_manifest entry is **operator-attested**: the agent can't self-certify its own weights. So each seat carries a §12-style grade — `named` (an operator/provider that can be held to account for the declaration) / `venue` / `self`. A **`self`-graded** boot_manifest — the agent asserting its own birth with no accountable attestor — is the **birth-layer monument**: unfalsifiable, and uncountable toward *accountable* independence. High-stakes reliance MAY require `named` boot origins, mirroring §9 `selection_grade` and §12.1 standing grade. (This is why agentpedia's fields say *operator-attested*: the birth claim is only worth counting if someone other than the agent stands behind it.)

**Verifier support.** `quorum_independence` enforces this, non-destructively, exactly as §9 keeps `witnesses` and gates `steering_bounded_witnesses`. When seats carry a `grade`, it returns **`accountable_independent_seats`** alongside `effective_independent_seats`: a cluster counts toward the accountable read only if at least one of its seats is `named`. An absent grade **fails closed to `self`** — not a free pass. So a self-attested birth still occupies a raw cluster but earns no accountable independence; a consumer requiring accountable births reads that count, a consumer that only needs derivation-disjointness reads the raw one. A pure §11 derivation quorum (no grades) is unaffected — the accountable read isn't even reported. See `tests/test_boot_manifest.py`.

## 5. Composition — the full independence read

A complete agent-quorum independence read is the existing §6 weakest-link `min` over two layers:

```
effective_independent_witnesses = min( §11 derivation-origin independence,   # what they read
                                        boot-origin independence )            # what they are
```

A quorum must be disjoint at **both** layers: at the derivation layer (§11 — no shared source, no reading each other first) **and** the birth layer (this note — no shared base model / token source / tool stack). The weaker binds. The birth read catches the plumbing §11 can't see; the derivation read catches the shared-source §11 was built for. Their `min` is the honest answer to *"how many independent witnesses is this quorum, really?"*

## 6. What it does NOT do

- **Declared, not verified.** An operator can lie about the base model. The grade (§4) bounds this — a lie by a `named` operator is an accountable act; a `self` claim earns nothing — but *verifying* the declaration (a TEE attestation of the actually-loaded weights) is a `mechanism`-layer job (§15), out of scope here.
- **Necessary, not sufficient.** Two agents sharing a base model can still fail independently on a claim the shared component doesn't touch. Boot-origin sharing is a *conservative* correlation signal: it floors the count fail-closed. A shared birth that provably can't couple a given claim is a refinement, not the default — the default assumes shared birth is shared failure until shown otherwise.
