"""Transporte de sedimentos preliminar."""
from __future__ import annotations
import numpy as np
import pandas as pd

RHO_W = 1000.0
RHO_S = 2650.0
G = 9.80665
THETA_C_DEFAULT = 0.047


def interpolate_granulometry(gran: pd.DataFrame, km_values) -> pd.DataFrame:
    if gran is None or gran.empty:
        return pd.DataFrame({"km": km_values, "d50_mm": 40.0, "d84_mm": 90.0, "fuente_granulometria": "asumida"})
    g = gran.copy().sort_values("km")
    for col in ["km", "d16_mm", "d35_mm", "d50_mm", "d65_mm", "d84_mm", "d90_mm", "peso_especifico_sedimento", "porosidad"]:
        if col in g.columns:
            g[col] = pd.to_numeric(g[col], errors="coerce")
    rows = []
    x = g["km"].values
    for km in km_values:
        row = {"km": km, "fuente_granulometria": "interpolada"}
        for col in ["d16_mm", "d35_mm", "d50_mm", "d65_mm", "d84_mm", "d90_mm", "peso_especifico_sedimento", "porosidad"]:
            if col in g.columns and g[col].notna().any():
                row[col] = float(np.interp(km, x, g[col].interpolate().bfill().ffill().values))
        if "d50_mm" not in row or not np.isfinite(row["d50_mm"]):
            row["d50_mm"] = 40.0
            row["fuente_granulometria"] = "asumida"
        if "d84_mm" not in row:
            row["d84_mm"] = row["d50_mm"] * 2.0
        if "porosidad" not in row:
            row["porosidad"] = 0.35
        rows.append(row)
    return pd.DataFrame(rows)


def shields_critical_shear(d50_mm: float, theta_c: float = THETA_C_DEFAULT, rho_s: float = RHO_S) -> float:
    d = d50_mm / 1000.0
    return theta_c * (rho_s - RHO_W) * G * d


def mpm_transport_qb(tau: float, d50_mm: float, theta_c: float = THETA_C_DEFAULT) -> float:
    """Transporte unitario de fondo MPM simplificado [m2/s] equivalente volumétrico por unidad de ancho."""
    d = max(d50_mm / 1000.0, 1e-6)
    theta = tau / ((RHO_S - RHO_W) * G * d)
    excess = max(theta - theta_c, 0.0)
    qb = 8.0 * (excess ** 1.5) * np.sqrt((RHO_S / RHO_W - 1) * G * d ** 3)
    return float(qb)


def compute_sediment_transport(hyd: pd.DataFrame, granulometria: pd.DataFrame, event_duration_h: float = 6.0) -> pd.DataFrame:
    if hyd is None or hyd.empty:
        return pd.DataFrame()
    gran = interpolate_granulometry(granulometria, sorted(hyd["km"].unique()))
    rows = []
    for _, r in hyd.iterrows():
        km = float(r["km"])
        gr = gran.iloc[(gran["km"] - km).abs().argsort()[:1]].iloc[0]
        d50 = float(gr.get("d50_mm", 40.0))
        tau = float(r.get("esfuerzo_cortante_pa", 0.0))
        tau_c = shields_critical_shear(d50)
        mobility = tau / tau_c if tau_c > 0 else np.nan
        qb = mpm_transport_qb(tau, d50)
        width = float(r.get("ancho_superficial_m", 1.0) or 1.0)
        qs_m3s = qb * width
        volume = qs_m3s * event_duration_h * 3600.0
        if mobility < 1:
            cls = "estable"
        elif mobility < 1.5:
            cls = "movilidad incipiente"
        elif mobility < 3:
            cls = "movilidad moderada"
        else:
            cls = "alta movilidad"
        rows.append({
            "id_seccion": r.get("id_seccion"), "km": km, "periodo_retorno": int(r["periodo_retorno"]),
            "d50_mm": d50, "d84_mm": gr.get("d84_mm"), "tau_actuante_pa": tau,
            "tau_critico_pa": tau_c, "relacion_movilidad": mobility,
            "condicion_movilidad": cls, "transporte_unitario_fondo_m2s": qb,
            "gasto_solido_m3s": qs_m3s, "duracion_evento_h": event_duration_h,
            "volumen_potencial_m3": volume, "fuente_granulometria": gr.get("fuente_granulometria", "")
        })
    return pd.DataFrame(rows)
