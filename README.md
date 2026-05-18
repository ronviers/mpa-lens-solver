# mpa-lens-solver

The substrate-class "ICC profile" solver for the MPA suite. Produces
per-substrate-class `TranslationField` instances that map raw substrate
observations (the multi-window FDR readouts mpa-solver computes and
mpa-central/library packages) into the canonical (chit, γ_AB) coordinates
the framework can read.

Third solver in the MPA suite:

| Solver | Job |
|---|---|
| [mpa-solver](https://github.com/ronviers/mpa-solver) | Forward substrate physics; produces measurement observations |
| [mpa-scale-solver](https://github.com/ronviers/mpa-scale-solver) | Canonical-space runtime (`apply_translation`, `forward_sweep_invert`, `regime_at`, `gamut_classify`, `flow`, `intent_map`) |
| **mpa-lens-solver** | Fits substrate-class `TranslationField`s from observations + cdv1 priors. The substrate's ICC profile. |

## Why "lens"

A substrate has its own physics. The framework has its own canonical coordinates.
The two don't natively speak the same language. A lens — in the camera/optical
sense — is the per-instrument calibration that bridges them. Chromatic
aberration correction is exactly the per-substrate characterization this solver
provides. Same camera (τ_obs per RFC-S §0.2), different lenses, framework
speaks the same words regardless of whether the substrate is a bacterial
colony, a mountain weathering across geological time, or a surface-code
quantum memory.

## Status

**v1.2 — one process + bootstrap mode + FitDiagnostics container.** A single
function `fit_translation_field` handles every case from "prior is exactly
right" (zero refinement passes) to "no prior exists" (bootstrap from random
within gamut, `bootstrap=True`). Same return shape, same call site, no
separate code paths.

Every cell's `canonical.extras` carries a `fit_diagnostics` dict — raw
confidence signals (residual_final, regime_confidence, predictor_gap, source,
n_passes). These are *raw* signals in their natural scale; lens-solver does
not threshold them. Calibration apparatus (per-substrate baseline percentiles +
cross-path agreement) lives downstream in mpa-conform — see [Confidence
quantities](#confidence-quantities) below.

The refinement is hill-climbing in 1D on chit (γ_AB is unobservable from the
single-mode gFDR locus per RFC-S Appendix B item 4) under two stacked guards:

1. **Regime-band guard** — candidates whose `vertex_regime` differs from the
   seed's are rejected. Catches gfdr-score-attractor crossings that would
   propagate to every camera consuming the LUT.
2. **Predictor-corrector bracket** — candidates outside the trajectory's
   extrapolated bracket are rejected. Bracket width is **adaptive**:
   `delta_predict = max(min_delta, k_step * |expected_step|)` — wide where
   the trajectory migrates aggressively, narrow where it moves in tight
   increments. The predictor reads **prior-chit history** (not refined),
   decoupling the observer from the process: if the score is biased, the
   bracket cannot wander because slope and width are anchored to the prior's
   shape, not the refinement's drift.

Cells are sorted internally by the substrate's natural trajectory order
(T ascending for glass, p_base ascending for quantum, scenario index for
brain). The trajectory is a first-class concept the solver owns.

## Install

```
pip install -e H:/mpa-lens-solver
```

(In-repo development install; the package is not on PyPI.)

## Quickstart

```python
from mpa_lens_solver import fit_translation_field
import json, glob

cells = [json.load(open(p)) for p in glob.glob("H:/mpa-central/library/data/glass/*spin-flip*.json")]

# Pure cdv1 prior (max_passes=0 default).
field = fit_translation_field(substrate="glass", cells=cells, xdot_kind="spin-flip")

# Or: refine against the cells' (C, chi) observations using the
# predictor-corrector with adaptive bracket and regime-band guard.
field = fit_translation_field(
    substrate="glass", cells=cells, xdot_kind="spin-flip",
    max_passes=100, tolerance=1e-3, n_candidates=32,
    min_delta=0.05, k_step=1.5,
)
# field is an mpa_scale_solver.TranslationField, ready for apply_translation /
# forward_sweep_invert in mpa-scale-solver's runtime.

# Or: bootstrap mode (mask the cdv1 prior; seed from uniform random within a
# substrate-class gamut). Useful for calibration sweeps that need to exercise
# the prior-less path on a substrate whose prior IS available — the prior'd
# run provides ground truth.
field = fit_translation_field(
    substrate="glass", cells=cells, xdot_kind="spin-flip",
    max_passes=100, bootstrap=True, bootstrap_seed_range=(-2.0, 2.0),
    rng_seed=42,
)
```

The field is consumed by mpa-conform's `library_sequence_shot.py` to feed
canonical states into the paired Mode B EXR render — both the empirical
substrate trajectory and the cadence-matched Banach analytical voice ride
through the same canonical coordinates.

## Wire format — TranslationField is the view-transform LUT

The returned `TranslationField` is structurally a lookup table
(`shape="lookup_table"`) — that's not just a name. The field IS the canonical
wire format every downstream camera reads:

- Mode B (camera rides the canonical flow) — `mpa-conform/conformer/shot/library_sequence_shot.py`
- Mode A / external analysis views (camera looks at the flow from outside) — future
- mpa-auditor viewport when it gains tumble / playback — future

**One LUT, multiple cameras.** Consumers read at the dataclass boundary:

| Field | Meaning |
|---|---|
| `field.direction` | always `"forward"` (substrate → canonical) |
| `field.shape` | always `"lookup_table"` (this solver's only shape) |
| `field.rule[i].operating_point` | substrate-side label, gt, and axes |
| `field.rule[i].canonical` | `(chit, gamma_AB, k_frust, method, extras)` |
| `field.rule[i].canonical.extras["prior_chit"]` | cdv1 prior seed (refined mode) |
| `field.rule[i].canonical.extras["prior_regime"]` | regime guard band (refined mode) |
| `field.rule[i].canonical.extras["predicted_chit"]` | line extension from prior history (None for first 2 cells) |
| `field.rule[i].canonical.extras["bracket_center"]` | center actually used (prior for first 2 cells, predicted thereafter) |
| `field.rule[i].canonical.extras["predictor_expected_step"]` | local slope magnitude (drives delta_predict) |
| `field.rule[i].canonical.extras["delta_predict"]` | adaptive bracket half-width used |
| `field.rule[i].canonical.extras["residual"]` | gfdr score at the stamped chit |
| `field.rule[i].canonical.extras["passes_used"]` | refinement passes that ran |
| `field.rule[i].canonical.extras["guard_regime"]` | whether the regime-band guard was active |
| `field.rule[i].canonical.extras["fit_diagnostics"]` | raw confidence vector — `{residual_final, regime_confidence, predictor_gap, source, n_passes}` |

JSON wire format: `dataclasses.asdict(field)` + `json.dumps`. The frozen
dataclasses round-trip cleanly; the `extras` dict carries only JSON-primitive
values. No custom encoders required.

## Confidence quantities

Lens-solver emits **raw** diagnostic signals per cell — not classifications.
Three orthogonal fields with uniform "higher = worse" semantics, all in
their natural scale:

| Field | Meaning |
|---|---|
| `residual_final` | Raw final residual of the gFDR locus score; lower = better fit. Path-conditional natural scale (no normalization). |
| `regime_confidence` | `1 − (off-regime candidate fraction over refinement passes)`. Range `[0, 1]`. High = score function pinned to one regime (potentially over-confident); low = score explored regimes (refinement had room to work). |
| `predictor_gap` | `\|final_chit − predicted_chit\|` in chit units. Raw distance, no bracket normalization. `None` when predictor was inactive (no trajectory history, single-cell call). |

Plus `source` (path identity: `lens_solver_prior` or `lens_solver_bootstrap`)
and `n_passes` (refinement passes used).

**Calibration apparatus lives downstream**, not in this repo. The recurring
failure of "single calibration-free per-fit confidence scalar" surveyed
across five attempts (raw thresholds, normalized thresholds, non-parametric
bootstrap, Laplace approximation, polished Laplace) showed the solvers'
robustness constraints intentionally defeat each metric class. The salvage:
split per-fit confidence into three calibration-free primitives, all in
mpa-conform's calibration subpackage:

- **Per-substrate baseline percentiles** ([`mpa-conform/conformer/calibration/baselines.py`](https://github.com/ronviers/mpa-conform/blob/master/conformer/calibration/baselines.py)) — known-good distribution of `fit_diagnostics` values per (substrate, path, field). New substrates extend the calibration set automatically.
- **Cross-path agreement** ([`mpa-conform/conformer/calibration/cross_path.py`](https://github.com/ronviers/mpa-conform/blob/master/conformer/calibration/cross_path.py)) — `|chit_two_stage − chit_lens_solver_prior|` in chit units. Independent-paths disagreement is a chit-unit signal needing no calibration.
- **Cross-substrate sweep harness** ([`mpa-conform/conformer/calibration/sweep.py`](https://github.com/ronviers/mpa-conform/blob/master/conformer/calibration/sweep.py)) — produces the parquet baselines are computed from. Re-run when the algorithm changes.

The downstream `declaration-bundle.v0.3` schema's `audit_delta` carries all
three plus the raw `fit_diagnostics`. The auditor consumes percentiles
(self-calibrating against substrate) + cross-path disagreement; raw
diagnostics ride along for forensics.

## What this repo does NOT do

- Run substrate physics. That's [mpa-solver](https://github.com/ronviers/mpa-solver).
- Canonical-space operations (`apply_translation`, `regime_at`, etc.).
  That's [mpa-scale-solver](https://github.com/ronviers/mpa-scale-solver).
  We *produce* TranslationFields; that repo *consumes* them.
- Render EXR sequences. That's [mpa-conform](https://github.com/ronviers/mpa-conform).
- Modify [mpa-central/library](https://github.com/ronviers/mpa-central).
  We read library cells; we never write to them.

Architectural authority: [`H:/mpa-conform/docs/SOLVERS_BLOCK_IN.md`](https://github.com/ronviers/mpa-conform/blob/main/docs/SOLVERS_BLOCK_IN.md)
names the three-solver split.

## Reproducibility & native-port readiness

Pure free functions on frozen dataclasses, value semantics, seeded RNG
(`numpy.random.default_rng(rng_seed + i)` per cell). Same inputs →
byte-identical output. The Python is shaped as the pseudo-spec a Rust /
wasm port reads directly when a consumer needs it (live in-browser
calibration, expensive score functions). For build-time LUT production
called by mpa-conform, the Python is fast enough — the per-frame hot
path lives in mpa-scale-solver, which is already Rust-canonical.

## Session Log

| # | Date | Session | Result | Notes |
|---|------|---------|--------|-------|
| 1 | 2026-05-17 | v1.0 architecture: prism + predictor-corrector | shipped | 53/53 tests; one-process collapses BLOCK_IN's v0/v0.2/v0.3+ ladder; predictor reads prior history; adaptive bracket sized by trajectory inertia; regime-band guard; QEC + glass paired Mode B shots show the c→s→r migration with Banach overlay diverging cleanly |
| 2 | 2026-05-18 | v1.2: FitDiagnostics + bootstrap mode + sweep characterization → salvage to mpa-conform calibration apparatus | shipped | 75/75 tests; FitDiagnostics container (residual_final, regime_confidence, predictor_gap, source, n_passes) emitted per cell; `bootstrap=True` masks the cdv1 prior; 56,880-fit sweep across 3×3×7×9×5 matrix in mpa-conform characterized 5 attempts at calibration-free per-fit confidence (all hit structural walls — solver robustness defeats data-perturbation metrics); salvage via per-substrate baseline percentiles + cross-path agreement landed in mpa-conform v0.3 schema |

## License

MIT (consistent with mpa-solver, mpa-scale-solver, mpa-central, mpa-conform, mpa-atlas, mpa-auditor).
