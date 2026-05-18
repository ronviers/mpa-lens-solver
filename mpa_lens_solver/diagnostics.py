"""Diagnostic vector for the fitting paths — v2, sweep-informed.

v1 (2026-05-18) defined residual_plateau, regime_stability, predictor_agreement
with normalized [0, 1] semantics. The first calibration sweep showed:

  - residual_plateau (ratio to tolerance) was degenerately scaled for
    lens-solver: tolerance=1e-3 is aspirational and the ratio always reads
    100-1000+. Threshold > 1 fired on essentially every fit.
  - regime_stability (off-regime candidate fraction) discriminated cleanly
    but the direction was inverted: HIGH off-regime = score function
    differentiating regimes = better fit; LOW off-regime = score pinned
    to one regime = worse fit. Correlation with gt_error: -0.81 (two-stage),
    -0.53 (bootstrap).
  - predictor_agreement (ratio to delta_predict) saturated at 1.0 for most
    fits because refinement almost always pulls to the bracket edge.

v2 carries raw signals with uniform "higher = worse" semantics:

  residual_final     : raw final residual; lower is better.
                       Path-conditional natural scale.
  regime_confidence  : 1 - off_regime_fraction. High = score function is
                       confident about one regime (potentially over-pinned).
                       Low = score function explores regimes (refinement has
                       room to work).
  predictor_gap      : |final_chit - predicted_chit| in chit units. Raw
                       distance, no bracket normalization. None when
                       predictor inactive.

Threshold defaults live in the report layer, sweep-informed. No downstream
consumer should bind to specific threshold values without referencing a
sweep run that justifies them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Optional


Source = Literal[
    "two_stage_inversion",     # mpa-conform conformer.compute.inversion.invert
    "lens_solver_prior",       # mpa_lens_solver, cdv1 prior + refinement
    "lens_solver_bootstrap",   # mpa_lens_solver, no prior, random seed within gamut
]


@dataclass(frozen=True)
class FitDiagnostics:
    """Three raw-signal fit-quality fields + path provenance.

    All three follow "higher = worse" semantics:
      residual_final    higher = larger residual = worse fit
      regime_confidence higher = score pinned to one regime = worse fit
      predictor_gap     higher = refinement disagrees with predictor = worse fit

    None values are honest: the path didn't natively compute that field
    (e.g. two_stage_inversion has no predictor, so predictor_gap is None).

    source: which fitting path produced these numbers.
    n_passes: refinement passes used (1 for single-pass non-iterative paths).
    """
    residual_final: Optional[float]
    regime_confidence: Optional[float]
    predictor_gap: Optional[float]
    source: Source
    n_passes: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RefineHistory:
    """Per-pass signals from refine_chit, used to construct FitDiagnostics.

    Internal shape — exists so refine_chit can return enough information to
    compute the diagnostic without callers re-running the loop. Tuple-typed
    for value semantics.
    """
    per_pass_off_regime_fraction: tuple[float, ...]
    per_pass_n_candidates: tuple[int, ...]
    per_pass_n_valid: tuple[int, ...]
    per_pass_best_chit: tuple[float, ...]
    tolerance: float
    seed_regime: Optional[str]
    predicted_chit: Optional[float]
    delta_predict: float
    passes_used: int


def build_diagnostics(
    *,
    final_chit: float,
    final_residual: float,
    refine_history: Optional[RefineHistory],
    source: Source,
) -> FitDiagnostics:
    """Construct a FitDiagnostics from refine_chit's history and final state.

    When refine_history is None or no passes ran, all signals are None —
    honest report that there's nothing iterative to measure.
    """
    if refine_history is None or refine_history.passes_used == 0:
        return FitDiagnostics(
            residual_final=None,
            regime_confidence=None,
            predictor_gap=None,
            source=source,
            n_passes=0,
        )

    h = refine_history

    residual = (
        float(final_residual)
        if final_residual is not None and final_residual == final_residual  # not NaN
        else None
    )

    # regime_confidence = 1 - mean(off_regime_fraction). High = score pinned.
    valid_fractions = [
        f for f, n in zip(h.per_pass_off_regime_fraction, h.per_pass_n_candidates) if n > 0
    ]
    if valid_fractions:
        off_regime_mean = sum(valid_fractions) / len(valid_fractions)
        confidence: Optional[float] = float(1.0 - off_regime_mean)
    else:
        confidence = None

    # predictor_gap: raw |final - predicted| in chit units.
    if h.predicted_chit is not None:
        gap: Optional[float] = abs(float(final_chit) - float(h.predicted_chit))
    else:
        gap = None

    return FitDiagnostics(
        residual_final=residual,
        regime_confidence=confidence,
        predictor_gap=gap,
        source=source,
        n_passes=int(h.passes_used),
    )
