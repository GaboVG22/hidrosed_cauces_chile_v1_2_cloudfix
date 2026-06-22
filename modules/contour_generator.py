"""Generación y exportación de curvas de nivel desde una grilla."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd


def contours_from_grid(gx, gy, gz, interval: float = 5.0) -> pd.DataFrame:
    import skimage.measure as measure
    zmin, zmax = float(np.nanmin(gz)), float(np.nanmax(gz))
    levels = np.arange(np.floor(zmin / interval) * interval, np.ceil(zmax / interval) * interval + interval, interval)
    rows = []
    for level in levels:
        cs = measure.find_contours(gz, level=level)
        for i, c in enumerate(cs):
            # c: row, col. convertir por índices nearest
            for pt in c[::max(1, len(c)//300)]:
                r, col = int(round(pt[0])), int(round(pt[1]))
                r = np.clip(r, 0, gx.shape[0] - 1); col = np.clip(col, 0, gx.shape[1] - 1)
                rows.append({"nivel_m": level, "linea": f"CN_{level:.0f}_{i}", "lon": float(gx[r, col]), "lat": float(gy[r, col])})
    return pd.DataFrame(rows)
