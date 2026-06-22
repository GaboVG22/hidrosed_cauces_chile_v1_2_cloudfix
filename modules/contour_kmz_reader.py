"""Lectura de curvas de nivel desde KML/KMZ."""
from __future__ import annotations
from pathlib import Path
from io import BytesIO
import re
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd

ELEV_RE = re.compile(r"(-?\d+(?:[\.,]\d+)?)\s*(?:m|msnm|metros)?", re.IGNORECASE)


def _read_kml_bytes(file_or_path) -> bytes:
    if hasattr(file_or_path, "read"):
        data = file_or_path.read()
    else:
        data = Path(file_or_path).read_bytes()
    name = str(getattr(file_or_path, "name", file_or_path)).lower()
    if name.endswith(".kmz") or data[:2] == b"PK":
        with zipfile.ZipFile(BytesIO(data)) as zf:
            kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError("El KMZ no contiene KML.")
            return zf.read(kml_names[0])
    return data


def _detect_elev(name: str | None, desc: str | None, coords: list[tuple[float, float, float | None]]) -> float | None:
    for text in [name, desc]:
        if text:
            # priorizar patrones con cota/elev/cn
            match = re.search(r"(?:cota|elev|elevation|cn)[^0-9-]*(-?\d+(?:[\.,]\d+)?)", text, re.IGNORECASE)
            if match:
                return float(match.group(1).replace(",", "."))
            nums = ELEV_RE.findall(text)
            nums = [float(n.replace(",", ".")) for n in nums]
            # evitar tomar IDs pequeños si hay más de un número; usar el último
            if nums:
                return nums[-1]
    zs = [c[2] for c in coords if c[2] is not None and np.isfinite(c[2])]
    if zs:
        return float(np.nanmedian(zs))
    return None


def read_contour_kmz(file_or_path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna líneas de curvas y puntos de elevación.

    lines_df columnas: contour_id, name, elev_m, n_points, needs_elevation
    points_df columnas: contour_id, lon, lat, elev_m
    """
    kml = _read_kml_bytes(file_or_path)
    root = ET.fromstring(kml)
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    lines, pts = [], []
    placemarks = root.findall(".//kml:Placemark", ns)
    cid = 0
    for pm in placemarks:
        name_el = pm.find("kml:name", ns)
        desc_el = pm.find("kml:description", ns)
        name = name_el.text.strip() if name_el is not None and name_el.text else f"Curva_{cid+1}"
        desc = desc_el.text if desc_el is not None else ""
        for coords_el in pm.findall(".//kml:LineString/kml:coordinates", ns):
            if not coords_el.text:
                continue
            coords = []
            for token in coords_el.text.strip().split():
                parts = token.split(",")
                if len(parts) >= 2:
                    lon, lat = float(parts[0]), float(parts[1])
                    z = float(parts[2]) if len(parts) > 2 and parts[2] not in ["", "0"] else None
                    coords.append((lon, lat, z))
            elev = _detect_elev(name, desc, coords)
            cid += 1
            lines.append({"contour_id": cid, "name": name, "elev_m": elev, "n_points": len(coords), "needs_elevation": elev is None})
            for lon, lat, _z in coords:
                pts.append({"contour_id": cid, "lon": lon, "lat": lat, "elev_m": elev})
    return pd.DataFrame(lines), pd.DataFrame(pts)


def apply_manual_elevations(points_df: pd.DataFrame, lines_df: pd.DataFrame) -> pd.DataFrame:
    if points_df.empty or lines_df.empty:
        return points_df
    elev_map = lines_df.set_index("contour_id")["elev_m"].to_dict()
    out = points_df.copy()
    out["elev_m"] = out["contour_id"].map(elev_map)
    return out
