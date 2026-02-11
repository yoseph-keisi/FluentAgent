from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "configs" / "example_naca2412.yaml"


@pytest.fixture
def sample_geometry_path() -> Path:
    return Path(__file__).resolve().parent.parent / "geometries" / "naca2412.csv"


@pytest.fixture
def naca0012_geometry_path() -> Path:
    return Path(__file__).resolve().parent.parent / "geometries" / "naca0012.csv"
