from __future__ import annotations

from typing import Any

import numpy as np

from fluent_agent.constants import CONSERVATIVE_URF, DEFAULT_URF, TurbulenceModel


def recommend_turbulence_model(re: float, mach: float, application: str = "external") -> str:
    """
    Recommend a turbulence model from flow conditions and application context.

    Rules implemented:
    - Internal or separated flow: k-epsilon-realizable
    - Low-Re external flow (Re < 5e5): transition-sst
    - Typical external aero range (5e5 to 1e7): k-omega-sst
    - Very high-Re attached flow (Re > 1e7): spalart-allmaras
    - Fallback: k-omega-sst
    """
    _ = mach  # Reserved for future compressibility-aware refinements.
    app = application.strip().lower()

    if app == "internal" or "separated" in app:
        return TurbulenceModel.K_EPSILON_REALIZABLE.value

    if re < 5.0e5:
        return TurbulenceModel.TRANSITION_SST.value

    if re > 1.0e7 and ("attached" in app or app in {"external", "airfoil"}):
        return TurbulenceModel.SPALART_ALLMARAS.value

    if 5.0e5 <= re <= 1.0e7 and app in {"external", "airfoil", "attached"}:
        return TurbulenceModel.K_OMEGA_SST.value

    return TurbulenceModel.K_OMEGA_SST.value


def recommend_domain_sizing(geometry_type: str = "airfoil") -> dict[str, float]:
    """Return default far-field sizing factors based on geometry category."""
    geometry = geometry_type.strip().lower()
    if geometry == "bluff_body":
        return {"upstream": 10.0, "downstream": 30.0, "lateral": 10.0}
    return {"upstream": 15.0, "downstream": 25.0, "lateral": 15.0}


def recommend_y_plus_target(turbulence_model: str) -> float:
    """Return y+ target suited to the turbulence model."""
    model = turbulence_model.strip().lower()
    if model == TurbulenceModel.K_EPSILON_REALIZABLE.value:
        return 30.0
    if model in {
        TurbulenceModel.K_OMEGA_SST.value,
        TurbulenceModel.SPALART_ALLMARAS.value,
        TurbulenceModel.TRANSITION_SST.value,
    }:
        return 1.0
    return 1.0


def validate_y_plus_results(measured_y_plus: np.ndarray, model: str) -> dict[str, Any]:
    """
    Validate measured wall y+ values against turbulence-model expectations.

    Returns:
        dict with keys:
            valid: bool
            mean_y_plus: float
            max_y_plus: float
            warnings: list[str]
    """
    if measured_y_plus.size == 0:
        raise ValueError("measured_y_plus must not be empty")

    values = np.asarray(measured_y_plus, dtype=float)
    if np.isnan(values).any():
        raise ValueError("measured_y_plus must not contain NaN values")

    model_normalized = model.strip().lower()
    mean_y_plus = float(np.mean(values))
    max_y_plus = float(np.max(values))
    min_y_plus = float(np.min(values))

    warnings: list[str] = []
    wall_resolved_models = {
        TurbulenceModel.K_OMEGA_SST.value,
        TurbulenceModel.SPALART_ALLMARAS.value,
        TurbulenceModel.TRANSITION_SST.value,
    }

    if model_normalized in wall_resolved_models and max_y_plus > 5.0:
        warnings.append("Wall-resolved model expects y+ <= 5; measured maximum exceeds limit.")

    if model_normalized == TurbulenceModel.K_EPSILON_REALIZABLE.value:
        if min_y_plus < 20.0 or max_y_plus > 100.0:
            warnings.append("k-epsilon wall functions expect y+ in the 20-100 range.")

    return {
        "valid": len(warnings) == 0,
        "mean_y_plus": mean_y_plus,
        "max_y_plus": max_y_plus,
        "warnings": warnings,
    }


def recommend_discretization_strategy(is_first_run: bool = True) -> dict[str, str]:
    """Return discretization settings for first run versus retry stabilization."""
    if is_first_run:
        return {
            "pressure": "second-order",
            "momentum": "second-order-upwind",
            "turbulent_kinetic_energy": "second-order-upwind",
            "specific_dissipation_rate": "second-order-upwind",
        }
    return {
        "pressure": "standard",
        "momentum": "first-order-upwind",
        "turbulent_kinetic_energy": "first-order-upwind",
        "specific_dissipation_rate": "first-order-upwind",
    }


def recommend_urf(turbulence_model: str, is_retry: bool = False) -> dict[str, float]:
    """Return default or conservative URFs depending on retry state."""
    _ = turbulence_model  # Reserved for model-specific URF tuning in Phase 2.
    if is_retry:
        return dict(CONSERVATIVE_URF)
    return dict(DEFAULT_URF)
