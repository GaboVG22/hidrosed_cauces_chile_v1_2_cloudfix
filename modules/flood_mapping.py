"""Mapeo aproximado de inundación en planta."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.interpolate import griddata
from scipy import ndimage


def build_water_surface_grid(gx: np.ndarray, gy: np.ndarray, hydraulic_profile: pd.DataFrame, axis_df: pd.DataFrame | None = None) -> np.ndarray:
    """Interpola cota de agua sobre grilla.

    Si existe axis_df con lon/lat/km, se usa para ubicar cada km. Si no, asume que el cauce
    cruza diagonalmente el dominio y distribuye km proporcionalmente.
    """
    hp = hydraulic_profile.dropna(subset=["km", "cota_agua_m"]).copy()
    if hp.empty:
        return np.full_like(gx, np.nan, dtype=float)
    if axis_df is not None and not axis_df.empty and {"km", "lon", "lat"}.issubset(axis_df.columns):
        axis = axis_df.dropna(subset=["km", "lon", "lat"]).sort_values("km")
        pts = []
        vals = []
        for _, h in hp.iterrows():
            lon = np.interp(h["km"], axis["km"], axis["lon"])
            lat = np.interp(h["km"], axis["km"], axis["lat"])
            pts.append((lon, lat)); vals.append(h["cota_agua_m"])
    else:
        kmin, kmax = hp["km"].min(), hp["km"].max()
        lon_min, lon_max = np.nanmin(gx), np.nanmax(gx)
        lat_min, lat_max = np.nanmin(gy), np.nanmax(gy)
        pts, vals = [], []
        for _, h in hp.iterrows():
            t = 0 if kmax == kmin else (h["km"] - kmin) / (kmax - kmin)
            pts.append((lon_min + t * (lon_max - lon_min), lat_min + t * (lat_max - lat_min)))
            vals.append(h["cota_agua_m"])
    if len(pts) == 1:
        return np.full_like(gx, vals[0], dtype=float)
    wse = griddata(np.array(pts), np.array(vals), (gx, gy), method="linear")
    if np.isnan(wse).any():
        nearest = griddata(np.array(pts), np.array(vals), (gx, gy), method="nearest")
        wse = np.where(np.isnan(wse), nearest, wse)
    return wse


def compute_depth_grid(wse_grid: np.ndarray, terrain_grid: np.ndarray) -> np.ndarray:
    depth = wse_grid - terrain_grid
    return np.where(np.isfinite(depth) & (depth > 0), depth, 0.0)


def connectivity_filter(depth: np.ndarray, seed_mask: np.ndarray | None = None, min_cells: int = 8) -> np.ndarray:
    wet = depth > 0
    if not wet.any():
        return wet
    labeled, n = ndimage.label(wet)
    if seed_mask is None or not seed_mask.any():
        # conservar componente principal
        counts = np.bincount(labeled.ravel())
        counts[0] = 0
        keep = counts.argmax()
        mask = labeled == keep
    else:
        keep_labels = np.unique(labeled[seed_mask & wet])
        keep_labels = keep_labels[keep_labels != 0]
        mask = np.isin(labeled, keep_labels)
    # eliminar polígonos espurios pequeños
    lab2, n2 = ndimage.label(mask)
    counts = np.bincount(lab2.ravel())
    bad = [i for i, c in enumerate(counts) if i != 0 and c < min_cells]
    for b in bad:
        mask[lab2 == b] = False
    return mask


def flood_summary(depth: np.ndarray, cell_area_m2: float = 900.0) -> dict:
    wet = depth > 0
    return {
        "area_inundada_m2": float(wet.sum() * cell_area_m2),
        "area_inundada_ha": float(wet.sum() * cell_area_m2 / 10000.0),
        "profundidad_max_m": float(np.nanmax(depth)) if wet.any() else 0.0,
        "profundidad_media_m": float(np.nanmean(depth[wet])) if wet.any() else 0.0,
    }
