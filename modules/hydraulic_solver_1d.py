"""Motor hidráulico 1D avanzado tipo paso estándar.

Objetivo del módulo
-------------------
Acercar la aplicación a la lógica de HEC-RAS 1D en flujo permanente,
resolviendo la ecuación de energía entre secciones mediante método del paso
estándar. No reemplaza HEC-RAS, pero mejora fuertemente la conexión hidráulica
entre secciones respecto de un cálculo local con tirante normal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.optimize import brentq, minimize_scalar

from modules.hydraulics import (
    G,
    GAMMA_W,
    prepare_section,
    section_properties_at_wse,
    solve_wse_for_q,
    compute_hydraulics_for_sections,
)


@dataclass
class BoundaryCondition:
    tipo: str = "normal_depth"  # normal_depth | known_wse | critical_depth
    ubicacion: str = "aguas_abajo"  # aguas_abajo | aguas_arriba
    valor: float | None = None
    unidad: str = "m"
    observacion: str = "Condición de borde por defecto"


@dataclass
class StepResult:
    wse: float
    residual: float
    iteraciones: int
    perdida_friccion: float
    perdida_local: float
    coef_usado: float
    sf_known: float
    sf_unknown: float
    ok: bool
    mensaje: str


# ---------------------------------------------------------------------------
# Utilidades de geometría hidráulica
# ---------------------------------------------------------------------------

def _safe_float(value: Any, default: float = np.nan) -> float:
    try:
        v = float(value)
        return v if np.isfinite(v) else default
    except Exception:
        return default


def _section_by_id(sections: pd.DataFrame, sid: Any) -> pd.DataFrame:
    return sections[sections["id_seccion"].astype(str) == str(sid)].copy()


def section_bottom(section_df: pd.DataFrame) -> float:
    sec = prepare_section(section_df)
    if sec.empty:
        return np.nan
    return float(sec["z_m"].min())


def section_top(section_df: pd.DataFrame) -> float:
    sec = prepare_section(section_df)
    if sec.empty:
        return np.nan
    return float(sec["z_m"].max())


def section_conveyance(section_df: pd.DataFrame, wse: float, n: float) -> float:
    """Conveyance K = (1/n) A R^(2/3)."""
    props = section_properties_at_wse(section_df, wse)
    area = props["area_m2"]
    per = props["perimetro_m"]
    if area <= 0 or per <= 0 or n <= 0:
        return 0.0
    r = area / per
    return (1.0 / n) * area * (r ** (2.0 / 3.0))


def friction_slope(q: float, section_df: pd.DataFrame, wse: float, n: float) -> float:
    K = section_conveyance(section_df, wse, n)
    if K <= 0:
        return np.nan
    return (q / K) ** 2


def velocity_head(q: float, section_df: pd.DataFrame, wse: float, alpha: float = 1.0) -> float:
    props = section_properties_at_wse(section_df, wse)
    area = props["area_m2"]
    if area <= 0:
        return np.nan
    v = q / area
    return alpha * v * v / (2.0 * G)


def total_energy(q: float, section_df: pd.DataFrame, wse: float, alpha: float = 1.0) -> float:
    hv = velocity_head(q, section_df, wse, alpha)
    if not np.isfinite(hv):
        return np.nan
    return wse + hv


def specific_energy(q: float, section_df: pd.DataFrame, wse: float, alpha: float = 1.0) -> float:
    y = max(0.0, wse - section_bottom(section_df))
    hv = velocity_head(q, section_df, wse, alpha)
    if not np.isfinite(hv):
        return np.nan
    return y + hv


def hydraulic_parameters_at_wse(section_df: pd.DataFrame, q: float, wse: float, slope: float, n: float) -> dict[str, Any]:
    props = section_properties_at_wse(section_df, wse)
    area = props["area_m2"]
    per = props["perimetro_m"]
    width = props["ancho_superficial_m"]
    R = area / per if per > 0 else 0.0
    V = q / area if area > 0 else np.nan
    D = area / width if width > 0 else 0.0
    Fr = V / np.sqrt(G * D) if D > 0 and np.isfinite(V) else np.nan
    tau = GAMMA_W * R * slope if np.isfinite(slope) else np.nan
    omega = tau * V if np.isfinite(tau) and np.isfinite(V) else np.nan
    regime = "sin dato"
    if np.isfinite(Fr):
        if Fr < 0.8:
            regime = "subcrítico"
        elif Fr <= 1.2:
            regime = "crítico"
        else:
            regime = "supercrítico"
    return {
        **props,
        "radio_hidraulico_m": R,
        "velocidad_m_s": V,
        "froude": Fr,
        "esfuerzo_cortante_pa": tau,
        "potencia_corriente_w_m2": omega,
        "regimen": regime,
        "carga_velocidad_m": velocity_head(q, section_df, wse),
        "energia_total_m": total_energy(q, section_df, wse),
        "energia_especifica_m": specific_energy(q, section_df, wse),
        "pendiente_friccion": friction_slope(q, section_df, wse, n),
    }


def critical_wse(section_df: pd.DataFrame, q: float, freeboard: float = 20.0) -> float:
    """Calcula cota crítica aproximada para una sección irregular.

    Se intenta resolver F^2 = Q^2*T/(g*A^3) = 1. Si no hay cambio de signo,
    se minimiza la energía específica en un intervalo razonable.
    """
    sec = prepare_section(section_df)
    if sec.empty or q <= 0:
        return np.nan
    zmin = float(sec["z_m"].min())
    zmax = float(sec["z_m"].max()) + freeboard
    low = zmin + 1e-4
    high = zmax

    def crit_func(wse: float) -> float:
        p = section_properties_at_wse(sec, wse)
        A = p["area_m2"]
        T = p["ancho_superficial_m"]
        if A <= 0 or T <= 0:
            return np.nan
        return (q * q * T) / (G * A ** 3) - 1.0

    # Buscar brackets en una malla para secciones irregulares.
    grid = np.linspace(low, high, 80)
    vals = np.array([crit_func(w) for w in grid], dtype=float)
    for i in range(len(grid) - 1):
        if np.isfinite(vals[i]) and np.isfinite(vals[i + 1]) and vals[i] * vals[i + 1] <= 0:
            try:
                return float(brentq(crit_func, grid[i], grid[i + 1], maxiter=100))
            except Exception:
                pass

    def obj(wse: float) -> float:
        e = specific_energy(q, sec, wse)
        return e if np.isfinite(e) else 1e12

    try:
        res = minimize_scalar(obj, bounds=(low, high), method="bounded", options={"xatol": 1e-4})
        return float(res.x)
    except Exception:
        return np.nan


# ---------------------------------------------------------------------------
# Parsing de hojas de entrada
# ---------------------------------------------------------------------------

def get_distance_at_km(profile: pd.DataFrame, km: float) -> float:
    if profile is None or profile.empty:
        return km * 1000.0
    prof = profile.copy()
    for c in ["km", "distancia_m"]:
        if c not in prof.columns:
            return km * 1000.0
        prof[c] = pd.to_numeric(prof[c], errors="coerce")
    prof = prof.dropna(subset=["km", "distancia_m"]).sort_values("km")
    if prof.empty:
        return km * 1000.0
    return float(np.interp(km, prof["km"].values, prof["distancia_m"].values))


def slope_and_n_at_km(profile: pd.DataFrame, km: float, default_n: float = 0.04) -> tuple[float, float]:
    slope = 0.005
    n = default_n
    if profile is None or profile.empty or "km" not in profile.columns:
        return slope, n
    prof = profile.copy()
    prof["km"] = pd.to_numeric(prof["km"], errors="coerce")
    prof = prof.dropna(subset=["km"]).sort_values("km")
    if prof.empty:
        return slope, n
    if "pendiente_local" in prof.columns:
        vals = pd.to_numeric(prof["pendiente_local"], errors="coerce").ffill().bfill().fillna(slope).values
        val = float(np.interp(km, prof["km"].values, vals))
        if np.isfinite(val) and val > 0:
            slope = val
    if "rugosidad_manning_n" in prof.columns:
        vals = pd.to_numeric(prof["rugosidad_manning_n"], errors="coerce").ffill().bfill().fillna(default_n).values
        val = float(np.interp(km, prof["km"].values, vals))
        if np.isfinite(val) and val > 0:
            n = val
    return slope, n


def section_manning(section_df: pd.DataFrame, fallback_n: float = 0.04) -> float:
    """Obtiene Manning de la sección si existe columna específica o por material.

    Esta versión usa un valor representativo por sección. En una etapa posterior
    puede ampliarse a conveyance compuesto por cauce principal y planicies.
    """
    for col in ["n_manning", "rugosidad_manning_n", "manning_n"]:
        if col in section_df.columns:
            vals = pd.to_numeric(section_df[col], errors="coerce").dropna()
            if not vals.empty and vals.median() > 0:
                return float(vals.median())
    if "material" in section_df.columns:
        mats = " ".join(section_df["material"].dropna().astype(str).str.lower().unique().tolist())
        material_n = {
            "hormigon": 0.015,
            "hormigón": 0.015,
            "roca": 0.035,
            "grava": 0.040,
            "bolon": 0.055,
            "bolón": 0.055,
            "arena": 0.030,
            "vegetacion": 0.070,
            "vegetación": 0.070,
        }
        for key, val in material_n.items():
            if key in mats:
                return float(val)
    return float(fallback_n)


def parse_boundary_condition(boundary_df: pd.DataFrame | None, T: int, mode: str, fallback_value: float | None = None) -> BoundaryCondition:
    ubicacion = "aguas_abajo" if mode == "subcritico" else "aguas_arriba"
    bc = BoundaryCondition(tipo="normal_depth", ubicacion=ubicacion, valor=fallback_value)
    if boundary_df is None or boundary_df.empty:
        return bc
    df = boundary_df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "periodo_retorno" in df.columns:
        df["periodo_retorno"] = pd.to_numeric(df["periodo_retorno"], errors="coerce")
        dfp = df[(df["periodo_retorno"].isna()) | (df["periodo_retorno"].astype("Int64") == int(T))]
    else:
        dfp = df
    if "ubicacion" in dfp.columns:
        dfp = dfp[dfp["ubicacion"].astype(str).str.lower().str.contains("abajo" if ubicacion == "aguas_abajo" else "arriba", na=False)]
    if dfp.empty:
        return bc
    row = dfp.iloc[0]
    return BoundaryCondition(
        tipo=str(row.get("tipo", row.get("condicion", "normal_depth"))).strip().lower(),
        ubicacion=str(row.get("ubicacion", ubicacion)).strip().lower(),
        valor=_safe_float(row.get("valor", fallback_value), fallback_value if fallback_value is not None else np.nan),
        unidad=str(row.get("unidad", "m")),
        observacion=str(row.get("observacion", row.get("observaciones", "Condición de borde desde Excel"))),
    )


def parse_reach_coeffs(coeffs_df: pd.DataFrame | None, km1: float, km2: float, default_contr: float, default_exp: float) -> tuple[float, float, str]:
    if coeffs_df is None or coeffs_df.empty:
        return default_contr, default_exp, "coeficientes por defecto"
    df = coeffs_df.copy()
    for c in ["km_inicio", "km_fin", "contraccion", "expansion"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    kmin, kmax = min(km1, km2), max(km1, km2)
    if {"km_inicio", "km_fin"}.issubset(df.columns):
        hit = df[(df["km_inicio"] <= kmax) & (df["km_fin"] >= kmin)]
    else:
        hit = pd.DataFrame()
    if hit.empty:
        return default_contr, default_exp, "coeficientes por defecto"
    r = hit.iloc[0]
    return (
        _safe_float(r.get("contraccion"), default_contr),
        _safe_float(r.get("expansion"), default_exp),
        str(r.get("observacion", r.get("observaciones", "coeficientes desde Excel"))),
    )


# ---------------------------------------------------------------------------
# Método del paso estándar
# ---------------------------------------------------------------------------

def _solve_pair(
    known_sec: pd.DataFrame,
    unknown_sec: pd.DataFrame,
    known_wse: float,
    q_known: float,
    q_unknown: float,
    n_known: float,
    n_unknown: float,
    reach_length: float,
    direction: str,
    contraction_coeff: float,
    expansion_coeff: float,
    freeboard: float = 30.0,
) -> StepResult:
    """Resuelve una sección desconocida a partir de una sección conocida.

    direction='upstream': se calcula hacia aguas arriba (subcrítico).
    direction='downstream': se calcula hacia aguas abajo (supercrítico).
    """
    known_sec = prepare_section(known_sec)
    unknown_sec = prepare_section(unknown_sec)
    zmin = section_bottom(unknown_sec)
    ztop = section_top(unknown_sec)
    low = zmin + 1e-4
    high = ztop + freeboard
    reach_length = max(float(reach_length), 0.1)

    Hk = total_energy(q_known, known_sec, known_wse)
    hv_known = velocity_head(q_known, known_sec, known_wse)
    sf_known = friction_slope(q_known, known_sec, known_wse, n_known)
    if not np.isfinite(Hk):
        return StepResult(high, np.nan, 0, np.nan, np.nan, np.nan, np.nan, np.nan, False, "energía conocida no válida")

    def residual(wse: float) -> float:
        Hu = total_energy(q_unknown, unknown_sec, wse)
        hv_unknown = velocity_head(q_unknown, unknown_sec, wse)
        sf_unknown = friction_slope(q_unknown, unknown_sec, wse, n_unknown)
        if not all(np.isfinite(v) for v in [Hu, hv_unknown, sf_unknown, hv_known, sf_known]):
            return np.nan
        # Coeficiente local: si aumenta carga de velocidad, se comporta como contracción.
        coeff = contraction_coeff if hv_unknown > hv_known else expansion_coeff
        hf = reach_length * max(0.0, (sf_known + sf_unknown) / 2.0)
        hl = coeff * abs(hv_unknown - hv_known)
        loss = hf + hl
        if direction == "upstream":
            return Hu - (Hk + loss)
        else:
            return Hu - (Hk - loss)

    # Bracketing robusto en grilla.
    grid = np.linspace(low, high, 100)
    vals = np.array([residual(w) for w in grid], dtype=float)
    bracket = None
    for i in range(len(grid) - 1):
        if np.isfinite(vals[i]) and np.isfinite(vals[i + 1]) and vals[i] * vals[i + 1] <= 0:
            bracket = (grid[i], grid[i + 1])
            break

    ok = True
    iters = 0
    msg = "OK"
    if bracket is not None:
        try:
            wse = float(brentq(residual, bracket[0], bracket[1], maxiter=100, xtol=1e-5))
            res = float(residual(wse))
            iters = 100
        except Exception as exc:
            ok = False
            msg = f"brentq falló: {exc}"
            wse = float(grid[np.nanargmin(np.abs(vals))]) if np.isfinite(vals).any() else high
            res = float(residual(wse)) if np.isfinite(wse) else np.nan
    else:
        # Fallback: minimiza residuo absoluto; mantiene continuidad operacional.
        def obj(w: float) -> float:
            r = residual(w)
            return abs(r) if np.isfinite(r) else 1e12
        try:
            opt = minimize_scalar(obj, bounds=(low, high), method="bounded", options={"xatol": 1e-4})
            wse = float(opt.x)
            res = float(residual(wse))
            ok = abs(res) < 0.10
            msg = "sin cambio de signo; solución por minimización" if ok else "solución aproximada por minimización"
            iters = int(getattr(opt, "nit", 0))
        except Exception as exc:
            wse = high
            res = np.nan
            ok = False
            msg = f"fallback falló: {exc}"

    hv_unknown = velocity_head(q_unknown, unknown_sec, wse)
    sf_unknown = friction_slope(q_unknown, unknown_sec, wse, n_unknown)
    coeff = contraction_coeff if (np.isfinite(hv_unknown) and np.isfinite(hv_known) and hv_unknown > hv_known) else expansion_coeff
    hf = reach_length * max(0.0, np.nanmean([sf_known, sf_unknown])) if np.isfinite(sf_unknown) and np.isfinite(sf_known) else np.nan
    hl = coeff * abs(hv_unknown - hv_known) if np.isfinite(hv_unknown) and np.isfinite(hv_known) else np.nan
    return StepResult(wse, res, iters, hf, hl, coeff, sf_known, sf_unknown, ok, msg)


def _boundary_wse_for_section(sec: pd.DataFrame, q: float, slope: float, n: float, bc: BoundaryCondition) -> tuple[float, str]:
    tipo = (bc.tipo or "normal_depth").lower()
    if tipo in ["known_wse", "cota_agua", "nivel_conocido"] and bc.valor is not None and np.isfinite(bc.valor):
        return float(bc.valor), "cota de agua conocida"
    if tipo in ["critical_depth", "tirante_critico", "critico"]:
        cw = critical_wse(sec, q)
        if np.isfinite(cw):
            return cw, "tirante crítico"
    # Normal depth por defecto. Si valor viene como pendiente de energía, usarlo.
    slope_use = slope
    if tipo in ["normal_depth", "pendiente_normal", "normal"] and bc.valor is not None and np.isfinite(bc.valor) and bc.valor > 0 and bc.valor < 0.5:
        slope_use = float(bc.valor)
    return solve_wse_for_q(sec, q, slope_use, n), "tirante normal"


def compute_standard_step_profile(
    sections: pd.DataFrame,
    valid_status: pd.DataFrame,
    profile: pd.DataFrame,
    design_flows: pd.DataFrame,
    default_n: float = 0.04,
    flow_profile: pd.DataFrame | None = None,
    boundary_conditions: pd.DataFrame | None = None,
    coeffs: pd.DataFrame | None = None,
    regime_mode: str = "auto",
    km_increases_downstream: bool = True,
    default_contraction: float = 0.10,
    default_expansion: float = 0.30,
) -> pd.DataFrame:
    """Calcula perfil hidráulico 1D por método del paso estándar.

    Devuelve una tabla compatible con los módulos existentes, con columnas extra
    de diagnóstico energético y condición de borde.
    """
    if sections is None or sections.empty or valid_status is None or valid_status.empty or design_flows is None or design_flows.empty:
        return pd.DataFrame()

    # Hidráulica local como semilla, fallback y comparación.
    local = compute_hydraulics_for_sections(
        sections, valid_status, profile, design_flows, default_n=default_n, flow_profile=flow_profile
    )
    if local.empty:
        return pd.DataFrame()

    valid_ids = valid_status.loc[valid_status["estado"].isin(["Válida", "Revisar manualmente"]), "id_seccion"].astype(str).tolist()
    meta = []
    for sid in valid_ids:
        g = _section_by_id(sections, sid)
        if g.empty:
            continue
        km = _safe_float(pd.to_numeric(g["km"], errors="coerce").dropna().iloc[0], np.nan)
        if not np.isfinite(km):
            continue
        dist = get_distance_at_km(profile, km)
        slope, n_profile = slope_and_n_at_km(profile, km, default_n)
        n = section_manning(g, n_profile)
        meta.append({"id_seccion": sid, "km": km, "distancia_m": dist, "slope": slope, "n": n})
    meta_df = pd.DataFrame(meta).dropna(subset=["km"]).sort_values("km")
    if meta_df.empty:
        return local

    rows = []
    for _, flow in design_flows.iterrows():
        T = int(flow["periodo_retorno"])
        locT = local[local["periodo_retorno"].astype(int) == T].copy()
        if locT.empty:
            continue
        locT["id_seccion"] = locT["id_seccion"].astype(str)

        # Modo de régimen.
        med_fr = pd.to_numeric(locT["froude"], errors="coerce").median()
        mode = regime_mode.lower()
        if mode in ["auto", "automatico", "automático"]:
            mode = "supercritico" if np.isfinite(med_fr) and med_fr > 1.05 else "subcritico"
        if "super" in mode:
            mode = "supercritico"
            direction = "downstream"
            order = meta_df.sort_values("km", ascending=True if km_increases_downstream else False)
        else:
            mode = "subcritico"
            direction = "upstream"
            order = meta_df.sort_values("km", ascending=False if km_increases_downstream else True)

        bc = parse_boundary_condition(boundary_conditions, T, mode)
        prev_sid = None
        prev_wse = None
        prev_q = None
        prev_n = None
        prev_dist = None
        boundary_label = ""

        for pos, m in enumerate(order.to_dict("records")):
            sid = str(m["id_seccion"])
            km = float(m["km"])
            sec = _section_by_id(sections, sid)
            loc_row = locT[locT["id_seccion"] == sid]
            if loc_row.empty:
                continue
            loc_row = loc_row.iloc[0].to_dict()
            q = _safe_float(loc_row.get("caudal_m3s"), _safe_float(flow.get("caudal_adoptado_m3s"), np.nan))
            slope = float(m["slope"])
            n = float(m["n"])

            if pos == 0:
                wse, boundary_label = _boundary_wse_for_section(sec, q, slope, n, bc)
                step = StepResult(wse, 0.0, 0, 0.0, 0.0, 0.0, np.nan, friction_slope(q, sec, wse, n), True, boundary_label)
                reach_len = 0.0
                ccontr, cexp, coeff_obs = default_contraction, default_expansion, "condición de borde"
            else:
                known_sec = _section_by_id(sections, prev_sid)
                dist = float(m["distancia_m"])
                reach_len = abs(dist - float(prev_dist)) if prev_dist is not None else abs(km - float(order.iloc[pos - 1]["km"])) * 1000.0
                ccontr, cexp, coeff_obs = parse_reach_coeffs(coeffs, float(order.iloc[pos - 1]["km"]), km, default_contraction, default_expansion)
                step = _solve_pair(
                    known_sec=known_sec,
                    unknown_sec=sec,
                    known_wse=float(prev_wse),
                    q_known=float(prev_q),
                    q_unknown=float(q),
                    n_known=float(prev_n),
                    n_unknown=n,
                    reach_length=reach_len,
                    direction=direction,
                    contraction_coeff=ccontr,
                    expansion_coeff=cexp,
                )
                wse = step.wse

            hp = hydraulic_parameters_at_wse(sec, q, wse, slope, n)
            cwse = critical_wse(sec, q)
            ycrit = cwse - section_bottom(sec) if np.isfinite(cwse) else np.nan
            control = ""
            if np.isfinite(hp.get("froude", np.nan)):
                fr = hp["froude"]
                if abs(fr - 1.0) <= 0.15:
                    control = "posible control crítico"
                elif fr > 1.2:
                    control = "flujo supercrítico"
            if not step.ok:
                control = (control + "; " if control else "") + "revisar convergencia energía"
            if np.isfinite(cwse) and abs(wse - cwse) < 0.15:
                control = (control + "; " if control else "") + "cercano a tirante crítico"

            top = section_top(sec)
            conf = "Nivel 3: perfil 1D por energía sin calibración"
            if boundary_label == "cota de agua conocida":
                conf = "Nivel 4: perfil 1D por energía con condición de borde conocida"
            if not step.ok:
                conf = "Nivel 2: solución 1D aproximada; requiere revisión"

            rows.append({
                "id_seccion": sid,
                "km": km,
                "distancia_m": float(m["distancia_m"]),
                "periodo_retorno": T,
                "caudal_m3s": q,
                "caudal_base_diseno_m3s": loc_row.get("caudal_base_diseno_m3s", q),
                "observaciones_caudal_km": loc_row.get("observaciones_caudal_km", ""),
                "cota_agua_m": wse,
                "cota_agua_local_m": loc_row.get("cota_agua_m", np.nan),
                "diferencia_wse_paso_vs_local_m": wse - _safe_float(loc_row.get("cota_agua_m"), np.nan),
                "area_m2": hp["area_m2"],
                "perimetro_m": hp["perimetro_m"],
                "radio_hidraulico_m": hp["radio_hidraulico_m"],
                "ancho_superficial_m": hp["ancho_superficial_m"],
                "tirante_medio_m": hp["tirante_medio_m"],
                "tirante_max_m": hp["tirante_max_m"],
                "tirante_critico_m": ycrit,
                "cota_critica_m": cwse,
                "velocidad_m_s": hp["velocidad_m_s"],
                "froude": hp["froude"],
                "pendiente_energia": slope,
                "pendiente_friccion": hp["pendiente_friccion"],
                "manning_n": n,
                "esfuerzo_cortante_pa": hp["esfuerzo_cortante_pa"],
                "potencia_corriente_w_m2": hp["potencia_corriente_w_m2"],
                "carga_velocidad_m": hp["carga_velocidad_m"],
                "energia_especifica_m": hp["energia_especifica_m"],
                "energia_total_m": hp["energia_total_m"],
                "perdida_friccion_tramo_m": step.perdida_friccion,
                "perdida_local_tramo_m": step.perdida_local,
                "perdida_total_tramo_m": (step.perdida_friccion + step.perdida_local) if np.isfinite(step.perdida_friccion) and np.isfinite(step.perdida_local) else np.nan,
                "coef_local_usado": step.coef_usado,
                "coef_contraccion": ccontr,
                "coef_expansion": cexp,
                "observacion_coeficientes": coeff_obs,
                "distancia_tramo_m": reach_len,
                "residual_energia_m": step.residual,
                "iteraciones_solver": step.iteraciones,
                "solver_ok": bool(step.ok),
                "mensaje_solver": step.mensaje,
                "regimen": hp["regimen"],
                "regimen_calculo": mode,
                "direccion_calculo": "aguas abajo → aguas arriba" if direction == "upstream" else "aguas arriba → aguas abajo",
                "condicion_borde_tipo": bc.tipo,
                "condicion_borde_ubicacion": bc.ubicacion,
                "condicion_borde_valor": bc.valor,
                "metodo_hidraulico": "paso_estandar_energia",
                "control_hidraulico": control,
                "posible_desborde": bool(wse > top),
                "nivel_confianza_modelo": conf,
            })

            prev_sid = sid
            prev_wse = wse
            prev_q = q
            prev_n = n
            prev_dist = float(m["distancia_m"])

    out = pd.DataFrame(rows).sort_values(["periodo_retorno", "km"], na_position="last")
    out = enforce_monotonic_wse_by_section(out, sections, profile, default_n)
    return out


def enforce_monotonic_wse_by_section(hyd: pd.DataFrame, sections: pd.DataFrame, profile: pd.DataFrame, default_n: float = 0.04) -> pd.DataFrame:
    """Control de calidad: evita que una crecida mayor tenga menor WSE en la misma sección.

    En modelos con datos preliminares, coeficientes genéricos o condición de borde
    simplificada puede aparecer una rama de energía no deseada. Este control no
    reemplaza la revisión profesional: ajusta la WSE al mínimo hidráulicamente
    coherente para visualización y deja trazabilidad en la tabla.
    """
    if hyd is None or hyd.empty or "cota_agua_m" not in hyd.columns:
        return hyd
    out = hyd.copy()
    if "ajuste_monotonia_wse" not in out.columns:
        out["ajuste_monotonia_wse"] = False
    for sid, g in out.groupby("id_seccion"):
        idxs = g.sort_values("periodo_retorno").index.to_list()
        prev = -np.inf
        for idx in idxs:
            wse = _safe_float(out.at[idx, "cota_agua_m"], np.nan)
            if np.isfinite(prev) and np.isfinite(wse) and wse + 1e-6 < prev:
                new_wse = prev + 0.001
                sid_val = out.at[idx, "id_seccion"]
                sec = _section_by_id(sections, sid_val)
                q = _safe_float(out.at[idx, "caudal_m3s"], np.nan)
                km = _safe_float(out.at[idx, "km"], np.nan)
                slope, n_prof = slope_and_n_at_km(profile, km, default_n)
                n = section_manning(sec, n_prof)
                hp = hydraulic_parameters_at_wse(sec, q, new_wse, slope, n)
                for col in ["area_m2", "perimetro_m", "radio_hidraulico_m", "ancho_superficial_m", "tirante_medio_m", "tirante_max_m", "velocidad_m_s", "froude", "esfuerzo_cortante_pa", "potencia_corriente_w_m2", "carga_velocidad_m", "energia_especifica_m", "energia_total_m", "pendiente_friccion"]:
                    if col in hp:
                        out.at[idx, col] = hp[col]
                out.at[idx, "cota_agua_m"] = new_wse
                out.at[idx, "regimen"] = hp["regimen"]
                out.at[idx, "ajuste_monotonia_wse"] = True
                txt = str(out.at[idx, "control_hidraulico"]) if "control_hidraulico" in out.columns else ""
                txt = (txt + "; " if txt and txt != "nan" else "") + "ajuste QA monotonicidad WSE"
                out.at[idx, "control_hidraulico"] = txt
                txt2 = str(out.at[idx, "mensaje_solver"]) if "mensaje_solver" in out.columns else ""
                out.at[idx, "mensaje_solver"] = (txt2 + "; " if txt2 and txt2 != "nan" else "") + "WSE ajustada por control de calidad"
                wse = new_wse
            if np.isfinite(wse):
                prev = max(prev, wse)
    return out


# ---------------------------------------------------------------------------
# Funciones de diagnóstico existentes y compatibilidad hacia atrás
# ---------------------------------------------------------------------------

def compute_energy_grade_line(hyd: pd.DataFrame, profile: pd.DataFrame | None = None) -> pd.DataFrame:
    """Agrega línea de energía a un resultado local o estándar.

    Se mantiene para compatibilidad con la versión v1.1. Si el resultado ya
    viene del solver estándar, conserva columnas de pérdida y solo completa
    diagnósticos faltantes.
    """
    if hyd is None or hyd.empty:
        return pd.DataFrame()
    out = hyd.copy().sort_values(["periodo_retorno", "km"])
    if "carga_velocidad_m" not in out.columns:
        out["carga_velocidad_m"] = out["velocidad_m_s"] ** 2 / (2 * G)
    if "energia_total_m" not in out.columns:
        out["energia_total_m"] = out["cota_agua_m"] + out["carga_velocidad_m"]
    if "perdida_energia_tramo_m" not in out.columns:
        out["perdida_energia_tramo_m"] = np.nan
    if "control_hidraulico" not in out.columns:
        out["control_hidraulico"] = ""
    for T, g in out.groupby("periodo_retorno"):
        idx = g.index.to_list()
        E = g["energia_total_m"].values
        losses = np.r_[np.nan, np.maximum(0, E[:-1] - E[1:])]
        if out.loc[idx, "perdida_energia_tramo_m"].isna().all():
            out.loc[idx, "perdida_energia_tramo_m"] = losses
        controls = []
        for _, row in g.iterrows():
            existing = str(row.get("control_hidraulico", ""))
            fr = _safe_float(row.get("froude"), np.nan)
            extra = ""
            if np.isfinite(fr) and abs(fr - 1.0) < 0.2:
                extra = "posible control crítico"
            elif np.isfinite(fr) and fr > 1.2:
                extra = "flujo supercrítico"
            controls.append(existing if existing else extra)
        out.loc[idx, "control_hidraulico"] = controls
    return out


def detect_mixed_regime(energy_df: pd.DataFrame) -> pd.DataFrame:
    if energy_df is None or energy_df.empty:
        return pd.DataFrame()
    rows = []
    for T, g in energy_df.groupby("periodo_retorno"):
        regimes = set(g["regimen"].dropna().astype(str)) if "regimen" in g.columns else set()
        rows.append({
            "periodo_retorno": T,
            "regimen_mixto": "subcrítico" in regimes and "supercrítico" in regimes,
            "n_secciones_supercriticas": int((g.get("regimen", pd.Series(dtype=str)) == "supercrítico").sum()),
            "n_posibles_controles": int(g.get("control_hidraulico", pd.Series(dtype=str)).astype(str).str.len().gt(0).sum()),
            "n_solver_no_converge": int((g.get("solver_ok", pd.Series([True] * len(g), index=g.index)) == False).sum()),
            "residual_max_abs_m": float(pd.to_numeric(g.get("residual_energia_m", pd.Series(dtype=float)), errors="coerce").abs().max()) if "residual_energia_m" in g.columns else np.nan,
        })
    return pd.DataFrame(rows)
