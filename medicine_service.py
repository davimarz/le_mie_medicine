"""Autenticazione passwordless e dati delle medicine su Turso."""
import hashlib
import hmac
import json
import re
import secrets
import time
import urllib.request
import uuid
from urllib.parse import urlencode, urlsplit

class AppError(Exception):
    pass

def now():
    return int(time.time())

def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()

def clean(value, label, maximum):
    value = str(value or "").strip()
    if not value or len(value) > maximum:
        raise AppError(f"{label}: inserisci da 1 a {maximum} caratteri.")
    return value

def email_address(value):
    value = str(value or "").strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise AppError("Inserisci un'email valida.")
    return value

class MedicineService:
    SESSION_TTL = 5 * 365 * 86400
    PREVIOUS_LINK_TTL = 3600

    def __init__(self, db, config, mailer=None):
        self.db, self.config, self.mailer = db, config, mailer

    def limit(self, key, maximum=5, seconds=3600):
        stamp = now()
        rows = self.db.rows("""INSERT INTO limits(key,count,expires) VALUES (?,1,?)
        ON CONFLICT(key) DO UPDATE SET count=CASE WHEN expires<? THEN 1 ELSE count+1 END,
        expires=CASE WHEN expires<? THEN excluded.expires ELSE expires END RETURNING count""",
        (digest(key), stamp + seconds, stamp, stamp))
        if rows[0]["count"] > maximum:
            raise AppError("Troppi tentativi. Attendi prima di riprovare.")

    def app_url(self):
        url = str(self.config.get("APP_URL", "")).strip().rstrip("/")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise AppError("Configura APP_URL nei Secrets.")
        return url

    def mail(self, email, subject, text):
        if self.mailer:
            return self.mailer(email, subject, text)
        url = self.config.get("MAIL_BRIDGE_URL", "")
        secret = self.config.get("MAIL_BRIDGE_SECRET", "")
        if not url.startswith("https://script.google.com/macros/s/") or len(secret) < 32:
            raise AppError("Invio email non configurato.")
        payload = json.dumps({"to": email, "subject": subject, "text": text,
                              "timestamp": int(time.time() * 1000), "nonce": secrets.token_hex(32)}, ensure_ascii=False)
        body = json.dumps({"payload": payload, "signature": hmac.new(
            secret.encode(), payload.encode(), hashlib.sha256).hexdigest()}).encode()
        try:
            request = urllib.request.Request(url, body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=20) as response:
                if not json.load(response).get("ok"):
                    raise ValueError()
        except Exception:
            raise AppError("Email non inviata. Riprova più tardi.") from None

    def request_access(self, email, name="", privacy=False):
        email = email_address(email)
        self.limit("send:" + email)
        rows = self.db.rows("SELECT id,name,verified FROM users WHERE email=?", (email,))
        created = False
        if not rows:
            if not privacy:
                raise AppError("Email non registrata. Usa la scheda Registrati.")
            name = clean(name, "Nome", 60)
            uid = uuid.uuid4().hex
            self.db.execute("""INSERT INTO users
                (id,name,email,verified,privacy_accepted_at,created_at) VALUES (?,?,?,?,?,?)""",
                (uid, name, email, 0, now(), now()))
            created = True
        else:
            uid = rows[0]["id"]
        old = self.db.rows("SELECT token_hash FROM access_links WHERE user_id=?", (uid,))
        raw = secrets.token_urlsafe(40)
        link = self.app_url() + "/?" + urlencode({"accesso": raw})
        try:
            self.mail(email, "Il tuo accesso — Le mie medicine",
                      "Apri questo collegamento personale per accedere:\n\n" + link +
                      "\n\nNon condividerlo: equivale a una password.")
        except Exception:
            if created:
                self.db.execute("DELETE FROM users WHERE id=? AND verified=0", (uid,))
            raise
        stamp = now()
        if old:
            self.db.execute("""UPDATE access_links SET previous_token_hash=token_hash,
                previous_expires=?,token_hash=?,created_at=? WHERE user_id=?""",
                (stamp + self.PREVIOUS_LINK_TTL, digest(raw), stamp, uid))
        else:
            self.db.execute("INSERT INTO access_links(user_id,token_hash,created_at) VALUES (?,?,?)",
                            (uid, digest(raw), stamp))

    def finish_link(self, raw):
        if not isinstance(raw, str) or not 32 <= len(raw) <= 128:
            raise AppError("Collegamento non valido.")
        stamp = now()
        rows = self.db.rows("""SELECT u.id FROM access_links a JOIN users u ON u.id=a.user_id
            WHERE a.token_hash=? OR (a.previous_token_hash=? AND a.previous_expires>?)""",
            (digest(raw), digest(raw), stamp))
        if not rows:
            raise AppError("Collegamento non valido o scaduto.")
        token = secrets.token_urlsafe(32)
        self.db.batch([
            ("UPDATE users SET verified=1,last_login=? WHERE id=?", (stamp, rows[0]["id"])),
            ("INSERT INTO sessions(token_hash,user_id,expires,created_at) VALUES (?,?,?,?)",
             (digest(token), rows[0]["id"], stamp + self.SESSION_TTL, stamp)),
            ("DELETE FROM sessions WHERE expires<?", (stamp,)),
        ])
        return token

    def user(self, token):
        rows = self.db.rows("""SELECT u.id,u.name,u.email FROM users u JOIN sessions s ON s.user_id=u.id
            WHERE s.token_hash=? AND s.expires>? AND u.verified=1""", (digest(token), now()))
        if not rows:
            raise AppError("Sessione scaduta. Richiedi un nuovo link.")
        return rows[0]

    def logout(self, token):
        self.db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))

    def logout_all(self, token):
        user = self.user(token)
        self.db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))

    def revoke_link(self, token):
        user = self.user(token)
        self.db.execute("DELETE FROM access_links WHERE user_id=?", (user["id"],))

    def delete_account(self, token):
        user = self.user(token)
        user_id = user["id"]
        self.db.batch([
            ("DELETE FROM sessions WHERE user_id=?", (user_id,)),
            ("DELETE FROM access_links WHERE user_id=?", (user_id,)),
            ("DELETE FROM medicines WHERE user_id=?", (user_id,)),
            ("DELETE FROM users WHERE id=?", (user_id,)),
        ])

    def medicines(self, token, deleted=False):
        user = self.user(token)
        operator = "IS NOT NULL" if deleted else "IS NULL"
        return self.db.rows(f"""SELECT * FROM medicines WHERE user_id=? AND deleted_at {operator}
            ORDER BY expiry, name""", (user["id"],))

    def lookup(self, token, value):
        _code, medicine = self.lookup_any(token, [value])
        return medicine

    def lookup_any(self, token, values):
        """Try every symbol found in one image and return the first AIFA match."""
        self.user(token)
        from barcode_scanner import medicine_lookup_candidates
        raw_values = [str(value or "").strip() for value in values if str(value or "").strip()]
        raw_values.sort(key=lambda value: (0 if re.search(r"A\d{9}", value.upper()) else 1))
        candidates = []
        for raw in raw_values:
            for candidate in medicine_lookup_candidates(raw):
                if candidate not in candidates:
                    candidates.append(candidate)
        for candidate in candidates:
            aic = candidate.zfill(9) if candidate.isdigit() and len(candidate) <= 9 else candidate
            rows = self.db.rows("SELECT * FROM aifa_catalog WHERE barcode=? OR aic=? LIMIT 1",
                                (candidate, aic))
            if rows:
                return candidate, rows[0]
        return (raw_values[0] if raw_values else ""), None

    def save(self, token, data, medicine_id=None):
        user = self.user(token)
        name = clean(data.get("name"), "Farmaco", 200)
        expiry = str(data.get("expiry", ""))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expiry):
            raise AppError("Scadenza non valida.")
        try:
            quantity = max(0, int(data.get("quantity", 0)))
            low_stock = max(0, int(data.get("low_stock", 1)))
            reminder_days = min(365, max(1, int(data.get("reminder_days", 30))))
        except (TypeError, ValueError):
            raise AppError("Quantità e soglie devono essere numeri interi.") from None
        values = (
            name, str(data.get("description") or "")[:500],
            str(data.get("active_ingredient") or "")[:300], str(data.get("company") or "")[:200],
            quantity, str(data.get("unit") or "Pezzi")[:30], expiry,
            str(data.get("aic") or "")[:20], str(data.get("barcode") or "")[:80],
            low_stock, reminder_days, now(),
        )
        if medicine_id:
            result = self.db.execute("""UPDATE medicines SET name=?,description=?,active_ingredient=?,company=?,
                quantity=?,unit=?,expiry=?,aic=?,barcode=?,low_stock=?,reminder_days=?,updated_at=?
                WHERE id=? AND user_id=?""", values + (medicine_id, user["id"]))
            if not result["count"]:
                raise AppError("Farmaco non trovato.")
            return medicine_id
        medicine_id = uuid.uuid4().hex
        self.db.execute("""INSERT INTO medicines
            (id,user_id,name,description,active_ingredient,company,quantity,unit,expiry,aic,barcode,
             low_stock,reminder_days,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (medicine_id, user["id"]) + values[:-1] + (values[-1], values[-1]))
        return medicine_id

    def trash(self, token, medicine_id):
        self._owned_update(token, medicine_id, "deleted_at", now())

    def restore(self, token, medicine_id):
        self._owned_update(token, medicine_id, "deleted_at", None)

    def delete(self, token, medicine_id):
        user = self.user(token)
        self.db.execute("DELETE FROM medicines WHERE id=? AND user_id=?", (medicine_id, user["id"]))

    def _owned_update(self, token, medicine_id, field, value):
        user = self.user(token)
        result = self.db.execute(f"UPDATE medicines SET {field}=?,updated_at=? WHERE id=? AND user_id=?",
                                 (value, now(), medicine_id, user["id"]))
        if not result["count"]:
            raise AppError("Farmaco non trovato.")

    def replace_catalog(self, token, rows, progress=None):
        user = self.user(token)
        if user["email"] != str(self.config.get("ADMIN_EMAIL", "")).strip().lower():
            raise AppError("Operazione riservata.")
        self.db.execute("DELETE FROM aifa_catalog_staging")
        total = max(len(rows), 1)
        try:
            for start in range(0, len(rows), 200):
                block = rows[start:start + 200]
                self.db.batch([("""INSERT OR REPLACE INTO aifa_catalog_staging
                    (aic,description,active_ingredient,company,barcode) VALUES (?,?,?,?,?)""",
                    (r["aic"], r["descrizione"], r.get("principio_attivo"), r.get("ditta"), r.get("barcode")))
                    for r in block])
                if progress:
                    progress(min(0.95, (start + len(block)) / total))
            self.db.batch([
                ("DELETE FROM aifa_catalog", ()),
                ("""INSERT INTO aifa_catalog(aic,description,active_ingredient,company,barcode)
                    SELECT aic,description,active_ingredient,company,barcode FROM aifa_catalog_staging""", ()),
                ("DELETE FROM aifa_catalog_staging", ()),
            ])
            if progress:
                progress(1.0)
        except Exception:
            self.db.execute("DELETE FROM aifa_catalog_staging")
            raise
