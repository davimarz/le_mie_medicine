import hashlib
from datetime import date, datetime
import pandas as pd
import streamlit as st

from aifa_catalog import download_official_catalog
from barcode_scanner import decode_codes
from database import Database, StorageError
from medicine_core import medicines_to_ics
from medicine_service import AppError, MedicineService
from pdf_report import build_inventory_pdf

st.set_page_config(page_title="Le mie medicine", page_icon="💊", layout="wide")
st.markdown("""<style>
:root{--brand:#087ea4;--ink:#17324d;--line:#d9e8ef}
.stApp{background:linear-gradient(180deg,#f4fbfd,#fff 320px);color:var(--ink)}
[data-testid="stSidebar"]{background:#eef8fb;border-right:1px solid var(--line)}
[data-testid="stVerticalBlockBorderWrapper"]{background:#fff;border-radius:18px!important;box-shadow:0 8px 24px #17324d0d}
.hero{padding:22px 24px;border-radius:22px;background:linear-gradient(135deg,#087ea4,#14a3b8);color:#fff;margin-bottom:20px}
.hero h1{margin:0;color:#fff}.hero p{margin:.4rem 0 0}
.stButton>button,.stDownloadButton>button{border-radius:12px;min-height:44px;font-weight:650}
.badge{display:inline-block;border-radius:999px;padding:5px 10px;font-weight:700;margin-bottom:8px}
.danger{background:#ffe5e5;color:#8b0000}.warning{background:#fff2cc;color:#624900}.ok{background:#dff5e5;color:#14532d}
@media(max-width:640px){.block-container{padding:1rem .8rem 5rem}.hero{padding:18px}.stButton>button{width:100%}}
</style>""", unsafe_allow_html=True)

def hero(title, text):
    st.markdown(f'<section class="hero"><h1>{title}</h1><p>{text}</p></section>', unsafe_allow_html=True)

def call(function, *args):
    try:
        return True, function(*args)
    except (AppError, StorageError) as error:
        st.error(str(error))
    except Exception:
        st.error("Operazione temporaneamente non disponibile.")
    return False, None

def go(page):
    st.session_state.page = page
    st.rerun()

def auth_page(service):
    hero("Le mie medicine", "Scansiona la confezione, indica quantità e scadenza")
    st.info("Strumento organizzativo: non sostituisce medico, farmacista o prescrizione.")
    access, register = st.tabs(["Ricevi il link", "Registrati"])
    with access:
        with st.form("access"):
            email = st.text_input("Email", autocomplete="email")
            submit = st.form_submit_button("Invia collegamento personale", type="primary", use_container_width=True)
        if submit:
            ok, _ = call(service.request_access, email)
            if ok:
                st.success("Controlla la posta. Per un'ora funziona anche il link precedente.")
    with register:
        with st.expander("Leggi l'informativa privacy"):
            try:
                st.markdown(open("PRIVACY.md", encoding="utf-8").read())
            except OSError:
                st.warning("Informativa non disponibile.")
        with st.form("register"):
            name = st.text_input("Nome")
            email = st.text_input("Email", key="registration_email")
            privacy = st.checkbox("Confermo di aver letto e accettato l'informativa")
            submit = st.form_submit_button("Registrati e ricevi il link", type="primary", use_container_width=True)
        if submit:
            ok, _ = call(service.request_access, email, name, privacy)
            if ok:
                st.success("Registrazione completata. Apri il collegamento ricevuto via email.")

def form_data(prefix, defaults):
    name = st.text_input("Farmaco", value=defaults.get("name") or "", key=prefix + "name")
    c1, c2 = st.columns(2)
    quantity = c1.number_input("Quantità", min_value=0, value=int(defaults.get("quantity", 1)), key=prefix + "quantity")
    raw = defaults.get("expiry")
    expiry = c2.date_input("Scadenza", value=date.fromisoformat(raw) if raw else date.today(), key=prefix + "expiry")
    with st.expander("Dettagli e promemoria"):
        active = st.text_input("Principio attivo", value=defaults.get("active_ingredient") or "", key=prefix + "active")
        description = st.text_area("Descrizione", value=defaults.get("description") or "", key=prefix + "description")
        company = st.text_input("Ditta", value=defaults.get("company") or "", key=prefix + "company")
        c3, c4, c5 = st.columns(3)
        units = ["Pezzi", "Compresse", "Bustine", "Flaconi", "Altro"]
        unit0 = defaults.get("unit") or "Pezzi"
        unit = c3.selectbox("Unità", units, index=units.index(unit0) if unit0 in units else 0, key=prefix + "unit")
        low_stock = c4.number_input("Avvisa sotto", min_value=0, value=int(defaults.get("low_stock", 1)), key=prefix + "low")
        reminder = c5.number_input("Preavviso scadenza (giorni)", 1, 365, int(defaults.get("reminder_days", 30)), key=prefix + "reminder")
    return {"name": name, "active_ingredient": active, "description": description, "company": company,
            "quantity": quantity, "unit": unit, "expiry": expiry.isoformat(),
            "aic": defaults.get("aic"), "barcode": defaults.get("barcode"),
            "low_stock": low_stock, "reminder_days": reminder}

def apply_scan(service, token, codes):
    values = list(codes) if isinstance(codes, (list, tuple)) else [codes]
    ok, result = call(service.lookup_any, token, values)
    if ok:
        matched_code, found = result
        st.session_state.scan_code = matched_code
        st.session_state.scan_result = found or {}
        st.session_state.form_epoch = st.session_state.get("form_epoch", 0) + 1
        st.session_state.scan_message = "Farmaco riconosciuto dal codice AIC." if found else "Nessun codice presente nel catalogo: completa i campi."
        st.rerun()

def editor(service, token, current=None):
    hero("Modifica farmaco" if current else "Aggiungi una medicina",
         "Scansiona la confezione: poi bastano quantità e scadenza")
    if not current:
        camera = st.camera_input("Inquadra QR, Data Matrix o codice a barre")
        if camera:
            raw = camera.getvalue()
            fingerprint = hashlib.sha256(raw).hexdigest()
            if st.session_state.get("last_scan") != fingerprint:
                st.session_state.last_scan = fingerprint
                try:
                    codes = decode_codes(raw)
                    if not codes:
                        raise AppError("Codice non leggibile. Evita riflessi e riprova.")
                    apply_scan(service, token, codes)
                except AppError as error:
                    st.warning(str(error))
        manual = st.text_input("Oppure inserisci AIC/EAN")
        if st.button("Cerca AIC/EAN", disabled=not manual, use_container_width=True):
            apply_scan(service, token, manual)
    message = st.session_state.pop("scan_message", None)
    if message:
        st.success(message) if st.session_state.get("scan_result") else st.warning(message)
    found = st.session_state.get("scan_result", {}) if not current else {}
    defaults = current or {"name": found.get("description", ""), "description": found.get("description", ""),
        "active_ingredient": found.get("active_ingredient", ""), "company": found.get("company", ""),
        "aic": found.get("aic"), "barcode": found.get("barcode") or st.session_state.get("scan_code"), "quantity": 1}
    if found:
        st.info(f"**{found.get('description')}**\n\n{found.get('active_ingredient') or 'Principio attivo non indicato'} · AIC {found.get('aic')}")
    epoch = st.session_state.get("form_epoch", 0)
    prefix = f"med_{(current or {}).get('id', 'new')}_{epoch}_"
    with st.form(prefix):
        data = form_data(prefix, defaults)
        save = st.form_submit_button("Salva medicina", type="primary", use_container_width=True)
    if save:
        ok, _ = call(service.save, token, data, (current or {}).get("id"))
        if ok:
            for key in ("scan_code", "scan_result", "edit_id", "last_scan"):
                st.session_state.pop(key, None)
            go("Medicine")
    if current:
        st.divider()
        confirm = st.checkbox("Confermo di voler spostare questa medicina nel cestino")
        if st.button("Sposta nel cestino", disabled=not confirm, use_container_width=True):
            ok, _ = call(service.trash, token, current["id"])
            if ok:
                st.session_state.pop("edit_id", None)
                go("Medicine")

def status(row):
    days = (date.fromisoformat(row["expiry"]) - date.today()).days
    if days < 0:
        return 0, "Scaduto", "danger"
    if row["quantity"] <= row.get("low_stock", 1):
        return 1, "Scorta bassa", "warning"
    if days <= row.get("reminder_days", 30):
        return 2, f"Scade tra {days} giorni", "warning"
    return 3, "Regolare", "ok"

def inventory(service, token):
    ok, rows = call(service.medicines, token)
    if not ok:
        return
    rows = sorted(rows, key=lambda row: (status(row)[0], row["expiry"], row["name"].lower()))
    hero("La mia farmacia", f"{len(rows)} medicinali registrati")
    if st.button("＋ Scansiona una confezione", type="primary", use_container_width=True):
        go("Aggiungi")
    if not rows:
        st.info("Non hai ancora medicine. Premi il pulsante qui sopra per scansionare la prima confezione.")
        return
    query = st.text_input("Cerca per nome, principio attivo, AIC o barcode").strip().lower()
    visible = [row for row in rows if query in " ".join(str(row.get(k) or "") for k in
               ("name", "active_ingredient", "aic", "barcode")).lower()]
    if not visible:
        st.info("Nessun farmaco corrisponde alla ricerca.")
    for row in visible:
        _, label, css = status(row)
        with st.container(border=True):
            st.markdown(f'<span class="badge {css}">{label}</span>', unsafe_allow_html=True)
            a, b = st.columns([5, 1])
            a.subheader(row["name"])
            a.write(f'{row["quantity"]} {row["unit"]} · scadenza {datetime.fromisoformat(row["expiry"]).strftime("%d/%m/%Y")}')
            if row.get("active_ingredient"):
                a.caption("Principio attivo: " + row["active_ingredient"])
            if b.button("Modifica", key="edit" + row["id"]):
                st.session_state.edit_id = row["id"]
                go("Aggiungi")

def trash_page(service, token):
    ok, rows = call(service.medicines, token, True)
    if not ok:
        return
    hero("Cestino", "Ripristina o elimina definitivamente")
    if not rows:
        st.info("Il cestino è vuoto.")
    for row in rows:
        with st.container(border=True):
            a, b, c = st.columns([4, 1, 1])
            a.write(row["name"])
            if b.button("Ripristina", key="r" + row["id"]):
                call(service.restore, token, row["id"]); st.rerun()
            confirm = st.checkbox("Conferma", key="c" + row["id"])
            if c.button("Elimina", key="d" + row["id"], disabled=not confirm):
                call(service.delete, token, row["id"]); st.rerun()

def catalog(service, token, user):
    hero("Catalogo AIFA", "Anagrafica ufficiale condivisa")
    if user["email"] != str(service.config.get("ADMIN_EMAIL", "")).strip().lower():
        st.info("Il catalogo viene aggiornato dal gestore.")
        return
    confirm = st.checkbox("Confermo l'aggiornamento dal portale AIFA")
    if st.button("Scarica e aggiorna da AIFA", type="primary", disabled=not confirm):
        bar = st.progress(0, "Download catalogo…")
        try:
            rows = download_official_catalog()
            service.replace_catalog(token, rows, lambda value: bar.progress(value, "Importazione in corso…"))
            st.success(f"Importate {len(rows):,} confezioni.")
        except Exception:
            st.error("Aggiornamento non riuscito: il catalogo precedente è rimasto intatto.")

def data_page(service, token, user):
    ok, rows = call(service.medicines, token)
    if not ok:
        return
    hero("Dati e calendario", "Scarica una copia delle tue medicine e i promemoria")
    converted = [{"id": r["id"], "nome": r["name"], "principio_attivo": r.get("active_ingredient"),
                  "quantita": r["quantity"], "tipo": r["unit"], "scadenza": r["expiry"], "aic": r.get("aic")}
                 for r in rows]
    df = pd.DataFrame(converted)
    st.dataframe(df, use_container_width=True, hide_index=True)
    a, b, c = st.columns(3)
    a.download_button("Scarica CSV", df.to_csv(index=False).encode("utf-8-sig"), "medicine.csv", use_container_width=True)
    b.download_button("Calendario ICS", medicines_to_ics(converted), "scadenze.ics", use_container_width=True)
    c.download_button("Rapporto PDF", build_inventory_pdf(converted, user["email"]), "medicine.pdf", use_container_width=True)

def account_page(service, token, user):
    hero("Account e privacy", "Gestisci accessi e dati personali")
    st.write(f"**{user['name']}** · {user['email']}")
    with st.expander("Informativa privacy"):
        st.markdown(open("PRIVACY.md", encoding="utf-8").read())
    if st.button("Revoca il collegamento personale", use_container_width=True):
        ok, _ = call(service.revoke_link, token)
        if ok:
            st.success("Collegamento revocato. Potrai richiederne uno nuovo dalla pagina iniziale.")
    if st.button("Disconnetti tutti i dispositivi", use_container_width=True):
        ok, _ = call(service.logout_all, token)
        if ok:
            st.session_state.clear(); st.rerun()
    st.subheader("Elimina account")
    phrase = st.text_input('Scrivi "ELIMINA" per cancellare definitivamente account e medicine')
    if st.button("Elimina definitivamente", disabled=phrase != "ELIMINA", type="primary", use_container_width=True):
        ok, _ = call(service.delete_account, token)
        if ok:
            st.session_state.clear(); st.rerun()

def main(service):
    if not st.session_state.get("token") and st.query_params.get("accesso"):
        ok, token = call(service.finish_link, st.query_params.get("accesso"))
        st.query_params.clear()
        if ok:
            st.session_state.token = token
            st.rerun()
    token = st.session_state.get("token")
    if not token:
        auth_page(service)
        return
    ok, user = call(service.user, token)
    if not ok:
        st.session_state.pop("token", None)
        return
    pages = ["Medicine", "Aggiungi", "Cestino", "Catalogo AIFA", "Dati", "Account"]
    with st.sidebar:
        st.title("Le mie medicine")
        st.caption(user["email"])
        page = st.radio("Menu", pages, index=pages.index(st.session_state.get("page", "Medicine"))
                        if st.session_state.get("page") in pages else 0)
        st.session_state.page = page
        if st.button("Esci", use_container_width=True):
            service.logout(token); st.session_state.clear(); st.rerun()
    if page == "Medicine":
        inventory(service, token)
    elif page == "Aggiungi":
        rows = service.medicines(token)
        current = next((row for row in rows if row["id"] == st.session_state.get("edit_id")), None)
        editor(service, token, current)
    elif page == "Cestino":
        trash_page(service, token)
    elif page == "Catalogo AIFA":
        catalog(service, token, user)
    elif page == "Dati":
        data_page(service, token, user)
    else:
        account_page(service, token, user)

try:
    config = dict(st.secrets)
    required = ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "ADMIN_EMAIL", "APP_URL", "MAIL_BRIDGE_URL", "MAIL_BRIDGE_SECRET")
    if not all(config.get(key) for key in required):
        raise AppError("Completa i Secrets Turso e posta elettronica.")
    database = Database(config["TURSO_DATABASE_URL"], config["TURSO_AUTH_TOKEN"])
    database.initialize()
    main(MedicineService(database, config))
except (AppError, StorageError) as error:
    hero("Le mie medicine", "Configurazione richiesta")
    st.info(str(error))
