# I miei farmaci

Web app Flask per la gestione personale dei farmaci, delle quantità e delle scadenze, con supporto alla ricerca dei medicinali tramite codice AIC e archivio AIFA.

## Funzioni principali

- registrazione e accesso utenti
- elenco personale dei farmaci
- quantità e scadenze
- segnalazione dei farmaci scaduti o prossimi alla scadenza
- ricerca tramite codice AIC
- importazione locale del dataset `confezioni.csv` per popolare la cache AIFA

## Avvio

1. Crea un ambiente virtuale Python.
2. Installa le dipendenze con `pip install -r requirements.txt`.
3. Imposta la variabile d'ambiente `SECRET_KEY`.
4. Assicurati che le pagine HTML richieste dall'app siano presenti nella cartella `templates/`.
5. Avvia l'applicazione secondo la configurazione del server Flask/PythonAnywhere.

## File non inclusi nel repository

Per motivi di privacy e dimensione non vengono versionati:

- `farmaci.db`
- `utenti_registrati.csv`
- `confezioni.csv`
- file `.env`

Il database e il CSV degli utenti possono contenere dati personali e non devono essere pubblicati.

## Stato del repository

Il codice Python principale è in `app.py`. Le cartelle `templates/` e gli eventuali asset statici usati dalla versione online devono essere aggiunti al repository quando disponibili.
