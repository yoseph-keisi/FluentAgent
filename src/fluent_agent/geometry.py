from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from fluent_agent.config import GeometryConfig
else:
    try:
        from fluent_agent.config import GeometryConfig
    except (ImportError, AttributeError):
        GeometryConfig = Any  # type: ignore[misc,assignment]


class GeometryHandler:
    def __init__(self, config: GeometryConfig) -> None:
        self.config: GeometryConfig = config
        self._coords: np.ndarray | None = None

    def load(self) -> np.ndarray:
        file_path_raw = getattr(self.config, "file_path", None)
        if not isinstance(file_path_raw, str) or not file_path_raw.strip():
            msg = "Geometry config must provide a non-empty file_path."
            raise ValueError(msg)

        file_path = Path(file_path_raw)
        try:
            frame = pd.read_csv(file_path)
        except Exception as exc:  # pragma: no cover - pandas error specifics are external
            msg = f"Failed to read geometry CSV: {file_path}"
            raise ValueError(msg) from exc

        if frame.shape[1] != 2:
            msg = "Geometry CSV must contain exactly 2 columns: x,y."
            raise ValueError(msg)

        frame.columns = [str(column).strip().lower() for column in frame.columns]
        if frame.columns.tolist() != ["x", "y"]:
            msg = "Geometry CSV columns must be exactly 'x' and 'y'."
            raise ValueError(msg)

        numeric = frame.apply(pd.to_numeric, errors="coerce")
        if numeric.isna().any().any():
            msg = "Geometry CSV contains NaN or non-numeric values."
            raise ValueError(msg)

        coords = numeric.to_numpy(dtype=float)
        if coords.ndim != 2 or coords.shape[1] != 2:
            msg = "Geometry coordinates must be an Nx2 array."
            raise ValueError(msg)

        if coords.shape[0] < 2:
            msg = "Geometry must contain at least two coordinate points."
            raise ValueError(msg)

        self._coords = coords
        return coords

    def compute_chord(self) -> float:
        if self._coords is None:
            msg = "Geometry not loaded. Call load() before compute_chord()."
            raise ValueError(msg)

        chord = float(np.max(self._coords[:, 0]) - np.min(self._coords[:, 0]))
        if chord <= 0.0:
            msg = "Computed chord must be positive."
            raise ValueError(msg)
        return chord

    def close_trailing_edge(self, coords: np.ndarray) -> np.ndarray:
        if coords.ndim != 2 or coords.shape[1] != 2:
            msg = "Input coordinates must be an Nx2 array."
            raise ValueError(msg)
        if coords.shape[0] < 2:
            msg = "At least two coordinate points are required to evaluate trailing-edge closure."
            raise ValueError(msg)

        chord = float(np.max(coords[:, 0]) - np.min(coords[:, 0]))
        if chord <= 0.0:
            msg = "Chord must be positive to evaluate trailing-edge closure."
            raise ValueError(msg)

        gap = float(np.linalg.norm(coords[0] - coords[-1]))
        threshold = 1e-6 * chord
        if gap <= threshold:
            return coords

        average_point = (coords[0] + coords[-1]) / 2.0
        return np.vstack([coords, average_point])

    def export_for_meshing(self, output_path: str) -> str:
        if not output_path.strip():
            msg = "output_path must be a non-empty string."
            raise ValueError(msg)

        if self._coords is None:
            self.load()

        assert self._coords is not None
        clean_coords = self.close_trailing_edge(self._coords)
        self._coords = clean_coords

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        np.savetxt(output, clean_coords, delimiter=",", header="x,y", comments="")
        return str(output)
