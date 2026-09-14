CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
 verified INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, last_login INTEGER
);
CREATE TABLE IF NOT EXISTS access_links (
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 token_hash TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS limits (
 key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS medicines (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 name TEXT NOT NULL, description TEXT, active_ingredient TEXT, quantity INTEGER NOT NULL DEFAULT 1,
 unit TEXT NOT NULL DEFAULT 'Pezzi', expiry TEXT NOT NULL, aic TEXT, barcode TEXT,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, deleted_at INTEGER
);
CREATE TABLE IF NOT EXISTS aifa_catalog (
 aic TEXT PRIMARY KEY, description TEXT NOT NULL, active_ingredient TEXT, company TEXT, barcode TEXT
);
CREATE INDEX IF NOT EXISTS medicines_user ON medicines(user_id,deleted_at,name);
CREATE INDEX IF NOT EXISTS catalog_barcode ON aifa_catalog(barcode);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires);
CREATE INDEX IF NOT EXISTS limits_expiry ON limits(expires);
