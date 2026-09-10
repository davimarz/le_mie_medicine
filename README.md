# I miei farmaci

Applicazione Streamlit per la gestione personale dei farmaci, delle quantità e delle scadenze, con ricerca tramite codice AIC e archivio AIFA.

## Funzioni

- registrazione e accesso utenti
- password salvate con hash sicuro
- compatibilità con i vecchi account Flask
- gestione farmaci personali
- quantità e scadenze
- evidenza dei farmaci scaduti o in scadenza entro 30 giorni
- ricerca tramite codice AIC
- importazione del dataset AIFA `confezioni.csv`
- esportazione dei propri farmaci in CSV

## Avvio locale

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Pubblicazione su Streamlit Community Cloud

1. Accedi a Streamlit Community Cloud con il tuo account GitHub.
2. Crea una nuova app.
3. Seleziona il repository `davimarz/le_mie_medicine`.
4. Seleziona il branch `main`.
5. Imposta `app.py` come Main file path.
6. Avvia il deployment.

Non è necessaria una `SECRET_KEY`: l'accesso utente usa la sessione Streamlit e le password vengono archiviate con hash.

## Archivio AIFA

`confezioni.csv` non viene inserito nel repository. Dopo l'accesso apri **Archivio AIFA** e carica il CSV dalla pagina dell'app. L'importazione popola la tabella `aifa_cache`.

## Database

Per mantenere compatibilità con la versione precedente l'app utilizza SQLite e il file `farmaci.db`. Il file è escluso da GitHub perché può contenere dati personali.

### Nota importante per Streamlit Community Cloud

Il filesystem di un'app cloud non deve essere considerato un archivio permanente. SQLite va bene per prove e uso locale, ma per un'app pubblica con utenti reali è consigliato collegare un database persistente esterno, ad esempio PostgreSQL/Supabase.

## File esclusi da GitHub

- `farmaci.db`
- `utenti_registrati.csv`
- `confezioni.csv`
- `.env` e altri file con segreti

Il progetto non usa più Flask, i template HTML o il foglio CSS della vecchia versione: l'interfaccia è interamente gestita da Streamlit.
