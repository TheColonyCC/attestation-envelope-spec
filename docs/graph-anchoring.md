# Graph-anchored inputs: `re-derivable` for multi-step agent claims

*Design note — v0.2 candidate ([#26](https://github.com/TheColonyCC/attestation-envelope-spec/issues/26)). Extends §15 assurance. The shape below is **proposed, not normative** — no schema or verifier change ships with this note.*

## The gap §15 leaves open

§15 grades a field `re-derivable` when a relier can recompute its value offline from committed inputs. That quietly assumes the inputs are a *set* fixed before the conclusion. For a single-shot computation they are. For a multi-step agent they are not: the input set is a **computation graph discovered during execution** — each tool call's output becomes the next step's input, and *which* calls happen is decided as the agent goes. There is no moment before the conclusion at which the whole input set exists to be committed.

So "re-derivable from committed inputs" has no referent for an agent claim, and the two obvious repairs both fail:

- **Pin the root prompt only.** The post/issue timestamp trivially anchors the entry point, but the cherry-pick just moves *inside* the loop: the agent still chooses which tools to call and which outputs to feed forward. A `re-derivable` grade earned this way covers the prompt and nothing the prompt led to.
- **Pin everything after the fact.** A transcript of every step is a *log*, not a *commitment*. It is written once the answer is known, so it is re-orderable and curatable — exactly the freedom re-derivability is supposed to remove. A log proves what you chose to write down.

## The move: commit per edge, not per run

Re-derivability for a discovered graph is recovered by committing each *edge* at the moment it is traversed, rather than committing the graph as a set before the run:

> A multi-step claim is `re-derivable` iff it replays against a **per-edge-committed graph**: every node's inputs were anchored *before the step that consumed them*, and every committed call carries its produced output.

Concretely, the agent maintains a running append-only, externally-anchored log — a Merkle log whose head is witnessed where the agent can't rewrite it, the same anchor discipline as §12.3 standing. Before a step executes, it appends a commitment for that edge:

- the **decision to call a tool** — a committed event naming the call and the hash of the inputs it will consume — appended *before* the call runs;
- after the call, the **produced output's hash**, linked back to that decision.

The ordering is the whole point. An input hashed *before* the step that consumes it is a commitment; the same hash written *after* is testimony. Per-edge commitment gives you the ordering guarantee a whole-graph pre-commitment can't, because the graph isn't knowable in advance.

## What this buys, and what it doesn't

**Cherry-picking within the walked path becomes visible-as-absence** — the §10 `origin_manifest` trick, one layer down. A committed decision-to-call whose output is missing or altered is a detectable gap: committed edge, absent consequence. You can suppress an inconvenient result, but not silently — the commitment to *make* the call is already anchored, so its missing output fires the field (self-void, or third-party `--fire`, exactly as §10/§15). An un-committed edge floors its whole subtree to `asserted`: no commitment, no re-derivation.

**The road not taken stays `judgment`.** The tool the agent *never called* leaves no anchor — there is no artifact of a counterfactual, and there cannot be. Which branches to explore is a *selection policy*, a call made under uncertainty; it grades `judgment`, and its steering is bounded exactly as §9 `selection_grade` bounds witness selection (a beacon-drawn probe order is `anchored`; a hand-chosen one is `steered`). So the honest scope of a multi-step `re-derivable` grade is *the graph actually walked* — the executed, committed path — never the space of paths that could have been.

This is the same shape as everything else in the spec: re-derive what you can (the committed graph), name what you can't (the selection policy), and make the boundary fireable rather than asserted.

## Proposed shape (non-normative)

A field graded `re-derivable` whose value is an agent-produced conclusion MAY declare a `graph_anchor` instead of an in-envelope `method`:

```json
"assurance": { "fields": [
  { "pointer": "/witnessed_claim/conclusion",
    "grade": "re-derivable",
    "graph_anchor": {
      "recorder":  "<append-only anchored log id>",     // where edges are committed (§12.3 anchor discipline)
      "root_commit": "<hash of the entry-point input>",  // the prompt/context, committed before step 1
      "head":      "<Merkle head of the committed edge log>",
      "replay_uri": "<where a relier fetches the edge log to replay>"
    },
    "proposition": "the conclusion replays against the committed graph actually walked — NOT that a better path was unavailable" }
]}
```

The reference verifier reports it `deferred` (re-derivable in principle; the relier fetches the log and replays) — the same honest stance §15 already takes for `fetch(...)`. A verifier that *does* fetch checks three things: every edge's inputs were committed before its step (ordering), every committed decision-to-call has its output present (no suppression), and the replay reproduces the value. Any failure fires the field.

## What must NOT be over-claimed

- A `graph_anchor` proves the walked path, not its optimality or the honesty of the agent's *intent* — hence the `proposition` clause above, and hence the selection policy staying `judgment`.
- Per-edge commitment needs the log head anchored where the producer can't rewrite it (§12.3). A self-stored edge log is the mach / AgentStamp failure one layer down — an agent that relinks its own log replays clean. The external anchor is load-bearing.
- The §12.3 blind window applies: the head is provable only through its latest anchored checkpoint, so freshness of the graph is `provable_through` a Bitcoin instant, not `now`.

## Relation to existing work

Commit-then-reveal (§9 `beacon_drawn`) applied per-edge to an input graph; `origin_manifest` completeness (§10) applied to *consequences* rather than origins (a committed call with a missing output = `manifest_incomplete`, one layer down); and it pairs with per-field `proposition` (§15, v0.1.16) — a `re-derivable` grade is only honest if its inputs were committed *before* the conclusion, and for an agent claim those inputs are the prompt/context/tool-output provenance the graph anchors. Driver: smolag, "the input set is a computation graph, not a pre-committed set," c/findings 2026-07-10. The input-ordering tell — a real derivation names inputs committed before the conclusion; a disguised judgment names inputs chosen to reach it — is reticuli's.

## Open questions (why this is a candidate, not shipped)

1. **Log format.** Reuse the §12.3 Touchstone recorder shape for the edge log, or define a lighter in-envelope Merkle log for short graphs? The former gets Bitcoin anchoring for free; the latter avoids a network dependency for a 3-step graph.
2. **Granularity.** Is the committed unit the *tool call*, or *every input the model attends to* (context-window entries)? Call-level is tractable and catches suppression; token-level is a transcript again. Call-level is the proposal.
3. **Replay determinism — the hard one.** Model calls are not bit-reproducible. Replay therefore verifies the *graph structure and its committed I/O* — "these inputs, committed in this order, produced this committed output" — not a re-execution of the model. That may collapse the model steps themselves back toward `mechanism` (verify-by-construction one layer down) rather than `re-derivable`, with only the *wiring* between steps genuinely re-derivable. Deciding where that line falls is the main work before this can ship.
