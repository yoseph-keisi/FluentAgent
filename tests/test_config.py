from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from fluent_agent.config import SimulationConfig
from fluent_agent.constants import DomainType, MeshFineness


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_load_valid_config(sample_config_path: Path) -> None:
    config = SimulationConfig.from_yaml(str(sample_config_path))
    assert config.flow.reynolds_number == pytest.approx(3.0e6)


def test_invalid_reynolds_number(sample_config_path: Path) -> None:
    payload = _load_yaml(sample_config_path)
    payload["flow"]["reynolds_number"] = -1.0

    with pytest.raises(ValidationError):
        SimulationConfig.model_validate(payload)


def test_invalid_angle_of_attack(sample_config_path: Path) -> None:
    payload = _load_yaml(sample_config_path)
    payload["flow"]["angle_of_attack"] = 100.0

    with pytest.raises(ValidationError):
        SimulationConfig.model_validate(payload)


def test_first_layer_height_auto_computation(sample_config_path: Path) -> None:
    payload = _load_yaml(sample_config_path)
    payload["mesh"]["inflation_layers"]["first_layer_height"] = None

    config = SimulationConfig.model_validate(payload)

    assert config.mesh.inflation_layers.first_layer_height is not None
    assert config.mesh.inflation_layers.first_layer_height > 0.0


def test_default_values() -> None:
    config = SimulationConfig.model_validate({})

    assert config.geometry.source_type == "csv"
    assert config.domain.type == DomainType.C_TYPE
    assert config.mesh.fineness == MeshFineness.MEDIUM
    assert config.output.generate_report is True


def test_serialization_roundtrip(sample_config_path: Path, tmp_path: Path) -> None:
    original = SimulationConfig.from_yaml(str(sample_config_path))
    output_path = tmp_path / "roundtrip.yaml"

    original.to_yaml(str(output_path))
    reloaded = SimulationConfig.from_yaml(str(output_path))

    assert original.model_dump() == reloaded.model_dump()


def test_invalid_turbulence_model(sample_config_path: Path) -> None:
    payload = _load_yaml(sample_config_path)
    payload["solver"]["turbulence_model"] = "bad-model"

    with pytest.raises(ValidationError):
        SimulationConfig.model_validate(payload)
