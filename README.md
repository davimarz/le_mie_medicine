# Le mie medicine

App Streamlit per inventario personale, scorte, scadenze e registrazione delle indicazioni ricevute da medico o farmacista. Autenticazione, database, RLS e Storage sono gestiti da Supabase.

> L'app è uno strumento organizzativo: non formula diagnosi, non prescrive farmaci e non modifica dosaggi.

## Funzioni

- registrazione e accesso passwordless tramite collegamento email univoco;
- sessioni con persistenza dei token ruotati;
- inserimento e modifica completa dei farmaci;
- scorte minime, scadenze e promemoria in-app;
- cestino recuperabile e registro delle attività;
- piano di assunzione trascritto dall'utente;
- scansione da fotocamera di QR, Data Matrix e barcode/EAN, con ricerca AIFA;
- catalogo AIFA condiviso con aggiornamento amministrativo atomico;
- fotografie private delle confezioni;
- caregiver in sola lettura con accesso revocabile;
- esportazione CSV, JSON, PDF e calendario ICS;
- importazione backup JSON ed eliminazione completa dell'account.

## Installazione

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
streamlit run app.py
```

Configura `SUPABASE_URL` e `SUPABASE_PUBLISHABLE_KEY` tramite Streamlit Secrets o variabili d'ambiente. Non usare mai una secret/service-role key nel client.

Per i collegamenti di accesso configura inoltre:

1. `APP_URL` con l'indirizzo pubblico Streamlit;
2. lo stesso indirizzo come **Site URL** e **Redirect URL** in Supabase Auth;
3. il template **Magic Link** con un link nel formato `{{ .SiteURL }}?token_hash={{ .TokenHash }}&type=email`.

Il catalogo viene alimentato con l'[Anagrafica Farmaci AIFA](https://www.aifa.gov.it/liste-dei-farmaci). Il barcode non è garantito per ogni record: quando manca la corrispondenza, l'utente può inserire l'AIC riportato sulla confezione o completare i campi manualmente.

## Database

Le migrazioni versionate sono in `supabase/migrations`. Tutte le tabelle esposte hanno RLS. Le funzioni privilegiate verificano `auth.uid()` o il ruolo amministrativo e negano l'esecuzione ad `anon`.

Per rendere un utente amministratore del catalogo AIFA, assegna `app_metadata.role = admin` tramite un ambiente server-side sicuro. Non usare `user_metadata` per autorizzazioni.

## Test

```bash
pip install -r requirements-dev.txt
pytest -q
```

GitHub Actions esegue compilazione, test e controllo delle dipendenze a ogni push e pull request.

Il test RLS transazionale è in `tests/rls_integration.sql`: crea due identità temporanee, verifica isolamento e condivisione caregiver, poi esegue sempre `ROLLBACK`.

## Privacy

Consulta [PRIVACY.md](PRIVACY.md). Prima dell'uso pubblico, completa l'informativa con i dati reali del titolare e verifica gli obblighi applicabili al trattamento di dati sanitari.
