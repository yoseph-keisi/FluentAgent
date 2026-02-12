from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from fluent_agent.config import SimulationConfig
from fluent_agent.logger import AgentLogger
from fluent_agent.meshing import MeshGenerator, MeshQualityError, MeshResult, QualityReport


def _build_generator(sample_config_path: Path, tmp_path: Path) -> MeshGenerator:
    """Create a MeshGenerator with isolated output path for tests."""
    config = SimulationConfig.from_yaml(str(sample_config_path))
    config.output.directory = str(tmp_path / "outputs")
    logger = AgentLogger(name=f"test-meshing-{tmp_path.name}")
    return MeshGenerator(config=config, logger=logger)


def test_compute_first_layer_height(sample_config_path: Path, tmp_path: Path) -> None:
    """First-layer estimate should be positive and in a physically reasonable range."""
    generator = _build_generator(sample_config_path, tmp_path)
    value = generator.compute_first_layer_height()
    assert value > 0.0
    assert 1.0e-7 < value < 1.0e-4


def test_quality_report_pass(sample_config_path: Path, tmp_path: Path) -> None:
    """Quality report should pass when all gates satisfy configured thresholds."""
    generator = _build_generator(sample_config_path, tmp_path)
    report = generator._check_quality(
        {
            "min_orthogonal_quality": 0.21,
            "max_skewness": 0.83,
            "max_aspect_ratio": 65.0,
            "total_cells": 150000,
        }
    )

    assert report.passed is True
    assert report.failures == []
    assert report.total_cells == 150000


def test_quality_report_fail(sample_config_path: Path, tmp_path: Path) -> None:
    """Quality report should fail and include each violated quality metric."""
    generator = _build_generator(sample_config_path, tmp_path)
    report = generator._check_quality(
        {
            "min_orthogonal_quality": 0.10,
            "max_skewness": 0.95,
            "max_aspect_ratio": 130.0,
            "total_cells": 85000,
        }
    )

    assert report.passed is False
    assert len(report.failures) == 3
    assert any("orthogonal quality" in failure for failure in report.failures)
    assert any("skewness" in failure for failure in report.failures)
    assert any("aspect ratio" in failure for failure in report.failures)


def test_adjust_parameters_high_skewness(sample_config_path: Path, tmp_path: Path) -> None:
    """High skewness should reduce max element size and increase smoothing."""
    generator = _build_generator(sample_config_path, tmp_path)
    baseline_max_size = float(generator._runtime_parameters["max_size"])
    report = QualityReport(
        min_orthogonal_quality=0.2,
        max_skewness=0.97,
        max_aspect_ratio=75.0,
        total_cells=50000,
        passed=False,
        failures=["skewness above threshold (0.970 > 0.900)"],
    )

    adjustments = generator._adjust_parameters(report, attempt=1)
    assert adjustments["max_size"] < baseline_max_size
    assert adjustments["smoothing_iterations"] > 0


def test_adjust_parameters_low_orthogonal_quality(sample_config_path: Path, tmp_path: Path) -> None:
    """Low orthogonal quality should reduce inflation growth rate."""
    generator = _build_generator(sample_config_path, tmp_path)
    baseline_growth_rate = float(generator._runtime_parameters["growth_rate"])
    report = QualityReport(
        min_orthogonal_quality=0.12,
        max_skewness=0.80,
        max_aspect_ratio=70.0,
        total_cells=50000,
        passed=False,
        failures=["orthogonal quality below threshold (0.120 < 0.150)"],
    )

    adjustments = generator._adjust_parameters(report, attempt=1)
    assert adjustments["growth_rate"] < baseline_growth_rate
    assert adjustments["growth_rate"] >= 1.05


def test_adjust_parameters_high_aspect_ratio(sample_config_path: Path, tmp_path: Path) -> None:
    """High aspect ratio should reduce first-layer height and growth rate."""
    generator = _build_generator(sample_config_path, tmp_path)
    baseline_first_layer = float(generator._runtime_parameters["first_layer_height"])
    baseline_growth_rate = float(generator._runtime_parameters["growth_rate"])
    report = QualityReport(
        min_orthogonal_quality=0.20,
        max_skewness=0.82,
        max_aspect_ratio=160.0,
        total_cells=50000,
        passed=False,
        failures=["aspect ratio above threshold (160.0 > 100.0)"],
    )

    adjustments = generator._adjust_parameters(report, attempt=1)
    assert adjustments["first_layer_height"] < baseline_first_layer
    assert adjustments["growth_rate"] < baseline_growth_rate
    assert adjustments["growth_rate"] >= 1.05


def test_mesh_result_dataclass() -> None:
    """MeshResult should store attempt metadata and success state."""
    report = QualityReport(
        min_orthogonal_quality=0.20,
        max_skewness=0.85,
        max_aspect_ratio=90.0,
        total_cells=1000,
        passed=True,
        failures=[],
    )
    result = MeshResult(
        mesh_path="outputs/mesh.msh",
        final_quality=report,
        attempts=1,
        iteration_log=[{"attempt": 1}],
        success=True,
    )

    assert result.mesh_path.endswith(".msh")
    assert result.final_quality.passed is True
    assert result.attempts == 1
    assert result.success is True


def test_generate_raises_mesh_quality_error(
    sample_config_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generate should raise MeshQualityError after exhausting failed attempts."""
    generator = _build_generator(sample_config_path, tmp_path)
    generator.config.mesh.max_retry_attempts = 2

    def _create_session() -> dict[str, Any]:
        return {
            "min_orthogonal_quality": 0.05,
            "max_skewness": 0.99,
            "max_aspect_ratio": 140.0,
            "total_cells": 25000,
        }

    monkeypatch.setattr(generator, "_create_mesh_session", _create_session)
    monkeypatch.setattr(generator, "_import_geometry", lambda session: None)
    monkeypatch.setattr(generator, "_create_domain", lambda session: None)
    monkeypatch.setattr(generator, "_apply_sizing", lambda session: None)
    monkeypatch.setattr(generator, "_apply_inflation", lambda session: None)
    monkeypatch.setattr(generator, "_generate_mesh_internal", lambda session: None)

    with pytest.raises(MeshQualityError):
        generator.generate()


@pytest.mark.integration
def test_generate_mesh_simple_geometry(
    sample_config_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Integration flow: mocked meshing orchestration passes in one attempt."""
    if not os.getenv("FLUENT_PATH"):
        pytest.skip("Integration test requires FLUENT_PATH environment variable.")

    generator = _build_generator(sample_config_path, tmp_path)
    session_payload = {
        "min_orthogonal_quality": 0.19,
        "max_skewness": 0.86,
        "max_aspect_ratio": 72.0,
        "total_cells": 42000,
    }

    monkeypatch.setattr(generator, "_create_mesh_session", lambda: session_payload)
    monkeypatch.setattr(generator, "_import_geometry", lambda session: None)
    monkeypatch.setattr(generator, "_create_domain", lambda session: None)
    monkeypatch.setattr(generator, "_apply_sizing", lambda session: None)
    monkeypatch.setattr(generator, "_apply_inflation", lambda session: None)
    monkeypatch.setattr(generator, "_generate_mesh_internal", lambda session: None)

    def _export_mesh(_: Any, output_path: str) -> str:
        Path(output_path).write_text("mock-mesh", encoding="utf-8")
        return output_path

    monkeypatch.setattr(generator, "_export_mesh", _export_mesh)
    result = generator.generate()

    assert result.success is True
    assert result.attempts == 1
    assert Path(result.mesh_path).exists()
    assert result.final_quality.passed is True


@pytest.mark.integration
def test_generate_mesh_quality_retry(
    sample_config_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Integration flow: first attempt fails quality, second attempt passes."""
    if not os.getenv("FLUENT_PATH"):
        pytest.skip("Integration test requires FLUENT_PATH environment variable.")

    generator = _build_generator(sample_config_path, tmp_path)
    generator.config.mesh.max_retry_attempts = 3
    session_payloads: list[dict[str, float | int]] = [
        {
            "min_orthogonal_quality": 0.10,
            "max_skewness": 0.95,
            "max_aspect_ratio": 130.0,
            "total_cells": 21000,
        },
        {
            "min_orthogonal_quality": 0.22,
            "max_skewness": 0.82,
            "max_aspect_ratio": 80.0,
            "total_cells": 39000,
        },
    ]

    def _create_session() -> dict[str, float | int]:
        return session_payloads.pop(0)

    monkeypatch.setattr(generator, "_create_mesh_session", _create_session)
    monkeypatch.setattr(generator, "_import_geometry", lambda session: None)
    monkeypatch.setattr(generator, "_create_domain", lambda session: None)
    monkeypatch.setattr(generator, "_apply_sizing", lambda session: None)
    monkeypatch.setattr(generator, "_apply_inflation", lambda session: None)
    monkeypatch.setattr(generator, "_generate_mesh_internal", lambda session: None)

    def _export_mesh(_: Any, output_path: str) -> str:
        Path(output_path).write_text("mock-mesh", encoding="utf-8")
        return output_path

    monkeypatch.setattr(generator, "_export_mesh", _export_mesh)
    result = generator.generate()

    assert result.success is True
    assert result.attempts == 2
    assert len(result.iteration_log) == 2
    assert result.iteration_log[0]["quality"]["passed"] is False
    assert result.iteration_log[1]["quality"]["passed"] is True
