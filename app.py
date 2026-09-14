import json, os
from datetime import date, datetime
import pandas as pd
import streamlit as st

from aifa_catalog import download_official_catalog
from barcode_scanner import decode_codes
from database import Database, StorageError
from medicine_core import medicines_to_ics
from medicine_service import AppError, MedicineService
from pdf_report import build_inventory_pdf

st.set_page_config(page_title="Le mie medicine",page_icon="💊",layout="wide")
st.markdown("""<style>
:root{--brand:#087ea4;--ink:#17324d;--line:#d9e8ef}.stApp{background:linear-gradient(180deg,#f5fbfd,#fff 300px);color:var(--ink)}
[data-testid="stSidebar"]{background:#eef8fb;border-right:1px solid var(--line)}
[data-testid="stVerticalBlockBorderWrapper"]{background:#fff;border-radius:18px!important;box-shadow:0 8px 24px #17324d0d}
.hero{padding:22px 24px;border-radius:22px;background:linear-gradient(135deg,#087ea4,#14a3b8);color:#fff;margin-bottom:20px}
.hero h1{margin:0;color:#fff}.stButton>button,.stDownloadButton>button{border-radius:12px;min-height:42px;font-weight:650}
@media(max-width:640px){.block-container{padding:1rem .8rem 4rem}.hero{padding:18px}}
</style>""",unsafe_allow_html=True)

def hero(title,text):st.markdown(f'<section class="hero"><h1>{title}</h1><p>{text}</p></section>',unsafe_allow_html=True)
def call(fn,*args):
    try:return True,fn(*args)
    except (AppError,StorageError) as e:st.error(str(e))
    except Exception:st.error("Operazione temporaneamente non disponibile.")
    return False,None

def auth_page(service):
    hero("Le mie medicine","Scansiona la confezione, indica quantità e scadenza")
    st.info("Strumento organizzativo: non sostituisce medico, farmacista o prescrizione.")
    access,register=st.tabs(["Ricevi il link","Registrati"])
    with access:
        with st.form("access"):
            email=st.text_input("Email",autocomplete="email")
            submit=st.form_submit_button("Invia collegamento personale",type="primary",use_container_width=True)
        if submit:
            ok,_=call(service.request_access,email)
            if ok:st.success("Controlla la posta. Il nuovo link sostituisce quello precedente.")
    with register:
        with st.expander("Informativa privacy"):
            try:st.markdown(open("PRIVACY.md",encoding="utf-8").read())
            except OSError:st.warning("Informativa non disponibile.")
        with st.form("register"):
            name=st.text_input("Nome")
            email=st.text_input("Email",key="registration_email")
            privacy=st.checkbox("Confermo di aver letto l'informativa privacy")
            submit=st.form_submit_button("Registrati e ricevi il link",type="primary",use_container_width=True)
        if submit:
            ok,_=call(service.request_access,email,name,privacy)
            if ok:st.success("Registrazione completata. Apri il collegamento ricevuto via email.")

def form_data(prefix,defaults):
    name=st.text_input("Farmaco",value=defaults.get("name") or "",key=prefix+"name")
    active=st.text_input("Principio attivo",value=defaults.get("active_ingredient") or "",key=prefix+"active")
    description=st.text_area("Descrizione",value=defaults.get("description") or "",key=prefix+"description")
    c1,c2,c3=st.columns(3)
    quantity=c1.number_input("Quantità",min_value=0,value=int(defaults.get("quantity") or 1),key=prefix+"quantity")
    units=["Pezzi","Compresse","Bustine","Flaconi","Altro"]; unit=defaults.get("unit") or "Pezzi"
    unit=c2.selectbox("Unità",units,index=units.index(unit) if unit in units else 0,key=prefix+"unit")
    raw=defaults.get("expiry"); expiry=date.fromisoformat(raw) if raw else date.today()
    expiry=c3.date_input("Scadenza",value=expiry,key=prefix+"expiry")
    return {"name":name,"active_ingredient":active,"description":description,"quantity":quantity,"unit":unit,
      "expiry":expiry.isoformat(),"aic":defaults.get("aic"),"barcode":defaults.get("barcode")}

def editor(service,token,current=None):
    hero("Modifica farmaco" if current else "Aggiungi una medicina","Fotografa il codice: dovrai indicare solo quantità e scadenza")
    if not current:
        camera=st.camera_input("Inquadra QR, Data Matrix o codice a barre")
        if camera and st.button("Leggi il codice",type="primary",use_container_width=True):
            try:
                codes=decode_codes(camera.getvalue())
                if not codes:raise AppError("Codice non leggibile. Evita riflessi e riprova.")
                code=codes[0]; ok,found=call(service.lookup,token,code)
                st.session_state.scan_code=code
                st.session_state.scan_result=found or {}
                st.session_state.form_epoch=st.session_state.get("form_epoch",0)+1
                if found:st.success("Farmaco riconosciuto.")
                else:st.warning("Codice non presente nel catalogo. Completa i campi manualmente.")
                st.rerun()
            except AppError as e:st.warning(str(e))
        manual=st.text_input("Oppure inserisci AIC/EAN")
        if st.button("Cerca AIC/EAN",disabled=not manual,use_container_width=True):
            ok,found=call(service.lookup,token,manual)
            if ok:
                st.session_state.scan_code=manual;st.session_state.scan_result=found or {}
                st.session_state.form_epoch=st.session_state.get("form_epoch",0)+1;st.rerun()
    found=st.session_state.get("scan_result",{}) if not current else {}
    defaults=current or {"name":found.get("description",""),"description":found.get("description",""),
      "active_ingredient":found.get("active_ingredient",""),"aic":found.get("aic"),
      "barcode":found.get("barcode") or st.session_state.get("scan_code"),"quantity":1}
    if found:st.info(f"**{found.get('description')}**\n\nPrincipio attivo: {found.get('active_ingredient') or 'non indicato'} · AIC {found.get('aic')}")
    epoch=st.session_state.get("form_epoch",0); prefix=f"med_{(current or {}).get('id','new')}_{epoch}_"
    with st.form(prefix):
        data=form_data(prefix,defaults); submit=st.form_submit_button("Salva",type="primary",use_container_width=True)
    if submit:
        ok,_=call(service.save,token,data,(current or {}).get("id"))
        if ok:
            for k in ("scan_code","scan_result","edit_id"):st.session_state.pop(k,None)
            st.session_state.page="Medicine";st.rerun()

def inventory(service,token):
    ok,rows=call(service.medicines,token)
    if not ok:return
    hero("La mia farmacia",f"{len(rows)} medicinali registrati")
    if st.button("＋ Scansiona una confezione",type="primary",use_container_width=True):
        st.session_state.page="Aggiungi";st.rerun()
    query=st.text_input("Cerca per nome, principio attivo, AIC o barcode").strip().lower()
    for row in rows:
        if query not in " ".join(str(row.get(k) or "") for k in ("name","active_ingredient","aic","barcode")).lower():continue
        with st.container(border=True):
            a,b=st.columns([5,1]);a.subheader(row["name"])
            a.write(f'{row["quantity"]} {row["unit"]} · scadenza {datetime.fromisoformat(row["expiry"]).strftime("%d/%m/%Y")}')
            if row.get("active_ingredient"):a.caption("Principio attivo: "+row["active_ingredient"])
            if b.button("Modifica",key="edit"+row["id"]):st.session_state.edit_id=row["id"];st.session_state.page="Aggiungi";st.rerun()

def trash(service,token):
    ok,rows=call(service.medicines,token,True)
    if not ok:return
    hero("Cestino","Ripristina o elimina definitivamente")
    for row in rows:
        with st.container(border=True):
            a,b,c=st.columns([4,1,1]);a.write(row["name"])
            if b.button("Ripristina",key="r"+row["id"]):call(service.restore,token,row["id"]);st.rerun()
            confirm=st.checkbox("Conferma",key="c"+row["id"])
            if c.button("Elimina",key="d"+row["id"],disabled=not confirm):call(service.delete,token,row["id"]);st.rerun()

def catalog(service,token,user):
    hero("Catalogo AIFA","Anagrafica ufficiale condivisa")
    if user["email"]!=str(service.config.get("ADMIN_EMAIL","")).strip().lower():
        st.info("Il catalogo viene aggiornato dal gestore.");return
    confirm=st.checkbox("Confermo l'aggiornamento dal portale AIFA")
    if st.button("Scarica e aggiorna da AIFA",type="primary",disabled=not confirm):
        try:
            with st.spinner("Download e importazione…"):
                rows=download_official_catalog();service.replace_catalog(token,rows)
            st.success(f"Importate {len(rows):,} confezioni.");st.rerun()
        except Exception:st.error("Aggiornamento non riuscito. Riprova più tardi.")

def data_page(service,token,user):
    ok,rows=call(service.medicines,token)
    if not ok:return
    hero("Dati e calendario","Scarica una copia delle tue medicine")
    converted=[{"id":r["id"],"nome":r["name"],"principio_attivo":r.get("active_ingredient"),"quantita":r["quantity"],"tipo":r["unit"],"scadenza":r["expiry"],"aic":r.get("aic")} for r in rows]
    df=pd.DataFrame(converted);st.dataframe(df,use_container_width=True,hide_index=True)
    a,b,c=st.columns(3)
    a.download_button("CSV",df.to_csv(index=False).encode("utf-8-sig"),"medicine.csv")
    b.download_button("Calendario",medicines_to_ics(converted),"scadenze.ics")
    c.download_button("PDF",build_inventory_pdf(converted,user["email"]),"medicine.pdf")

def main(service):
    if not st.session_state.get("token") and st.query_params.get("accesso"):
        ok,token=call(service.finish_link,st.query_params.get("accesso"));st.query_params.clear()
        if ok:st.session_state.token=token;st.rerun()
    token=st.session_state.get("token")
    if not token:auth_page(service);return
    ok,user=call(service.user,token)
    if not ok:st.session_state.pop("token",None);return
    pages=["Medicine","Aggiungi","Cestino","Catalogo AIFA","Dati"]
    with st.sidebar:
        st.title("Le mie medicine");st.caption(user["email"])
        page=st.radio("Menu",pages,index=pages.index(st.session_state.get("page","Medicine")) if st.session_state.get("page") in pages else 0)
        st.session_state.page=page
        if st.button("Esci",use_container_width=True):service.logout(token);st.session_state.clear();st.rerun()
    if page=="Medicine":inventory(service,token)
    elif page=="Aggiungi":
        rows=service.medicines(token);current=next((r for r in rows if r["id"]==st.session_state.get("edit_id")),None)
        editor(service,token,current)
    elif page=="Cestino":trash(service,token)
    elif page=="Catalogo AIFA":catalog(service,token,user)
    else:data_page(service,token,user)

try:
    config=dict(st.secrets)
    required=("TURSO_DATABASE_URL","TURSO_AUTH_TOKEN","ADMIN_EMAIL","APP_URL","MAIL_BRIDGE_URL","MAIL_BRIDGE_SECRET")
    if not all(config.get(k) for k in required):raise AppError("Completa i Secrets Turso e posta elettronica.")
    db=Database(config["TURSO_DATABASE_URL"],config["TURSO_AUTH_TOKEN"]);db.initialize()
    main(MedicineService(db,config))
except (AppError,StorageError) as e:hero("Le mie medicine","Configurazione richiesta");st.info(str(e))
