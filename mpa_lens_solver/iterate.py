"""Random-perturbation refinement of the canonical chit per cell.

One process: max_passes=0 returns the cdv1 prior unchanged. max_passes>0 perturbs
the prior, scores via mpa-scale-solver's gfdr forward model, accepts improvements.
Same machinery whether the prior is perfect (zero passes used) or absent (many).

gFDR locus depends on chit alone (gamma_AB is unobservable from the single-mode
locus per RFC-S Appendix B item 4), so the refinement is a 1D random search
over chit. gamma_AB stays at the lens-solver default.

Two guards stack on the random search:

1. **Regime-band guard** (guard_regime=True, default): each accepted candidate
   must land in the same 5-bucket vertex_regime as the seed chit. Prevents
   gfdr-attractor crossings that would propagate to every camera that consumes
   the TranslationField as a view-transform LUT.

2. **Predictor-corrector bracket** (predicted_chit=..., delta_predict=...):
   given a prediction from the trajectory's local tangent
   (predict_next_chit applied to refined-cells history), candidates must lie
   within +/- delta_predict of the prediction. This is the
   trajectory-shape-aware bound — narrower than fixed-delta-around-prior, and
   self-tuning because the prediction is a function of trajectory continuity,
   not a hand-picked anchor.

The two guards compose by intersection; either or both can be disabled.

refine_chit returns a 3-tuple by default. Pass return_history=True to also
receive the RefineHistory of per-pass signals — feeds the FitDiagnostics
constructor in diagnostics.build_diagnostics.
"""
from __future__ import annotations

from typing import Optional, Union

import numpy as np

from mpa_scale_solver.gfdr_model import (
    locus_residual,
    locus_residual_array,
    vertex_regime,
)

from .diagnostics import RefineHistory


def empirical_rows_from_cell(cell: dict) -> tuple[list[dict], float]:
    """Pull (tau, C, chi) rows from a library cell; tau normalized by tau_env."""
    samples = cell.get("results", {}).get("all_samples", [])
    rows: list[dict] = []
    for s in samples:
        tau = s.get("t")
        C = s.get("C_mean")
        chi = s.get("chi_mean")
        if tau is None or C is None or chi is None:
            continue
        rows.append({"tau": float(tau), "C": float(C), "chi": float(chi)})

    tau_env_block = cell.get("tau_env_analytic") or {}
    tau_env = tau_env_block.get("value")
    if not (isinstance(tau_env, (int, float)) and tau_env > 0 and np.isfinite(tau_env)):
        taus = [r["tau"] for r in rows]
        tau_env = float(np.median(taus)) if taus else 1.0

    rows_dim = [{**r, "tau": r["tau"] / float(tau_env)} for r in rows]
    return rows_dim, float(tau_env)


def predict_next_chit(
    history: list[float],
    trail_window: int = 3,
) -> Optional[tuple[float, float]]:
    """Linear extrapolation through the camera node (last refined cell).

    Returns (predicted_chit, expected_step) where expected_step is the
    magnitude of the local slope per cell-step. Returns None when history
    has fewer than 2 points (predictor inactive — caller falls back to the
    prior anchor).

    Slope is fit through the first and last of the last
    `min(trail_window, len(history))` history points. For a perfectly linear
    trajectory the prediction is exact.
    """
    n = len(history)
    if n < 2:
        return None
    window = min(trail_window, n)
    trail = history[-window:]
    slope_per_step = (trail[-1] - trail[0]) / (window - 1)
    predicted = trail[-1] + slope_per_step
    return predicted, abs(slope_per_step)


_EMPTY_HISTORY_TEMPLATE = dict(
    per_pass_off_regime_fraction=(),
    per_pass_n_candidates=(),
    per_pass_n_valid=(),
    per_pass_best_chit=(),
)


def _empty_history(
    *, tolerance: float, seed_regime: Optional[str],
    predicted_chit: Optional[float], delta_predict: float,
) -> RefineHistory:
    return RefineHistory(
        **_EMPTY_HISTORY_TEMPLATE,
        tolerance=tolerance,
        seed_regime=seed_regime,
        predicted_chit=predicted_chit,
        delta_predict=delta_predict,
        passes_used=0,
    )


def refine_chit(
    initial_chit: float,
    empirical_rows: list[dict],
    *,
    max_passes: int,
    tolerance: float = 1e-3,
    n_candidates: int = 32,
    rng_seed: int = 0,
    sigma_init: float = 0.5,
    anneal: float = 0.7,
    patience: int = 10,
    guard_regime: bool = True,
    predicted_chit: Optional[float] = None,
    delta_predict: float = 0.2,
    return_history: bool = False,
) -> Union[
    tuple[float, float, int],
    tuple[float, float, int, RefineHistory],
]:
    """Hill-climb on chit by sampling K Gaussian perturbations per pass.

    Returns (final_chit, final_residual, passes_used). When return_history
    is True, returns (final_chit, final_residual, passes_used, history) —
    the history is a RefineHistory the diagnostics builder consumes.
    passes_used == 0 means the initial chit was already within tolerance
    (or there were no rows to score against).

    When guard_regime is True (default), candidates whose vertex_regime
    differs from the seed's are rejected. When predicted_chit is given,
    candidates outside [predicted_chit - delta_predict, predicted_chit +
    delta_predict] are also rejected. The two filters compose by intersection.

    Per-pass diagnostic signals are always computed (they're cheap — one
    vertex_regime call per candidate) but only returned when requested.
    """
    current_chit = float(initial_chit)
    seed_regime_for_diag = vertex_regime(current_chit)

    if not empirical_rows:
        if return_history:
            return current_chit, float("nan"), 0, _empty_history(
                tolerance=tolerance, seed_regime=seed_regime_for_diag,
                predicted_chit=predicted_chit, delta_predict=delta_predict,
            )
        return current_chit, float("nan"), 0

    current_residual = float(locus_residual(empirical_rows, current_chit))
    if current_residual <= tolerance:
        if return_history:
            return current_chit, current_residual, 0, _empty_history(
                tolerance=tolerance, seed_regime=seed_regime_for_diag,
                predicted_chit=predicted_chit, delta_predict=delta_predict,
            )
        return current_chit, current_residual, 0

    seed_regime = vertex_regime(current_chit) if guard_regime else None
    rng = np.random.default_rng(rng_seed)
    sigma = float(sigma_init)
    no_improvement = 0
    passes_used = 0

    pp_off_regime: list[float] = []
    pp_n_cand: list[int] = []
    pp_n_valid: list[int] = []
    pp_best_chit: list[float] = []

    for _ in range(max_passes):
        passes_used += 1
        candidates = current_chit + rng.normal(0.0, sigma, size=n_candidates)
        cand_regimes = [vertex_regime(float(c)) for c in candidates]

        off_count = sum(1 for r in cand_regimes if r != seed_regime_for_diag)
        pp_off_regime.append(off_count / max(1, len(candidates)))
        pp_n_cand.append(int(len(candidates)))

        valid = np.ones(candidates.shape[0], dtype=bool)
        if guard_regime:
            valid &= np.array([r == seed_regime for r in cand_regimes], dtype=bool)
        if predicted_chit is not None:
            valid &= np.abs(candidates - float(predicted_chit)) <= float(delta_predict)

        pp_n_valid.append(int(valid.sum()))

        if not valid.any():
            no_improvement += 1
            sigma *= anneal
            pp_best_chit.append(current_chit)
            if no_improvement >= patience and sigma < 1e-4:
                break
            continue

        valid_candidates = candidates[valid]
        residuals = locus_residual_array(empirical_rows, valid_candidates)
        best_idx = int(np.argmin(residuals))
        best_res = float(residuals[best_idx])
        if best_res < current_residual:
            current_chit = float(valid_candidates[best_idx])
            current_residual = best_res
            no_improvement = 0
        else:
            no_improvement += 1
            sigma *= anneal

        pp_best_chit.append(current_chit)

        if current_residual <= tolerance:
            break
        if no_improvement >= patience and sigma < 1e-4:
            break

    if return_history:
        history = RefineHistory(
            per_pass_off_regime_fraction=tuple(pp_off_regime),
            per_pass_n_candidates=tuple(pp_n_cand),
            per_pass_n_valid=tuple(pp_n_valid),
            per_pass_best_chit=tuple(pp_best_chit),
            tolerance=tolerance,
            seed_regime=seed_regime_for_diag,
            predicted_chit=predicted_chit,
            delta_predict=delta_predict,
            passes_used=passes_used,
        )
        return current_chit, current_residual, passes_used, history
    return current_chit, current_residual, passes_used
