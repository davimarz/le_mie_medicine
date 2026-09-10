# I miei farmaci

Web app Streamlit per gestire farmaci, quantità e scadenze, con autenticazione e database persistente su Supabase.

## Architettura

- **Streamlit**: interfaccia web
- **Supabase Auth**: registrazione e accesso utenti
- **Supabase PostgreSQL**: farmaci e archivio AIFA persistenti
- **Row Level Security (RLS)**: ogni utente può leggere e modificare solo i propri dati

Il progetto non usa più SQLite per i dati applicativi, quindi i dati non vengono persi quando Streamlit riavvia l'app.

## Pubblicazione su Streamlit Community Cloud

Usa questi parametri:

- Repository: `davimarz/le_mie_medicine`
- Branch: `main`
- Main file path: `app.py`

Le credenziali usate nel codice sono esclusivamente la URL pubblica del progetto Supabase e la **publishable key**. La sicurezza dei dati è gestita dalle policy RLS nel database. Non inserire mai nel repository una `service_role` key.

## Funzioni

- registrazione account tramite email
- login tramite email e password
- gestione personale dei farmaci
- quantità e scadenze
- segnalazione farmaci scaduti o in scadenza
- ricerca per nome, principio attivo e AIC
- caricamento di `confezioni.csv` AIFA associato al singolo account
- esportazione dei propri farmaci in CSV

## Database Supabase

Il progetto Supabase dedicato è `I miei farmaci` in regione `eu-central-1`.

Tabelle principali:

- `profiles`
- `farmaci`
- `aifa_cache`

Tutte le tabelle applicative hanno Row Level Security attiva.

## Installazione locale

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Su Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## File esclusi da Git

Il `.gitignore` continua a escludere vecchi database locali, file CSV con dati utenti, `.env`, ambienti virtuali e file temporanei.
