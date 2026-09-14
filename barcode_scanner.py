from __future__ import annotations
from io import BytesIO
import re

def _scan_priority(result) -> tuple[int, str]:
    value = (result.text or "").strip().upper()
    if re.search(r"A\d{9}", value):
        return (0, value)
    if "DATAMATRIX" in str(result.format).upper():
        return (1, value)
    return (2, value)

def decode_codes(raw: bytes) -> list[str]:
    """Decode and prioritize pharmaceutical Data Matrix, AIC and EAN values."""
    if not raw:
        return []
    from PIL import Image
    import zxingcpp
    image = Image.open(BytesIO(raw)).convert("RGB")
    values = []
    for result in sorted(zxingcpp.read_barcodes(image), key=_scan_priority):
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
    """Return likely AIC first, followed by barcode and GTIN candidates."""
    raw = (value or "").strip().upper()
    gs1 = parse_gs1(raw)
    candidates = []

    def add(item):
        item = "".join(ch for ch in str(item or "") if ch.isalnum())
        if item and item not in candidates:
            candidates.append(item)

    # Italian pharmaceutical stickers commonly expose A + the 9-digit AIC.
    for aic in re.findall(r"A(\d{9})", raw):
        add(aic)
    # Also recover AIC values embedded in multi-field Data Matrix payloads.
    for digits9 in re.findall(r"(?<!\d)(\d{9})(?!\d)", raw):
        add(digits9)

    normalized = "".join(ch for ch in (gs1.get("01") or raw) if ch.isalnum())
    add(normalized)
    digits = "".join(ch for ch in normalized if ch.isdigit())
    if len(digits) == 14 and digits.startswith("0"):
        add(digits[1:])
        digits = digits[1:]
    if len(digits) == 13:
        if digits.startswith("803"):
            add(digits[3:12])
        add(digits[-10:-1])
    if len(digits) in (8, 9):
        add(digits.zfill(9))
    return candidates
