"""cdv1-prior translation fields per substrate class + iterative refinement.

Three substrate-class prior functions plus a dispatch produce the seed
canonical state per cell. fit_translation_field stamps the prior, then
(if max_passes > 0) refines each cell's chit against the cell's emitted
(C, chi) curve via mpa_lens_solver.iterate.refine_chit.

One process: max_passes=0 returns the pure cdv1 prior (clear-in-zero-passes
case). max_passes>0 lets each cell take as many passes as it needs to fall
under tolerance. Same return shape either way.

bootstrap=True masks the cdv1 prior — initial chit per cell is drawn
uniformly from bootstrap_seed_range using a deterministic per-cell seed.
The predictor then reads refined-chit history (not prior history) since
no prior trajectory exists. Use this to exercise the bootstrap path on a
substrate whose prior IS available — the prior'd run provides ground truth
for sweep/calibration work.

bootstrap=None (default) dispatches per substrate: known substrates
(_PRIOR_DISPATCH) use the cdv1 prior; unknown substrates fall through
to bootstrap. bootstrap_seed_range=None dispatches similarly via
_BOOTSTRAP_SEED_RANGE_DISPATCH with DEFAULT_BOOTSTRAP_SEED_RANGE as the
unknown-substrate fallback.

Prism per the pipeline canonical (mpa-conform SUITE_BLOCK_IN): substrate-native
operating points enter, canonical (chit, gamma_AB) exit. Each substrate class
has its own ICC profile:

    Glass:   chit = Tc - T,   with Tc = 1.1                     (cdv1 §gFDR)
    QEC:     chit = ln(p_threshold / p_base), p_threshold = 1e-2 (cdv1 §Surface-code)
    Brain:   scenario table  {committed: +0.6, suspended: +0.1,
                              conflict: 0.0,    reset:    -0.5}  (hand-cal; flag for adjudication)
"""
from __future__ import annotations

import math

import numpy as np

from mpa_scale_solver.types import (
    CanonicalPoint,
    OperatingPoint,
    TranslationField,
    TranslationRule,
)

from .diagnostics import FitDiagnostics, build_diagnostics
from .iterate import empirical_rows_from_cell, predict_next_chit, refine_chit


GLASS_TC = 1.1
QEC_P_THRESHOLD = 1e-2
BRAIN_SCENARIO_CHIT: dict[str, float] = {
    "committed": +0.6,
    "suspended": +0.1,
    "conflict":   0.0,
    "reset":     -0.5,
}

DEFAULT_GAMMA_AB = -0.3
DEFAULT_K_FRUST = False
DEFAULT_BOOTSTRAP_SEED_RANGE: tuple[float, float] = (-2.0, 2.0)

# Per-substrate bootstrap seed ranges, padded ~25% beyond the cdv1-prior
# chit envelope across the library's operating points. Unknown substrates
# fall back to DEFAULT_BOOTSTRAP_SEED_RANGE.
_BOOTSTRAP_SEED_RANGE_DISPATCH: dict[str, tuple[float, float]] = {
    "glass":   (-1.0, 1.2),    # prior envelope: -0.7 to +0.9 (T = 0.2..1.8)
    "quantum": (-2.5, 5.5),    # prior envelope: -1.6 to +4.6 (p_base = 1e-4..5e-2)
    "brain":   (-1.0, 1.0),    # prior envelope: -0.5 to +0.6 (4 scenarios)
}


def glass_prior(op: dict) -> float:
    T = op.get("T")
    if T is None:
        raise ValueError(f"glass operating_point requires T; got: {op}")
    return GLASS_TC - float(T)


def quantum_prior(op: dict) -> float:
    p_base = op.get("p_base")
    if p_base is None or float(p_base) <= 0.0:
        raise ValueError(f"quantum operating_point requires positive p_base; got: {op}")
    return math.log(QEC_P_THRESHOLD / float(p_base))


def brain_prior(op: dict) -> float:
    scenario = op.get("scenario")
    if scenario not in BRAIN_SCENARIO_CHIT:
        raise ValueError(
            f"brain operating_point requires scenario in "
            f"{sorted(BRAIN_SCENARIO_CHIT)}; got: {op}"
        )
    return BRAIN_SCENARIO_CHIT[scenario]


_PRIOR_DISPATCH = {
    "glass":   glass_prior,
    "quantum": quantum_prior,
    "brain":   brain_prior,
}

_OPERATING_POINT_AXES = {
    "glass":   ("T", "h_field"),
    "quantum": ("p_base", "delta_p"),
    "brain":   ("scenario",),
}

# Natural trajectory order per substrate (camera flies in this direction).
# All three substrates have monotone chit under this ordering: chit descends
# from deep_c at the start to deep_r at the end. The predictor relies on this
# continuity, so we sort internally rather than trusting caller order.
_BRAIN_SCENARIO_ORDER = {"committed": 0, "suspended": 1, "conflict": 2, "reset": 3}


def _natural_sort_key(substrate: str, cell: dict):
    op = cell["operating_point"]
    if substrate == "glass":
        return (float(op["T"]),)
    if substrate == "quantum":
        return (float(op["p_base"]),)
    if substrate == "brain":
        return (_BRAIN_SCENARIO_ORDER.get(op.get("scenario"), 99),)
    # Unknown substrate: preserve caller's input order via stable sort.
    return (0,)


def _resolve_bootstrap(substrate: str, override: bool | None) -> bool:
    """Honour explicit override; otherwise bootstrap iff substrate is
    unknown to _PRIOR_DISPATCH. The bootstrap path becomes the zero-
    knowledge fallback for substrates the framework hasn't characterized."""
    if override is not None:
        return override
    return substrate not in _PRIOR_DISPATCH


def _resolve_bootstrap_seed_range(
    substrate: str,
    override: tuple[float, float] | None,
) -> tuple[float, float]:
    """Honour explicit override; otherwise dispatch on substrate with
    fallback to DEFAULT_BOOTSTRAP_SEED_RANGE."""
    if override is not None:
        return override
    return _BOOTSTRAP_SEED_RANGE_DISPATCH.get(substrate, DEFAULT_BOOTSTRAP_SEED_RANGE)


def cdv1_prior_chit(substrate: str, op: dict) -> float:
    prior = _PRIOR_DISPATCH.get(substrate)
    if prior is None:
        raise ValueError(
            f"unknown substrate {substrate!r}; expected one of {sorted(_PRIOR_DISPATCH)}"
        )
    return prior(op)


def _operating_point_from_cell(substrate: str, cell: dict) -> OperatingPoint:
    op = cell["operating_point"]
    axes_keys = _OPERATING_POINT_AXES.get(substrate)
    if axes_keys is None:
        # Unknown substrate: take every op key except label and gt.
        axes_keys = tuple(k for k in op if k not in ("label", "gt"))
    axes = {k: op[k] for k in axes_keys if op.get(k) is not None}
    return OperatingPoint(label=op["label"], gt=op["gt"], axes=axes)


def fit_translation_field(
    substrate: str,
    cells: list[dict],
    xdot_kind: str,
    *,
    max_passes: int = 0,
    tolerance: float = 1e-3,
    n_candidates: int = 32,
    rng_seed: int = 0,
    guard_regime: bool = True,
    min_delta: float = 0.05,
    k_step: float = 1.5,
    trail_window: int = 3,
    bootstrap: bool | None = None,
    bootstrap_seed_range: tuple[float, float] | None = None,
) -> TranslationField:
    """One process. Stamp cdv1 prior (or random seed if bootstrap); refine
    each cell up to max_passes.

    `bootstrap=None` (default): dispatched per substrate. Substrates in
    `_PRIOR_DISPATCH` (glass / quantum / brain) use the cdv1 prior;
    unknown substrates fall through to bootstrap. Pass an explicit
    `True`/`False` to override (e.g. sweep/calibration runs exercising
    the bootstrap path on a substrate whose prior IS available — the
    prior'd run provides ground truth).

    `bootstrap_seed_range=None` (default): per-substrate dispatch from
    `_BOOTSTRAP_SEED_RANGE_DISPATCH` (padded ~25% beyond each known
    substrate's prior envelope). Unknown substrates fall back to
    DEFAULT_BOOTSTRAP_SEED_RANGE = (-2.0, 2.0). Pass an explicit tuple
    to override.

    max_passes=0 (default): pure prior, no scoring, no observation read.
    max_passes>0: per cell, score against (C, chi) and hill-climb on chit
    within two guards — the regime band (no crossings out of the seed's
    vertex_regime) and the predictor bracket (no further than delta_predict
    from the line extended through the camera node from trailing history).

    The bracket half-width is **adaptive**, computed per cell from the
    predictor's own slope magnitude: delta_predict = max(min_delta,
    k_step * expected_step). Wide where the trajectory migrates aggressively
    (QEC steps ~0.6 chit/cell -> bracket ~0.9), tight where it moves in
    small increments (glass steps ~0.1/cell -> bracket ~0.15). Cells with no
    trajectory history yet (i < 2) fall back to bracket = min_delta around
    the seed — narrow enough to exclude gfdr-attractor boundaries.

    Predictor history source — by mode:
      bootstrap=False: prior-chit history. The "line extending through the
        camera node" is the prior trajectory's inertia, decoupled from
        refinement's local settling. If the score is biased (e.g.
        gfdr-attractor pull), the bracket cannot wander because the slope
        is anchored to the prior's shape, not the refinement's drift.
      bootstrap=True: refined-chit history. No prior trajectory exists, so
        the predictor reads the realized refined chits as the trajectory.
        Acknowledged-different from prior'd mode; the bracket can wander if
        early-cell refinement misfires. This is the mode whose diagnostic
        signals the sweep characterization is built to inspect.

    Cells are sorted internally by the substrate's natural trajectory order
    (T ascending for glass, p_base ascending for quantum, scenario index for
    brain). The returned TranslationField rules are in that order.

    Every cell's TranslationRule.canonical.extras carries a `fit_diagnostics`
    dict — see mpa_lens_solver.diagnostics.FitDiagnostics for the shape.
    """
    from mpa_scale_solver.gfdr_model import vertex_regime  # noqa: PLC0415

    bootstrap = _resolve_bootstrap(substrate, bootstrap)
    bootstrap_seed_range = _resolve_bootstrap_seed_range(substrate, bootstrap_seed_range)

    sorted_cells = sorted(cells, key=lambda c: _natural_sort_key(substrate, c))

    source = "lens_solver_bootstrap" if bootstrap else "lens_solver_prior"

    rules: list[TranslationRule] = []
    # In prior'd mode this is the cdv1 prior trajectory (decoupled from
    # refinement). In bootstrap mode it's the realized refined-chit history
    # (no prior to decouple from).
    seed_history: list[float] = []

    for i, cell in enumerate(sorted_cells):
        op_dict = cell["operating_point"]

        if bootstrap:
            cell_rng = np.random.default_rng(rng_seed + i)
            lo, hi = bootstrap_seed_range
            initial_chit = float(cell_rng.uniform(lo, hi))
        else:
            initial_chit = cdv1_prior_chit(substrate, op_dict)

        if max_passes > 0:
            empirical, tau_env = empirical_rows_from_cell(cell)
            prediction = predict_next_chit(seed_history, trail_window=trail_window)
            if prediction is not None:
                predicted_chit = prediction[0]
                expected_step = prediction[1]
                bracket_center = predicted_chit
                delta_predict = max(min_delta, k_step * expected_step)
            else:
                predicted_chit = None
                expected_step = None
                bracket_center = initial_chit
                delta_predict = min_delta

            final_chit, residual, passes_used, refine_history = refine_chit(
                initial_chit=initial_chit,
                empirical_rows=empirical,
                max_passes=max_passes,
                tolerance=tolerance,
                n_candidates=n_candidates,
                rng_seed=rng_seed + i,
                guard_regime=guard_regime,
                predicted_chit=bracket_center,
                delta_predict=delta_predict,
                return_history=True,
            )
            method = "bootstrap_refined_v0" if bootstrap else "cdv1_refined_v0"
            diagnostics = build_diagnostics(
                final_chit=final_chit,
                final_residual=residual,
                refine_history=refine_history,
                source=source,
            )
            extras = {
                "prior_chit": initial_chit,
                "prior_regime": vertex_regime(initial_chit),
                "predicted_chit": predicted_chit,
                "bracket_center": bracket_center,
                "predictor_expected_step": expected_step,
                "delta_predict": delta_predict,
                "residual": residual,
                "passes_used": passes_used,
                "tau_env": tau_env,
                "guard_regime": guard_regime,
                "fit_diagnostics": diagnostics.to_dict(),
            }
        else:
            final_chit = initial_chit
            method = "bootstrap_seed_v0" if bootstrap else "cdv1_prior_v0"
            diagnostics = FitDiagnostics(
                residual_final=None,
                regime_confidence=None,
                predictor_gap=None,
                source=source,
                n_passes=0,
            )
            extras = {"fit_diagnostics": diagnostics.to_dict()}

        seed_history.append(final_chit if bootstrap else initial_chit)

        rules.append(TranslationRule(
            operating_point=_operating_point_from_cell(substrate, cell),
            xdot_choice=xdot_kind,
            canonical=CanonicalPoint(
                chit=final_chit,
                gamma_AB=DEFAULT_GAMMA_AB,
                k_frust=DEFAULT_K_FRUST,
                method=method,
                extras=extras,
            ),
        ))

    mode_descr = (
        f"bootstrap (cdv1 prior masked; seed range {bootstrap_seed_range})"
        if bootstrap else "cdv1-prior seeded"
    )
    if max_passes > 0:
        description = (
            f"{mode_descr} + observation-refined canonical states for {substrate}. "
            f"max_passes={max_passes}, tolerance={tolerance}, n_candidates={n_candidates}, "
            f"guard_regime={guard_regime}, "
            f"adaptive delta_predict (min={min_delta}, k_step={k_step}), "
            f"trail_window={trail_window}."
        )
    else:
        description = (
            f"{mode_descr} canonical states per operating point for {substrate}. "
            f"v0: no fitting; pure seed application."
        )

    return TranslationField(
        direction="forward",
        shape="lookup_table",
        rule=rules,
        description=description,
    )
