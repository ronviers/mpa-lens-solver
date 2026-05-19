# mpa-lens-solver — next-session handoff

v1.2 shipped 2026-05-18. v1.0's architecture (predictor-corrector + adaptive
bracket + regime-band guard) is unchanged. v1.2 adds the FitDiagnostics
container + `bootstrap=True` mode to `fit_translation_field`; the calibration
apparatus that would consume those signals lives in mpa-conform, not here.

This document is the **thin open-items list** the next session reads cold to
decide where to pick up. The items are independent and none is gating.

---

## Open items

### 1. Score-function depth — cdv1 character extension

`mpa_scale_solver.gfdr_model.locus_residual` is a closed-form analytical model
with regime-boundary attractors at chit ≈ +0.2 and +0.7. Refinement against
real substrate (C, χ) data plateaus around residual ~0.05–0.20 today; the
regime guard + predictor bracket contain the damage.

The richer-score question is **not** "how do we make refinement beat the
prior?" — that framing led us astray (the prior is *physics*; framing
refinement as "beating physics" makes it look unfair, when it isn't).
The cdv1-aligned framing
([`CHARACTER_FRAMING.md`](CHARACTER_FRAMING.md) §Refinement reads character):
the prior is the substrate's leading-order universality form; a richer score
lets refinement surface the *substrate-thermodynamic deviation* from that
form. cdv1's Open Items section names that derivation as the canonical
extension mode of the framework's API — universality fixes exponents,
substrates fix amplitudes.

Concrete: glass refinement measures `α_s` (CK aging-diagonal slope); QEC
refinement measures surface-code departure from pure-laser analogue at
regime boundaries; brain refinement measures context-modulated departures
from the scenario table.

**Trigger for this work:** a specific cdv1 posit's deviation we want
measured on a specific substrate. Not generic depth. Any future
score-depth work names the posit and the substrate up front. Until that
trigger fires, the v1.2 FitDiagnostics surface (raw signals; mpa-conform
percentile absorption) is the right resting state.

Candidate richer-score shapes when the trigger fires: extra latent shape
parameters per regime; per-cell empirical kernel fit; multi-window
residual weighted by τ range.

### 2. QEC chi normalizer — do not reintroduce as preprocessing (resolved 2026-05-18)

When mpa-conform's old inversion path was removed, `_quantum_scale_q` (the
chi normalizer that divided QEC's empirical chi by its deep-r asymptote) went
with it. Without it, QEC's empirical chi is on a different scale than the
analytical locus, so residuals are inflated (~150+ vs glass's ~0.1). v1.2
calibration sweeps confirmed: quantum's `residual_final` p50 ≈ 147, glass's
p50 ≈ 0.2.

**Decision: do not reintroduce as preprocessing here.** The v0.3 calibration
apparatus (per-substrate baselines at
[`H:/mpa-conform/conformer/calibration/baselines.py`](../../mpa-conform/conformer/calibration/baselines.py),
percentile lookup at
[`percentile.py`](../../mpa-conform/conformer/calibration/percentile.py))
absorbs the scale mismatch at the correct layer — the auditor sees
percentiles, not raw values, so quantum's p50 ≈ 147 reads as "p50, normal
for the substrate" alongside glass's p50 ≈ 0.2 (per
[`H:/mpa-central/SYSTEM_OVERVIEW.md`](../../mpa-central/SYSTEM_OVERVIEW.md) §5).
The cross-path agreement signal lives in chit units and is scale-free by
construction.

Reintroducing the normalizer in `empirical_rows_from_cell` would:

1. Duplicate the correction — once in lens-solver, once in mpa-conform's
   baselines, with no single source of truth for the scale.
2. Couple `residual_final`'s meaning to a substrate-specific preprocessing
   choice, breaking the "raw signal" framing the v1.2 `FitDiagnostics`
   container is built around.
3. Violate the [`CLAUDE.md`](../CLAUDE.md) preprocessing rule (*"The
   TranslationField IS the normalization, returned as data"*).

**The deeper why:** QEC's deep-r chi asymptote is substrate-class character
(code distance + stabilizer structure), not arbitrary scale. Character
lives in the TranslationField, not in preprocessing. The right long-term
home is a TranslationField shape extension that declares observable
conventions per substrate; the present TranslationField shape
(`operating_point → chit, γ_AB, k_frust`) does not carry them. See
[`CHARACTER_FRAMING.md`](CHARACTER_FRAMING.md) §Observable conventions
belong in TranslationField for the full frame, including the trigger
condition for that extension. Until the trigger fires, the per-substrate
baseline absorption is the correct present shape — the inflated QEC
residual is honest substrate-class scale fingerprint data flowing into
the baseline where it belongs.

### 3. Bootstrap rollout — landed 2026-05-18

The bootstrap path exists, is tested, and now dispatches automatically.
Behavior:

- `bootstrap=None` (default) → known substrates (`_PRIOR_DISPATCH`:
  glass / quantum / brain) use the cdv1 prior; unknown substrates fall
  through to bootstrap. Explicit `True`/`False` overrides as before.
- `bootstrap_seed_range=None` (default) → per-substrate dispatch from
  `_BOOTSTRAP_SEED_RANGE_DISPATCH` (glass `(-1.0, 1.2)`, quantum
  `(-2.5, 5.5)`, brain `(-1.0, 1.0)`, padded ~25% beyond each known
  substrate's prior envelope across the library). Unknown substrates
  fall back to `DEFAULT_BOOTSTRAP_SEED_RANGE = (-2.0, 2.0)`. Explicit
  tuple overrides.
- `_natural_sort_key` and `_operating_point_from_cell` fall back to
  preserve-input-order + take-all-op-keys respectively for unknown
  substrates, so the dispatch produces a usable TranslationField end-
  to-end. (Tested in `tests/test_priors.py::test_fit_translation_field_unknown_substrate_auto_bootstraps`.)

Calibration sweep characterization (mpa-conform, May 2026) showed the
bootstrap path has higher gt_error tails than prior paths, as expected;
per-substrate baselines absorb the difference. Predictor reads
**refined-chit history** in bootstrap mode (vs prior-chit history in
prior'd mode) — a documented difference.

When a real prior-less substrate lands (e.g. a "mountain weathering"
substrate), no lens-solver change is required — call
`fit_translation_field("mountain_weathering", cells, "weathering-rate")`
and the dispatch handles it. Promoting to a known substrate later means
adding a prior to `_PRIOR_DISPATCH` and an entry to
`_BOOTSTRAP_SEED_RANGE_DISPATCH`; both `_OPERATING_POINT_AXES` and
`_BRAIN_SCENARIO_ORDER`-style natural-sort handlers earn their weight
when the substrate's trajectory order is non-trivial.

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
