import csv
import io
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from werkzeug.security import check_password_hash, generate_password_hash

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "farmaci.db"

st.set_page_config(
    page_title="I miei farmaci",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------
# Database
# -----------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(150) UNIQUE NOT NULL,
                email VARCHAR(150) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS farmaco (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome VARCHAR(100) NOT NULL,
                descrizione VARCHAR(300),
                principio_attivo VARCHAR(300),
                quantita INTEGER NOT NULL,
                tipo VARCHAR(50) NOT NULL DEFAULT 'Pezzi',
                scadenza DATE NOT NULL,
                aic VARCHAR(50),
                user_id INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES user(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS aifa_cache (
                aic VARCHAR(20) PRIMARY KEY,
                descrizione VARCHAR(300),
                principio_attivo VARCHAR(300),
                ditta VARCHAR(150)
            )
            """
        )
        conn.commit()


def get_user_by_username(username):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM user WHERE username = ?", (username.strip(),)
        ).fetchone()


def register_user(username, email, password):
    username = username.strip()
    email = email.strip().lower()
    if not username or not email or not password:
        return False, "Compila tutti i campi."
    if len(password) < 6:
        return False, "La password deve contenere almeno 6 caratteri."

    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO user (username, email, password) VALUES (?, ?, ?)",
                (username, email, generate_password_hash(password)),
            )
            conn.commit()
        return True, "Registrazione completata."
    except sqlite3.IntegrityError:
        return False, "Username o email già registrati."


def verify_password(user, password):
    stored = user["password"] or ""
    try:
        if stored.startswith(("scrypt:", "pbkdf2:")):
            return check_password_hash(stored, password), None
    except ValueError:
        pass

    # Compatibilità con i vecchi account Flask che avevano password in chiaro.
    if stored == password:
        new_hash = generate_password_hash(password)
        with get_conn() as conn:
            conn.execute("UPDATE user SET password = ? WHERE id = ?", (new_hash, user["id"]))
            conn.commit()
        return True, "Password aggiornata automaticamente in formato sicuro."

    return False, None


def list_medicines(user_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM farmaco WHERE user_id = ? ORDER BY nome COLLATE NOCASE",
            (user_id,),
        ).fetchall()


def add_medicine(user_id, nome, descrizione, principio_attivo, quantita, tipo, scadenza, aic):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO farmaco
            (nome, descrizione, principio_attivo, quantita, tipo, scadenza, aic, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nome.strip(),
                descrizione.strip(),
                principio_attivo.strip(),
                int(quantita),
                tipo,
                scadenza.isoformat(),
                aic.strip(),
                user_id,
            ),
        )
        conn.commit()


def update_quantity(medicine_id, user_id, quantity):
    with get_conn() as conn:
        conn.execute(
            "UPDATE farmaco SET quantita = ? WHERE id = ? AND user_id = ?",
            (int(quantity), medicine_id, user_id),
        )
        conn.commit()


def delete_medicine(medicine_id, user_id):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM farmaco WHERE id = ? AND user_id = ?",
            (medicine_id, user_id),
        )
        conn.commit()


def find_aifa(aic):
    code = (aic or "").strip().upper()
    if code.startswith("A") and code[1:].isdigit():
        code = code[1:]

    candidates = [code]
    if code.isdigit():
        candidates.append(code.zfill(9))
        if code.startswith("0"):
            candidates.append(code[1:])

    with get_conn() as conn:
        for candidate in dict.fromkeys(candidates):
            row = conn.execute(
                "SELECT * FROM aifa_cache WHERE aic = ?", (candidate,)
            ).fetchone()
            if row:
                return row
    return None


def import_aifa(uploaded_file):
    raw = uploaded_file.getvalue()
    text = None
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Codifica del CSV non riconosciuta.")

    sample = text[:5000]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("CSV senza intestazioni.")

    rows = []
    for row in reader:
        raw_aic = (row.get("codice_aic") or "").strip()
        if raw_aic.isdigit():
            raw_aic = raw_aic.zfill(9)

        denominazione = (row.get("denominazione") or "").strip()
        descrizione = (row.get("descrizione") or "").strip()
        ditta = (row.get("ragione_sociale") or "").strip()
        principio = (
            row.get("pa_associati")
            or row.get("principio_attivo")
            or ""
        ).strip()

        if raw_aic and denominazione:
            rows.append(
                (
                    raw_aic,
                    f"{denominazione} {descrizione}".strip()[:300],
                    principio[:300],
                    ditta[:150],
                )
            )

    with get_conn() as conn:
        conn.execute("DELETE FROM aifa_cache")
        conn.executemany(
            "INSERT OR REPLACE INTO aifa_cache (aic, descrizione, principio_attivo, ditta) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    return len(rows)


def aifa_count():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM aifa_cache").fetchone()[0]


# -----------------------------
# UI helpers
# -----------------------------
def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return date.today()


def logout():
    st.session_state.pop("user_id", None)
    st.session_state.pop("username", None)
    st.rerun()


def show_login():
    st.title("I miei farmaci")
    st.caption("Gestione personale di farmaci, quantità e scadenze")

    login_tab, register_tab = st.tabs(["Accedi", "Registrati"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Accedi", use_container_width=True)

        if submitted:
            user = get_user_by_username(username)
            if not user:
                st.error("Credenziali non valide.")
            else:
                ok, note = verify_password(user, password)
                if ok:
                    st.session_state.user_id = user["id"]
                    st.session_state.username = user["username"]
                    if note:
                        st.toast(note)
                    st.rerun()
                else:
                    st.error("Credenziali non valide.")

    with register_tab:
        with st.form("register_form"):
            new_username = st.text_input("Username", key="reg_username")
            new_email = st.text_input("Email")
            new_password = st.text_input("Password", type="password", key="reg_password")
            confirm = st.text_input("Conferma password", type="password")
            submitted = st.form_submit_button("Crea account", use_container_width=True)

        if submitted:
            if new_password != confirm:
                st.error("Le password non coincidono.")
            else:
                ok, message = register_user(new_username, new_email, new_password)
                if ok:
                    st.success(message + " Ora puoi accedere.")
                else:
                    st.error(message)


def show_dashboard():
    medicines = list_medicines(st.session_state.user_id)
    today = date.today()
    expired = sum(parse_date(m["scadenza"]) < today for m in medicines)
    expiring = sum(
        today <= parse_date(m["scadenza"]) <= today + timedelta(days=30)
        for m in medicines
    )

    st.title("La mia farmacia")
    st.caption(f"Utente: {st.session_state.username}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Farmaci", len(medicines))
    c2.metric("In scadenza", expiring)
    c3.metric("Scaduti", expired)
    c4.metric("Archivio AIFA", aifa_count())

    st.divider()

    if not medicines:
        st.info("Non hai ancora inserito farmaci. Usa 'Aggiungi farmaco' dal menu laterale.")
        return

    query = st.text_input("Cerca nei tuoi farmaci", placeholder="Nome, principio attivo o AIC")
    query_lower = query.strip().lower()

    filtered = []
    for med in medicines:
        haystack = " ".join(
            str(med[k] or "")
            for k in ("nome", "descrizione", "principio_attivo", "aic")
        ).lower()
        if not query_lower or query_lower in haystack:
            filtered.append(med)

    for med in filtered:
        expiry = parse_date(med["scadenza"])
        days = (expiry - today).days
        if days < 0:
            status = f"Scaduto da {-days} giorni"
        elif days <= 30:
            status = f"Scade tra {days} giorni"
        else:
            status = f"Scadenza {expiry.strftime('%d/%m/%Y')}"

        with st.container(border=True):
            left, middle, right = st.columns([4, 2, 1])
            with left:
                st.subheader(med["nome"])
                details = []
                if med["principio_attivo"]:
                    details.append(f"Principio attivo: {med['principio_attivo']}")
                if med["aic"]:
                    details.append(f"AIC: {med['aic']}")
                if med["descrizione"]:
                    details.append(med["descrizione"])
                st.write("  \n".join(details) if details else "Nessun dettaglio aggiuntivo")
                st.caption(status)

            with middle:
                qty = st.number_input(
                    f"Quantità ({med['tipo']})",
                    min_value=0,
                    value=int(med["quantita"]),
                    step=1,
                    key=f"qty_{med['id']}",
                )
                if qty != med["quantita"]:
                    if st.button("Salva quantità", key=f"save_{med['id']}"):
                        update_quantity(med["id"], st.session_state.user_id, qty)
                        st.rerun()

            with right:
                if st.button("Elimina", key=f"delete_{med['id']}", type="secondary"):
                    delete_medicine(med["id"], st.session_state.user_id)
                    st.rerun()


def show_add():
    st.title("Aggiungi farmaco")

    st.subheader("Ricerca AIFA")
    aic_search = st.text_input("Codice AIC", placeholder="Es. 012345678")
    found = None
    if aic_search:
        found = find_aifa(aic_search)
        if found:
            st.success("Farmaco trovato nell'archivio AIFA.")
            st.write(f"**{found['descrizione']}**")
            if found["principio_attivo"]:
                st.write(f"Principio attivo: {found['principio_attivo']}")
            if found["ditta"]:
                st.caption(f"Ditta: {found['ditta']}")
        else:
            st.warning("AIC non trovato nell'archivio caricato.")

    with st.form("add_medicine_form"):
        nome_default = found["descrizione"] if found else ""
        principio_default = found["principio_attivo"] if found else ""
        aic_default = found["aic"] if found else aic_search

        nome = st.text_input("Nome farmaco", value=nome_default)
        principio = st.text_input("Principio attivo", value=principio_default or "")
        descrizione = st.text_area("Descrizione / note")
        c1, c2 = st.columns(2)
        quantita = c1.number_input("Quantità", min_value=0, value=1, step=1)
        tipo = c2.selectbox("Unità", ["Pezzi", "Compresse", "Bustine", "Flaconi", "Altro"])
        scadenza = st.date_input("Data di scadenza", min_value=date.today())
        aic = st.text_input("AIC", value=aic_default or "")
        submitted = st.form_submit_button("Salva farmaco", use_container_width=True)

    if submitted:
        if not nome.strip():
            st.error("Inserisci il nome del farmaco.")
        else:
            add_medicine(
                st.session_state.user_id,
                nome,
                descrizione,
                principio,
                quantita,
                tipo,
                scadenza,
                aic,
            )
            st.success("Farmaco aggiunto.")
            st.session_state.page = "I miei farmaci"
            st.rerun()


def show_aifa():
    st.title("Archivio AIFA")
    st.write(f"Record presenti: **{aifa_count():,}**".replace(",", "."))
    st.caption("Carica il file confezioni.csv scaricato da AIFA. Il nuovo import sostituisce la cache precedente.")

    uploaded = st.file_uploader("Carica confezioni.csv", type=["csv"])
    if uploaded is not None and st.button("Importa archivio AIFA", type="primary"):
        try:
            with st.spinner("Importazione in corso..."):
                count = import_aifa(uploaded)
            st.success(f"Importati {count:,} farmaci.".replace(",", "."))
            st.rerun()
        except Exception as exc:
            st.error(f"Errore durante l'importazione: {exc}")

    st.divider()
    st.subheader("Verifica un AIC")
    code = st.text_input("AIC da cercare", key="aifa_lookup")
    if code:
        row = find_aifa(code)
        if row:
            st.write(f"**{row['descrizione']}**")
            st.write(f"Principio attivo: {row['principio_attivo'] or '—'}")
            st.write(f"Ditta: {row['ditta'] or '—'}")
        else:
            st.info("Nessun risultato.")


def show_export():
    st.title("Esporta i miei farmaci")
    medicines = list_medicines(st.session_state.user_id)
    if not medicines:
        st.info("Non ci sono farmaci da esportare.")
        return

    df = pd.DataFrame([dict(row) for row in medicines])
    df = df.drop(columns=["user_id"], errors="ignore")
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button(
        "Scarica CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="i_miei_farmaci.csv",
        mime="text/csv",
        use_container_width=True,
    )


# -----------------------------
# App
# -----------------------------
init_db()

if "user_id" not in st.session_state:
    show_login()
    st.stop()

if "page" not in st.session_state:
    st.session_state.page = "I miei farmaci"

st.sidebar.title("I miei farmaci")
st.sidebar.write(f"Accesso: **{st.session_state.username}**")

pages = ["I miei farmaci", "Aggiungi farmaco", "Archivio AIFA", "Esporta"]
selected = st.sidebar.radio(
    "Menu",
    pages,
    index=pages.index(st.session_state.page) if st.session_state.page in pages else 0,
)
st.session_state.page = selected

st.sidebar.divider()
if st.sidebar.button("Esci", use_container_width=True):
    logout()

if selected == "I miei farmaci":
    show_dashboard()
elif selected == "Aggiungi farmaco":
    show_add()
elif selected == "Archivio AIFA":
    show_aifa()
elif selected == "Esporta":
    show_export()
