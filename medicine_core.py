import csv
import io
import re
from datetime import date, datetime, timedelta


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_aic(value: str | None) -> str:
    code = (value or "").strip().upper()
    if code.startswith("A") and code[1:].isdigit():
        code = code[1:]
    return code.zfill(9) if code.isdigit() else code


def parse_date(value, fallback: date | None = None) -> date:
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback or date.today()


def expiry_status(value, today: date | None = None, warning_days: int = 30):
    today = today or date.today()
    expiry = parse_date(value, today)
    days = (expiry - today).days
    if days < 0:
        return "expired", days, f"Scaduto da {-days} giorni"
    if days <= warning_days:
        return "expiring", days, f"Scade tra {days} giorni"
    return "ok", days, f"Scadenza {expiry.strftime('%d/%m/%Y')}"


def validate_password(password: str) -> list[str]:
    errors = []
    if len(password) < 10:
        errors.append("usa almeno 10 caratteri")
    if not re.search(r"[A-Za-z]", password):
        errors.append("aggiungi almeno una lettera")
    if not re.search(r"\d", password):
        errors.append("aggiungi almeno un numero")
    return errors


def parse_aifa_csv(raw: bytes, max_bytes: int = 25_000_000) -> list[dict]:
    if len(raw) > max_bytes:
        raise ValueError("Il CSV supera il limite di 25 MB.")
    text = None
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            pass
    if text is None:
        raise ValueError("Codifica del CSV non riconosciuta.")
    sample = text[:5000]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    required = {"codice_aic", "denominazione"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError("Il CSV deve contenere codice_aic e denominazione.")
    rows = []
    seen = set()
    for row in reader:
        aic = normalize_aic(row.get("codice_aic"))
        name = (row.get("denominazione") or "").strip()
        if not aic or not name or aic in seen:
            continue
        seen.add(aic)
        rows.append({
            "aic": aic,
            "descrizione": f"{name} {(row.get('descrizione') or '').strip()}".strip()[:300],
            "principio_attivo": ((row.get("pa_associati") or row.get("principio_attivo") or "").strip()[:300] or None),
            "ditta": ((row.get("ragione_sociale") or "").strip()[:150] or None),
            "barcode": ((row.get("barcode") or row.get("ean") or "").strip()[:32] or None),
        })
    if not rows:
        raise ValueError("Il CSV non contiene record AIFA validi.")
    return rows


def reminders(medicines: list[dict], today: date | None = None) -> list[dict]:
    today = today or date.today()
    items = []
    for med in medicines:
        expiry = parse_date(med.get("scadenza"), today)
        if expiry <= today + timedelta(days=int(med.get("reminder_days") or 30)):
            items.append({"kind": "expiry", "medicine": med, "date": expiry})
        threshold = int(med.get("soglia_scorta") or 0)
        if int(med.get("quantita") or 0) <= threshold:
            items.append({"kind": "stock", "medicine": med, "date": today})
    return sorted(items, key=lambda item: (item["date"], item["medicine"].get("nome", "")))


def escape_ics(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def medicines_to_ics(medicines: list[dict]) -> bytes:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Le mie medicine//IT"]
    for med in medicines:
        expiry = parse_date(med.get("scadenza"))
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:medicine-{med.get('id')}@le-mie-medicine",
            f"DTSTART;VALUE=DATE:{expiry.strftime('%Y%m%d')}",
            f"SUMMARY:{escape_ics('Scadenza ' + str(med.get('nome', 'farmaco')))}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")
