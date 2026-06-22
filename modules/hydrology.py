"""Métodos hidrológicos preliminares para caudales de diseño."""
from __future__ import annotations

import numpy as np
import pandas as pd

RETURN_PERIODS = [2, 5, 10, 25, 50, 100, 200]


def _scalar(df: pd.DataFrame, col: str, default=None):
    if col in df.columns and not df[col].dropna().empty:
        return df[col].dropna().iloc[0]
    return default


def recommend_method(area_km2: float, has_flow_data: bool, has_precip: bool) -> str:
    if has_flow_data:
        return "Análisis de frecuencia / contraste fluviométrico"
    if area_km2 < 20 and has_precip:
        return "Racional o racional modificado"
    if 20 <= area_km2 <= 10000 and has_precip:
        return "DGA-AC / Verni-King modificado / regional + contraste"
    if has_precip:
        return "Método regional con advertencia y caudal adoptado manual"
    return "Caudal manual requerido por falta de datos"


def intensity_from_precip(precip: pd.DataFrame) -> pd.DataFrame:
    out = precip.copy()
    if "intensidad_mm_h" not in out.columns:
        out["intensidad_mm_h"] = np.nan
    if "duracion_h" in out.columns and "precipitacion_mm" in out.columns:
        mask = out["intensidad_mm_h"].isna() & out["duracion_h"].gt(0)
        out.loc[mask, "intensidad_mm_h"] = out.loc[mask, "precipitacion_mm"] / out.loc[mask, "duracion_h"]
    return out


def rational_q(area_km2: float, intensity_mm_h: float, runoff_c: float, factor: float = 1.0) -> float:
    # Q [m3/s] = 0.278 C I A, con I mm/h y A km2
    return 0.278 * float(runoff_c) * float(intensity_mm_h) * float(area_km2) * float(factor)


def build_design_flows(
    cuenca: pd.DataFrame,
    precipitacion: pd.DataFrame,
    manual_flows: pd.DataFrame | None = None,
    mode: str = "calculado",
) -> pd.DataFrame:
    area = float(_scalar(cuenca, "area_km2", 1.0) or 1.0)
    c = float(_scalar(cuenca, "coeficiente_escorrentia_c", 0.45) or 0.45)
    tc = float(_scalar(cuenca, "tiempo_concentracion_h", 1.0) or 1.0)
    precip = intensity_from_precip(precipitacion)
    rows = []
    method = recommend_method(area, manual_flows is not None and not manual_flows.empty, not precip.empty)
    for T in RETURN_PERIODS:
        pT = precip[pd.to_numeric(precip.get("periodo_retorno", pd.Series(dtype=float)), errors="coerce") == T] if not precip.empty else pd.DataFrame()
        if pT.empty:
            # extrapolación simple de apoyo: I crece logarítmicamente si no hay dato
            base_i = float(pd.to_numeric(precip.get("intensidad_mm_h", pd.Series([25.0])), errors="coerce").dropna().median() if not precip.empty else 25.0)
            intensidad = base_i * (1 + 0.12 * np.log(max(T, 2) / 2))
            precip_mm = intensidad * tc
            obs = "precipitación interpolada/asumida"
        else:
            # usar duración más cercana al tiempo de concentración
            pT = pT.copy()
            pT["diff_tc"] = (pd.to_numeric(pT["duracion_h"], errors="coerce") - tc).abs()
            rec = pT.sort_values("diff_tc").iloc[0]
            intensidad = float(rec.get("intensidad_mm_h", np.nan))
            precip_mm = float(rec.get("precipitacion_mm", intensidad * tc if np.isfinite(intensidad) else np.nan))
            obs = str(rec.get("observaciones", ""))
        q_calc = rational_q(area, intensidad, c)
        q_adopt = q_calc
        if manual_flows is not None and not manual_flows.empty and "periodo_retorno" in manual_flows.columns:
            m = manual_flows[pd.to_numeric(manual_flows["periodo_retorno"], errors="coerce") == T]
            if not m.empty and "caudal_m3s" in m.columns:
                q_adopt = float(pd.to_numeric(m["caudal_m3s"], errors="coerce").dropna().iloc[0])
                obs += " | caudal manual adoptado"
        if T == 200 and "DGA" in method:
            obs += " | T=200 puede exceder rango recomendado de métodos regionales"
        rows.append({
            "periodo_retorno": T,
            "precipitacion_adoptada_mm": precip_mm,
            "intensidad_adoptada_mm_h": intensidad,
            "tiempo_concentracion_h": tc,
            "metodo_utilizado": "Manual" if mode.lower().startswith("manual") else method,
            "coeficiente_escorrentia_c": c,
            "area_km2": area,
            "caudal_calculado_m3s": q_calc,
            "caudal_adoptado_m3s": q_adopt,
            "observaciones_tecnicas": obs,
        })
    return pd.DataFrame(rows)
