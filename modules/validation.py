"""Validaciones de datos y geometrías."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

MIN_COLS = {
    "Perfil_Longitudinal": ["km", "distancia_m", "cota_fondo_m"],
    "Secciones": ["id_seccion", "km", "x_m", "z_m"],
    "Cuenca": ["area_km2"],
    "Precipitacion": ["periodo_retorno", "duracion_h", "precipitacion_mm"],
    "Granulometria": ["km", "d50_mm"],
    "Parametros": ["parametro", "valor"],
}

@dataclass
class ValidationReport:
    errors: List[str]
    warnings: List[str]
    section_status: pd.DataFrame

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_columns(sheets: Dict[str, pd.DataFrame]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for sheet, cols in MIN_COLS.items():
        if sheet not in sheets:
            errors.append(f"Falta hoja requerida: {sheet}")
            continue
        df = sheets[sheet]
        missing = [c for c in cols if c not in df.columns]
        if missing:
            errors.append(f"Hoja {sheet}: faltan columnas mínimas {missing}")
    return errors, warnings


def validate_profile(profile: pd.DataFrame) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    if profile.empty:
        errors.append("Perfil longitudinal vacío.")
        return errors, warnings
    for col in ["km", "distancia_m", "cota_fondo_m"]:
        if col in profile.columns:
            nulls = int(profile[col].isna().sum())
            if nulls:
                warnings.append(f"Perfil: columna {col} tiene {nulls} valores nulos.")
    if "km" in profile.columns and profile["km"].duplicated().any():
        warnings.append("Perfil: existen km duplicados; se usará el primer registro ordenado.")
    if "distancia_m" in profile.columns:
        vals = pd.to_numeric(profile["distancia_m"], errors="coerce").dropna().values
        if len(vals) > 1 and np.any(np.diff(vals) < 0):
            warnings.append("Perfil: distancia_m no está ordenada; se ordenará automáticamente.")
    return errors, warnings


def _section_has_both_banks(g: pd.DataFrame) -> bool:
    if "ribera" not in g.columns:
        # alternativa geométrica: extremos al menos 0.5 m sobre fondo
        z = pd.to_numeric(g["z_m"], errors="coerce").dropna().values
        if len(z) < 5:
            return False
        return (z[0] > np.nanmin(z) + 0.3) and (z[-1] > np.nanmin(z) + 0.3)
    r = set(str(v).lower() for v in g["ribera"].dropna().unique())
    return any("iz" in v for v in r) and any("der" in v for v in r)


def classify_sections(sections: pd.DataFrame, min_points: int = 5) -> pd.DataFrame:
    rows = []
    if sections.empty or "id_seccion" not in sections.columns:
        return pd.DataFrame(columns=["id_seccion", "km", "estado", "motivo", "n_puntos"])
    for sid, g in sections.groupby("id_seccion"):
        reasons = []
        gg = g.copy()
        n = len(gg)
        if n < min_points:
            reasons.append(f"menos de {min_points} puntos")
        for col in ["km", "x_m", "z_m"]:
            if col not in gg.columns or gg[col].isna().any():
                reasons.append(f"faltan valores en {col}")
        x = pd.to_numeric(gg.get("x_m"), errors="coerce").values
        z = pd.to_numeric(gg.get("z_m"), errors="coerce").values
        if np.any(~np.isfinite(x)) or np.any(~np.isfinite(z)):
            reasons.append("coordenadas no numéricas")
        else:
            if np.any(np.diff(x) < 0):
                reasons.append("puntos x desordenados")
            if np.nanmax(z) - np.nanmin(z) < 0.30:
                reasons.append("relieve transversal insuficiente")
        if not _section_has_both_banks(gg):
            reasons.append("no se reconocen ambas riberas")
        km_val = float(pd.to_numeric(gg["km"], errors="coerce").dropna().iloc[0]) if "km" in gg.columns and pd.to_numeric(gg["km"], errors="coerce").notna().any() else np.nan
        if not reasons:
            estado = "Válida"
            motivo = "OK"
        elif any("desordenados" in r for r in reasons) and len(reasons) == 1:
            estado = "Revisar manualmente"
            motivo = "; ".join(reasons)
        else:
            estado = "Descartada"
            motivo = "; ".join(reasons)
        rows.append({"id_seccion": sid, "km": km_val, "estado": estado, "motivo": motivo, "n_puntos": n})
    return pd.DataFrame(rows).sort_values(["km", "id_seccion"], na_position="last")


def validate_flow_points(flow_points: pd.DataFrame) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    if flow_points is None or flow_points.empty:
        return errors, warnings
    required = ["km", "periodo_retorno", "caudal_m3s"]
    missing = [c for c in required if c not in flow_points.columns]
    if missing:
        errors.append(f"Hoja Caudales_Km: faltan columnas mínimas {missing}")
        return errors, warnings
    q = pd.to_numeric(flow_points["caudal_m3s"], errors="coerce")
    if q.isna().any():
        warnings.append("Caudales_Km: existen caudales no numéricos; serán ignorados.")
    if (q.dropna() < 0).any():
        warnings.append("Caudales_Km: existen caudales negativos; use tipo_caudal='extraccion' para restar caudal.")
    if "tipo_caudal" not in flow_points.columns and "tipo_aporte" not in flow_points.columns:
        warnings.append("Caudales_Km: no se indicó tipo_caudal; se asumirá aporte_lateral.")
    return errors, warnings


def validate_all(sheets: Dict[str, pd.DataFrame]) -> ValidationReport:
    errors, warnings = validate_columns(sheets)
    e, w = validate_profile(sheets.get("Perfil_Longitudinal", pd.DataFrame()))
    errors += e
    warnings += w
    flow_sheet = sheets.get("Caudales_Km", sheets.get("Caudales_Por_Km", pd.DataFrame()))
    e, w = validate_flow_points(flow_sheet)
    errors += e
    warnings += w
    status = classify_sections(sheets.get("Secciones", pd.DataFrame()))
    if not status.empty:
        discarded = status[status["estado"] == "Descartada"]
        if len(discarded):
            warnings.append(f"{len(discarded)} secciones fueron descartadas automáticamente.")
        review = status[status["estado"] == "Revisar manualmente"]
        if len(review):
            warnings.append(f"{len(review)} secciones requieren revisión manual.")
    else:
        warnings.append("No se pudo clasificar secciones; revise hoja Secciones.")
    return ValidationReport(errors=errors, warnings=warnings, section_status=status)
