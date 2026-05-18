# mpa-lens-solver — next-session handoff

v1.0 shipped 2026-05-17. The v0 / v0.2 / v0.3+ ladder collapsed into one
process: `fit_translation_field` with the predictor-corrector + adaptive
bracket + regime-band guard. Architecture documented in
[`../README.md`](../README.md). Session log there is the historical residue.

This document is the **thin open-items list** the next session reads cold to
decide where to pick up. It is not a roadmap; the items are independent and
none is gating.

---

## Open items

### 1. Score-function depth

The bottleneck for prior'd substrates. `mpa_scale_solver.gfdr_model.locus_residual`
is a closed-form analytical model with regime-boundary attractors at chit ≈
+0.2 (s_critical / c_near_s boundary) and chit = +0.7 (deep_c / c_near_s
boundary). Refinement against real substrate (C, χ) data plateaus around
residual ~0.05–0.20 and gets pulled toward those boundaries. The regime guard
+ predictor bracket contain the damage (no LUT-corrupting regime crossings,
no unbounded drift), but the residual is a *consistency check*, not a
*calibration knob*.

A richer score would make `max_passes > 0` load-bearing for prior'd substrates,
not just protective. Candidates:

- A model with more parametric flexibility per regime (extra latent shape
  parameters beyond chit).
- A per-cell empirical kernel fit instead of a closed-form locus.
- Multi-window residual that weights different τ ranges differently.

This is the move that would close the open question "when does refinement
beat the prior?" Today the answer is "almost never, for substrates with
analytical priors." A better score flips that.

### 2. QEC chi normalizer

When we removed mpa-conform's old inversion path, we also removed
`_quantum_scale_q` — the chi normalizer that divided QEC's empirical chi by
its deep-r asymptote so chi/(1−C) → 1, matching the gfdr model's assumption.
Without it, QEC's empirical chi is on a different scale than the analytical
locus, so residuals are inflated (~150+ vs glass's ~0.1).

The regime guard + bracket prevent visible damage in the rendered shots
(refinement stays bounded), but the QEC residual numbers in
`extras["residual"]` are not directly comparable to glass's. The chi
normalizer belongs in `iterate.py::empirical_rows_from_cell` as a
substrate-conditional preprocessing step.

Out of scope: the normalizer itself is straightforward (port from
`mpa-conform/conformer/shot/library_sequence_shot.py` deleted block, git
history before 2026-05-17). Decision needed: should the normalization be
substrate-conditional in `empirical_rows_from_cell` (simple) or expressed as
a property of the substrate-class registry (cleaner, more code)?

### 3. Bootstrap path — substrates without analytical priors

The iterator has the machinery for prior-less substrates: when
`cdv1_prior_chit(substrate, ...)` is undefined, the bootstrap shape is
"random seed within gamut → predictor builds the trajectory from refinement
history → regime guard contains the search." No prior-less substrate exists
in the library yet to exercise this.

When one lands (a candidate "mountain" weathering substrate is mentioned in
program memory), the work is:

- Add the substrate name to `_PRIOR_DISPATCH` with a no-prior marker (or
  refactor so the dispatch can return `None` for "no analytical prior").
- Define a default seed strategy (uniform-random within a substrate-class
  gamut envelope, perhaps from mpa-scale-solver's `GamutSpec`).
- The predictor and regime guard already work prior-less by design — they
  read history and gt-declaration, not priors.

This is the test that proves "one process" actually generalizes.

### 4. Native port (Rust + wasm)

Not urgent. The lens-solver is called once per shot to build a LUT
(~35 000 score evaluations per substrate, sub-second in Python). The hot
per-frame path lives in mpa-scale-solver, which is already Rust-canonical.

The port becomes load-bearing when either:
- A wasm consumer needs to rebuild LUTs in-browser (live calibration in the
  external analysis view).
- The score function (item 1 above) gets expensive enough that build-time
  becomes a bottleneck.

The Python is already shaped for direct port: frozen dataclasses, pure free
functions, seeded RNG, value semantics. Follow the mpa-scale-solver pattern
(`H:/mpa-scale-solver/rust/`).

### 5. External view consumer

Out of scope for this repo. Documented at
[`../README.md#wire-format-translationfield-is-the-view-transform-lut`](../README.md).
The TranslationField is the canonical wire format; somebody else's repo (a
future analysis view) reads it via `dataclasses.asdict` + `json`. File-import
boundary, not our work.

---

## What's not on this list (and why)

- **A new TranslationField shape** (tangent_flow, learned MLP). The original
  BLOCK_IN §v0.3+ planned these. They're subsumed: the `lookup_table` shape
  + iterative refinement covers what they would have. If a future score
  function (item 1) wants gradient-based optimization, tangent_flow becomes
  worth revisiting — but as an optimization detail, not a separate version.
- **gamma_AB refinement.** The gFDR locus doesn't constrain gamma_AB (RFC-S
  Appendix B item 4); refining it would be moving in a null direction.
  Stays at the lens-solver default.
- **Substrate physics, EXR rendering, canonical-space ops.** Owned by other
  repos per the three-solver split.

---

## Reading order when a session opens this document

1. [`../README.md`](../README.md) — current architecture, wire format,
   session log.
2. [`../CLAUDE.md`](../CLAUDE.md) — session discipline.
3. The open items above — pick one or pivot.
