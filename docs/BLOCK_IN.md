# mpa-lens-solver — next-session handoff

v1.2 shipped 2026-05-18. v1.0's architecture (predictor-corrector + adaptive
bracket + regime-band guard) is unchanged. v1.2 adds the FitDiagnostics
container + `bootstrap=True` mode to `fit_translation_field`; the calibration
apparatus that would consume those signals lives in mpa-conform, not here.

This document is the **thin open-items list** the next session reads cold to
decide where to pick up. The items are independent and none is gating.

---

## Open items

### 1. Score-function depth (unchanged from v1.0)

`mpa_scale_solver.gfdr_model.locus_residual` is a closed-form analytical model
with regime-boundary attractors at chit ≈ +0.2 and +0.7. Refinement against
real substrate (C, χ) data plateaus around residual ~0.05–0.20 and gets pulled
toward those boundaries. The regime guard + predictor bracket contain the
damage; the residual is a *consistency check*, not a *calibration knob*.

A richer score would make `max_passes > 0` load-bearing for prior'd
substrates. Candidates: extra latent shape parameters per regime; per-cell
empirical kernel fit; multi-window residual weighted by τ range.

This is the move that closes "when does refinement beat the prior?" Today it
almost never does for substrates with analytical priors. v1.2 didn't change
this — the FitDiagnostics surface measures *what* the score does, not how
deep it is.

### 2. QEC chi normalizer (unchanged from v1.0)

When mpa-conform's old inversion path was removed, `_quantum_scale_q` (the
chi normalizer that divided QEC's empirical chi by its deep-r asymptote) went
with it. Without it, QEC's empirical chi is on a different scale than the
analytical locus, so residuals are inflated (~150+ vs glass's ~0.1). v1.2
calibration sweeps confirmed: quantum's `residual_final` p50 ≈ 147, glass's
p50 ≈ 0.2. Per-substrate baselines absorb this in mpa-conform, but the
underlying scale mismatch remains.

The normalizer belongs in `iterate.py::empirical_rows_from_cell` as a
substrate-conditional preprocessing step. Decision needed: substrate-
conditional in `empirical_rows_from_cell` (simple) vs property of the
substrate-class registry (cleaner, more code).

### 3. Bootstrap path exercised (v1.2 update)

The bootstrap path now exists and is tested. `fit_translation_field(...,
bootstrap=True, bootstrap_seed_range=(-2.0, 2.0))` masks the cdv1 prior and
draws uniform-random initial chits. The predictor reads **refined-chit
history** in bootstrap mode (vs prior-chit history in prior'd mode) — a
documented difference. Calibration sweep characterization (mpa-conform, May
2026) showed the bootstrap path has higher gt_error tails than prior paths,
as expected; per-substrate baselines absorb the difference.

When a real prior-less substrate lands (a "mountain weathering" substrate
mentioned in program memory), the only remaining work is:

- Add the substrate name to `_PRIOR_DISPATCH` or refactor it to dispatch
  bootstrap by default for unknown substrates.
- Decide a default `bootstrap_seed_range` per substrate class (currently
  uniform `(-2, 2)` for all).

The predictor and regime guard already work prior-less.

### 4. Native port (Rust + wasm) — unchanged from v1.0

Not urgent. The lens-solver is called once per shot to build a LUT
(~35 000 score evaluations per substrate, sub-second in Python). The hot
per-frame path lives in mpa-scale-solver, which is already Rust-canonical.

The port becomes load-bearing when either:
- A wasm consumer needs to rebuild LUTs in-browser (live calibration in an
  external analysis view).
- The score function (item 1) gets expensive enough that build-time becomes
  a bottleneck.

The Python is already shaped for direct port: frozen dataclasses, pure free
functions, seeded RNG, value semantics. Follow the mpa-scale-solver pattern
(`H:/mpa-scale-solver/rust/`).

### 5. External view consumer — unchanged from v1.0

Out of scope for this repo. Documented at [`../README.md#wire-format-translationfield-is-the-view-transform-lut`](../README.md). The
TranslationField is the canonical wire format; somebody else's repo (a future
analysis view) reads it via `dataclasses.asdict` + `json`. File-import
boundary, not our work.

---

## What v1.2 added (background for next session)

- **`FitDiagnostics` dataclass** (`mpa_lens_solver/diagnostics.py`): frozen
  container with `residual_final`, `regime_confidence`, `predictor_gap`,
  `source`, `n_passes`. Source tag is one of `lens_solver_prior` or
  `lens_solver_bootstrap`. The dataclass shape is shared with mpa-conform's
  two-stage inversion (same FitDiagnostics, source = `two_stage_inversion`).
- **`fit_translation_field(bootstrap=True, bootstrap_seed_range=...)`**: masks
  the cdv1 prior; everything else (refinement, regime guard, predictor) runs
  as in the prior'd path.
- **Every `canonical.extras` carries a `fit_diagnostics` dict** (JSON-
  primitive form via `FitDiagnostics.to_dict()`). Downstream readers branch
  on the `source` field.

## What v1.2 deliberately did NOT add

- **Per-fit confidence classification.** Five attempts at a calibration-free
  per-fit scalar all hit structural walls; the conclusion (documented at
  [`H:/mpa-conform/docs/open_fit_confidence_framing.md`](../../mpa-conform/docs/open_fit_confidence_framing.md))
  is that the solver's robustness constraints intentionally defeat
  data-perturbation metrics. The lens-solver emits raw signals; the
  calibration apparatus (per-substrate baselines, cross-path agreement)
  lives in mpa-conform, not here.
- **Schema knowledge.** lens-solver does not know about
  `declaration-bundle.v0.3`; conform's curator wraps these signals into the
  bundle's `audit_delta`.

---

## What's not on this list (and why)

- **A new TranslationField shape** (tangent_flow, learned MLP). The original
  BLOCK_IN §v0.3+ planned these. They're subsumed: `lookup_table` shape +
  iterative refinement covers what they would have. If a future score
  function (item 1) wants gradient-based optimization, tangent_flow becomes
  worth revisiting — but as an optimization detail, not a separate version.
- **gamma_AB refinement.** The gFDR locus doesn't constrain gamma_AB (RFC-S
  Appendix B item 4); refining it would be moving in a null direction. Stays
  at the lens-solver default.
- **Substrate physics, EXR rendering, canonical-space ops.** Owned by other
  repos per the three-solver split.

---

## Reading order when a session opens this document

1. [`../README.md`](../README.md) — current architecture, wire format,
   session log, confidence quantities.
2. [`../CLAUDE.md`](../CLAUDE.md) — session discipline.
3. The open items above — pick one or pivot.
4. For confidence/calibration questions:
   [`H:/mpa-conform/docs/open_fit_confidence_framing.md`](../../mpa-conform/docs/open_fit_confidence_framing.md)
   captures the recurring-failure pattern that drove the v0.3 schema design.
