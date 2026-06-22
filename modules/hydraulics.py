"""Cálculo geométrico e hidráulico por sección transversal."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq

G = 9.80665
GAMMA_W = 9810.0


def prepare_section(section_df: pd.DataFrame) -> pd.DataFrame:
    sec = section_df[["x_m", "z_m"]].copy()
    sec["x_m"] = pd.to_numeric(sec["x_m"], errors="coerce")
    sec["z_m"] = pd.to_numeric(sec["z_m"], errors="coerce")
    sec = sec.dropna().sort_values("x_m")
    return sec


def section_properties_at_wse(section_df: pd.DataFrame, wse: float) -> dict:
    sec = prepare_section(section_df)
    x = sec["x_m"].values.astype(float)
    z = sec["z_m"].values.astype(float)
    if len(x) < 2:
        return {"area_m2": 0, "perimetro_m": 0, "ancho_superficial_m": 0, "tirante_max_m": 0, "tirante_medio_m": 0}
    area = 0.0
    perim = 0.0
    wet_x = []
    for i in range(len(x) - 1):
        x1, x2 = x[i], x[i + 1]
        z1, z2 = z[i], z[i + 1]
        h1, h2 = wse - z1, wse - z2
        dx = x2 - x1
        seg_len = float(np.hypot(dx, z2 - z1))
        if h1 <= 0 and h2 <= 0:
            continue
        if h1 > 0 and h2 > 0:
            area += 0.5 * (h1 + h2) * dx
            perim += seg_len
            wet_x += [x1, x2]
        else:
            # intersección con lámina
            frac = (wse - z1) / (z2 - z1) if z2 != z1 else 0.0
            xi = x1 + frac * dx
            if h1 > 0:
                area += 0.5 * h1 * abs(xi - x1)
                perim += float(np.hypot(xi - x1, wse - z1))
                wet_x += [x1, xi]
            elif h2 > 0:
                area += 0.5 * h2 * abs(x2 - xi)
                perim += float(np.hypot(x2 - xi, z2 - wse))
                wet_x += [xi, x2]
    width = max(wet_x) - min(wet_x) if wet_x else 0.0
    hmax = max(0.0, float(wse - np.nanmin(z)))
    hmean = area / width if width > 0 else 0.0
    return {
        "area_m2": max(area, 0.0),
        "perimetro_m": max(perim, 0.0),
        "ancho_superficial_m": max(width, 0.0),
        "tirante_max_m": hmax,
        "tirante_medio_m": max(hmean, 0.0),
    }


def manning_capacity(area: float, perimeter: float, slope: float, n: float) -> float:
    if area <= 0 or perimeter <= 0 or slope <= 0 or n <= 0:
        return 0.0
    r = area / perimeter
    return (1.0 / n) * area * (r ** (2 / 3)) * (slope ** 0.5)


def solve_wse_for_q(section_df: pd.DataFrame, q: float, slope: float, n: float, freeboard: float = 5.0) -> float:
    sec = prepare_section(section_df)
    zmin, zmax = float(sec["z_m"].min()), float(sec["z_m"].max())
    low = zmin + 1e-4
    high = zmax + freeboard
    def f(wse):
        p = section_properties_at_wse(sec, wse)
        return manning_capacity(p["area_m2"], p["perimetro_m"], slope, n) - q
    if f(high) < 0:
        return high
    try:
        return float(brentq(f, low, high, maxiter=80))
    except Exception:
        return high


def compute_hydraulics_for_sections(sections: pd.DataFrame, valid_status: pd.DataFrame, profile: pd.DataFrame, design_flows: pd.DataFrame, default_n: float = 0.04, flow_profile: pd.DataFrame | None = None) -> pd.DataFrame:
    rows = []
    if valid_status.empty:
        return pd.DataFrame()
    valid_ids = valid_status.loc[valid_status["estado"].isin(["Válida", "Revisar manualmente"]), "id_seccion"].tolist()
    profile_sorted = profile.sort_values("km") if "km" in profile.columns else profile
    for sid in valid_ids:
        g = sections[sections["id_seccion"] == sid].copy()
        if g.empty:
            continue
        km = float(pd.to_numeric(g["km"], errors="coerce").dropna().iloc[0])
        slope = 0.005
        n = default_n
        if not profile_sorted.empty and "km" in profile_sorted.columns:
            prof = profile_sorted.copy()
            for c in ["km", "pendiente_local", "rugosidad_manning_n"]:
                if c in prof.columns:
                    prof[c] = pd.to_numeric(prof[c], errors="coerce")
            if "pendiente_local" in prof.columns:
                slope_val = np.interp(km, prof["km"].dropna(), prof["pendiente_local"].ffill().bfill())
                if np.isfinite(slope_val) and slope_val > 0:
                    slope = float(slope_val)
            if "rugosidad_manning_n" in prof.columns:
                n_val = np.interp(km, prof["km"].dropna(), prof["rugosidad_manning_n"].fillna(default_n))
                if np.isfinite(n_val) and n_val > 0:
                    n = float(n_val)
        for _, flow in design_flows.iterrows():
            T = int(flow["periodo_retorno"])
            q_default = float(flow["caudal_adoptado_m3s"])
            q = q_default
            q_obs = "caudal uniforme de diseño"
            if flow_profile is not None and not flow_profile.empty:
                fp = flow_profile[(flow_profile["periodo_retorno"].astype(int) == T) & (flow_profile["id_seccion"].astype(str) == str(sid))]
                if fp.empty:
                    tmp = flow_profile[flow_profile["periodo_retorno"].astype(int) == T].copy()
                    if not tmp.empty and "km" in tmp.columns:
                        tmp["_dist"] = (pd.to_numeric(tmp["km"], errors="coerce") - km).abs()
                        fp = tmp.sort_values("_dist").head(1)
                if not fp.empty:
                    q = float(fp.iloc[0].get("caudal_km_m3s", q_default))
                    q_obs = str(fp.iloc[0].get("observaciones_caudal_km", "caudal por km"))
            wse = solve_wse_for_q(g, q, slope, n)
            props = section_properties_at_wse(g, wse)
            area, per, width = props["area_m2"], props["perimetro_m"], props["ancho_superficial_m"]
            R = area / per if per > 0 else 0.0
            V = q / area if area > 0 else np.nan
            D = area / width if width > 0 else 0.0
            Fr = V / np.sqrt(G * D) if D > 0 and np.isfinite(V) else np.nan
            tau = GAMMA_W * R * slope
            omega = tau * V if np.isfinite(V) else np.nan
            regime = "subcrítico" if np.isfinite(Fr) and Fr < 0.8 else "crítico" if np.isfinite(Fr) and Fr <= 1.2 else "supercrítico" if np.isfinite(Fr) else "sin dato"
            overtopping = wse > float(g["z_m"].max())
            rows.append({
                "id_seccion": sid, "km": km, "periodo_retorno": T, "caudal_m3s": q,
                "caudal_base_diseno_m3s": q_default, "observaciones_caudal_km": q_obs,
                "cota_agua_m": wse, "area_m2": area, "perimetro_m": per,
                "radio_hidraulico_m": R, "ancho_superficial_m": width,
                "tirante_medio_m": props["tirante_medio_m"], "tirante_max_m": props["tirante_max_m"],
                "velocidad_m_s": V, "froude": Fr, "pendiente_energia": slope,
                "manning_n": n, "esfuerzo_cortante_pa": tau, "potencia_corriente_w_m2": omega,
                "regimen": regime, "posible_desborde": bool(overtopping),
            })
    return pd.DataFrame(rows)
