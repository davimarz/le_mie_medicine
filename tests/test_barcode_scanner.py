from barcode_scanner import medicine_lookup_candidates


def test_candidates_keep_scanned_ean_and_extract_likely_aic():
    candidates = medicine_lookup_candidates("8031234567890")
    assert candidates[0] == "8031234567890"
    assert "123456789" in candidates


def test_candidates_normalize_short_aic():
    assert medicine_lookup_candidates("12345678") == ["12345678", "012345678"]


def test_candidates_extract_aspirina_c_aic_from_bollino():
    assert medicine_lookup_candidates("A004763114")[0] == "004763114"


def test_candidates_extract_aic_from_multifield_datamatrix():
    candidates = medicine_lookup_candidates("A004763114\x1d072050014")
    assert candidates[0] == "004763114"
