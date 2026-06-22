"""Exportación preliminar de geometría y caudales para preproceso HEC-RAS.

No genera archivos .prj/.gxx nativos completos; entrega CSV ordenados y trazables para ingresar o convertir a HEC-RAS.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd


def export_hecras_preprocessor(profile: pd.DataFrame, sections: pd.DataFrame, flows: pd.DataFrame, out_dir: str | Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    paths["perfil_csv"] = out / "hecras_perfil_longitudinal.csv"
    paths["secciones_csv"] = out / "hecras_secciones.csv"
    paths["caudales_csv"] = out / "hecras_caudales.csv"
    profile.to_csv(paths["perfil_csv"], index=False)
    sections.to_csv(paths["secciones_csv"], index=False)
    flows.to_csv(paths["caudales_csv"], index=False)
    return paths
