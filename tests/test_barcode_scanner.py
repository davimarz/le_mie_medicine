from barcode_scanner import medicine_lookup_candidates


def test_candidates_keep_scanned_ean_and_extract_likely_aic():
    candidates = medicine_lookup_candidates("8031234567890")
    assert candidates[0] == "8031234567890"
    assert "123456789" in candidates


def test_candidates_normalize_short_aic():
    assert medicine_lookup_candidates("12345678") == ["12345678", "012345678"]
