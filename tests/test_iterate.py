"""Tests for the multi-pass iterator: empirical extraction + refine_chit."""
from __future__ import annotations

import math

import pytest

from mpa_lens_solver import (
    empirical_rows_from_cell,
    fit_translation_field,
    predict_next_chit,
    refine_chit,
)
from mpa_scale_solver.gfdr_model import generate_locus, vertex_regime


# --- empirical_rows_from_cell --------------------------------------------

def _cell_with_samples(samples: list[dict], tau_env: float | None = None) -> dict:
    op = {
        "operating_point": {
            "label": "test", "scenario": None, "h_field": None,
            "T": 0.5, "p_base": None, "delta_p": None, "gt": "c",
        },
        "results": {"all_samples": samples},
    }
    if tau_env is not None:
        op["tau_env_analytic"] = {"value": tau_env}
    return op


def test_empirical_rows_normalizes_by_tau_env():
    cell = _cell_with_samples(
        [{"t": 2.0, "C_mean": 0.9, "chi_mean": 0.1},
         {"t": 4.0, "C_mean": 0.8, "chi_mean": 0.2}],
        tau_env=2.0,
    )
    rows, tau_env = empirical_rows_from_cell(cell)
    assert tau_env == 2.0
    assert rows[0]["tau"] == pytest.approx(1.0)
    assert rows[1]["tau"] == pytest.approx(2.0)
    assert rows[0]["C"] == 0.9
    assert rows[1]["chi"] == 0.2


def test_empirical_rows_fallback_to_median_tau():
    cell = _cell_with_samples(
        [{"t": 1.0, "C_mean": 0.9, "chi_mean": 0.1},
         {"t": 3.0, "C_mean": 0.8, "chi_mean": 0.2},
         {"t": 5.0, "C_mean": 0.7, "chi_mean": 0.3}],
    )
    rows, tau_env = empirical_rows_from_cell(cell)
    assert tau_env == 3.0
    assert rows[1]["tau"] == pytest.approx(1.0)


def test_empirical_rows_skips_incomplete_rows():
    cell = _cell_with_samples(
        [{"t": 1.0, "C_mean": 0.9, "chi_mean": 0.1},
         {"t": 2.0, "C_mean": None, "chi_mean": 0.2},
         {"t": 3.0, "C_mean": 0.8, "chi_mean": 0.3}],
        tau_env=1.0,
    )
    rows, _ = empirical_rows_from_cell(cell)
    assert len(rows) == 2
    assert rows[0]["tau"] == 1.0
    assert rows[1]["tau"] == 3.0


# --- refine_chit ---------------------------------------------------------

def _synthetic_rows(chit_true: float) -> list[dict]:
    """Generate empirical rows from the analytical locus at chit_true."""
    locus = generate_locus(chit_true, vertex_regime(chit_true))
    return [{"tau": p["tau"], "C": p["C"], "chi": p["chi"]} for p in locus]


def test_refine_chit_zero_passes_when_already_at_truth():
    rows = _synthetic_rows(0.5)
    final, residual, passes = refine_chit(
        initial_chit=0.5, empirical_rows=rows,
        max_passes=100, tolerance=1e-6,
    )
    assert passes == 0
    assert final == 0.5
    assert residual < 1e-12


def test_refine_chit_converges_from_wrong_in_band_seed():
    """Truth and seed both c_near_s; refinement should find truth within regime."""
    chit_true = 0.5
    rows = _synthetic_rows(chit_true)
    final, residual, passes = refine_chit(
        initial_chit=0.3,  # wrong, but same regime as truth
        empirical_rows=rows,
        max_passes=200, tolerance=1e-4, n_candidates=64,
    )
    assert passes > 0
    assert residual < 1e-3
    assert abs(final - chit_true) < 0.1


def test_refine_chit_no_passes_when_max_passes_zero():
    rows = _synthetic_rows(0.5)
    final, residual, passes = refine_chit(
        initial_chit=-1.0, empirical_rows=rows,
        max_passes=0, tolerance=1e-6,
    )
    assert passes == 0
    assert final == -1.0
    assert residual > 0.0


def test_refine_chit_handles_empty_rows():
    final, residual, passes = refine_chit(
        initial_chit=0.3, empirical_rows=[],
        max_passes=50, tolerance=1e-3,
    )
    assert passes == 0
    assert final == 0.3
    assert math.isnan(residual)


def test_refine_chit_deterministic_given_seed():
    rows = _synthetic_rows(0.5)
    a = refine_chit(initial_chit=-1.0, empirical_rows=rows,
                    max_passes=50, tolerance=1e-6, rng_seed=42)
    b = refine_chit(initial_chit=-1.0, empirical_rows=rows,
                    max_passes=50, tolerance=1e-6, rng_seed=42)
    assert a == b


# --- fit_translation_field integration ----------------------------------

def _glass_cell_with_locus(T: float, chit_synth: float | None = None) -> dict:
    """Glass cell whose embedded locus is synthesized at chit_synth (or at Tc-T if None)."""
    if chit_synth is None:
        chit_synth = 1.1 - T
    locus = generate_locus(chit_synth, vertex_regime(chit_synth))
    samples = [{"t": p["tau"], "C_mean": p["C"], "chi_mean": p["chi"]} for p in locus]
    return {
        "operating_point": {
            "label": f"T={T}", "scenario": None, "h_field": None,
            "T": T, "p_base": None, "delta_p": None, "gt": "c",
        },
        "results": {"all_samples": samples},
        "tau_env_analytic": {"value": 1.0},
    }


def test_fit_translation_field_max_passes_zero_unchanged():
    """max_passes=0 path returns identical chit values to the v0 stamp."""
    cells = [_glass_cell_with_locus(0.2), _glass_cell_with_locus(0.5)]
    a = fit_translation_field("glass", cells, "spin-flip")
    b = fit_translation_field("glass", cells, "spin-flip", max_passes=0)
    for ra, rb in zip(a.rule, b.rule):
        assert ra.canonical.chit == rb.canonical.chit
        assert ra.canonical.method == "cdv1_prior_v0"
        assert rb.canonical.method == "cdv1_prior_v0"


def test_fit_translation_field_refine_perfect_prior_zero_passes():
    """When the embedded locus matches the prior, refinement uses zero passes per cell."""
    cells = [_glass_cell_with_locus(0.2), _glass_cell_with_locus(0.5)]
    field = fit_translation_field(
        "glass", cells, "spin-flip",
        max_passes=20, tolerance=1e-3,
    )
    for r in field.rule:
        assert r.canonical.method == "cdv1_refined_v0"
        assert r.canonical.extras["passes_used"] == 0
        assert r.canonical.extras["residual"] < 1e-3


def test_fit_translation_field_refine_stays_in_bracket():
    """Single-cell, no history: bracket = min_delta around prior. Refinement
    cannot leave the bracket regardless of where truth sits or what the score
    function attracts toward."""
    # Synth at chit=0.3 (well outside the bracket [0.55, 0.65]); the predicted
    # bracket forbids the refinement from reaching it.
    cell = _glass_cell_with_locus(0.5, chit_synth=0.3)
    field = fit_translation_field(
        "glass", [cell], "spin-flip",
        max_passes=50, tolerance=1e-10, n_candidates=64,
        min_delta=0.05, k_step=1.5,
    )
    rule = field.rule[0]
    # Bracket is [0.55, 0.65]; chit must end there even though score wants 0.3.
    assert 0.55 <= rule.canonical.chit <= 0.65


def test_fit_translation_field_guard_blocks_cross_regime_pull():
    """Cross-regime: prior c_near_s, truth s_critical. Guard keeps chit in c_near_s."""
    cell = _glass_cell_with_locus(0.5, chit_synth=0.1)  # truth is s_critical
    field = fit_translation_field(
        "glass", [cell], "spin-flip",
        max_passes=50, tolerance=1e-4, n_candidates=64,
    )
    rule = field.rule[0]
    assert rule.canonical.extras["prior_regime"] == "c_near_s"
    # Refined chit stays in c_near_s (chit >= 0.2).
    assert rule.canonical.chit >= 0.2


def test_fit_translation_field_description_reflects_mode():
    cells = [_glass_cell_with_locus(0.2)]
    prior = fit_translation_field("glass", cells, "spin-flip")
    refined = fit_translation_field("glass", cells, "spin-flip", max_passes=5)
    assert "no fitting" in prior.description
    assert "refined" in refined.description


# --- regime-band guard --------------------------------------------------

def test_refine_chit_guard_keeps_candidate_in_seed_regime():
    """Locus embedded at chit=0.1 (s_critical); seed at chit=0.9 (deep_c).
    With guard, refinement stays in deep_c (chit >= 0.7)."""
    rows = _synthetic_rows(0.1)
    final, _, _ = refine_chit(
        initial_chit=0.9, empirical_rows=rows,
        max_passes=200, tolerance=1e-6,
        n_candidates=64, rng_seed=0, guard_regime=True,
    )
    assert final >= 0.7  # stayed in deep_c


def test_refine_chit_no_guard_allows_regime_flip():
    """Same setup, guard off — refinement crosses the regime boundary."""
    rows = _synthetic_rows(0.1)
    final, _, _ = refine_chit(
        initial_chit=0.9, empirical_rows=rows,
        max_passes=200, tolerance=1e-6,
        n_candidates=64, rng_seed=0, guard_regime=False,
    )
    assert final < 0.7  # crossed out of deep_c


def test_refine_chit_guard_allows_in_band_refinement():
    """Locus at chit=0.85 (deep_c), seed at chit=0.95 (also deep_c).
    Guard does not block; refinement pulls toward 0.85."""
    rows = _synthetic_rows(0.85)
    final, residual, _ = refine_chit(
        initial_chit=0.95, empirical_rows=rows,
        max_passes=200, tolerance=1e-6,
        n_candidates=64, rng_seed=0, guard_regime=True,
    )
    assert final >= 0.7
    assert abs(final - 0.85) < 0.1
    assert residual < 1e-3


def test_fit_translation_field_guard_default_on():
    """guard_regime defaults to True via fit_translation_field."""
    cell = _glass_cell_with_locus(0.5, chit_synth=0.85)  # in deep_c
    field = fit_translation_field(
        "glass", [cell], "spin-flip",
        max_passes=50, tolerance=1e-4,
    )
    extras = field.rule[0].canonical.extras
    assert extras["guard_regime"] is True
    assert extras["prior_regime"] == "c_near_s"  # T=0.5 → prior chit=0.6 → c_near_s


def test_fit_translation_field_guard_can_be_disabled():
    cell = _glass_cell_with_locus(0.5)
    field = fit_translation_field(
        "glass", [cell], "spin-flip",
        max_passes=5, guard_regime=False,
    )
    assert field.rule[0].canonical.extras["guard_regime"] is False


# --- predict_next_chit ---------------------------------------------------

def test_predict_next_chit_none_when_history_too_short():
    assert predict_next_chit([]) is None
    assert predict_next_chit([0.5]) is None


def test_predict_next_chit_two_point_extrapolation():
    # Trail [0.9, 0.8] → slope -0.1/step → predicted 0.7.
    pred, step = predict_next_chit([0.9, 0.8])
    assert pred == pytest.approx(0.7)
    assert step == pytest.approx(0.1)


def test_predict_next_chit_three_point_linear():
    # Linear trajectory [a, a+d, a+2d] → next predicted = a+3d.
    pred, step = predict_next_chit([1.0, 0.8, 0.6])
    assert pred == pytest.approx(0.4)
    assert step == pytest.approx(0.2)


def test_predict_next_chit_uses_trail_window():
    # Long history; only last `trail_window` points considered.
    history = [10.0, 5.0, 1.0, 0.8, 0.6]
    pred, step = predict_next_chit(history, trail_window=3)
    # Last 3: [1.0, 0.8, 0.6] → slope -0.2 → predicted 0.4.
    assert pred == pytest.approx(0.4)
    assert step == pytest.approx(0.2)


# --- predicted-bracket guard in refine_chit ------------------------------

def test_refine_chit_predicted_bracket_filters_candidates():
    """Locus embedded at chit=0.85 (deep_c); seed at chit=0.9 (deep_c too).
    Predicted=0.95 with delta=0.05 → bracket [0.9, 1.0] — excludes truth 0.85.
    Refinement should NOT find truth (filtered out)."""
    rows = _synthetic_rows(0.85)
    final, _, _ = refine_chit(
        initial_chit=0.95, empirical_rows=rows,
        max_passes=100, tolerance=1e-6,
        n_candidates=64, rng_seed=0,
        guard_regime=False,  # isolate the predicted-bracket effect
        predicted_chit=0.95, delta_predict=0.05,
    )
    # Final must be inside the bracket; cannot reach 0.85.
    assert 0.90 <= final <= 1.00


def test_refine_chit_predicted_bracket_allows_truth_inside():
    """Same locus, but predicted=0.85 with delta=0.1 → bracket [0.75, 0.95]
    includes the truth. Refinement converges."""
    rows = _synthetic_rows(0.85)
    final, residual, _ = refine_chit(
        initial_chit=0.92, empirical_rows=rows,
        max_passes=200, tolerance=1e-6,
        n_candidates=64, rng_seed=0,
        guard_regime=False,
        predicted_chit=0.85, delta_predict=0.1,
    )
    assert abs(final - 0.85) < 0.05
    assert residual < 1e-3


# --- fit_translation_field with predictor + sort ------------------------

def test_fit_translation_field_sorts_glass_cells_internally():
    """Cells passed in reverse T order; field returned in natural T-ascending order."""
    cells = [_glass_cell_with_locus(1.8), _glass_cell_with_locus(0.5),
             _glass_cell_with_locus(0.2)]
    field = fit_translation_field("glass", cells, "spin-flip")
    labels = [r.operating_point.label for r in field.rule]
    assert labels == ["T=0.2", "T=0.5", "T=1.8"]


def test_fit_translation_field_first_two_cells_use_prior_as_bracket_center():
    """Predictor needs >=2 history points; first two cells fall back to prior anchor."""
    cells = [_glass_cell_with_locus(0.2), _glass_cell_with_locus(0.3),
             _glass_cell_with_locus(0.5)]
    field = fit_translation_field("glass", cells, "spin-flip", max_passes=5)
    # predicted_chit is from history only; None for first two.
    assert field.rule[0].canonical.extras["predicted_chit"] is None
    assert field.rule[1].canonical.extras["predicted_chit"] is None
    assert field.rule[2].canonical.extras["predicted_chit"] is not None
    # bracket_center is what was actually used; falls back to prior for first two.
    assert field.rule[0].canonical.extras["bracket_center"] == pytest.approx(0.9)
    assert field.rule[1].canonical.extras["bracket_center"] == pytest.approx(0.8)
    assert field.rule[2].canonical.extras["bracket_center"] == pytest.approx(0.7)


def test_fit_translation_field_adaptive_delta_floors_first_cells():
    """First two cells (no history) get bracket = min_delta around the prior."""
    cells = [_glass_cell_with_locus(0.2), _glass_cell_with_locus(0.3),
             _glass_cell_with_locus(0.5)]
    field = fit_translation_field(
        "glass", cells, "spin-flip", max_passes=5,
        min_delta=0.05, k_step=1.5,
    )
    assert field.rule[0].canonical.extras["delta_predict"] == pytest.approx(0.05)
    assert field.rule[1].canonical.extras["delta_predict"] == pytest.approx(0.05)


def test_fit_translation_field_adaptive_delta_scales_with_step():
    """Cell with predictor active: delta = max(min_delta, k_step * |expected_step|).
    Glass priors step by 0.1/cell → delta = max(0.05, 1.5*0.1) = 0.15."""
    cells = [_glass_cell_with_locus(0.2), _glass_cell_with_locus(0.3),
             _glass_cell_with_locus(0.5)]
    field = fit_translation_field(
        "glass", cells, "spin-flip", max_passes=5,
        min_delta=0.05, k_step=1.5,
    )
    # Cell 2: history [0.9, 0.8] → step 0.1 → delta 0.15.
    assert field.rule[2].canonical.extras["delta_predict"] == pytest.approx(0.15)


def test_fit_translation_field_adaptive_delta_floors_when_step_small():
    """If k_step * expected_step < min_delta, the floor wins."""
    cells = [_glass_cell_with_locus(0.2), _glass_cell_with_locus(0.21),
             _glass_cell_with_locus(0.22)]
    # Priors: 0.9, 0.89, 0.88 → steps 0.01/cell, k_step*step = 0.015 < min_delta 0.05.
    field = fit_translation_field(
        "glass", cells, "spin-flip", max_passes=5,
        min_delta=0.05, k_step=1.5,
    )
    assert field.rule[2].canonical.extras["delta_predict"] == pytest.approx(0.05)


def test_predictor_decouples_from_refinement_drift():
    """The predictor reads prior history, not refined history. Force a refinement
    that drifts away from the prior; the next cell's predicted_chit must still
    reflect the prior trajectory's inertia, not the drift."""
    # Three glass cells with priors that step by 0.1 each: 0.9, 0.8, 0.6.
    # Cell 1's locus is synthesized at chit=0.55 — well below its prior 0.8 —
    # but inside cell 1's bracket [0.75, 0.85] the refinement gets clipped to
    # 0.75. If the predictor used refined history, cell 2's slope would read
    # (0.75 - 0.9)/1 = -0.15. With prior history it reads (0.8 - 0.9)/1 = -0.10.
    cells = [
        _glass_cell_with_locus(0.2),                      # prior 0.9
        _glass_cell_with_locus(0.3, chit_synth=0.55),     # prior 0.8, locus pull-down
        _glass_cell_with_locus(0.5),                      # prior 0.6
    ]
    field = fit_translation_field(
        "glass", cells, "spin-flip",
        max_passes=200, tolerance=1e-10, n_candidates=64,
        min_delta=0.05, k_step=1.5,
    )
    # Cell 2's predictor reads prior history [0.9, 0.8]; slope = -0.1.
    assert field.rule[2].canonical.extras["predictor_expected_step"] == pytest.approx(0.1)
    # And the predicted chit is 0.7 (= 0.8 + slope), independent of cell 1's drift.
    assert field.rule[2].canonical.extras["predicted_chit"] == pytest.approx(0.7)


def test_fit_translation_field_predictor_extends_history():
    """Glass priors: chit = 1.1 - T. With history [0.9, 0.8] → predicted 0.7 for
    cell 2. Refinement (with perfect prior locus) leaves chit at 0.6 (the prior),
    so predicted_chit for cell 2 reflects the line extrapolation, not the refined value."""
    cells = [_glass_cell_with_locus(0.2), _glass_cell_with_locus(0.3),
             _glass_cell_with_locus(0.5)]
    field = fit_translation_field("glass", cells, "spin-flip",
                                  max_passes=10, tolerance=1e-3)
    # Cell 2 sees history [refined_cell_0, refined_cell_1] = [0.9, 0.8] (perfect prior).
    # Predictor: slope = -0.1 → predicted = 0.7.
    assert field.rule[2].canonical.extras["predicted_chit"] == pytest.approx(0.7)


def test_fit_translation_field_predictor_records_expected_step():
    cells = [_glass_cell_with_locus(0.2), _glass_cell_with_locus(0.3),
             _glass_cell_with_locus(0.5)]
    field = fit_translation_field("glass", cells, "spin-flip", max_passes=5)
    assert field.rule[2].canonical.extras["predictor_expected_step"] == pytest.approx(0.1)
