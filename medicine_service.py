"""Autenticazione passwordless e dati delle medicine su Turso."""
import hashlib,hmac,json,re,secrets,time,urllib.request,uuid
from urllib.parse import urlencode,urlsplit

class AppError(Exception):pass
def now():return int(time.time())
def digest(v):return hashlib.sha256(str(v).encode()).hexdigest()
def clean(v,label,maximum):
    v=str(v or "").strip()
    if not v or len(v)>maximum:raise AppError(f"{label}: inserisci da 1 a {maximum} caratteri.")
    return v
def email_address(v):
    v=str(v or "").strip().lower()
    if len(v)>254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",v):raise AppError("Inserisci un'email valida.")
    return v

class MedicineService:
    SESSION_TTL=5*365*86400
    def __init__(self,db,config):self.db,self.config=db,config
    def limit(self,key,maximum=5,seconds=3600):
        stamp=now(); rows=self.db.rows("""INSERT INTO limits(key,count,expires) VALUES (?,1,?)
        ON CONFLICT(key) DO UPDATE SET count=CASE WHEN expires<? THEN 1 ELSE count+1 END,
        expires=CASE WHEN expires<? THEN excluded.expires ELSE expires END RETURNING count""",
        (digest(key),stamp+seconds,stamp,stamp))
        if rows[0]["count"]>maximum:raise AppError("Troppi tentativi. Attendi prima di riprovare.")
    def app_url(self):
        url=str(self.config.get("APP_URL","")).strip().rstrip("/"); p=urlsplit(url)
        if p.scheme!="https" or not p.hostname or p.username or p.password or p.query or p.fragment:raise AppError("Configura APP_URL nei Secrets.")
        return url
    def mail(self,email,subject,text):
        url=self.config.get("MAIL_BRIDGE_URL",""); secret=self.config.get("MAIL_BRIDGE_SECRET","")
        if not url.startswith("https://script.google.com/macros/s/") or len(secret)<32:raise AppError("Invio email non configurato.")
        payload=json.dumps({"to":email,"subject":subject,"text":text,"timestamp":int(time.time()*1000),"nonce":secrets.token_hex(32)},ensure_ascii=False)
        body=json.dumps({"payload":payload,"signature":hmac.new(secret.encode(),payload.encode(),hashlib.sha256).hexdigest()}).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(url,body,{"Content-Type":"application/json"}),timeout=20) as r:
                if not json.load(r).get("ok"):raise ValueError()
        except Exception:raise AppError("Email non inviata. Riprova più tardi.") from None
    def request_access(self,email,name="",privacy=False):
        email=email_address(email); self.limit("send:"+email)
        rows=self.db.rows("SELECT id,name,verified FROM users WHERE email=?",(email,))
        if not rows:
            if not privacy:raise AppError("Per registrarti devi accettare l'informativa privacy.")
            name=clean(name,"Nome",60); uid=uuid.uuid4().hex
            self.db.execute("INSERT INTO users(id,name,email,verified,created_at) VALUES (?,?,?,?,?)",(uid,name,email,0,now()))
        else:uid=rows[0]["id"]
        links=self.db.rows("SELECT token_hash FROM access_links WHERE user_id=?",(uid,))
        raw=secrets.token_urlsafe(40)
        if links:self.db.execute("UPDATE access_links SET token_hash=?,created_at=? WHERE user_id=?",(digest(raw),now(),uid))
        else:self.db.execute("INSERT INTO access_links(user_id,token_hash,created_at) VALUES (?,?,?)",(uid,digest(raw),now()))
        link=self.app_url()+"/?"+urlencode({"accesso":raw})
        self.mail(email,"Il tuo accesso — Le mie medicine","Apri questo collegamento personale per accedere:\n\n"+link+"\n\nNon condividerlo: equivale a una password.")
    def finish_link(self,raw):
        if not isinstance(raw,str) or not 32<=len(raw)<=128:raise AppError("Collegamento non valido.")
        rows=self.db.rows("""SELECT u.id FROM access_links a JOIN users u ON u.id=a.user_id
        WHERE a.token_hash=?""",(digest(raw),))
        if not rows:raise AppError("Collegamento non valido o sostituito.")
        token=secrets.token_urlsafe(32); stamp=now()
        self.db.batch([("UPDATE users SET verified=1,last_login=? WHERE id=?",(stamp,rows[0]["id"])),
          ("INSERT INTO sessions(token_hash,user_id,expires) VALUES (?,?,?)",(digest(token),rows[0]["id"],stamp+self.SESSION_TTL)),
          ("DELETE FROM sessions WHERE expires<?",(stamp,))])
        return token
    def user(self,token):
        rows=self.db.rows("""SELECT u.id,u.name,u.email FROM users u JOIN sessions s ON s.user_id=u.id
        WHERE s.token_hash=? AND s.expires>? AND u.verified=1""",(digest(token),now()))
        if not rows:raise AppError("Sessione scaduta. Richiedi un nuovo link.")
        return rows[0]
    def logout(self,token):self.db.execute("DELETE FROM sessions WHERE token_hash=?",(digest(token),))
    def medicines(self,token,deleted=False):
        user=self.user(token); op="IS NOT NULL" if deleted else "IS NULL"
        return self.db.rows(f"SELECT * FROM medicines WHERE user_id=? AND deleted_at {op} ORDER BY name",(user["id"],))
    def lookup(self,token,value):
        self.user(token); value=re.sub(r"[^0-9A-Za-z]","",str(value))
        candidates=[value]
        if value.isdigit() and len(value)==13:candidates.append(value[3:12])
        if value.isdigit() and len(value)<9:candidates.append(value.zfill(9))
        for c in dict.fromkeys(candidates):
            rows=self.db.rows("SELECT * FROM aifa_catalog WHERE barcode=? OR aic=? LIMIT 1",(c,c.zfill(9) if c.isdigit() else c))
            if rows:return rows[0]
    def save(self,token,data,medicine_id=None):
        user=self.user(token); name=clean(data.get("name"),"Farmaco",200)
        expiry=str(data.get("expiry",""))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",expiry):raise AppError("Scadenza non valida.")
        values=(name,str(data.get("description") or "")[:500],str(data.get("active_ingredient") or "")[:300],
          max(0,int(data.get("quantity",0))),str(data.get("unit") or "Pezzi")[:30],expiry,
          str(data.get("aic") or "")[:20],str(data.get("barcode") or "")[:80],now())
        if medicine_id:
            result=self.db.execute("""UPDATE medicines SET name=?,description=?,active_ingredient=?,quantity=?,unit=?,
            expiry=?,aic=?,barcode=?,updated_at=? WHERE id=? AND user_id=?""",values+(medicine_id,user["id"]))
            if not result["count"]:raise AppError("Farmaco non trovato.")
            return medicine_id
        mid=uuid.uuid4().hex; self.db.execute("""INSERT INTO medicines
        (id,user_id,name,description,active_ingredient,quantity,unit,expiry,aic,barcode,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",(mid,user["id"])+values[:-1]+(values[-1],values[-1])); return mid
    def trash(self,token,mid):self._owned_update(token,mid,"deleted_at",now())
    def restore(self,token,mid):self._owned_update(token,mid,"deleted_at",None)
    def delete(self,token,mid):
        u=self.user(token); self.db.execute("DELETE FROM medicines WHERE id=? AND user_id=?",(mid,u["id"]))
    def _owned_update(self,token,mid,field,value):
        u=self.user(token); self.db.execute(f"UPDATE medicines SET {field}=?,updated_at=? WHERE id=? AND user_id=?",(value,now(),mid,u["id"]))
    def replace_catalog(self,token,rows):
        u=self.user(token)
        if u["email"]!=str(self.config.get("ADMIN_EMAIL","")).strip().lower():raise AppError("Operazione riservata.")
        self.db.execute("DELETE FROM aifa_catalog")
        for start in range(0,len(rows),200):
            self.db.batch([("INSERT OR REPLACE INTO aifa_catalog(aic,description,active_ingredient,company,barcode) VALUES (?,?,?,?,?)",
              (r["aic"],r["descrizione"],r.get("principio_attivo"),r.get("ditta"),r.get("barcode"))) for r in rows[start:start+200]])
