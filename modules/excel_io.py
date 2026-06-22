"""Lectura y exportación de Excel para HidroSed Cauces Chile."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

REQUIRED_SHEETS = [
    "Perfil_Longitudinal",
    "Secciones",
    "Cuenca",
    "Precipitacion",
    "Granulometria",
    "Parametros",
]
OPTIONAL_SHEETS = [
    "Caudales_Observados",
    "Caudales_Km",
    "Caudales_Por_Km",
    "Condiciones_Borde",
    "Coeficientes_Hidraulicos",
    "Obras",
    "Observaciones_Hidraulicas",
    "Hidrogramas",
    "Sedimento_Entrada",
    "Terreno",
    "Curvas_Nivel",
    "Eje_Cauce",
    "Uso_Suelo_Rugosidad",
]

COLUMN_ALIASES = {
    "kilometro": "km",
    "progresiva": "km",
    "distancia": "distancia_m",
    "cota_fondo": "cota_fondo_m",
    "n": "rugosidad_manning_n",
    "manning": "rugosidad_manning_n",
    "x": "x_m",
    "z": "z_m",
    "y": "y_m",
    "elevacion": "cota_m",
    "cota": "cota_m",
}

@dataclass
class ExcelLoadResult:
    sheets: Dict[str, pd.DataFrame]
    missing_sheets: list[str]
    warnings: list[str]


def _normalize_col(col: str) -> str:
    col = str(col).strip().lower()
    col = col.replace(" ", "_").replace("-", "_")
    col = col.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    return COLUMN_ALIASES.get(col, col)


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_normalize_col(c) for c in df.columns]
    return df


def load_excel(file_or_path) -> ExcelLoadResult:
    """Carga libro Excel desde UploadedFile, bytes o ruta."""
    warnings: list[str] = []
    try:
        xls = pd.ExcelFile(file_or_path)
    except Exception as exc:
        raise ValueError(f"No fue posible leer el Excel: {exc}") from exc

    sheets: Dict[str, pd.DataFrame] = {}
    existing = set(xls.sheet_names)
    missing = [s for s in REQUIRED_SHEETS if s not in existing]

    for sheet_name in xls.sheet_names:
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            sheets[sheet_name] = normalize_dataframe(df)
        except Exception as exc:
            warnings.append(f"No fue posible leer hoja {sheet_name}: {exc}")

    return ExcelLoadResult(sheets=sheets, missing_sheets=missing, warnings=warnings)


def get_sheet(sheets: Dict[str, pd.DataFrame], name: str, required: bool = False) -> pd.DataFrame:
    if name not in sheets:
        if required:
            raise KeyError(f"Falta hoja requerida: {name}")
        return pd.DataFrame()
    return sheets[name].copy()


def export_results_excel(results: Dict[str, pd.DataFrame], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        for name, df in results.items():
            safe = str(name)[:31].replace("/", "_").replace("\\", "_")
            if df is None:
                df = pd.DataFrame()
            df.to_excel(writer, sheet_name=safe, index=False)
            ws = writer.sheets[safe]
            for i, col in enumerate(df.columns):
                width = min(max(len(str(col)) + 2, 12), 35)
                ws.set_column(i, i, width)
    return output_path


def to_excel_bytes(results: Dict[str, pd.DataFrame]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        for name, df in results.items():
            safe = str(name)[:31].replace("/", "_").replace("\\", "_")
            if df is None:
                df = pd.DataFrame()
            df.to_excel(writer, sheet_name=safe, index=False)
            ws = writer.sheets[safe]
            for i, col in enumerate(df.columns):
                ws.set_column(i, i, min(max(len(str(col)) + 2, 12), 35))
    return buffer.getvalue()
