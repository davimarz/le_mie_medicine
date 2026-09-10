import csv
import io
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from supabase import create_client

SUPABASE_URL = "https://maiildnzyocmdjnodofh.supabase.co"
SUPABASE_KEY = "sb_publishable_O_ey2wT14cC-RHQdgv6_uA_ql9980Q9"

st.set_page_config(
    page_title="I miei farmaci",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def client(authed=True):
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    if authed and st.session_state.get("access_token") and st.session_state.get("refresh_token"):
        sb.auth.set_session(st.session_state.access_token, st.session_state.refresh_token)
    return sb


def remember_session(session):
    st.session_state.access_token = session.access_token
    st.session_state.refresh_token = session.refresh_token
    st.session_state.user_id = session.user.id
    st.session_state.email = session.user.email


def clear_session():
    for key in ("access_token", "refresh_token", "user_id", "email", "username", "page"):
        st.session_state.pop(key, None)


def restore_session():
    if not st.session_state.get("access_token") or not st.session_state.get("refresh_token"):
        return False
    try:
        result = client().auth.get_user()
        if not result or not result.user:
            clear_session()
            return False
        st.session_state.user_id = result.user.id
        st.session_state.email = result.user.email
        profile = client().table("profiles").select("username").eq("id", result.user.id).maybe_single().execute()
        if profile.data:
            st.session_state.username = profile.data.get("username")
        return True
    except Exception:
        clear_session()
        return False


def login(email, password):
    try:
        response = client(False).auth.sign_in_with_password({"email": email.strip().lower(), "password": password})
        remember_session(response.session)
        profile = client().table("profiles").select("username").eq("id", response.user.id).maybe_single().execute()
        st.session_state.username = (profile.data or {}).get("username") or email.split("@", 1)[0]
        return True, "Accesso effettuato."
    except Exception as exc:
        return False, f"Accesso non riuscito: {exc}"


def register(username, email, password):
    username = username.strip()
    email = email.strip().lower()
    if not username or not email or not password:
        return False, "Compila tutti i campi."
    if len(password) < 6:
        return False, "La password deve contenere almeno 6 caratteri."
    try:
        response = client(False).auth.sign_up(
            {
                "email": email,
                "password": password,
                "options": {"data": {"username": username}},
            }
        )
        if response.session:
            remember_session(response.session)
            st.session_state.username = username
            return True, "Account creato e accesso effettuato."
        return True, "Account creato. Controlla l'email per confermare la registrazione, poi accedi."
    except Exception as exc:
        return False, f"Registrazione non riuscita: {exc}"


def logout():
    try:
        client().auth.sign_out()
    except Exception:
        pass
    clear_session()
    st.rerun()


def list_medicines():
    response = (
        client()
        .table("farmaci")
        .select("id,nome,descrizione,principio_attivo,quantita,tipo,scadenza,aic,created_at")
        .order("nome")
        .execute()
    )
    return response.data or []


def add_medicine(nome, descrizione, principio_attivo, quantita, tipo, scadenza, aic):
    payload = {
        "user_id": st.session_state.user_id,
        "nome": nome.strip(),
        "descrizione": descrizione.strip() or None,
        "principio_attivo": principio_attivo.strip() or None,
        "quantita": int(quantita),
        "tipo": tipo,
        "scadenza": scadenza.isoformat(),
        "aic": aic.strip() or None,
    }
    client().table("farmaci").insert(payload).execute()


def update_quantity(medicine_id, quantity):
    client().table("farmaci").update({"quantita": int(quantity)}).eq("id", medicine_id).execute()


def delete_medicine(medicine_id):
    client().table("farmaci").delete().eq("id", medicine_id).execute()


def find_aifa(aic):
    code = (aic or "").strip().upper()
    if code.startswith("A") and code[1:].isdigit():
        code = code[1:]
    candidates = [code]
    if code.isdigit():
        candidates.append(code.zfill(9))
        if code.startswith("0"):
            candidates.append(code[1:])
    for candidate in dict.fromkeys(candidates):
        result = (
            client()
            .table("aifa_cache")
            .select("aic,descrizione,principio_attivo,ditta")
            .eq("aic", candidate)
            .maybe_single()
            .execute()
        )
        if result.data:
            return result.data
    return None


def aifa_count():
    result = client().table("aifa_cache").select("aic", count="exact").limit(1).execute()
    return result.count or 0


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

    delimiter = ";" if text[:5000].count(";") >= text[:5000].count(",") else ","
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
        principio = (row.get("pa_associati") or row.get("principio_attivo") or "").strip()
        if raw_aic and denominazione:
            rows.append(
                {
                    "user_id": st.session_state.user_id,
                    "aic": raw_aic,
                    "descrizione": f"{denominazione} {descrizione}".strip()[:300],
                    "principio_attivo": principio[:300] or None,
                    "ditta": ditta[:150] or None,
                }
            )

    sb = client()
    sb.table("aifa_cache").delete().eq("user_id", st.session_state.user_id).execute()
    batch_size = 500
    for start in range(0, len(rows), batch_size):
        sb.table("aifa_cache").upsert(rows[start : start + batch_size], on_conflict="user_id,aic").execute()
    return len(rows)


def parse_date(value):
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return date.today()


def show_login():
    st.title("I miei farmaci")
    st.caption("Gestione personale di farmaci, quantità e scadenze")
    login_tab, register_tab = st.tabs(["Accedi", "Registrati"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Accedi", use_container_width=True)
        if submitted:
            ok, message = login(email, password)
            if ok:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    with register_tab:
        with st.form("register_form"):
            username = st.text_input("Nome utente")
            email = st.text_input("Email", key="reg_email")
            password = st.text_input("Password", type="password", key="reg_password")
            confirm = st.text_input("Conferma password", type="password")
            submitted = st.form_submit_button("Crea account", use_container_width=True)
        if submitted:
            if password != confirm:
                st.error("Le password non coincidono.")
            else:
                ok, message = register(username, email, password)
                if ok:
                    st.success(message)
                    if st.session_state.get("user_id"):
                        st.rerun()
                else:
                    st.error(message)


def show_dashboard():
    medicines = list_medicines()
    today = date.today()
    expired = sum(parse_date(m["scadenza"]) < today for m in medicines)
    expiring = sum(today <= parse_date(m["scadenza"]) <= today + timedelta(days=30) for m in medicines)

    st.title("La mia farmacia")
    st.caption(f"Utente: {st.session_state.get('username') or st.session_state.email}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Farmaci", len(medicines))
    c2.metric("In scadenza", expiring)
    c3.metric("Scaduti", expired)
    c4.metric("Archivio AIFA", aifa_count())

    st.divider()
    if not medicines:
        st.info("Non hai ancora inserito farmaci. Usa 'Aggiungi farmaco' dal menu laterale.")
        return

    query = st.text_input("Cerca nei tuoi farmaci", placeholder="Nome, principio attivo o AIC").strip().lower()
    filtered = []
    for med in medicines:
        haystack = " ".join(str(med.get(k) or "") for k in ("nome", "descrizione", "principio_attivo", "aic")).lower()
        if not query or query in haystack:
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
                if med.get("principio_attivo"):
                    st.write(f"Principio attivo: {med['principio_attivo']}")
                if med.get("aic"):
                    st.write(f"AIC: {med['aic']}")
                if med.get("descrizione"):
                    st.write(med["descrizione"])
                st.caption(status)
            with middle:
                qty = st.number_input(
                    f"Quantità ({med['tipo']})",
                    min_value=0,
                    value=int(med["quantita"]),
                    step=1,
                    key=f"qty_{med['id']}",
                )
                if qty != int(med["quantita"]):
                    if st.button("Salva quantità", key=f"save_{med['id']}"):
                        update_quantity(med["id"], qty)
                        st.rerun()
            with right:
                if st.button("Elimina", key=f"delete_{med['id']}"):
                    delete_medicine(med["id"])
                    st.rerun()


def show_add():
    st.title("Aggiungi farmaco")
    st.subheader("Ricerca AIFA")
    aic_search = st.text_input("Codice AIC", placeholder="Es. 012345678")
    found = None
    if aic_search:
        try:
            found = find_aifa(aic_search)
        except Exception as exc:
            st.warning(f"Ricerca AIFA non disponibile: {exc}")
        if found:
            st.success("Farmaco trovato nell'archivio AIFA.")
            st.write(f"**{found['descrizione']}**")
            if found.get("principio_attivo"):
                st.write(f"Principio attivo: {found['principio_attivo']}")
            if found.get("ditta"):
                st.caption(f"Ditta: {found['ditta']}")

    with st.form("add_medicine_form"):
        nome = st.text_input("Nome farmaco", value=(found or {}).get("descrizione", ""))
        principio = st.text_input("Principio attivo", value=(found or {}).get("principio_attivo") or "")
        descrizione = st.text_area("Descrizione / note")
        c1, c2 = st.columns(2)
        quantita = c1.number_input("Quantità", min_value=0, value=1, step=1)
        tipo = c2.selectbox("Unità", ["Pezzi", "Compresse", "Bustine", "Flaconi", "Altro"])
        scadenza = st.date_input("Data di scadenza", min_value=date.today())
        aic = st.text_input("AIC", value=(found or {}).get("aic") or aic_search)
        submitted = st.form_submit_button("Salva farmaco", use_container_width=True)
    if submitted:
        if not nome.strip():
            st.error("Inserisci il nome del farmaco.")
        else:
            add_medicine(nome, descrizione, principio, quantita, tipo, scadenza, aic)
            st.success("Farmaco aggiunto.")
            st.session_state.page = "I miei farmaci"
            st.rerun()


def show_aifa():
    st.title("Archivio AIFA")
    try:
        count = aifa_count()
    except Exception:
        count = 0
    st.write(f"Record presenti per il tuo account: **{count:,}**".replace(",", "."))
    st.caption("Carica il file confezioni.csv. L'archivio è privato e associato al tuo account.")
    uploaded = st.file_uploader("Carica confezioni.csv", type=["csv"])
    if uploaded is not None and st.button("Importa archivio AIFA", type="primary"):
        try:
            with st.spinner("Importazione in corso..."):
                count = import_aifa(uploaded)
            st.success(f"Importati {count:,} record.".replace(",", "."))
        except Exception as exc:
            st.error(f"Importazione non riuscita: {exc}")


def show_export():
    st.title("Esporta i miei farmaci")
    rows = list_medicines()
    if not rows:
        st.info("Non ci sono farmaci da esportare.")
        return
    df = pd.DataFrame(rows)
    wanted = ["nome", "descrizione", "principio_attivo", "quantita", "tipo", "scadenza", "aic"]
    df = df[[c for c in wanted if c in df.columns]]
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button(
        "Scarica CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="i_miei_farmaci.csv",
        mime="text/csv",
        use_container_width=True,
    )


if not restore_session():
    show_login()
    st.stop()

with st.sidebar:
    st.title("I miei farmaci")
    st.caption(st.session_state.get("email", ""))
    choices = ["I miei farmaci", "Aggiungi farmaco", "Archivio AIFA", "Esporta dati"]
    current = st.session_state.get("page", "I miei farmaci")
    if current not in choices:
        current = choices[0]
    page = st.radio("Menu", choices, index=choices.index(current))
    st.session_state.page = page
    st.divider()
    if st.button("Esci", use_container_width=True):
        logout()

try:
    if page == "I miei farmaci":
        show_dashboard()
    elif page == "Aggiungi farmaco":
        show_add()
    elif page == "Archivio AIFA":
        show_aifa()
    else:
        show_export()
except Exception as exc:
    st.error(f"Errore di collegamento al database: {exc}")
    st.caption("Riprova tra qualche secondo. I dati sono salvati su Supabase e non dipendono dal filesystem di Streamlit.")
