from __future__ import annotations

from enum import Enum

RHO_AIR_SL = 1.225
MU_AIR_SL = 1.7894e-5
GAMMA_AIR = 1.4
R_AIR = 287.058
T_SL = 288.15
P_SL = 101325.0


class TurbulenceModel(str, Enum):
    SPALART_ALLMARAS = "spalart-allmaras"
    K_EPSILON_REALIZABLE = "k-epsilon-realizable"
    K_OMEGA_SST = "k-omega-sst"
    TRANSITION_SST = "transition-sst"


class DomainType(str, Enum):
    C_TYPE = "c-type"
    H_TYPE = "h-type"
    RECTANGULAR = "rectangular"


class MeshFineness(str, Enum):
    COARSE = "coarse"
    MEDIUM = "medium"
    FINE = "fine"
    ULTRA_FINE = "ultra-fine"


class ConvergenceStatus(str, Enum):
    CONVERGED = "converged"
    DIVERGED = "diverged"
    STAGNATED = "stagnated"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    NEEDS_MESH_REFINEMENT = "needs_mesh_refinement"


MESH_FINENESS_PRESETS: dict[MeshFineness, dict[str, float]] = {
    MeshFineness.COARSE: {
        "min_size": 0.005,
        "max_size": 0.1,
        "curvature_normal_angle": 18.0,
    },
    MeshFineness.MEDIUM: {
        "min_size": 0.001,
        "max_size": 0.05,
        "curvature_normal_angle": 12.0,
    },
    MeshFineness.FINE: {
        "min_size": 0.0005,
        "max_size": 0.02,
        "curvature_normal_angle": 8.0,
    },
    MeshFineness.ULTRA_FINE: {
        "min_size": 0.00025,
        "max_size": 0.01,
        "curvature_normal_angle": 6.0,
    },
}

DEFAULT_QUALITY_GATES: dict[str, float] = {
    "min_orthogonal_quality": 0.15,
    "max_skewness": 0.90,
    "max_aspect_ratio": 100.0,
}

DEFAULT_URF: dict[str, float] = {
    "pressure": 0.3,
    "momentum": 0.7,
    "turbulent_kinetic_energy": 0.8,
    "specific_dissipation_rate": 0.8,
}

CONSERVATIVE_URF: dict[str, float] = {
    "pressure": 0.2,
    "momentum": 0.5,
    "turbulent_kinetic_energy": 0.6,
    "specific_dissipation_rate": 0.6,
}
