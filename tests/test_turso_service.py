import sqlite3
from pathlib import Path

import pytest

from database import Database
from medicine_service import AppError, MedicineService, digest

CONFIG = {
    "APP_URL": "https://lemiemedicine.streamlit.app",
    "ADMIN_EMAIL": "admin@example.com",
}

@pytest.fixture
def service(tmp_path):
    sent = []
    database = Database(local_path=str(tmp_path / "app.db"))
    database.initialize()
    return MedicineService(database, CONFIG, lambda email, subject, text: sent.append((email, text))), sent

def register(service, email="mario@example.com"):
    app, sent = service
    app.request_access(email, "Mario", True)
    raw = sent[-1][1].split("accesso=")[1].splitlines()[0]
    return app, app.finish_link(raw)

def test_fresh_database_registration_login_and_zero_quantity(service):
    app, token = register(service)
    app.save(token, {"name": "Prova", "quantity": 0, "expiry": "2030-01-01"})
    assert app.medicines(token)[0]["quantity"] == 0

def test_failed_email_keeps_previous_link(tmp_path):
    database = Database(local_path=str(tmp_path / "app.db"))
    database.initialize()
    sent = []
    app = MedicineService(database, CONFIG, lambda email, subject, text: sent.append(text))
    app.request_access("mario@example.com", "Mario", True)
    old = sent[-1].split("accesso=")[1].splitlines()[0]
    app.mailer = lambda *args: (_ for _ in ()).throw(AppError("posta ko"))
    with pytest.raises(AppError):
        app.request_access("mario@example.com")
    assert app.finish_link(old)

def test_trash_restore_and_account_cascade(service):
    app, token = register(service)
    medicine_id = app.save(token, {"name": "Prova", "quantity": 1, "expiry": "2030-01-01"})
    app.trash(token, medicine_id)
    assert len(app.medicines(token, True)) == 1
    app.restore(token, medicine_id)
    assert len(app.medicines(token)) == 1
    app.delete_account(token)
    assert app.db.rows("SELECT COUNT(*) AS n FROM medicines")[0]["n"] == 0

def test_catalog_swap_is_atomic(service):
    app, token = register(service, "admin@example.com")
    app.db.execute("INSERT INTO aifa_catalog(aic,description) VALUES (?,?)", ("000000001", "Vecchio"))
    app.replace_catalog(token, [{"aic": "000000002", "descrizione": "Nuovo"}])
    assert app.db.rows("SELECT description FROM aifa_catalog") == [{"description": "Nuovo"}]
