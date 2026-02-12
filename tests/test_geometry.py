from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fluent_agent.geometry import GeometryHandler


@dataclass
class _GeometryConfigStub:
    file_path: str


def _handler_for(path: Path) -> GeometryHandler:
    return GeometryHandler(_GeometryConfigStub(file_path=str(path)))


def test_load_naca2412() -> None:
    handler = _handler_for(Path("geometries/naca2412.csv"))
    coords = handler.load()
    assert coords.shape == (200, 2)


def test_load_naca0012() -> None:
    handler = _handler_for(Path("geometries/naca0012.csv"))
    coords = handler.load()
    assert coords.shape == (200, 2)


def test_chord_length() -> None:
    handler = _handler_for(Path("geometries/naca2412.csv"))
    handler.load()
    chord = handler.compute_chord()
    assert abs(chord - 1.0) <= 0.02


def test_trailing_edge_closure() -> None:
    handler = _handler_for(Path("geometries/naca2412.csv"))
    open_te = np.array([[1.0, 0.01], [0.5, 0.1], [0.0, 0.0], [0.5, -0.1], [1.0, -0.01]])
    closed = handler.close_trailing_edge(open_te)
    assert closed.shape[0] == open_te.shape[0] + 1
    np.testing.assert_allclose(closed[-1], np.array([1.0, 0.0]))


def test_reject_malformed_csv(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.csv"
    bad_path.write_text("x\n0.0\n1.0\n", encoding="utf-8")

    handler = _handler_for(bad_path)
    with pytest.raises(ValueError, match="exactly 2 columns"):
        handler.load()


def test_reject_nan_values(tmp_path: Path) -> None:
    nan_path = tmp_path / "nan.csv"
    frame = pd.DataFrame({"x": [0.0, 0.5, 1.0], "y": [0.0, np.nan, 0.0]})
    frame.to_csv(nan_path, index=False)

    handler = _handler_for(nan_path)
    with pytest.raises(ValueError, match="NaN"):
        handler.load()
