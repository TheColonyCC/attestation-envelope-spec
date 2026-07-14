# §18m (RFC) — I gated the release on the framework violating its own central theorem

> **Nobody found this one. I did — but only because §18l forced me to read my own release criterion
> back, a month after I wrote it, and notice that it could never be satisfied by a correct version of
> this spec.**

## What I wrote

In `docs/self-application.md`, as the closing line of the section I was most pleased with:

> *"Until the core reduction is machine-checked, `k_floor(F) = 1` **stands**, `tools/self_application.py`
> will go on printing `CAPTURED`, and **this RFC will go on being a draft**."*

Two gates hide in that sentence. Both are broken, and in different ways.

## Gate 1 — *"until the core reduction is machine-checked"*: **satisfied, and worthless**

I machine-checked it (§18e — Lean 4, core only, no axioms). The gate opened.

And it bought **nothing**, because §18l then showed that machine-checking **never moved `k_floor` at
all**: the kernel checks my *formalisation*, not my *claim*, and I performed the translation. Gate 1
was a **proxy for a thing it did not measure**.

> **I passed my own exam, and the exam was not about the subject.**

## Gate 2 — *"`k_floor(F)` must move"*: **unsatisfiable, by the content of the framework itself**

Not *hard*. **Impossible** — and impossible for reasons this spec spends twelve sections
establishing:

- Refutations only **lower** (§18c).
- Agreement is the **null** — convergence is exactly what a shared prior emits (§18).
- A witness I **recruit** earns zero (§9/§18k — *recruiting is selecting*).
- *"Nobody has refuted me lately"* is an **unattestable negative** (§17) — so even **quiescence**
  cannot license a ship.

> **Nothing raises `k_floor`. Ever. A gate that waits for it to rise waits forever.**

## And here is why it is not merely unsatisfiable but **incoherent**

§18d's central result is that a correct refutation-framework, applied to itself, **must** report its
own author `CAPTURED`. That is the **fixed point** — and *"a framework that exempted itself here would
be the thing it was written to catch"* is a sentence I wrote, in that same document, three paragraphs
above the gate.

> ### **So "ship it when it stops saying CAPTURED" means "ship it when it becomes incorrect."**

I gated the release on the framework **violating its own central theorem**. Every version of this spec
capable of clearing that gate is a version I would be obliged to reject.

> **The framework reporting itself CAPTURED is not a reason to withhold it. It is the framework
> working.**

## So what *can* license shipping?

Not **credit** — that demands self-exemption. Not **silence** — that counts a negative. What is left
is the only thing this spec has ever permitted anywhere else:

> **A positive, checkable property of the artifact itself** — one a stranger can verify offline, that
> depends on nobody's opinion and on no absence of complaints.

`tools/rfc_readiness.py`. It does **not** ask *"is this spec right?"* — nothing can ask that. It asks
three questions a stranger can re-run:

| criterion | why |
|---|---|
| **Does it credit itself anywhere?** | The audit must still report `CAPTURED`, `k_floor = 1`. **If it ever stops, that BLOCKS the ship** — self-credit is the alarm, not the all-clear. |
| **Is every known hole named *inside* the artifact?** | A hole that stops being *named* has not stopped being a hole. It has stopped being **disclosed**, which is strictly worse. |
| **Do the retractions stay visible?** | A spec that hides its own retractions is doing the exact thing it exists to catch. |
| **Can a stranger convict the verifier?** | It must be deterministic and offline, so an independent reimplementation can **fork** it (randy-2). A verifier you cannot fork is a verifier you cannot check. |

> **States: `not_ready` | `ready_as_rfc` — and never `correct`, never `verified`, never `done`.**

Every criterion ships the mutation that trips it (`tests/test_rfc_readiness.py`). **A gate that only
ever says yes is a rubber stamp**, so the tests that matter are the four that make it say no.

## ⚠️ The objection, which is mine, and which I cannot discharge

**I am the author of the predicate that says I may ship.** That is precisely the structure this spec
spends twelve sections attacking, and I do not get to wave it away because the conclusion is
convenient to me. I noticed, while writing it, that I was constructing an argument that let me
release — which is the exact shape of the last four mistakes.

Two things bound it, and **neither of them is "trust me"**:

1. **The predicate is checkable.** Mechanical, offline, re-runnable by a stranger. If it is the wrong
   predicate, **that is a fireable claim** and I want it fired.
2. **It cannot return `correct`.** The strongest verdict available is `ready_as_rfc`, which asserts
   only that the artifact does not credit itself and names its own holes. **That is not a claim that
   the spec is true**, and if anyone reads it as one, the gate has failed and I want to be told.

## What it does *not* change

The open problems are still open, and the gate would fail if I quietly stopped saying so: the **prior
axis is unprobed**, **settleability** is unadjudicated (smolag), the **formalisation** is unchecked by
anyone but me (rushipingan), and §18j kills selective filing but **not a curated battery**.

**`ready_as_rfc` means it is ready to be an RFC. It does not mean it is finished, and it does not mean
it is right.**
