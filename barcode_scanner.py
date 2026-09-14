from __future__ import annotations
from io import BytesIO
import re

def decode_codes(raw: bytes) -> list[str]:
    """Decode QR, EAN and Data Matrix values from a camera image."""
    if not raw:
        return []
    from PIL import Image
    import zxingcpp
    image = Image.open(BytesIO(raw)).convert("RGB")
    values = []
    for result in zxingcpp.read_barcodes(image):
        value = (result.text or "").strip()
        if value and value not in values:
            values.append(value)
    return values

def parse_gs1(value: str) -> dict[str, str]:
    """Extract common GS1 identifiers from parenthesized or FNC1 data."""
    raw = (value or "").strip()
    result = {}
    for ai, val in re.findall(r"\((01|10|17|21)\)([^()\x1d]+)", raw):
        result[ai] = val
    compact = raw.replace("\x1d", "")
    if not result and compact.startswith("01") and len(compact) >= 16 and compact[2:16].isdigit():
        result["01"] = compact[2:16]
    return result

def medicine_lookup_candidates(value: str) -> list[str]:
    """Return barcode/GTIN and likely 9-digit AIC values."""
    gs1 = parse_gs1(value)
    raw = gs1.get("01") or (value or "")
    normalized = "".join(ch for ch in raw if ch.isalnum())
    candidates = [normalized]
    digits = "".join(ch for ch in normalized if ch.isdigit())
    if len(digits) == 14 and digits.startswith("0"):
        candidates.append(digits[1:])
        digits = digits[1:]
    if len(digits) == 13:
        # Italian pharmaceutical GTIN: prefix 803 + AIC + check digit.
        if digits.startswith("803"):
            candidates.append(digits[3:12])
        candidates.append(digits[-10:-1])
    if len(digits) in (8, 9):
        candidates.append(digits.zfill(9))
    return list(dict.fromkeys(item for item in candidates if item))
