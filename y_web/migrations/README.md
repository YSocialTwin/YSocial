# Migration manuali (storiche)

Questa directory contiene i 31 script di migrazione manuale usati da YSocial
prima dell'adozione di **Flask-Migrate** (settembre 2026).

Sono mantenuti come **riferimento storico** e documentazione dello schema.
Non vengono più eseguiti automaticamente — il sistema di migrazione è ora
gestito da Alembic tramite `y_web/alembic/versions/`.

## Sistema precedente

Le migration erano applicate da `y_web/db_init/migrations.py` (`run_migrations()`)
all'avvio dell'applicazione. Ogni script includeva la propria logica di
"skip if already applied" (`ALTER TABLE IF NOT EXISTS`, eccezioni catturate).

## Sistema corrente (Flask-Migrate)

Le nuove migration vanno create con:

```bash
flask --app y_social.py db migrate -m "descrizione del cambiamento"
flask --app y_social.py db upgrade
```

I file delle nuove migration si trovano in `y_web/alembic/versions/`.

## Baseline

Il punto di partenza di Alembic è `0001_baseline` (no-op) — rappresenta
lo stato del database dopo l'applicazione di tutti i 31 script in questa
directory.

Per un database esistente già aggiornato, eseguire una tantum:

```bash
flask --app y_social.py db stamp 0001_baseline
```
