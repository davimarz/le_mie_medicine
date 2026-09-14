from __future__ import annotations

from io import BytesIO


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


def medicine_lookup_candidates(value: str) -> list[str]:
    """Return likely database keys encoded by Italian medicine packages."""
    value = "".join(ch for ch in (value or "").strip() if ch.isalnum())
    candidates = [value]
    # Italian pharmaceutical EANs often contain the 9 digit AIC before check digit.
    if value.isdigit() and len(value) == 13:
        candidates.extend((value[-10:-1], value[3:12]))
    if value.isdigit() and len(value) in (8, 9):
        candidates.append(value.zfill(9))
    return list(dict.fromkeys(item for item in candidates if item))
