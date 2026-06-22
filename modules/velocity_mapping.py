"""Mapeo aproximado de velocidad y peligrosidad."""
from __future__ import annotations
import numpy as np

G = 9.80665


def velocity_grid_from_depth(depth: np.ndarray, slope: float = 0.005, n: float = 0.05) -> np.ndarray:
    depth = np.maximum(depth, 0.0)
    v = (1.0 / max(n, 1e-6)) * (depth ** (2.0 / 3.0)) * (max(slope, 1e-6) ** 0.5)
    return np.where(depth > 0, v, 0.0)


def classify_velocity(v: np.ndarray) -> np.ndarray:
    cls = np.zeros_like(v, dtype=np.uint8)
    cls[(v >= 1.0) & (v < 2.0)] = 1
    cls[(v >= 2.0) & (v < 3.0)] = 2
    cls[v >= 3.0] = 3
    return cls


def hazard_index(depth: np.ndarray, velocity: np.ndarray) -> np.ndarray:
    return depth * velocity


def velocity_summary(v: np.ndarray, depth: np.ndarray, cell_area_m2: float = 900.0) -> dict:
    wet = depth > 0
    crit = v >= 3.0
    return {
        "velocidad_max_m_s": float(np.nanmax(v)) if wet.any() else 0.0,
        "velocidad_media_m_s": float(np.nanmean(v[wet])) if wet.any() else 0.0,
        "area_critica_velocidad_ha": float((crit & wet).sum() * cell_area_m2 / 10000.0),
        "hv_max_m2_s": float(np.nanmax(hazard_index(depth, v))) if wet.any() else 0.0,
    }
