"""SQLite locale per test; SQL over HTTP Turso in produzione."""
import json
import sqlite3
import urllib.parse
import urllib.request
from contextlib import closing
from pathlib import Path

class StorageError(Exception):
    pass

class Database:
    def __init__(self, url="", token="", local_path=None):
        self.local_path, self.token = local_path, token
        url = url.replace("libsql://", "https://").replace("turso://", "https://")
        parsed = urllib.parse.urlparse(url)
        if not local_path and (
            parsed.scheme != "https" or not parsed.hostname
            or not parsed.hostname.endswith(".turso.io") or parsed.username
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")
        ):
            raise StorageError("Controlla TURSO_DATABASE_URL nei Secrets.")
        self.url = url.rstrip("/") + "/v2/pipeline"

    @staticmethod
    def stmt(sql, args=()):
        def typed(value):
            if value is None:
                return {"type": "null"}
            if isinstance(value, int):
                return {"type": "integer", "value": str(value)}
            return {"type": "text", "value": str(value)}
        return {"type": "execute", "stmt": {"sql": sql, "args": [typed(v) for v in args]}}

    def _post(self, body):
        request = urllib.request.Request(
            self.url, json.dumps(body).encode(),
            {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except Exception:
            raise StorageError("Database non raggiungibile. Riprova.") from None

    @staticmethod
    def decode(item):
        if item.get("type") != "ok":
            raise StorageError("Operazione database non riuscita.")
        result = item["response"].get("result", {})
        names = [column["name"] for column in result.get("cols", [])]
        def value(cell):
            if cell["type"] == "null":
                return None
            if cell["type"] == "integer":
                return int(cell["value"])
            return cell.get("value")
        return {
            "rows": [dict(zip(names, map(value, row))) for row in result.get("rows", [])],
            "count": result.get("affected_row_count", 0),
        }

    def batch(self, statements):
        if self.local_path:
            with closing(sqlite3.connect(self.local_path, timeout=20)) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys=ON")
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    output = []
                    for sql, args in statements:
                        cursor = connection.execute(sql, args)
                        output.append({"rows": [dict(r) for r in cursor.fetchall()], "count": max(cursor.rowcount, 0)})
                    connection.commit()
                    return output
                except Exception:
                    connection.rollback()
                    raise
        body = self._post({"requests": [self.stmt("PRAGMA foreign_keys=ON"), self.stmt("BEGIN IMMEDIATE")]
                           + [self.stmt(sql, args) for sql, args in statements]})
        baton = body.get("baton")
        try:
            output = [self.decode(item) for item in body["results"]]
            if len(output) != len(statements) + 2 or not baton:
                raise StorageError("Risposta database incompleta.")
        except Exception:
            if baton:
                self._post({"baton": baton, "requests": [self.stmt("ROLLBACK"), {"type": "close"}]})
            raise
        end = self._post({"baton": baton, "requests": [self.stmt("COMMIT"), {"type": "close"}]})
        self.decode(end["results"][0])
        return output[2:]

    def execute(self, sql, args=()):
        if self.local_path:
            return self.batch([(sql, args)])[0]
        result = self._post({"requests": [self.stmt(sql, args), {"type": "close"}]})
        return self.decode(result["results"][0])

    def rows(self, sql, args=()):
        return self.execute(sql, args)["rows"]

    def _columns(self, table):
        return {row["name"] for row in self.rows("PRAGMA table_info(" + table + ")")}

    def _add_column(self, table, name, definition):
        if name not in self._columns(table):
            self.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def initialize(self):
        sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        statements = [(part.strip(), ()) for part in sql.split(";")
                      if part.strip() and not part.strip().upper().startswith("PRAGMA")]
        self.batch(statements)
        migrations = {
            "users": {
                "privacy_accepted_at": "INTEGER",
                "last_login": "INTEGER",
            },
            "access_links": {
                "previous_token_hash": "TEXT",
                "previous_expires": "INTEGER",
            },
            "sessions": {
                "created_at": "INTEGER NOT NULL DEFAULT 0",
            },
            "medicines": {
                "company": "TEXT",
                "low_stock": "INTEGER NOT NULL DEFAULT 1",
                "reminder_days": "INTEGER NOT NULL DEFAULT 30",
            },
        }
        for table, columns in migrations.items():
            for name, definition in columns.items():
                self._add_column(table, name, definition)
        self.execute("INSERT OR IGNORE INTO schema_version(version,applied_at) VALUES (1,strftime('%s','now'))")
