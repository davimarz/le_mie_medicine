from datetime import date
import pytest
from medicine_core import expiry_status, medicines_to_ics, normalize_aic, parse_aifa_csv, reminders, validate_password

def test_normalize_aic():
    assert normalize_aic("A123") == "000000123"
    assert normalize_aic(" 012345678 ") == "012345678"

def test_expiry_status():
    assert expiry_status("2026-09-13", date(2026, 9, 14))[0] == "expired"
    assert expiry_status("2026-10-01", date(2026, 9, 14))[0] == "expiring"

def test_password_policy():
    assert validate_password("short")
    assert validate_password("passwordonly")
    assert not validate_password("Farmaco2026")

def test_parse_aifa_csv_and_limit():
    raw = "codice_aic;denominazione;pa_associati;ragione_sociale\n123;Test;Principio;Ditta\n".encode()
    assert parse_aifa_csv(raw)[0]["aic"] == "000000123"
    with pytest.raises(ValueError): parse_aifa_csv(raw, max_bytes=2)

def test_reminders_and_calendar():
    meds = [{"id":1,"nome":"Test","scadenza":"2026-09-20","quantita":1,"soglia_scorta":1,"reminder_days":30}]
    assert {item["kind"] for item in reminders(meds,date(2026,9,14))} == {"expiry","stock"}
    calendar = medicines_to_ics(meds).decode()
    assert "DTSTART;VALUE=DATE:20260920" in calendar
    assert "SUMMARY:Scadenza Test" in calendar
