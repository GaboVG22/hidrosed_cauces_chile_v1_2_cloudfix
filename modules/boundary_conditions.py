"""Condiciones de borde hidráulicas."""
from __future__ import annotations
import pandas as pd


def parse_boundary_conditions(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {"tipo": "normal_depth", "ubicacion": "aguas_abajo", "valor": None, "unidad": "pendiente"}
    row = df.iloc[0].to_dict()
    return {
        "tipo": str(row.get("tipo", "normal_depth")),
        "ubicacion": str(row.get("ubicacion", "aguas_abajo")),
        "km": row.get("km"),
        "valor": row.get("valor"),
        "unidad": row.get("unidad", ""),
        "observacion": row.get("observacion", ""),
    }
