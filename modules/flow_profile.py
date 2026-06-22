"""Caudales longitudinales por km.

Permite incorporar aportes puntuales/laterales, extracciones o caudales conocidos
por km del cauce y período de retorno. La convención base es que el km aumenta
hacia aguas abajo; por lo tanto, un aporte en km=X afecta las secciones con km>=X.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.hydrology import RETURN_PERIODS

TYPE_ALIASES = {
    "aporte": "aporte_lateral",
    "aporte_lateral": "aporte_lateral",
    "tributario": "aporte_lateral",
    "afluente": "aporte_lateral",
    "lateral": "aporte_lateral",
    "extraccion": "extraccion",
    "extracción": "extraccion",
    "retiro": "extraccion",
    "resta": "extraccion",
    "caudal_adoptado": "caudal_control",
    "control": "caudal_control",
    "caudal_control": "caudal_control",
    "reemplaza": "caudal_control",
    "medido": "caudal_control",
    "local": "caudal_local",
    "caudal_local": "caudal_local",
}


def normalize_flow_points(flow_points: pd.DataFrame | None) -> pd.DataFrame:
    """Normaliza una tabla de caudales por km.

    Columnas esperadas:
    - km
    - periodo_retorno
    - caudal_m3s
    - tipo_caudal o tipo_aporte: aporte_lateral, extraccion, caudal_control, caudal_local
    - descripcion/observaciones opcional
    """
    if flow_points is None or flow_points.empty:
        return pd.DataFrame(columns=["km", "periodo_retorno", "caudal_m3s", "tipo_caudal", "observaciones"])

    df = flow_points.copy()
    # La normalización de excel_io ya baja a minúsculas; aquí se aceptan variantes.
    rename = {}
    if "tipo_aporte" in df.columns and "tipo_caudal" not in df.columns:
        rename["tipo_aporte"] = "tipo_caudal"
    if "q_m3s" in df.columns and "caudal_m3s" not in df.columns:
        rename["q_m3s"] = "caudal_m3s"
    if "caudal" in df.columns and "caudal_m3s" not in df.columns:
        rename["caudal"] = "caudal_m3s"
    if "tr" in df.columns and "periodo_retorno" not in df.columns:
        rename["tr"] = "periodo_retorno"
    if "periodo" in df.columns and "periodo_retorno" not in df.columns:
        rename["periodo"] = "periodo_retorno"
    df = df.rename(columns=rename)

    for col in ["km", "periodo_retorno", "caudal_m3s"]:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "tipo_caudal" not in df.columns:
        df["tipo_caudal"] = "aporte_lateral"
    if "observaciones" not in df.columns:
        df["observaciones"] = ""

    def _norm_type(v: object) -> str:
        txt = str(v).strip().lower().replace(" ", "_")
        return TYPE_ALIASES.get(txt, txt if txt else "aporte_lateral")

    df["tipo_caudal"] = df["tipo_caudal"].map(_norm_type)
    df = df.dropna(subset=["km", "periodo_retorno", "caudal_m3s"])
    df["periodo_retorno"] = df["periodo_retorno"].astype(int)
    df = df[df["periodo_retorno"].isin(RETURN_PERIODS)]
    return df[["km", "periodo_retorno", "caudal_m3s", "tipo_caudal", "observaciones"]].sort_values(["periodo_retorno", "km"])


def get_section_kms(sections: pd.DataFrame, section_status: pd.DataFrame | None = None) -> pd.DataFrame:
    if sections is None or sections.empty or "id_seccion" not in sections.columns:
        return pd.DataFrame(columns=["id_seccion", "km"])
    df = sections[["id_seccion", "km"]].copy()
    df["km"] = pd.to_numeric(df["km"], errors="coerce")
    df = df.dropna().drop_duplicates().sort_values("km")
    if section_status is not None and not section_status.empty and "estado" in section_status.columns:
        valid_ids = section_status.loc[section_status["estado"].isin(["Válida", "Revisar manualmente"]), "id_seccion"].tolist()
        df = df[df["id_seccion"].isin(valid_ids)]
    return df


def build_flow_profile_by_km(
    design_flows: pd.DataFrame,
    section_kms: pd.DataFrame | list[float] | np.ndarray,
    flow_points: pd.DataFrame | None = None,
    km_increases_downstream: bool = True,
) -> pd.DataFrame:
    """Construye caudal adoptado por sección/km y período de retorno.

    Reglas:
    - base: caudal_adoptado_m3s de la tabla de diseño.
    - aporte_lateral: suma desde el km indicado hacia aguas abajo.
    - extraccion: resta desde el km indicado hacia aguas abajo.
    - caudal_control: reemplaza el caudal base desde ese km hacia aguas abajo.
      Si existen varios controles aguas arriba, se usa el último control alcanzado.
    - caudal_local: se asigna solo a la sección/km más cercano al punto indicado.
    """
    if design_flows is None or design_flows.empty:
        return pd.DataFrame()
    if isinstance(section_kms, pd.DataFrame):
        sk = section_kms.copy()
        if "id_seccion" not in sk.columns:
            sk["id_seccion"] = [f"KM_{v:.3f}" for v in sk["km"]]
    else:
        vals = pd.to_numeric(pd.Series(section_kms), errors="coerce").dropna().values
        sk = pd.DataFrame({"id_seccion": [f"KM_{v:.3f}" for v in vals], "km": vals})
    sk["km"] = pd.to_numeric(sk["km"], errors="coerce")
    sk = sk.dropna(subset=["km"]).drop_duplicates().sort_values("km")
    fp = normalize_flow_points(flow_points)
    rows = []
    for _, f in design_flows.iterrows():
        T = int(f["periodo_retorno"])
        base_q = float(f.get("caudal_adoptado_m3s", f.get("caudal_calculado_m3s", 0.0)))
        ptsT = fp[fp["periodo_retorno"] == T].sort_values("km")
        for _, s in sk.iterrows():
            km = float(s["km"])
            if km_increases_downstream:
                upstream = ptsT[ptsT["km"] <= km]
            else:
                upstream = ptsT[ptsT["km"] >= km]
            q = base_q
            obs_parts = ["caudal base de diseño"]
            controls = upstream[upstream["tipo_caudal"] == "caudal_control"]
            if not controls.empty:
                # último control alcanzado en el sentido de escurrimiento
                ctrl = controls.iloc[-1] if km_increases_downstream else controls.iloc[0]
                q = float(ctrl["caudal_m3s"])
                obs_parts.append(f"control/reemplazo en km {float(ctrl['km']):.3f}")
            add = upstream[upstream["tipo_caudal"] == "aporte_lateral"]["caudal_m3s"].sum()
            ext = upstream[upstream["tipo_caudal"] == "extraccion"]["caudal_m3s"].sum()
            q = q + float(add) - float(ext)
            if add:
                obs_parts.append(f"+ aportes {add:.3f} m3/s")
            if ext:
                obs_parts.append(f"- extracciones {ext:.3f} m3/s")
            local = ptsT[ptsT["tipo_caudal"] == "caudal_local"]
            if not local.empty:
                nearest_idx = (sk["km"] - local.iloc[0]["km"]).abs().idxmin()
                if s.name == nearest_idx:
                    q = float(local.iloc[0]["caudal_m3s"])
                    obs_parts.append(f"caudal local asignado en km {float(local.iloc[0]['km']):.3f}")
            rows.append({
                "id_seccion": s.get("id_seccion", f"KM_{km:.3f}"),
                "km": km,
                "periodo_retorno": T,
                "caudal_base_m3s": base_q,
                "caudal_km_m3s": max(q, 0.0),
                "aporte_acumulado_m3s": float(add) if 'add' in locals() else 0.0,
                "extraccion_acumulada_m3s": float(ext) if 'ext' in locals() else 0.0,
                "observaciones_caudal_km": " | ".join(obs_parts),
            })
    return pd.DataFrame(rows).sort_values(["periodo_retorno", "km"])


def flow_for_section(flow_profile: pd.DataFrame | None, section_id: str, km: float, T: int, default_q: float) -> tuple[float, str]:
    if flow_profile is None or flow_profile.empty:
        return float(default_q), "caudal uniforme de diseño"
    fp = flow_profile[flow_profile["periodo_retorno"].astype(int) == int(T)].copy()
    if fp.empty:
        return float(default_q), "sin perfil de caudal para este período"
    if "id_seccion" in fp.columns:
        m = fp[fp["id_seccion"].astype(str) == str(section_id)]
        if not m.empty:
            r = m.iloc[0]
            return float(r.get("caudal_km_m3s", default_q)), str(r.get("observaciones_caudal_km", "caudal por km"))
    fp["dist"] = (pd.to_numeric(fp["km"], errors="coerce") - float(km)).abs()
    r = fp.sort_values("dist").iloc[0]
    return float(r.get("caudal_km_m3s", default_q)), str(r.get("observaciones_caudal_km", "caudal por km cercano"))
