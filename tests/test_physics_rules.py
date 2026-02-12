from __future__ import annotations

import numpy as np

from fluent_agent.constants import CONSERVATIVE_URF, DEFAULT_URF
from fluent_agent.physics_rules import (
    recommend_discretization_strategy,
    recommend_domain_sizing,
    recommend_turbulence_model,
    recommend_urf,
    recommend_y_plus_target,
    validate_y_plus_results,
)


def test_recommend_turbulence_model_external_high_re() -> None:
    model = recommend_turbulence_model(re=3.0e6, mach=0.2, application="external")
    assert model == "k-omega-sst"


def test_recommend_turbulence_model_low_re() -> None:
    model = recommend_turbulence_model(re=1.0e5, mach=0.1, application="external")
    assert model == "transition-sst"


def test_recommend_turbulence_model_very_high_re() -> None:
    model = recommend_turbulence_model(re=2.0e7, mach=0.15, application="attached")
    assert model == "spalart-allmaras"


def test_recommend_turbulence_model_internal() -> None:
    model = recommend_turbulence_model(re=1.0e6, mach=0.05, application="internal")
    assert model == "k-epsilon-realizable"


def test_recommend_y_plus_target_sst() -> None:
    y_plus = recommend_y_plus_target("k-omega-sst")
    assert y_plus == 1.0


def test_recommend_y_plus_target_ke() -> None:
    y_plus = recommend_y_plus_target("k-epsilon-realizable")
    assert y_plus == 30.0


def test_recommend_domain_sizing_airfoil() -> None:
    sizing = recommend_domain_sizing("airfoil")
    assert sizing["upstream"] == 15.0
    assert sizing["downstream"] == 25.0
    assert sizing["lateral"] == 15.0


def test_recommend_urf_normal() -> None:
    urf = recommend_urf("k-omega-sst", is_retry=False)
    assert urf == DEFAULT_URF


def test_recommend_urf_retry() -> None:
    urf = recommend_urf("k-omega-sst", is_retry=True)
    assert urf == CONSERVATIVE_URF


def test_validate_y_plus_good() -> None:
    measured = np.array([0.9, 1.0, 1.1, 1.2])
    result = validate_y_plus_results(measured, model="k-omega-sst")
    assert result["valid"] is True
    assert result["warnings"] == []


def test_validate_y_plus_bad() -> None:
    measured = np.array([10.0, 10.5, 9.8, 11.0])
    result = validate_y_plus_results(measured, model="k-omega-sst")
    assert result["valid"] is False
    assert len(result["warnings"]) > 0


def test_recommend_discretization_strategy_first_run() -> None:
    strategy = recommend_discretization_strategy(is_first_run=True)
    assert strategy["pressure"] == "second-order"
    assert strategy["momentum"] == "second-order-upwind"


def test_recommend_discretization_strategy_retry() -> None:
    strategy = recommend_discretization_strategy(is_first_run=False)
    assert strategy["pressure"] == "standard"
    assert strategy["momentum"] == "first-order-upwind"
