"""SQLite locale per test; SQL over HTTP Turso in produzione."""
import json, sqlite3, urllib.parse, urllib.request
from contextlib import closing
from pathlib import Path

class StorageError(Exception): pass

class Database:
    def __init__(self, url="", token="", local_path=None):
        self.local_path, self.token = local_path, token
        url = url.replace("libsql://","https://").replace("turso://","https://")
        p = urllib.parse.urlparse(url)
        if not local_path and (p.scheme!="https" or not p.hostname or not p.hostname.endswith(".turso.io") or p.username or p.query or p.fragment or p.path not in ("","/")):
            raise StorageError("Controlla TURSO_DATABASE_URL nei Secrets.")
        self.url=url.rstrip("/")+"/v2/pipeline"
    @staticmethod
    def stmt(sql,args=()):
        def typed(v):
            if v is None:return {"type":"null"}
            if isinstance(v,int):return {"type":"integer","value":str(v)}
            return {"type":"text","value":str(v)}
        return {"type":"execute","stmt":{"sql":sql,"args":[typed(v) for v in args]}}
    def _post(self,body):
        req=urllib.request.Request(self.url,json.dumps(body).encode(),{"Authorization":"Bearer "+self.token,"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=25) as res:return json.load(res)
        except Exception: raise StorageError("Database non raggiungibile. Riprova.") from None
    @staticmethod
    def decode(item):
        if item.get("type")!="ok":raise StorageError("Operazione database non riuscita.")
        result=item["response"].get("result",{}); names=[c["name"] for c in result.get("cols",[])]
        def val(v):
            if v["type"]=="null":return None
            if v["type"]=="integer":return int(v["value"])
            return v.get("value")
        return {"rows":[dict(zip(names,map(val,row))) for row in result.get("rows",[])],"count":result.get("affected_row_count",0)}
    def batch(self,statements):
        if self.local_path:
            with closing(sqlite3.connect(self.local_path,timeout=20)) as con,con:
                con.row_factory=sqlite3.Row; con.execute("PRAGMA foreign_keys=ON")
                out=[]
                for sql,args in statements:
                    cur=con.execute(sql,args); out.append({"rows":[dict(r) for r in cur.fetchall()],"count":max(cur.rowcount,0)})
                return out
        body=self._post({"requests":[self.stmt("BEGIN IMMEDIATE")]+[self.stmt(s,a) for s,a in statements]})
        baton=body.get("baton")
        try:
            out=[self.decode(x) for x in body["results"]]
            if len(out)!=len(statements)+1 or not baton:raise StorageError("Risposta database incompleta.")
        except Exception:
            if baton:self._post({"baton":baton,"requests":[self.stmt("ROLLBACK"),{"type":"close"}]})
            raise
        end=self._post({"baton":baton,"requests":[self.stmt("COMMIT"),{"type":"close"}]}); self.decode(end["results"][0])
        return out[1:]
    def execute(self,sql,args=()):
        if self.local_path:return self.batch([(sql,args)])[0]
        result=self._post({"requests":[self.stmt(sql,args),{"type":"close"}]})
        return self.decode(result["results"][0])
    def rows(self,sql,args=()):return self.execute(sql,args)["rows"]
    def initialize(self):
        sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        self.batch([(part.strip(),()) for part in sql.split(";") if part.strip()])
