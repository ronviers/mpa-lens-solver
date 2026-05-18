"""Unit tests for the v0 cdv1-prior translation fields."""
from __future__ import annotations

import math

import pytest

from mpa_lens_solver import (
    BRAIN_SCENARIO_CHIT,
    GLASS_TC,
    QEC_P_THRESHOLD,
    brain_prior,
    cdv1_prior_chit,
    fit_translation_field,
    glass_prior,
    quantum_prior,
)
from mpa_scale_solver.types import (
    CanonicalPoint,
    OperatingPoint,
    TranslationField,
    TranslationRule,
)


# --- per-substrate priors -------------------------------------------------

def test_glass_prior_deep_c():
    assert glass_prior({"T": 0.2}) == pytest.approx(GLASS_TC - 0.2)


def test_glass_prior_at_critical():
    assert glass_prior({"T": GLASS_TC}) == pytest.approx(0.0)


def test_glass_prior_deep_r():
    assert glass_prior({"T": 1.8}) == pytest.approx(GLASS_TC - 1.8)


def test_glass_prior_missing_T_raises():
    with pytest.raises(ValueError, match="requires T"):
        glass_prior({"T": None})


def test_quantum_prior_deep_c():
    assert quantum_prior({"p_base": 1e-4}) == pytest.approx(math.log(QEC_P_THRESHOLD / 1e-4))


def test_quantum_prior_at_threshold():
    assert quantum_prior({"p_base": QEC_P_THRESHOLD}) == pytest.approx(0.0)


def test_quantum_prior_deep_r():
    assert quantum_prior({"p_base": 5e-2}) == pytest.approx(math.log(QEC_P_THRESHOLD / 5e-2))


def test_quantum_prior_missing_p_base_raises():
    with pytest.raises(ValueError, match="positive p_base"):
        quantum_prior({"p_base": None})


def test_quantum_prior_zero_p_base_raises():
    with pytest.raises(ValueError, match="positive p_base"):
        quantum_prior({"p_base": 0.0})


def test_brain_prior_table():
    for scenario, expected in BRAIN_SCENARIO_CHIT.items():
        assert brain_prior({"scenario": scenario}) == expected


def test_brain_prior_unknown_scenario_raises():
    with pytest.raises(ValueError, match="requires scenario"):
        brain_prior({"scenario": "fugue"})


# --- dispatch -------------------------------------------------------------

def test_cdv1_prior_chit_dispatch():
    assert cdv1_prior_chit("glass",   {"T": 0.5})       == pytest.approx(GLASS_TC - 0.5)
    assert cdv1_prior_chit("quantum", {"p_base": 1e-3}) == pytest.approx(math.log(10.0))
    assert cdv1_prior_chit("brain",   {"scenario": "conflict"}) == 0.0


def test_cdv1_prior_chit_unknown_substrate_raises():
    with pytest.raises(ValueError, match="unknown substrate"):
        cdv1_prior_chit("mountain", {"elevation": 1234})


# --- fit_translation_field ------------------------------------------------

def _glass_cell(T: float, h_field: float = 0.1, gt: str = "c") -> dict:
    return {
        "operating_point": {
            "label": f"T={T:.3f}", "scenario": None, "h_field": h_field,
            "T": T, "p_base": None, "delta_p": None, "gt": gt,
        },
    }


def _quantum_cell(p_base: float, delta_p: float = 1e-3, gt: str = "c") -> dict:
    return {
        "operating_point": {
            "label": f"p_base={p_base}", "scenario": None, "h_field": None,
            "T": None, "p_base": p_base, "delta_p": delta_p, "gt": gt,
        },
    }


def _brain_cell(scenario: str, gt: str = "c") -> dict:
    return {
        "operating_point": {
            "label": scenario, "scenario": scenario, "h_field": None,
            "T": None, "p_base": None, "delta_p": None, "gt": gt,
        },
    }


def test_fit_translation_field_glass_shape():
    cells = [_glass_cell(0.2), _glass_cell(1.1, gt="s"), _glass_cell(1.8, gt="r")]
    field = fit_translation_field("glass", cells, "spin-flip")
    assert isinstance(field, TranslationField)
    assert field.direction == "forward"
    assert field.shape == "lookup_table"
    assert len(field.rule) == 3
    for r in field.rule:
        assert isinstance(r, TranslationRule)
        assert isinstance(r.operating_point, OperatingPoint)
        assert isinstance(r.canonical, CanonicalPoint)
        assert r.xdot_choice == "spin-flip"
        assert r.canonical.method == "cdv1_prior_v0"


def test_fit_translation_field_glass_canonical_values():
    cells = [_glass_cell(0.2), _glass_cell(1.1, gt="s"), _glass_cell(1.8, gt="r")]
    field = fit_translation_field("glass", cells, "spin-flip")
    chits = [r.canonical.chit for r in field.rule]
    assert chits[0] == pytest.approx(0.9)
    assert chits[1] == pytest.approx(0.0)
    assert chits[2] == pytest.approx(GLASS_TC - 1.8)


def test_fit_translation_field_quantum_canonical_values():
    cells = [_quantum_cell(1e-4), _quantum_cell(1e-2, gt="s"), _quantum_cell(5e-2, gt="r")]
    field = fit_translation_field("quantum", cells, "detection-event")
    chits = [r.canonical.chit for r in field.rule]
    assert chits[0] == pytest.approx(math.log(100.0))
    assert chits[1] == pytest.approx(0.0)
    assert chits[2] == pytest.approx(math.log(QEC_P_THRESHOLD / 5e-2))


def test_fit_translation_field_brain_canonical_values():
    cells = [_brain_cell(s) for s in ("committed", "suspended", "conflict", "reset")]
    field = fit_translation_field("brain", cells, "velocity")
    chits = [r.canonical.chit for r in field.rule]
    assert chits == [+0.6, +0.1, 0.0, -0.5]


def test_fit_translation_field_axes_extraction():
    cells = [_glass_cell(0.5, h_field=0.2)]
    field = fit_translation_field("glass", cells, "spin-flip")
    axes = field.rule[0].operating_point.axes
    assert axes == {"T": 0.5, "h_field": 0.2}

    cells = [_quantum_cell(1e-3, delta_p=2e-3)]
    field = fit_translation_field("quantum", cells, "detection-event")
    axes = field.rule[0].operating_point.axes
    assert axes == {"p_base": 1e-3, "delta_p": 2e-3}

    cells = [_brain_cell("committed")]
    field = fit_translation_field("brain", cells, "velocity")
    axes = field.rule[0].operating_point.axes
    assert axes == {"scenario": "committed"}


def test_fit_translation_field_defaults():
    cells = [_glass_cell(0.5)]
    field = fit_translation_field("glass", cells, "spin-flip")
    cp = field.rule[0].canonical
    assert cp.gamma_AB == -0.3
    assert cp.k_frust is False


def test_fit_translation_field_empty_cells():
    field = fit_translation_field("glass", [], "spin-flip")
    assert field.rule == []
    assert field.shape == "lookup_table"


def test_fit_translation_field_deterministic():
    cells = [_quantum_cell(1e-4), _quantum_cell(1e-3), _quantum_cell(1e-2, gt="s")]
    a = fit_translation_field("quantum", cells, "detection-event")
    b = fit_translation_field("quantum", cells, "detection-event")
    for ra, rb in zip(a.rule, b.rule):
        assert ra.canonical.chit == rb.canonical.chit
        assert ra.canonical.gamma_AB == rb.canonical.gamma_AB
        assert ra.operating_point.label == rb.operating_point.label
