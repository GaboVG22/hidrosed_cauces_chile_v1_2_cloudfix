"""Descarga DEM COP30/SRTM desde OpenTopography GlobalDEM."""
from __future__ import annotations
from pathlib import Path
import requests

GLOBALDEM_URL = "https://portal.opentopography.org/API/globaldem"


def build_globaldem_url(bbox: dict, api_key: str, demtype: str = "COP30", output_format: str = "GTiff") -> str:
    params = {
        "demtype": demtype,
        "south": bbox["south"], "north": bbox["north"], "west": bbox["west"], "east": bbox["east"],
        "outputFormat": output_format,
        "API_Key": api_key,
    }
    req = requests.Request("GET", GLOBALDEM_URL, params=params).prepare()
    return req.url


def download_dem(bbox: dict, api_key: str, output_path: str | Path, demtype: str = "COP30") -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not api_key:
        raise ValueError("Se requiere API Key de OpenTopography para descargar DEM global.")
    url = build_globaldem_url(bbox, api_key, demtype=demtype)
    r = requests.get(url, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Error OpenTopography {r.status_code}: {r.text[:300]}")
    ctype = r.headers.get("content-type", "")
    if "text" in ctype.lower() and b"error" in r.content[:500].lower():
        raise RuntimeError(f"Respuesta no raster desde OpenTopography: {r.text[:300]}")
    output_path.write_bytes(r.content)
    return output_path
