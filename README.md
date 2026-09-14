# Le mie medicine

Web app Streamlit per inventario personale, scorte e scadenze. Usa Turso (SQLite distribuito) per la persistenza e un collegamento personale inviato per email per l'accesso. Supabase non è richiesto.

> È uno strumento organizzativo: non formula diagnosi, non prescrive farmaci e non suggerisce dosaggi.

## Funzioni

- registrazione e accesso passwordless tramite collegamento email;
- scansione automatica di QR, Data Matrix ed EAN/AIC;
- ricerca nel catalogo ufficiale AIFA e compilazione assistita;
- quantità, scadenza, soglia scorta e preavviso;
- priorità visive per scaduti, scadenze vicine e scorte basse;
- modifica, cestino, ripristino ed eliminazione confermata;
- esportazione CSV, PDF e calendario ICS;
- revoca del link, disconnessione di tutti i dispositivi ed eliminazione account;
- importazione AIFA tramite staging e sostituzione atomica.

## Avvio locale

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
streamlit run app.py
```

## Configurazione

Crea un database Turso e inserisci nei Secrets di Streamlit:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `ADMIN_EMAIL`
- `APP_URL = "https://lemiemedicine.streamlit.app"`
- `MAIL_BRIDGE_URL`
- `MAIL_BRIDGE_SECRET` di almeno 32 caratteri

Il bridge email può essere lo stesso Google Apps Script usato dall'app “Cose da fare”: deve accettare il payload JSON firmato HMAC e restituire `{"ok": true}`.

In Streamlit Community Cloud seleziona repository `davimarz/le_mie_medicine`, branch `main` e main file `app.py`. Il file diventa disponibile su `main` dopo il merge della PR.

## Catalogo AIFA

Accedi con l'indirizzo configurato in `ADMIN_EMAIL`, apri **Catalogo AIFA** e avvia l'aggiornamento. Il nuovo catalogo viene caricato in staging; quello attivo viene sostituito solo a importazione completa.

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest -q
pip-audit
```

La CI compila tutti i moduli, esegue i test, `pip check` e il controllo delle vulnerabilità.

## Privacy

Prima di aprire l'app al pubblico, completa [PRIVACY.md](PRIVACY.md) con i dati reali del titolare e verifica gli obblighi relativi a dati potenzialmente sanitari.
