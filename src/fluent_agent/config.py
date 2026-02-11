from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from fluent_agent.constants import (
    DEFAULT_QUALITY_GATES,
    MESH_FINENESS_PRESETS,
    DomainType,
    MeshFineness,
    TurbulenceModel,
)


class GeometryConfig(BaseModel):
    source_type: str = "csv"
    file_path: str = "geometries/naca2412.csv"
    chord_length: float = 1.0
    reference_area: float = 1.0

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        allowed = {"csv", "stp", "stl", "igs"}
        if value not in allowed:
            raise ValueError(f"source_type must be one of {sorted(allowed)}")
        return value


class DomainConfig(BaseModel):
    type: DomainType = DomainType.C_TYPE
    upstream_distance: float = 15.0
    downstream_distance: float = 25.0
    lateral_distance: float = 15.0


class InflationConfig(BaseModel):
    first_layer_height: float | None = None
    growth_rate: float = 1.2
    num_layers: int = 20
    target_y_plus: float = 1.0

    @field_validator("growth_rate")
    @classmethod
    def validate_growth_rate(cls, value: float) -> float:
        if value <= 1.0:
            raise ValueError("growth_rate must be > 1.0")
        return value

    @field_validator("num_layers")
    @classmethod
    def validate_num_layers(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("num_layers must be > 0")
        return value

    @field_validator("target_y_plus")
    @classmethod
    def validate_target_y_plus(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("target_y_plus must be > 0")
        return value


class SurfaceSizingConfig(BaseModel):
    min_size: float = 0.001
    max_size: float = 0.05
    curvature_normal_angle: float = 12.0

    @model_validator(mode="after")
    def validate_bounds(self) -> SurfaceSizingConfig:
        if self.min_size <= 0:
            raise ValueError("min_size must be > 0")
        if self.max_size <= 0:
            raise ValueError("max_size must be > 0")
        if self.max_size < self.min_size:
            raise ValueError("max_size must be >= min_size")
        return self


class QualityGatesConfig(BaseModel):
    min_orthogonal_quality: float = DEFAULT_QUALITY_GATES["min_orthogonal_quality"]
    max_skewness: float = DEFAULT_QUALITY_GATES["max_skewness"]
    max_aspect_ratio: float = DEFAULT_QUALITY_GATES["max_aspect_ratio"]


class MeshConfig(BaseModel):
    strategy: str = "auto"
    fineness: MeshFineness = MeshFineness.MEDIUM
    inflation_layers: InflationConfig = Field(default_factory=InflationConfig)
    surface_sizing: SurfaceSizingConfig = Field(default_factory=SurfaceSizingConfig)
    quality_gates: QualityGatesConfig = Field(default_factory=QualityGatesConfig)
    max_retry_attempts: int = 3

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, value: str) -> str:
        allowed = {"auto", "manual"}
        if value not in allowed:
            raise ValueError(f"strategy must be one of {sorted(allowed)}")
        return value

    @field_validator("max_retry_attempts")
    @classmethod
    def validate_max_retry_attempts(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_retry_attempts must be > 0")
        return value

    @model_validator(mode="after")
    def apply_fineness_presets(self) -> MeshConfig:
        preset = MESH_FINENESS_PRESETS[self.fineness]
        if self.strategy == "auto":
            self.surface_sizing = SurfaceSizingConfig(
                min_size=preset["min_size"],
                max_size=preset["max_size"],
                curvature_normal_angle=preset["curvature_normal_angle"],
            )
        return self


class FluidConfig(BaseModel):
    density: float = 1.225
    viscosity: float = 1.7894e-5

    @field_validator("density", "viscosity")
    @classmethod
    def validate_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("value must be > 0")
        return value


class FlowConfig(BaseModel):
    reynolds_number: float = 3.0e6
    freestream_velocity: float = 43.822
    angle_of_attack: float = 0.0
    mach_number: float = 0.13
    fluid: FluidConfig = Field(default_factory=FluidConfig)

    @field_validator("reynolds_number")
    @classmethod
    def validate_reynolds_number(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("reynolds_number must be > 0")
        return value

    @field_validator("angle_of_attack")
    @classmethod
    def validate_angle_of_attack(cls, value: float) -> float:
        if not -90.0 <= value <= 90.0:
            raise ValueError("angle_of_attack must be in [-90, 90]")
        return value

    @field_validator("freestream_velocity", "mach_number")
    @classmethod
    def validate_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("value must be >= 0")
        return value


class DiscretizationConfig(BaseModel):
    pressure: str = "second-order"
    momentum: str = "second-order-upwind"
    turbulent_kinetic_energy: str = "second-order-upwind"
    specific_dissipation_rate: str = "second-order-upwind"


class ResidualTargetsConfig(BaseModel):
    continuity: float = 1.0e-6
    x_velocity: float = 1.0e-6
    y_velocity: float = 1.0e-6
    k: float = 1.0e-6
    omega: float = 1.0e-6


class ConvergenceConfig(BaseModel):
    residual_targets: ResidualTargetsConfig = Field(default_factory=ResidualTargetsConfig)
    max_iterations: int = 5000
    monitor_cl: bool = True
    monitor_cd: bool = True
    cl_convergence_window: int = 100
    cl_convergence_tolerance: float = 0.001

    @field_validator("max_iterations", "cl_convergence_window")
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be > 0")
        return value


class AdaptiveRetryConfig(BaseModel):
    enabled: bool = True
    max_retries: int = 3

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("max_retries must be >= 0")
        return value


class SolverConfig(BaseModel):
    turbulence_model: TurbulenceModel = TurbulenceModel.K_OMEGA_SST
    pressure_velocity_coupling: str = "coupled"
    discretization: DiscretizationConfig = Field(default_factory=DiscretizationConfig)
    initialization: str = "hybrid"
    convergence: ConvergenceConfig = Field(default_factory=ConvergenceConfig)
    adaptive_retry: AdaptiveRetryConfig = Field(default_factory=AdaptiveRetryConfig)

    @field_validator("pressure_velocity_coupling")
    @classmethod
    def validate_pv_coupling(cls, value: str) -> str:
        allowed = {"coupled", "simple", "simplec"}
        if value not in allowed:
            raise ValueError(f"pressure_velocity_coupling must be one of {sorted(allowed)}")
        return value

    @field_validator("initialization")
    @classmethod
    def validate_initialization(cls, value: str) -> str:
        allowed = {"hybrid", "standard", "fmg"}
        if value not in allowed:
            raise ValueError(f"initialization must be one of {sorted(allowed)}")
        return value


class PlotsConfig(BaseModel):
    residuals: bool = True
    cl_cd_history: bool = True
    pressure_coefficient: bool = True
    wall_y_plus: bool = True


class OutputConfig(BaseModel):
    directory: str = "outputs/run_001"
    save_case_file: bool = True
    save_data_file: bool = True
    export_residuals_csv: bool = True
    export_force_coefficients_csv: bool = True
    generate_plots: PlotsConfig = Field(default_factory=PlotsConfig)
    generate_report: bool = True


class SimulationConfig(BaseModel):
    geometry: GeometryConfig = Field(default_factory=GeometryConfig)
    domain: DomainConfig = Field(default_factory=DomainConfig)
    mesh: MeshConfig = Field(default_factory=MeshConfig)
    flow: FlowConfig = Field(default_factory=FlowConfig)
    solver: SolverConfig = Field(default_factory=SolverConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    @model_validator(mode="after")
    def compute_first_layer_height(self) -> SimulationConfig:
        if self.mesh.inflation_layers.first_layer_height is not None:
            return self

        reynolds_number = self.flow.reynolds_number
        density = self.flow.fluid.density
        velocity = self.flow.freestream_velocity
        viscosity = self.flow.fluid.viscosity
        y_plus = self.mesh.inflation_layers.target_y_plus

        skin_friction_coefficient = 0.058 * (reynolds_number ** -0.2)
        wall_shear_stress = 0.5 * skin_friction_coefficient * density * (velocity**2)
        friction_velocity = (wall_shear_stress / density) ** 0.5

        if friction_velocity <= 0:
            raise ValueError("Computed friction velocity must be positive")

        first_layer_height = (y_plus * viscosity) / (friction_velocity * density)
        self.mesh.inflation_layers.first_layer_height = first_layer_height
        return self

    @classmethod
    def from_yaml(cls, path: str) -> SimulationConfig:
        yaml_path = Path(path)
        with yaml_path.open("r", encoding="utf-8") as handle:
            raw_config = yaml.safe_load(handle) or {}
        return cls.model_validate(raw_config)

    def to_yaml(self, path: str) -> None:
        yaml_path = Path(path)
        payload = self.model_dump(mode="json")
        with yaml_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False)
