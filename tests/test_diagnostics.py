"""Tests for the diagnostic vector (v2) + bootstrap mode of fit_translation_field."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from mpa_lens_solver import (
    FitDiagnostics,
    RefineHistory,
    build_diagnostics,
    fit_translation_field,
    refine_chit,
)


# --- FitDiagnostics shape -------------------------------------------------

def test_fit_diagnostics_is_frozen():
    d = FitDiagnostics(
        residual_final=0.05, regime_confidence=0.8, predictor_gap=0.1,
        source="lens_solver_prior", n_passes=3,
    )
    with pytest.raises(FrozenInstanceError):
        d.residual_final = 0.9  # type: ignore[misc]


def test_fit_diagnostics_to_dict_round_trips_fields():
    d = FitDiagnostics(
        residual_final=0.05, regime_confidence=None, predictor_gap=0.2,
        source="lens_solver_bootstrap", n_passes=7,
    )
    out = d.to_dict()
    assert out == {
        "residual_final": 0.05,
        "regime_confidence": None,
        "predictor_gap": 0.2,
        "source": "lens_solver_bootstrap",
        "n_passes": 7,
    }


# --- build_diagnostics ----------------------------------------------------

def _history(
    *, passes_used: int = 3, off_regime=(0.0, 0.1, 0.2), tolerance: float = 0.01,
    predicted_chit=0.5, delta_predict: float = 0.2,
    n_cand=(32, 32, 32), n_valid=(30, 28, 25), best=(0.5, 0.55, 0.6),
    seed_regime: str = "c_near_s",
) -> RefineHistory:
    return RefineHistory(
        per_pass_off_regime_fraction=tuple(off_regime),
        per_pass_n_candidates=tuple(n_cand),
        per_pass_n_valid=tuple(n_valid),
        per_pass_best_chit=tuple(best),
        tolerance=tolerance,
        seed_regime=seed_regime,
        predicted_chit=predicted_chit,
        delta_predict=delta_predict,
        passes_used=passes_used,
    )


def test_build_diagnostics_none_history_returns_all_none():
    d = build_diagnostics(
        final_chit=0.5, final_residual=0.001, refine_history=None,
        source="lens_solver_prior",
    )
    assert d.residual_final is None
    assert d.regime_confidence is None
    assert d.predictor_gap is None
    assert d.source == "lens_solver_prior"
    assert d.n_passes == 0


def test_build_diagnostics_zero_passes_returns_all_none():
    h = _history(passes_used=0, off_regime=(), n_cand=(), n_valid=(), best=())
    d = build_diagnostics(
        final_chit=0.5, final_residual=0.001, refine_history=h,
        source="lens_solver_prior",
    )
    assert d.residual_final is None
    assert d.regime_confidence is None
    assert d.predictor_gap is None
    assert d.n_passes == 0


def test_build_diagnostics_residual_final_is_raw_value():
    h = _history(tolerance=0.01)
    d = build_diagnostics(
        final_chit=0.6, final_residual=0.05, refine_history=h,
        source="lens_solver_prior",
    )
    assert d.residual_final == pytest.approx(0.05)


def test_build_diagnostics_regime_confidence_is_one_minus_mean_off_regime():
    # off_regime mean = (0.0 + 0.2 + 0.4) / 3 = 0.2 -> confidence = 0.8
    h = _history(off_regime=(0.0, 0.2, 0.4))
    d = build_diagnostics(
        final_chit=0.6, final_residual=0.001, refine_history=h,
        source="lens_solver_prior",
    )
    assert d.regime_confidence == pytest.approx(0.8)


def test_build_diagnostics_regime_confidence_high_when_all_candidates_agree():
    # off_regime fraction = 0 for every pass -> confidence = 1.0 (fully pinned)
    h = _history(off_regime=(0.0, 0.0, 0.0))
    d = build_diagnostics(
        final_chit=0.6, final_residual=0.001, refine_history=h,
        source="lens_solver_prior",
    )
    assert d.regime_confidence == pytest.approx(1.0)


def test_build_diagnostics_regime_confidence_skips_zero_candidate_passes():
    # First pass had 0 candidates -> excluded. Mean of (0.5, 0.4) = 0.45 -> conf = 0.55
    h = _history(off_regime=(0.0, 0.5, 0.4), n_cand=(0, 32, 32))
    d = build_diagnostics(
        final_chit=0.6, final_residual=0.001, refine_history=h,
        source="lens_solver_prior",
    )
    assert d.regime_confidence == pytest.approx(0.55)


def test_build_diagnostics_predictor_gap_is_raw_chit_distance():
    h = _history(predicted_chit=0.5, delta_predict=0.2)
    d = build_diagnostics(
        final_chit=0.6, final_residual=0.001, refine_history=h,
        source="lens_solver_prior",
    )
    # |0.6 - 0.5| = 0.1 (raw, no normalization)
    assert d.predictor_gap == pytest.approx(0.1)


def test_build_diagnostics_predictor_gap_not_clipped():
    """Raw gap can exceed delta_predict (no normalization to clip)."""
    h = _history(predicted_chit=0.5, delta_predict=0.2)
    d = build_diagnostics(
        final_chit=1.0, final_residual=0.001, refine_history=h,
        source="lens_solver_prior",
    )
    assert d.predictor_gap == pytest.approx(0.5)


def test_build_diagnostics_predictor_gap_none_when_no_predictor():
    h = _history(predicted_chit=None)
    d = build_diagnostics(
        final_chit=0.6, final_residual=0.001, refine_history=h,
        source="lens_solver_bootstrap",
    )
    assert d.predictor_gap is None


def test_build_diagnostics_carries_source_and_n_passes():
    h = _history(passes_used=5)
    d = build_diagnostics(
        final_chit=0.6, final_residual=0.001, refine_history=h,
        source="lens_solver_bootstrap",
    )
    assert d.source == "lens_solver_bootstrap"
    assert d.n_passes == 5


# --- refine_chit return shape --------------------------------------------

_SYNTHETIC_ROWS = [
    {"tau": 0.5, "C": 0.95, "chi": 0.05},
    {"tau": 1.0, "C": 0.80, "chi": 0.20},
    {"tau": 2.0, "C": 0.60, "chi": 0.40},
    {"tau": 4.0, "C": 0.40, "chi": 0.60},
]


def test_refine_chit_default_returns_three_tuple():
    result = refine_chit(0.5, _SYNTHETIC_ROWS, max_passes=2, rng_seed=42)
    assert len(result) == 3
    chit, residual, passes = result
    assert isinstance(chit, float)
    assert isinstance(residual, float)
    assert isinstance(passes, int)


def test_refine_chit_with_history_returns_four_tuple():
    result = refine_chit(
        0.5, _SYNTHETIC_ROWS, max_passes=2, rng_seed=42, return_history=True,
    )
    assert len(result) == 4
    chit, residual, passes, history = result
    assert isinstance(history, RefineHistory)
    assert history.passes_used == passes
    assert len(history.per_pass_off_regime_fraction) == passes
    assert len(history.per_pass_n_candidates) == passes


def test_refine_chit_empty_rows_returns_empty_history_when_requested():
    result = refine_chit(
        0.5, [], max_passes=5, return_history=True,
    )
    chit, residual, passes, history = result
    assert passes == 0
    assert history.passes_used == 0
    assert history.per_pass_n_candidates == ()


# --- fit_translation_field emits fit_diagnostics --------------------------

def _glass_cell(T: float, gt: str = "c") -> dict:
    return {
        "operating_point": {
            "label": f"T={T:.3f}", "scenario": None, "h_field": 0.1,
            "T": T, "p_base": None, "delta_p": None, "gt": gt,
        },
    }


def _glass_cell_with_samples(T: float, samples: list[dict], gt: str = "c") -> dict:
    cell = _glass_cell(T, gt=gt)
    cell["results"] = {"all_samples": samples}
    cell["tau_env_analytic"] = {"value": 1.0}
    return cell


_SAMPLES = [
    {"t": 0.5, "C_mean": 0.95, "chi_mean": 0.05},
    {"t": 1.0, "C_mean": 0.80, "chi_mean": 0.20},
    {"t": 2.0, "C_mean": 0.60, "chi_mean": 0.40},
    {"t": 4.0, "C_mean": 0.40, "chi_mean": 0.60},
]


def test_prior_mode_zero_passes_emits_diagnostics_with_source_prior():
    cells = [_glass_cell(0.2), _glass_cell(0.5), _glass_cell(1.1, gt="s")]
    field = fit_translation_field("glass", cells, "spin-flip")
    for rule in field.rule:
        diag = rule.canonical.extras["fit_diagnostics"]
        assert diag["source"] == "lens_solver_prior"
        assert diag["n_passes"] == 0
        assert diag["residual_final"] is None
        assert diag["regime_confidence"] is None
        assert diag["predictor_gap"] is None


def test_bootstrap_mode_zero_passes_emits_diagnostics_with_source_bootstrap():
    cells = [_glass_cell(0.2), _glass_cell(0.5)]
    field = fit_translation_field(
        "glass", cells, "spin-flip", bootstrap=True, rng_seed=7,
    )
    for rule in field.rule:
        diag = rule.canonical.extras["fit_diagnostics"]
        assert diag["source"] == "lens_solver_bootstrap"
        assert diag["n_passes"] == 0


def test_bootstrap_mode_produces_different_chit_than_prior_mode():
    cells = [_glass_cell(0.2), _glass_cell(0.5), _glass_cell(1.1, gt="s")]
    prior_field = fit_translation_field("glass", cells, "spin-flip", rng_seed=0)
    boot_field = fit_translation_field(
        "glass", cells, "spin-flip", bootstrap=True, rng_seed=0,
    )
    prior_chits = [r.canonical.chit for r in prior_field.rule]
    boot_chits = [r.canonical.chit for r in boot_field.rule]
    assert prior_chits != boot_chits
    for r in boot_field.rule:
        assert r.canonical.method == "bootstrap_seed_v0"


def test_bootstrap_mode_is_deterministic_for_same_seed():
    cells = [_glass_cell(0.2), _glass_cell(0.5), _glass_cell(1.1, gt="s")]
    a = fit_translation_field(
        "glass", cells, "spin-flip", bootstrap=True, rng_seed=42,
    )
    b = fit_translation_field(
        "glass", cells, "spin-flip", bootstrap=True, rng_seed=42,
    )
    a_chits = [r.canonical.chit for r in a.rule]
    b_chits = [r.canonical.chit for r in b.rule]
    assert a_chits == b_chits


def test_prior_mode_with_refinement_emits_residual_final():
    cells = [
        _glass_cell_with_samples(0.2, _SAMPLES),
        _glass_cell_with_samples(0.5, _SAMPLES),
        _glass_cell_with_samples(1.1, _SAMPLES, gt="s"),
    ]
    field = fit_translation_field(
        "glass", cells, "spin-flip", max_passes=10, rng_seed=0,
    )
    residuals = [r.canonical.extras["fit_diagnostics"]["residual_final"] for r in field.rule]
    assert any(r is not None for r in residuals)
    for r in field.rule:
        diag = r.canonical.extras["fit_diagnostics"]
        assert diag["source"] == "lens_solver_prior"
        assert isinstance(diag["n_passes"], int)


def test_bootstrap_mode_with_refinement_runs_and_emits_diagnostics():
    cells = [
        _glass_cell_with_samples(0.2, _SAMPLES),
        _glass_cell_with_samples(0.5, _SAMPLES),
        _glass_cell_with_samples(1.1, _SAMPLES, gt="s"),
    ]
    field = fit_translation_field(
        "glass", cells, "spin-flip", max_passes=10, bootstrap=True, rng_seed=0,
    )
    for r in field.rule:
        diag = r.canonical.extras["fit_diagnostics"]
        assert diag["source"] == "lens_solver_bootstrap"
        assert r.canonical.method == "bootstrap_refined_v0"


def test_diagnostics_dict_is_json_serializable():
    import json
    cells = [_glass_cell(0.2)]
    field = fit_translation_field("glass", cells, "spin-flip")
    diag = field.rule[0].canonical.extras["fit_diagnostics"]
    json.dumps(diag)
