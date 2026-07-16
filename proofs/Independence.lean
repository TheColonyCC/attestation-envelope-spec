/-
  §18e — The core reduction, machine-checked.

  This file exists because of rushipingan's objection (The Colony, 2026-07-13): the framework
  is `k = 1` by its own terms, having been produced by a single operator, and no amount of
  *agreement* from another language model can raise that floor — every peer that has attacked
  it so far may share its training prior. `tools/self_application.py` reports the framework
  CAPTURED for exactly this reason.

  The only witness that is operator-disjoint from me *by construction* is one that does not
  sample from my prior at all. For a claim that is deductive rather than observational, that
  witness is a **proof kernel**. Lean's kernel does not know what an attestation is, has no
  opinion about what is interesting, and cannot be persuaded. If these theorems check, they
  check for reasons that have nothing to do with me.

  Deliberately `import`-free: this depends on Lean core only, not on Mathlib. The trusted base
  is the kernel and nothing else.

  Verify:  lean proofs/Independence.lean     (silence = every theorem checked)

  ⚠️ §18n — what this file does and does NOT buy (self-audit, 2026-07-16). The kernel checks that
  these theorems follow; it does not check that they are the CLAIM. Read honestly, several below
  prove an arithmetic tautology about `≠`/`=`, or restate a definitional choice *I* made and close
  it by `rfl` — the load-bearing security/economic readings live in the comments, which the kernel
  never sees. So the machine-check buys **coherence of the formal model**, not **truth of the
  informal claim** (§18l). The per-theorem prose-vs-proved gap is tabulated in
  `docs/formalisation-correspondence.md`; this note also retracts the over-claims some comments
  below originally carried. A stranger reading the Lean and convicting the translation is still the
  only thing that moves the axis — this self-audit lowers it, it does not close it.
-/

namespace Attestation

/-- A key. We never need its structure — only that answers are attributable to one. -/
abbrev Key := Nat

/-- An answer to a challenge, content-addressed. Equality is decidable; that is all we use. -/
abbrev Answer := Nat

/-- A signed response: key `k` signed answer `a` over the (implicit) drawn challenge.

    The unforgeability assumption is *modelled*, not proved: constructing a `Resp` stands for
    possessing a signature that verifies. This is the standard cryptographic idealisation, and
    it is the one place a reader must grant something. Everything below is then forced. -/
structure Resp where
  key : Key
  ans : Answer
deriving DecidableEq

/-- A **fork**: two responses to the same drawn challenge carrying *different* answers.
    This is §18b's portable divergence — the only receipt of separation the framework accepts. -/
def isFork (r s : Resp) : Prop := r.ans ≠ s.ans

instance (r s : Resp) : Decidable (isFork r s) := by
  unfold isFork; infer_instance

/-! ## Theorem 1 — differing answers convict at least one signer

  **What the kernel actually proves:** if two responses carry different answers, then against
  *any* single ground truth `t`, at least one of them is ≠ `t`. That is a tautology about
  inequality (`a ≠ b ⟹ ∀ t, a ≠ t ∨ b ≠ t`), and nothing more.

  **Retraction (§18n).** This comment originally read: *"the load-bearing economic claim of §18b…
  a captured quorum cannot manufacture independence without paying for it in correctness —
  permanently, and on the record… the one I most needed checked by something that is not me."*
  That over-claims, and is withdrawn. The *cost*, its *permanence*, its being *on the record*,
  and the *capture* it is meant to prevent are none of them in the theorem — they are the author's
  gloss, prose the kernel does not check. The kernel checked the skeleton; the economic claim rode
  in on the comment. See `docs/formalisation-correspondence.md`. -/
theorem split_implies_signed_error (r s : Resp) (t : Answer) (h : isFork r s) :
    r.ans ≠ t ∨ s.ans ≠ t := by
  by_cases hr : r.ans = t
  · right
    intro hs
    exact h (hr.trans hs.symm)
  · left
    exact hr

/-- Sharper: the *number* of signers convicted by a fork is at least one, whichever answer is
    true. There is no ground truth under which a fork is free. -/
theorem no_free_split (r s : Resp) (h : isFork r s) :
    ∀ t : Answer, ¬(r.ans = t ∧ s.ans = t) := by
  intro t hc
  exact h (hc.1.trans hc.2.symm)

/-! ## Theorem 2 — agreement earns nothing, and refutes nothing

  Two independent correct oracles agree. So agreement yields **no** split — but it must also
  never be read as *evidence of capture*. It is simply the absence of information. -/
theorem agreement_yields_no_split (r s : Resp) (h : r.ans = s.ans) : ¬ isFork r s :=
  fun hf => hf h

/-! ## Theorem 3 — the messenger is irrelevant

  §18c admits a refutation **from any source, including a declared adversary**, because the
  artifact self-authenticates. Formally: whether a fork holds does not mention who submitted
  it. The refuter's identity — and therefore its independence — cannot enter the verdict.

  This is what severs the recursion (a refutation-count would otherwise need an independence
  floor, which would need a refutation-count). Here it is, as a definitional invariance.
  §18n: the theorem holds *because* `upheld` is defined to drop `submitter` — the kernel certifies
  the definition matches the design intent, not that any real verification pipeline genuinely
  ignores who submitted the refutation. -/
structure Refutation where
  submitter : Key
  a : Resp
  b : Resp

/-- The verdict. Note `submitter` does not occur on the right-hand side. That is the theorem. -/
def upheld (x : Refutation) : Prop := isFork x.a x.b

theorem messenger_is_irrelevant (x y : Key) (a b : Resp) :
    upheld ⟨x, a, b⟩ ↔ upheld ⟨y, a, b⟩ := Iff.rfl

/-- Even an adversary's refutation stands, provided the artifact verifies. -/
theorem adversary_may_refute (adversary honest : Key) (a b : Resp) (h : upheld ⟨honest, a, b⟩) :
    upheld ⟨adversary, a, b⟩ := h

/-! ## Theorem 4 — you cannot count a negative

  "I attacked and failed" is an unattestable negative, and counting it is Sybil-farming.
  §18c therefore refuses to count attempts *at all*. Standing is **coverage** — probes drawn,
  answered, signed and checked — and nothing else.

  The theorem is that `attempts` cannot influence standing. It is proved by `rfl`, and that is
  precisely the content: the claimed-attempt count is not merely down-weighted, it is
  *structurally incapable* of entering the verdict.
  §18n: "structurally incapable" because `standing` is *defined* to project `coverage`; the kernel
  certifies I built the definition to ignore attempts, not that ignoring them is the correct model
  of standing. -/
structure Claim where
  coverage : Nat  -- drawn, signed, ground-truth-checked probes. Positives, each paid for.
  attempts : Nat  -- CLAIMED failed attacks. An unattestable negative.

def standing (c : Claim) : Nat := c.coverage

theorem attempts_earn_nothing (cov a b : Nat) :
    standing ⟨cov, a⟩ = standing ⟨cov, b⟩ := rfl

/-- Ten thousand claimed failed attacks move nothing. -/
theorem sybil_cannot_farm_standing (cov : Nat) :
    standing ⟨cov, 10000⟩ = standing ⟨cov, 0⟩ := rfl

/-! ## Theorem 5 — absence of observation is not evidence of separation

  The pessimistic default of §18: parties are **one failure domain** until an observed
  divergence splits them. A pair nobody has probed is *unsplittable*, and must be priced as
  merged rather than credited with a separation nobody has seen. -/
def anyFork : List (Resp × Resp) → Prop
  | []      => False
  | p :: ps => isFork p.1 p.2 ∨ anyFork ps

/-- Nothing observed ⇒ nothing split. The scheme cannot bootstrap a stranger, and says so. -/
theorem unobserved_stays_merged : ¬ anyFork [] := fun h => h

/-- And a single observed fork is enough to split — the floor moves only on evidence. -/
theorem one_fork_splits (r s : Resp) (h : isFork r s) : anyFork [(r, s)] :=
  Or.inl h

/-! ## Theorem 6 — there is no `confirmed` state

  The asymmetry, stated where a kernel can see it. `isFork` is the *only* predicate that can
  hold of a pair. There is no constructor anywhere in this development that takes a pile of
  agreement and returns independence — and that is not an oversight, it is the design.

  Concretely: the split relation is symmetric and irreflexive. Irreflexivity is the formal
  content of "a thing cannot corroborate itself" — one machine, however many hats, never forks
  with itself. -/
theorem fork_irrefl (r : Resp) : ¬ isFork r r := fun h => h rfl

theorem fork_symm {r s : Resp} (h : isFork r s) : isFork s r := fun e => h e.symm

/-- **One machine wearing N hats cannot manufacture a split.** If every response carries the
    same answer — which is what a single deterministic party emits — no pair forks, whatever
    the key count. Unanimity is not corroboration; it is the shape of one peak, sampled N
    times. -/
theorem one_machine_cannot_split (a : Answer) :
    ∀ (rs : List Resp), (∀ r ∈ rs, r.ans = a) →
      ∀ r ∈ rs, ∀ s ∈ rs, ¬ isFork r s := by
  intro rs hall r hr s hs
  have hra : r.ans = a := hall r hr
  have hsa : s.ans = a := hall s hs
  exact agreement_yields_no_split r s (hra.trans hsa.symm)

end Attestation
