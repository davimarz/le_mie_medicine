import json
import os
from datetime import date

import pandas as pd
import streamlit as st
from supabase import create_client

from data_access import MedicineRepository
from medicine_core import EMAIL_RE, expiry_status, medicines_to_ics, normalize_aic, parse_aifa_csv, parse_date, reminders, validate_password
from pdf_report import build_inventory_pdf

st.set_page_config(page_title="Le mie medicine", page_icon="💊", layout="wide")


def setting(name, fallback=""):
    try:
        return st.secrets.get(name, os.getenv(name, fallback))
    except Exception:
        return os.getenv(name, fallback)


SB_URL = setting("SUPABASE_URL", "https://maiildnzyocmdjnodofh.supabase.co")
SB_KEY = setting("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_O_ey2wT14cC-RHQdgv6_uA_ql9980Q9")


def client():
    if "_client" not in st.session_state:
        st.session_state._client = create_client(SB_URL, SB_KEY)
    return st.session_state._client


def remember(session):
    if session:
        st.session_state.access_token = session.access_token
        st.session_state.refresh_token = session.refresh_token
        st.session_state.user_id = session.user.id
        st.session_state.email = session.user.email
        st.session_state.app_metadata = session.user.app_metadata or {}


def clear_session():
    for key in list(st.session_state):
        if key != "_client":
            st.session_state.pop(key, None)


def restore_session():
    if not st.session_state.get("access_token") or not st.session_state.get("refresh_token"):
        return False
    try:
        response = client().auth.set_session(st.session_state.access_token, st.session_state.refresh_token)
        remember(response.session)  # Persist rotated access and refresh tokens.
        user = client().auth.get_user().user
        if not user:
            raise ValueError("invalid session")
        profile = client().table("profiles").select("username").eq("id", user.id).maybe_single().execute()
        st.session_state.username = (profile.data or {}).get("username") or user.email.split("@", 1)[0]
        return True
    except Exception:
        clear_session()
        return False


def safe_error(label):
    st.error(f"{label}. Riprova; se il problema continua contatta l'assistenza.")


def login_page():
    st.title("Le mie medicine")
    st.caption("Inventario personale di farmaci, scorte e scadenze")
    st.info("Strumento organizzativo: non sostituisce medico, farmacista o prescrizione.")
    access, register, reset = st.tabs(["Accedi", "Registrati", "Password dimenticata"])
    with access:
        with st.form("login"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Accedi", use_container_width=True)
        if submit:
            try:
                remember(client().auth.sign_in_with_password({"email": email.strip().lower(), "password": password}).session)
                st.rerun()
            except Exception:
                st.error("Email o password non validi.")
    with register:
        with st.form("register"):
            username = st.text_input("Nome visualizzato")
            email = st.text_input("Email", key="reg_email")
            password = st.text_input("Password", type="password", key="reg_password")
            confirm = st.text_input("Conferma password", type="password")
            privacy = st.checkbox("Accetto l'informativa privacy")
            submit = st.form_submit_button("Crea account", use_container_width=True)
        if submit:
            errors = validate_password(password)
            if not username.strip() or not EMAIL_RE.match(email.strip()): st.error("Nome o email non validi.")
            elif errors: st.error("Password: " + ", ".join(errors) + ".")
            elif password != confirm: st.error("Le password non coincidono.")
            elif not privacy: st.error("Accetta l'informativa privacy.")
            else:
                try:
                    response = client().auth.sign_up({"email": email.strip().lower(), "password": password, "options": {"data": {"username": username.strip(), "privacy_accepted_at": date.today().isoformat()}}})
                    if response.session: remember(response.session); st.rerun()
                    st.success("Controlla l'email per confermare la registrazione.")
                except Exception: safe_error("Registrazione non riuscita")
    with reset:
        email = st.text_input("Email dell'account", key="reset_email")
        if st.button("Invia link di recupero", use_container_width=True):
            try: client().auth.reset_password_email(email.strip().lower()); st.success("Se l'indirizzo è registrato riceverai un'email.")
            except Exception: safe_error("Invio non riuscito")


def form_values(prefix, d):
    units = ["Pezzi", "Compresse", "Bustine", "Flaconi", "Altro"]
    nome = st.text_input("Nome farmaco", value=d.get("nome") or "", key=prefix+"nome")
    principio = st.text_input("Principio attivo", value=d.get("principio_attivo") or "", key=prefix+"pa")
    descrizione = st.text_area("Descrizione / note", value=d.get("descrizione") or "", key=prefix+"desc")
    c1, c2, c3 = st.columns(3)
    quantita = c1.number_input("Quantità", min_value=0, value=int(d.get("quantita") or 0), key=prefix+"qty")
    unit = d.get("tipo") if d.get("tipo") in units else "Pezzi"
    tipo = c2.selectbox("Unità", units, index=units.index(unit), key=prefix+"unit")
    scadenza = c3.date_input("Scadenza", value=parse_date(d.get("scadenza")), key=prefix+"exp")
    aic = st.text_input("AIC", value=d.get("aic") or "", key=prefix+"aic")
    barcode = st.text_input("Barcode / EAN (compatibile con lettori USB)", value=d.get("barcode") or "", key=prefix+"bar")
    c1, c2 = st.columns(2)
    soglia = c1.number_input("Soglia scorta", min_value=0, value=int(d.get("soglia_scorta") or 0), key=prefix+"stock")
    reminder_days = c2.number_input("Preavviso scadenza", 1, 365, int(d.get("reminder_days") or 30), key=prefix+"days")
    dosaggio = st.text_input("Dosaggio prescritto", value=d.get("dosaggio") or "", key=prefix+"dose")
    orari = st.text_input("Orari prescritti", value=d.get("orari") or "", key=prefix+"times")
    note_mediche = st.text_area("Note personali sulla prescrizione", value=d.get("note_mediche") or "", key=prefix+"notes")
    return {"nome": nome.strip(), "descrizione": descrizione.strip() or None, "principio_attivo": principio.strip() or None, "quantita": int(quantita), "tipo": tipo, "scadenza": scadenza.isoformat(), "aic": normalize_aic(aic) or None, "barcode": barcode.strip() or None, "soglia_scorta": int(soglia), "reminder_days": int(reminder_days), "dosaggio": dosaggio.strip() or None, "orari": orari.strip() or None, "note_mediche": note_mediche.strip() or None}


def dashboard(repo):
    meds = repo.medicines()
    alert_items = reminders(meds)
    st.title("La mia farmacia")
    a, b, c = st.columns(3); a.metric("Farmaci", len(meds)); b.metric("Promemoria", len(alert_items)); c.metric("Catalogo AIFA", repo.catalog_count())
    for item in alert_items:
        med = item["medicine"]; message = "scorta bassa" if item["kind"] == "stock" else expiry_status(med["scadenza"])[2].lower()
        st.warning(f"{med['nome']}: {message}")
    query = st.text_input("Cerca", placeholder="Nome, principio attivo, AIC o barcode").strip().lower()
    for med in meds:
        if query and query not in " ".join(str(med.get(k) or "") for k in ("nome", "principio_attivo", "aic", "barcode", "descrizione")).lower(): continue
        with st.container(border=True):
            left, right = st.columns([5, 1]); left.subheader(med["nome"]); left.write(f"{med['quantita']} {med['tipo']} · {expiry_status(med['scadenza'])[2]}")
            if med.get("principio_attivo"): left.caption("Principio attivo: " + med["principio_attivo"])
            if med.get("photo_path"):
                try: right.image(repo.signed_photo_url(med["photo_path"]), width=120)
                except Exception: pass
            if right.button("Modifica", key=f"edit_{med['id']}"): st.session_state.edit_id=med["id"]; st.session_state.page="Aggiungi o modifica"; st.rerun()


def editor(repo):
    meds = repo.medicines(); edit_id = st.session_state.get("edit_id"); current = next((m for m in meds if m["id"] == edit_id), None)
    st.title("Modifica farmaco" if current else "Aggiungi farmaco")
    lookup = st.text_input("Cerca nel catalogo tramite AIC o barcode")
    found = None
    if lookup:
        try: found = repo.catalog_lookup(lookup)
        except Exception: safe_error("Catalogo non disponibile")
    defaults = current or ({"nome": (found or {}).get("descrizione", ""), "principio_attivo": (found or {}).get("principio_attivo", ""), "aic": (found or {}).get("aic", ""), "barcode": (found or {}).get("barcode", ""), "quantita": 1} if found else {"quantita": 1})
    with st.form(f"medicine_{edit_id or 'new'}"):
        payload = form_values(str(edit_id or "new"), defaults); photo = st.file_uploader("Foto confezione (massimo 5 MB)", type=["jpg", "jpeg", "png", "webp"]); save = st.form_submit_button("Salva", type="primary", use_container_width=True)
    if save:
        if not payload["nome"]: st.error("Il nome è obbligatorio."); return
        try:
            if photo: payload["photo_path"] = repo.upload_photo(photo)
            repo.update_medicine(current["id"], payload) if current else repo.create_medicine(payload)
            st.session_state.pop("edit_id", None); st.session_state.page="I miei farmaci"; st.rerun()
        except Exception: safe_error("Salvataggio non riuscito")
    if current:
        confirmed = st.checkbox("Confermo lo spostamento nel cestino")
        if st.button("Sposta nel cestino", disabled=not confirmed): repo.trash(current["id"]); st.session_state.pop("edit_id", None); st.rerun()


def trash(repo):
    st.title("Cestino")
    for med in [m for m in repo.medicines(True) if m.get("deleted_at")]:
        a,b,c=st.columns([4,1,1]); a.write(med["nome"])
        if b.button("Ripristina", key=f"restore_{med['id']}"): repo.restore(med["id"]); st.rerun()
        if c.button("Elimina definitivamente", key=f"purge_{med['id']}"): repo.permanently_delete(med["id"]); st.rerun()


def treatments(repo):
    st.title("Piano di assunzione"); st.warning("Registra solo indicazioni ricevute da medico o farmacista; l'app non calcola dosaggi.")
    meds=repo.medicines()
    with st.form("treatment"):
        med=st.selectbox("Farmaco", meds, format_func=lambda x:x["nome"], disabled=not meds); instruction=st.text_input("Indicazione prescritta"); times=st.text_input("Orari"); start=st.date_input("Dal"); end=st.date_input("Al", value=None); add=st.form_submit_button("Aggiungi", disabled=not meds)
    if add and instruction.strip(): repo.add_treatment({"medicine_id":med["id"],"instruction":instruction.strip(),"times":times.strip() or None,"start_date":start.isoformat(),"end_date":end.isoformat() if end else None}); st.rerun()
    for row in repo.treatments():
        a,b=st.columns([5,1]); a.write(f"{row['instruction']} · {row.get('times') or 'orario non indicato'}")
        if b.button("Rimuovi",key=f"treat_{row['id']}"): repo.delete_treatment(row["id"]); st.rerun()


def caregivers(repo):
    st.title("Accesso caregiver"); st.caption("Il caregiver deve avere un account e riceve accesso in sola lettura.")
    with st.form("invite"):
        email=st.text_input("Email caregiver"); label=st.text_input("Etichetta"); invite=st.form_submit_button("Condividi")
    if invite:
        try: repo.invite_caregiver(email,label); st.success("Accesso condiviso."); st.rerun()
        except Exception: safe_error("Condivisione non riuscita; verifica che l'account esista")
    for share in repo.shares():
        a,b=st.columns([5,1]); a.write(share.get("label") or "Caregiver")
        if share.get("owner_id")==st.session_state.user_id and b.button("Revoca",key=f"share_{share['id']}"): repo.remove_share(share["id"]); st.rerun()


def data_page(repo):
    st.title("Esporta, importa e calendario"); rows=repo.medicines(); df=pd.DataFrame(rows); st.dataframe(df,use_container_width=True,hide_index=True)
    clean=[{k:v for k,v in row.items() if k not in {"id","user_id","created_at","updated_at","deleted_at"}} for row in rows]
    a,b,c,d=st.columns(4); a.download_button("CSV",df.to_csv(index=False).encode("utf-8-sig"),"medicine.csv"); b.download_button("Backup JSON",json.dumps(clean,ensure_ascii=False,default=str,indent=2),"medicine-backup.json"); c.download_button("Calendario",medicines_to_ics(rows),"scadenze.ics"); d.download_button("PDF",build_inventory_pdf(rows,st.session_state.email),"medicine.pdf")
    backup=st.file_uploader("Ripristina backup JSON",type=["json"])
    if backup and st.button("Importa backup"):
        try:
            payload=json.loads(backup.getvalue().decode()); assert isinstance(payload,list) and len(payload)<=1000
            allowed={"nome","descrizione","principio_attivo","quantita","tipo","scadenza","aic","barcode","soglia_scorta","reminder_days","dosaggio","orari","note_mediche"}
            for row in payload:
                item={k:v for k,v in row.items() if k in allowed}
                if item.get("nome") and item.get("scadenza"): repo.create_medicine(item)
            st.success("Backup importato."); st.rerun()
        except Exception: st.error("Backup non valido.")


def catalog(repo):
    st.title("Catalogo AIFA condiviso"); st.write(f"Record: **{repo.catalog_count():,}**".replace(",","."))
    if st.session_state.get("app_metadata",{}).get("role")!="admin": st.info("Il catalogo è aggiornato centralmente dagli amministratori."); return
    upload=st.file_uploader("CSV AIFA",type=["csv"]); confirm=st.checkbox("Confermo la sostituzione atomica")
    if upload and st.button("Aggiorna catalogo",disabled=not confirm):
        try: rows=parse_aifa_csv(upload.getvalue()); repo.import_catalog(rows); st.success(f"Importati {len(rows):,} record.")
        except Exception: safe_error("Aggiornamento non riuscito")


def account(repo):
    st.title("Account, privacy e attività"); st.markdown("I dati servono esclusivamente all'inventario personale. Puoi esportarli o eliminare l'account. L'app non fornisce diagnosi o prescrizioni.")
    with st.form("password"):
        password=st.text_input("Nuova password",type="password"); change=st.form_submit_button("Cambia password")
    if change:
        errors=validate_password(password)
        if errors: st.error("Password: "+", ".join(errors)+".")
        else:
            try: client().auth.update_user({"password":password}); st.success("Password aggiornata.")
            except Exception: safe_error("Modifica non riuscita")
    with st.expander("Registro attività"): st.dataframe(pd.DataFrame(repo.audit_events()),use_container_width=True,hide_index=True)
    phrase=st.text_input("Per eliminare account e dati scrivi ELIMINA")
    if st.button("Elimina definitivamente il mio account",disabled=phrase!="ELIMINA"):
        try: client().rpc("delete_own_account").execute(); clear_session(); st.rerun()
        except Exception: safe_error("Eliminazione non riuscita")


if not restore_session(): login_page(); st.stop()
repo=MedicineRepository(client(),st.session_state.user_id)
pages={"I miei farmaci":dashboard,"Aggiungi o modifica":editor,"Piano di assunzione":treatments,"Cestino":trash,"Caregiver":caregivers,"Catalogo AIFA":catalog,"Dati e calendario":data_page,"Account e privacy":account}
with st.sidebar:
    st.title("Le mie medicine"); st.caption(st.session_state.email); current=st.session_state.get("page","I miei farmaci"); page=st.radio("Menu",list(pages),index=list(pages).index(current) if current in pages else 0); st.session_state.page=page
    if st.button("Esci",use_container_width=True):
        try: client().auth.sign_out()
        finally: clear_session(); st.rerun()
try: pages[page](repo)
except Exception: safe_error("Operazione non disponibile")
