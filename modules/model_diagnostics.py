"""Chequeos automáticos para tres corridas de revisión."""
from __future__ import annotations
import pandas as pd


def run_technical_checks(flows: pd.DataFrame, hyd: pd.DataFrame, flood_summary: pd.DataFrame | None = None) -> list[str]:
    issues = []
    if flows is not None and not flows.empty:
        q = flows.sort_values("periodo_retorno")["caudal_adoptado_m3s"].values
        if any(q[i] > q[i+1] for i in range(len(q)-1)):
            issues.append("Caudales adoptados no son monótonos crecientes con T.")
    if hyd is not None and not hyd.empty:
        for sid, g in hyd.groupby("id_seccion"):
            pivot = g.sort_values("periodo_retorno")["tirante_max_m"].values
            if any(pivot[i] > pivot[i+1] + 1e-6 for i in range(len(pivot)-1)):
                issues.append(f"Tirantes no crecen con T en sección {sid}.")
        if "velocidad_m_s" in hyd.columns and (pd.to_numeric(hyd["velocidad_m_s"], errors="coerce") > 6).any():
            issues.append("Existen velocidades mayores a 6 m/s; revisar n, pendiente, geometría o caudal.")
        if "froude" in hyd.columns and (pd.to_numeric(hyd["froude"], errors="coerce") > 1.2).any():
            issues.append("Se detectan tramos supercríticos; revisar control hidráulico y posible resalto.")
        if "solver_ok" in hyd.columns and (~hyd["solver_ok"].astype(bool)).any():
            issues.append("El solver de energía no convergió estrictamente en una o más secciones; revisar condición de borde/régimen/geometría.")
        if "residual_energia_m" in hyd.columns:
            residual = pd.to_numeric(hyd["residual_energia_m"], errors="coerce").abs()
            if residual.max() > 0.25:
                issues.append(f"Residual máximo de energía {residual.max():.2f} m; revisar tramos con cierre energético deficiente.")
        if "posible_desborde" in hyd.columns and hyd["posible_desborde"].astype(bool).any():
            issues.append("Existen secciones con posible desborde; revisar extensión de secciones y planicie.")
    if flood_summary is not None and not flood_summary.empty and "profundidad_max_m" in flood_summary.columns:
        if (flood_summary["profundidad_max_m"] < 0).any():
            issues.append("Profundidades negativas en mapa de inundación.")
    return issues
