"""Lectura de punto de control desde KML/KMZ."""
from __future__ import annotations
from pathlib import Path
import re
import zipfile
from io import BytesIO
import xml.etree.ElementTree as ET


def _read_kml_bytes(file_or_path) -> bytes:
    if hasattr(file_or_path, "read"):
        data = file_or_path.read()
    else:
        data = Path(file_or_path).read_bytes()
    if str(getattr(file_or_path, "name", file_or_path)).lower().endswith(".kmz") or data[:2] == b"PK":
        with zipfile.ZipFile(BytesIO(data)) as zf:
            kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError("El KMZ no contiene archivo KML.")
            return zf.read(kml_names[0])
    return data


def read_control_point(file_or_path) -> dict:
    kml = _read_kml_bytes(file_or_path)
    root = ET.fromstring(kml)
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    name = None
    n = root.find(".//kml:Placemark/kml:name", ns)
    if n is not None and n.text:
        name = n.text.strip()
    coord_el = root.find(".//kml:Point/kml:coordinates", ns)
    if coord_el is None or not coord_el.text:
        # buscar cualquier coordenada, usar la primera
        coord_el = root.find(".//kml:coordinates", ns)
    if coord_el is None or not coord_el.text:
        raise ValueError("No se detectaron coordenadas en el KMZ/KML.")
    txt = coord_el.text.strip().split()[0]
    parts = txt.split(",")
    lon, lat = float(parts[0]), float(parts[1])
    alt = float(parts[2]) if len(parts) > 2 and parts[2] else None
    return {"nombre": name or "Punto de control", "latitud": lat, "longitud": lon, "elevacion": alt}


def bbox_from_point(lat: float, lon: float, margin_deg: float = 0.05) -> dict:
    return {"south": lat - margin_deg, "north": lat + margin_deg, "west": lon - margin_deg, "east": lon + margin_deg}
