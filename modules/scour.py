"""Estimación preliminar de socavación y depositación."""
from __future__ import annotations
import numpy as np
import pandas as pd


def compute_scour_deposition(hyd: pd.DataFrame, sed: pd.DataFrame, routing: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if hyd is None or hyd.empty or sed is None or sed.empty:
        return pd.DataFrame(), pd.DataFrame()
    merged = hyd.merge(sed[["id_seccion", "periodo_retorno", "relacion_movilidad", "volumen_potencial_m3", "condicion_movilidad"]], on=["id_seccion", "periodo_retorno"], how="left")
    sc_rows, dep_rows = [], []
    for _, r in merged.iterrows():
        mobility = float(r.get("relacion_movilidad", np.nan))
        vel = float(r.get("velocidad_m_s", np.nan))
        h = float(r.get("tirante_max_m", 0.0))
        scour_depth = max(0.0, min(0.6 * h, 0.15 * h * max(mobility - 1.0, 0.0))) if np.isfinite(mobility) else 0.0
        deposition_depth = 0.0
        if np.isfinite(vel) and vel < 0.6 and mobility < 1.0:
            deposition_depth = 0.05 * h
        sc_rows.append({
            "id_seccion": r["id_seccion"], "km": r["km"], "periodo_retorno": r["periodo_retorno"],
            "tipo_socavacion": "general preliminar", "profundidad_socavacion_m": scour_depth,
            "criterio": "exceso de movilidad Shields + limitación por tirante", "observaciones": "revisar con método específico si existe obra"
        })
        dep_rows.append({
            "id_seccion": r["id_seccion"], "km": r["km"], "periodo_retorno": r["periodo_retorno"],
            "profundidad_depositacion_m": deposition_depth,
            "tendencia_depositacion": "probable" if deposition_depth > 0 else "baja/no detectada",
            "criterio": "baja velocidad y movilidad menor a 1"
        })
    return pd.DataFrame(sc_rows), pd.DataFrame(dep_rows)
