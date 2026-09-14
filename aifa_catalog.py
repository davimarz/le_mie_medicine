from __future__ import annotations

import requests

from medicine_core import parse_aifa_csv


AIFA_CONFEZIONI_URL = "https://drive.aifa.gov.it/farmaci/confezioni_fornitura.csv"


def download_official_catalog(max_bytes: int = 50_000_000) -> list[dict]:
    """Download and validate the official AIFA medicines registry."""
    response = requests.get(AIFA_CONFEZIONI_URL, timeout=(10, 90), stream=True)
    response.raise_for_status()
    content = bytearray()
    for chunk in response.iter_content(1024 * 256):
        content.extend(chunk)
        if len(content) > max_bytes:
            raise ValueError("Il catalogo AIFA supera il limite previsto.")
    return parse_aifa_csv(bytes(content), max_bytes=max_bytes)
