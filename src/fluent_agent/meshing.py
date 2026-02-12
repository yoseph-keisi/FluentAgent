from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from fluent_agent.config import SimulationConfig
from fluent_agent.geometry import GeometryHandler
from fluent_agent.logger import AgentLogger
from fluent_agent.physics_rules import recommend_y_plus_target


PYFLUENT_TODO_MESSAGE = (
    "TODO: verify PyFluent >= 0.20 API — see docs at https://fluent.docs.pyansys.com/"
)


class MeshQualityError(Exception):
    """Raised when mesh quality gates fail after all retry attempts."""


class MeshGenerationError(Exception):
    """Raised when meshing operations fail before a quality verdict is available."""


@dataclass
class QualityReport:
    """
    Mesh quality metrics extracted from meshing output.

    Attributes:
        min_orthogonal_quality: Minimum orthogonal quality in the mesh.
        max_skewness: Maximum skewness in the mesh.
        max_aspect_ratio: Maximum cell aspect ratio in the mesh.
        total_cells: Total number of mesh cells.
        passed: Overall quality gate result.
        failures: Human-readable descriptions of gate failures.
    """

    min_orthogonal_quality: float
    max_skewness: float
    max_aspect_ratio: float
    total_cells: int
    passed: bool
    failures: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Normalize values and enforce pass/fail consistency."""
        self.min_orthogonal_quality = float(self.min_orthogonal_quality)
        self.max_skewness = float(self.max_skewness)
        self.max_aspect_ratio = float(self.max_aspect_ratio)
        self.total_cells = int(self.total_cells)
        self.failures = list(self.failures)
        if self.failures:
            self.passed = False


@dataclass
class MeshResult:
    """
    Complete mesh generation outcome.

    Attributes:
        mesh_path: Path to exported mesh file.
        final_quality: Final quality metrics from the successful attempt.
        attempts: Number of attempts used.
        iteration_log: Per-attempt parameters and quality details.
        success: Whether generation completed successfully.
    """

    mesh_path: str
    final_quality: QualityReport
    attempts: int
    iteration_log: list[dict[str, Any]]
    success: bool

    def __post_init__(self) -> None:
        """Ensure a valid MeshResult instance."""
        if self.attempts <= 0:
            raise ValueError("attempts must be > 0")


class MeshGenerator:
    """
    Generate mesh with quality-based adaptive retries.

    This class is intentionally structured so that quality and adaptation logic are
    testable without a Fluent license. PyFluent-specific actions are isolated in
    helper methods, and unresolved API calls raise a documented NotImplementedError.
    """

    def __init__(self, config: SimulationConfig, logger: AgentLogger) -> None:
        """
        Initialize meshing orchestrator state.

        Args:
            config: Fully validated simulation configuration.
            logger: Shared project logger.
        """
        self.config = config
        self.logger = logger
        self.geometry_handler = GeometryHandler(config.geometry)
        self._runtime_parameters: dict[str, float | int | bool] = {
            "min_size": float(config.mesh.surface_sizing.min_size),
            "max_size": float(config.mesh.surface_sizing.max_size),
            "curvature_normal_angle": float(config.mesh.surface_sizing.curvature_normal_angle),
            "first_layer_height": float(config.mesh.inflation_layers.first_layer_height or 0.0),
            "growth_rate": float(config.mesh.inflation_layers.growth_rate),
            "num_layers": int(config.mesh.inflation_layers.num_layers),
            "smoothing_iterations": 0,
            "use_curvature_refinement": True,
        }

    def compute_first_layer_height(self) -> float:
        """
        Estimate first cell height from target y+ using turbulent flat-plate correlation.

        Formula:
            Cf = 0.058 * Re^(-0.2)
            tau_w = 0.5 * Cf * rho * U^2
            u_tau = sqrt(tau_w / rho)
            y = (y_plus * mu) / (u_tau * rho)

        Returns:
            First layer height in meters.
        """
        reynolds_number = self.config.flow.reynolds_number
        density = self.config.flow.fluid.density
        viscosity = self.config.flow.fluid.viscosity
        chord = self.config.geometry.chord_length
        velocity = self.config.flow.freestream_velocity
        model = self.config.solver.turbulence_model.value
        recommended_y_plus = recommend_y_plus_target(model)
        target_y_plus = self.config.mesh.inflation_layers.target_y_plus or recommended_y_plus

        if reynolds_number <= 0:
            raise ValueError("reynolds_number must be > 0 to compute first-layer height")
        if density <= 0 or viscosity <= 0:
            raise ValueError("fluid density and viscosity must be > 0")
        if chord <= 0:
            raise ValueError("geometry.chord_length must be > 0")
        if velocity <= 0:
            velocity = (reynolds_number * viscosity) / (density * chord)
        if velocity <= 0:
            raise ValueError("freestream velocity must be computable as a positive value")

        skin_friction = 0.058 * (reynolds_number**-0.2)
        wall_shear = 0.5 * skin_friction * density * (velocity**2)
        friction_velocity = (wall_shear / density) ** 0.5
        if friction_velocity <= 0:
            raise ValueError("computed friction velocity must be positive")

        first_layer_height = (target_y_plus * viscosity) / (friction_velocity * density)
        self.logger.info(
            "Computed first layer height: %.6e m (target y+ = %.2f)",
            first_layer_height,
            target_y_plus,
        )
        return first_layer_height

    def generate(self) -> MeshResult:
        """
        Run adaptive meshing attempts until quality passes or retries are exhausted.

        Returns:
            MeshResult containing final mesh file path and diagnostics.

        Raises:
            MeshQualityError: Quality gates failed for all attempts.
            MeshGenerationError: Meshing execution failed unexpectedly.
            NotImplementedError: PyFluent API call path has unresolved syntax.
        """
        self.logger.stage("MESHING")
        self.geometry_handler.load()

        if self.config.mesh.inflation_layers.first_layer_height is None:
            first_layer_height = self.compute_first_layer_height()
            self.config.mesh.inflation_layers.first_layer_height = first_layer_height
            self._runtime_parameters["first_layer_height"] = first_layer_height

        output_dir = Path(self.config.output.directory)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "mesh.msh"
        max_attempts = max(1, int(self.config.mesh.max_retry_attempts))

        iteration_log: list[dict[str, Any]] = []
        last_report: QualityReport | None = None

        for attempt in range(1, max_attempts + 1):
            session: Any = None
            try:
                self.logger.info("Mesh quality check - Attempt %d/%d", attempt, max_attempts)
                session = self._create_mesh_session()
                self._import_geometry(session)
                self._create_domain(session)
                self._apply_sizing(session)
                self._apply_inflation(session)
                self._generate_mesh_internal(session)

                quality_report = self._check_quality(session)
                last_report = quality_report
                iteration_log.append(
                    {
                        "attempt": attempt,
                        "parameters": dict(self._runtime_parameters),
                        "quality": asdict(quality_report),
                    }
                )

                if quality_report.passed:
                    mesh_path = self._export_mesh(session, str(output_path))
                    self.logger.info(
                        "Mesh generated successfully in %d attempt(s) with %d cells",
                        attempt,
                        quality_report.total_cells,
                    )
                    return MeshResult(
                        mesh_path=mesh_path,
                        final_quality=quality_report,
                        attempts=attempt,
                        iteration_log=iteration_log,
                        success=True,
                    )

                self.logger.warning(
                    "Mesh quality failed on attempt %d: %s",
                    attempt,
                    ", ".join(quality_report.failures),
                )
                if attempt < max_attempts:
                    adjustments = self._adjust_parameters(quality_report, attempt)
                    self._apply_adjustments(adjustments)
            except NotImplementedError:
                raise
            except MeshGenerationError:
                raise
            except Exception as exc:
                msg = f"Mesh generation attempt {attempt} failed: {exc}"
                raise MeshGenerationError(msg) from exc
            finally:
                self._close_session(session)

        diagnostics = {
            "attempts": max_attempts,
            "last_quality": asdict(last_report) if last_report is not None else None,
            "iteration_log": iteration_log,
        }
        msg = f"Mesh quality gates failed after {max_attempts} attempts: {diagnostics}"
        raise MeshQualityError(msg)

    def _create_mesh_session(self) -> Any:
        """
        Launch PyFluent meshing session.

        Raises:
            MeshGenerationError: PyFluent import/setup failed.
            NotImplementedError: API call syntax is pending verification.
        """
        try:
            import ansys.fluent.core as pyfluent  # noqa: F401
        except Exception as exc:
            raise MeshGenerationError(
                "PyFluent dependency unavailable; install ansys-fluent-core to enable meshing."
            ) from exc
        raise NotImplementedError(PYFLUENT_TODO_MESSAGE)

    def _import_geometry(self, session: Any) -> None:
        """
        Import geometry into a meshing session.

        Args:
            session: Active meshing session.
        """
        geometry_path = Path(self.config.output.directory) / "geometry_for_meshing.csv"
        exported = self.geometry_handler.export_for_meshing(str(geometry_path))
        try:
            if hasattr(session, "import_geometry"):
                session.import_geometry(exported)
                return
            raise NotImplementedError(PYFLUENT_TODO_MESSAGE)
        except NotImplementedError:
            raise
        except Exception as exc:
            raise MeshGenerationError(f"Geometry import failed: {exc}") from exc

    def _create_domain(self, session: Any) -> None:
        """
        Create computational domain boundaries based on configured domain extents.

        Args:
            session: Active meshing session.
        """
        domain_payload = {
            "domain_type": self.config.domain.type.value,
            "upstream_distance": self.config.domain.upstream_distance,
            "downstream_distance": self.config.domain.downstream_distance,
            "lateral_distance": self.config.domain.lateral_distance,
        }
        try:
            if hasattr(session, "create_domain"):
                session.create_domain(domain_payload)
                return
            raise NotImplementedError(PYFLUENT_TODO_MESSAGE)
        except NotImplementedError:
            raise
        except Exception as exc:
            raise MeshGenerationError(f"Domain creation failed: {exc}") from exc

    def _apply_sizing(self, session: Any) -> None:
        """
        Apply surface and curvature sizing functions.

        Args:
            session: Active meshing session.
        """
        sizing_payload = {
            "min_size": self._runtime_parameters["min_size"],
            "max_size": self._runtime_parameters["max_size"],
            "curvature_normal_angle": self._runtime_parameters["curvature_normal_angle"],
            "use_curvature_refinement": self._runtime_parameters["use_curvature_refinement"],
            "smoothing_iterations": self._runtime_parameters["smoothing_iterations"],
        }
        try:
            if hasattr(session, "apply_sizing"):
                session.apply_sizing(sizing_payload)
                return
            raise NotImplementedError(PYFLUENT_TODO_MESSAGE)
        except NotImplementedError:
            raise
        except Exception as exc:
            raise MeshGenerationError(f"Sizing application failed: {exc}") from exc

    def _apply_inflation(self, session: Any) -> None:
        """
        Apply inflation-layer controls to the wall boundary.

        Args:
            session: Active meshing session.
        """
        inflation_payload = {
            "first_layer_height": self._runtime_parameters["first_layer_height"],
            "growth_rate": self._runtime_parameters["growth_rate"],
            "num_layers": self._runtime_parameters["num_layers"],
        }
        try:
            if hasattr(session, "apply_inflation"):
                session.apply_inflation(inflation_payload)
                return
            raise NotImplementedError(PYFLUENT_TODO_MESSAGE)
        except NotImplementedError:
            raise
        except Exception as exc:
            raise MeshGenerationError(f"Inflation setup failed: {exc}") from exc

    def _generate_mesh_internal(self, session: Any) -> None:
        """
        Trigger mesh generation.

        Args:
            session: Active meshing session.
        """
        try:
            if hasattr(session, "generate_mesh"):
                session.generate_mesh()
                return
            raise NotImplementedError(PYFLUENT_TODO_MESSAGE)
        except NotImplementedError:
            raise
        except Exception as exc:
            raise MeshGenerationError(f"PyFluent mesh generation failed: {exc}") from exc

    def _check_quality(self, session: Any) -> QualityReport:
        """
        Evaluate mesh quality metrics against configured quality gates.

        Args:
            session: Active meshing session or a quality-metric mapping (for tests).

        Returns:
            QualityReport describing pass/fail status and failure reasons.
        """
        metrics = self._query_quality_metrics(session)
        min_orthogonal_quality = self._read_metric(
            metrics,
            ("min_orthogonal_quality", "orthogonal_quality_min", "orthogonal_quality"),
        )
        max_skewness = self._read_metric(metrics, ("max_skewness", "skewness_max", "skewness"))
        max_aspect_ratio = self._read_metric(
            metrics,
            ("max_aspect_ratio", "aspect_ratio_max", "aspect_ratio"),
        )
        total_cells = int(self._read_metric(metrics, ("total_cells", "cell_count", "n_cells")))

        gates = self.config.mesh.quality_gates
        failures: list[str] = []
        if min_orthogonal_quality < gates.min_orthogonal_quality:
            failures.append(
                "orthogonal quality below threshold "
                f"({min_orthogonal_quality:.3f} < {gates.min_orthogonal_quality:.3f})"
            )
        if max_skewness > gates.max_skewness:
            failures.append(
                f"skewness above threshold ({max_skewness:.3f} > {gates.max_skewness:.3f})"
            )
        if max_aspect_ratio > gates.max_aspect_ratio:
            failures.append(
                "aspect ratio above threshold "
                f"({max_aspect_ratio:.1f} > {gates.max_aspect_ratio:.1f})"
            )

        report = QualityReport(
            min_orthogonal_quality=min_orthogonal_quality,
            max_skewness=max_skewness,
            max_aspect_ratio=max_aspect_ratio,
            total_cells=total_cells,
            passed=len(failures) == 0,
            failures=failures,
        )
        self.logger.info(
            "  Orthogonal Quality: %.3f (min %.3f)",
            report.min_orthogonal_quality,
            gates.min_orthogonal_quality,
        )
        self.logger.info(
            "  Skewness: %.3f (max %.3f)",
            report.max_skewness,
            gates.max_skewness,
        )
        self.logger.info(
            "  Aspect Ratio: %.1f (max %.1f)",
            report.max_aspect_ratio,
            gates.max_aspect_ratio,
        )
        if report.passed:
            self.logger.info("Mesh quality PASSED")
        else:
            self.logger.warning("Mesh quality FAILED: %s", ", ".join(report.failures))
        return report

    def _adjust_parameters(self, quality_report: QualityReport, attempt: int) -> dict[str, Any]:
        """
        Compute retry adjustments from failed quality metrics.

        Args:
            quality_report: Quality report from the failed attempt.
            attempt: Current attempt number (1-indexed).

        Returns:
            Dictionary of updated meshing parameters.
        """
        adjustments: dict[str, Any] = {}
        failure_text = " ".join(quality_report.failures).lower()
        aggressiveness = max(1.0, 1.0 + (attempt - 1) * 0.5)

        if "skewness" in failure_text:
            current_max_size = float(self._runtime_parameters["max_size"])
            current_min_size = float(self._runtime_parameters["min_size"])
            reduction = 0.20 if attempt <= 2 else 0.30
            new_max_size = max(current_min_size * 1.1, current_max_size * (1.0 - reduction))
            adjustments["max_size"] = new_max_size
            current_smoothing = int(self._runtime_parameters["smoothing_iterations"])
            adjustments["smoothing_iterations"] = current_smoothing + int(2 * aggressiveness)

        if "orthogonal quality" in failure_text:
            current_growth = float(self._runtime_parameters["growth_rate"])
            new_growth = max(1.05, current_growth - (0.05 * aggressiveness))
            adjustments["growth_rate"] = new_growth
            current_smoothing = int(self._runtime_parameters["smoothing_iterations"])
            requested_smoothing = int(adjustments.get("smoothing_iterations", current_smoothing))
            adjustments["smoothing_iterations"] = max(
                requested_smoothing,
                current_smoothing + int(1 * aggressiveness),
            )

        if "aspect ratio" in failure_text:
            current_growth = float(
                adjustments.get("growth_rate", self._runtime_parameters["growth_rate"])
            )
            current_first_layer = float(self._runtime_parameters["first_layer_height"])
            new_growth = max(1.05, current_growth - (0.05 * aggressiveness))
            new_first_layer = max(
                1.0e-9,
                current_first_layer * (0.8 if attempt <= 2 else 0.65),
            )
            adjustments["growth_rate"] = new_growth
            adjustments["first_layer_height"] = new_first_layer

        if attempt >= 4:
            adjustments["use_curvature_refinement"] = False
            current_angle = float(self._runtime_parameters["curvature_normal_angle"])
            adjustments["curvature_normal_angle"] = min(30.0, current_angle + 2.0)

        return adjustments

    def _export_mesh(self, session: Any, output_path: str) -> str:
        """
        Export mesh and return output path.

        Args:
            session: Active meshing session.
            output_path: Destination .msh path.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if hasattr(session, "export_mesh"):
                session.export_mesh(str(path))
                return str(path)
            raise NotImplementedError(PYFLUENT_TODO_MESSAGE)
        except NotImplementedError:
            raise
        except Exception as exc:
            raise MeshGenerationError(f"Mesh export failed: {exc}") from exc

    def _query_quality_metrics(self, session: Any) -> Mapping[str, Any]:
        """
        Obtain quality metrics from a mapping or session adapter.

        Args:
            session: Session object or dictionary-like metrics payload.
        """
        try:
            if isinstance(session, Mapping):
                return session
            if hasattr(session, "get_quality_metrics"):
                raw_metrics = session.get_quality_metrics()
                if isinstance(raw_metrics, Mapping):
                    return raw_metrics
                raise MeshGenerationError("get_quality_metrics() did not return a mapping")
            if hasattr(session, "quality_metrics"):
                raw_metrics = getattr(session, "quality_metrics")
                if isinstance(raw_metrics, Mapping):
                    return raw_metrics
                raise MeshGenerationError("quality_metrics attribute is not a mapping")
            raise NotImplementedError(PYFLUENT_TODO_MESSAGE)
        except NotImplementedError:
            raise
        except MeshGenerationError:
            raise
        except Exception as exc:
            raise MeshGenerationError(f"Failed to query mesh quality metrics: {exc}") from exc

    def _read_metric(self, metrics: Mapping[str, Any], candidates: tuple[str, ...]) -> float:
        """
        Read one metric value from multiple candidate keys.

        Args:
            metrics: Mapping containing mesh-quality values.
            candidates: Candidate keys in priority order.
        """
        for key in candidates:
            if key in metrics:
                try:
                    return float(metrics[key])
                except (TypeError, ValueError) as exc:
                    msg = f"Metric '{key}' is not numeric: {metrics[key]!r}"
                    raise MeshGenerationError(msg) from exc
        msg = f"Missing mesh quality metric; tried keys: {candidates}"
        raise MeshGenerationError(msg)

    def _apply_adjustments(self, adjustments: dict[str, Any]) -> None:
        """
        Apply adaptive retry adjustments to runtime meshing parameters.

        Args:
            adjustments: Parameter updates derived from quality failures.
        """
        if not adjustments:
            self.logger.warning("No adaptive adjustments produced for failed quality report.")
            return

        self.logger.info("Applying parameter adjustments:")
        for key, value in adjustments.items():
            old_value = self._runtime_parameters.get(key)
            self._runtime_parameters[key] = value
            self.logger.info("  %s: %s -> %s", key, old_value, value)

    def _close_session(self, session: Any) -> None:
        """
        Gracefully close session if it exposes an exit method.

        Args:
            session: Session object or None.
        """
        if session is None:
            return
        if not hasattr(session, "exit"):
            return
        try:
            session.exit()
        except Exception as exc:  # pragma: no cover - cleanup best effort
            self.logger.warning("Failed to close meshing session cleanly: %s", exc)
