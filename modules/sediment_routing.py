"""Balance sedimentológico por tramos usando lógica Exner simplificada."""
from __future__ import annotations
import numpy as np
import pandas as pd


def exner_balance(sed: pd.DataFrame, porosity: float = 0.35) -> pd.DataFrame:
    if sed is None or sed.empty:
        return pd.DataFrame()
    rows = []
    for T, g in sed.sort_values("km").groupby("periodo_retorno"):
        gg = g.sort_values("km").reset_index(drop=True)
        for i in range(len(gg) - 1):
            a, b = gg.iloc[i], gg.iloc[i + 1]
            dx = max((b["km"] - a["km"]) * 1000.0, 1.0)
            qsin = float(a.get("gasto_solido_m3s", 0.0))
            qsout = float(b.get("gasto_solido_m3s", 0.0))
            dq = qsout - qsin
            width = max(float(b.get("ancho_superficial_m", 10.0) if "ancho_superficial_m" in b else 10.0), 1.0)
            dz_rate = -dq / ((1 - porosity) * width * dx)
            tendency = "erosión/degradación" if dz_rate < 0 else "depositación/agradación" if dz_rate > 0 else "equilibrio"
            rows.append({
                "periodo_retorno": T, "km_inicio": a["km"], "km_fin": b["km"],
                "gasto_solido_entrada_m3s": qsin, "gasto_solido_salida_m3s": qsout,
                "delta_qs_m3s": dq, "delta_z_relativo_m_s": dz_rate,
                "tendencia": tendency,
            })
    return pd.DataFrame(rows)
