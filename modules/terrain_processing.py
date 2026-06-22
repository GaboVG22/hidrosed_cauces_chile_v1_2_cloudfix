"""Procesamiento de terreno: DEM, curvas y grillas."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.interpolate import griddata


def contours_to_grid(points: pd.DataFrame, resolution: float = 0.0002, method: str = "linear") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Interpola una grilla lon/lat/elev desde puntos de curvas. resolution en grados."""
    pts = points.dropna(subset=["lon", "lat", "elev_m"]).copy()
    if len(pts) < 4:
        raise ValueError("Se requieren al menos 4 puntos con cota para interpolar terreno.")
    lon = pts["lon"].astype(float).values
    lat = pts["lat"].astype(float).values
    z = pts["elev_m"].astype(float).values
    gx, gy = np.meshgrid(np.arange(lon.min(), lon.max(), resolution), np.arange(lat.min(), lat.max(), resolution))
    gz = griddata((lon, lat), z, (gx, gy), method=method)
    if np.isnan(gz).any():
        gz_nearest = griddata((lon, lat), z, (gx, gy), method="nearest")
        gz = np.where(np.isnan(gz), gz_nearest, gz)
    return gx, gy, gz


def read_dem_raster(path: str | Path):
    import rasterio
    src = rasterio.open(path)
    arr = src.read(1, masked=True).filled(np.nan)
    return src, arr


def hillshade(elevation: np.ndarray, azimuth: float = 315, angle_altitude: float = 45) -> np.ndarray:
    x, y = np.gradient(elevation)
    slope = np.pi / 2. - np.arctan(np.sqrt(x * x + y * y))
    aspect = np.arctan2(-x, y)
    az = np.deg2rad(azimuth)
    alt = np.deg2rad(angle_altitude)
    shaded = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    return 255 * (shaded + 1) / 2


def sample_profile_from_dem(profile: pd.DataFrame, axis_df: pd.DataFrame | None = None, dem_path: str | Path | None = None) -> pd.DataFrame:
    # Placeholder robusto: si no hay raster/axis retorna perfil original.
    return profile.copy()
