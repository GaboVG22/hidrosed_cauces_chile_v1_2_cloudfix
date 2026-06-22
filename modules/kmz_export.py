"""Exportación KML/KMZ."""
from __future__ import annotations
from pathlib import Path
import zipfile
import pandas as pd


def _write_basic_kml(path: Path, placemarks: list[str]):
    kml = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<kml xmlns=\"http://www.opengis.net/kml/2.2\"><Document>\n""" + "\n".join(placemarks) + "\n</Document></kml>"
    path.write_text(kml, encoding="utf-8")


def export_sections_kmz(sections_status: pd.DataFrame, output_path: str | Path, axis_df: pd.DataFrame | None = None) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    placemarks = []
    if sections_status is not None and not sections_status.empty:
        for _, r in sections_status.iterrows():
            color = "ff0000ff" if r["estado"] == "Descartada" else "ffff0000" if r["estado"] == "Válida" else "ff00a5ff"
            # si no hay coordenadas, usar km como lon ficticio en KML no útil, pero válido como placeholder
            lon, lat = -70.0 + float(r.get("km", 0))/100.0, -30.0
            if axis_df is not None and not axis_df.empty and {"km", "lon", "lat"}.issubset(axis_df.columns):
                lon = float(pd.Series(axis_df["lon"]).interpolate().iloc[(axis_df["km"]-r["km"]).abs().argsort()[:1]].iloc[0])
                lat = float(pd.Series(axis_df["lat"]).interpolate().iloc[(axis_df["km"]-r["km"]).abs().argsort()[:1]].iloc[0])
            placemarks.append(f"""
<Placemark><name>{r['id_seccion']} km {r['km']} - {r['estado']}</name><description>{r['motivo']}</description>
<Style><IconStyle><color>{color}</color><scale>1.1</scale></IconStyle></Style>
<Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>""")
    kml_path = output_path.with_suffix(".kml")
    _write_basic_kml(kml_path, placemarks)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(kml_path, arcname="doc.kml")
    try:
        kml_path.unlink()
    except Exception:
        pass
    return output_path


def export_flood_kmz(summary_df: pd.DataFrame, output_path: str | Path) -> Path:
    # placeholder: puntos resumen por periodo; para polígonos reales usar shapely/rasterio.features en etapa SIG avanzada
    output_path = Path(output_path)
    placemarks = []
    if summary_df is not None and not summary_df.empty:
        for i, r in summary_df.iterrows():
            lon, lat = -70.0 + i * 0.01, -30.0
            desc = "<br/>".join([f"{c}: {r[c]}" for c in summary_df.columns])
            placemarks.append(f"<Placemark><name>Inundación T={r.get('periodo_retorno','')}</name><description>{desc}</description><Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>")
    kml_path = output_path.with_suffix(".kml")
    _write_basic_kml(kml_path, placemarks)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(kml_path, arcname="doc.kml")
    kml_path.unlink(missing_ok=True)
    return output_path
