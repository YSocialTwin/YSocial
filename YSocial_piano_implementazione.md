# YSocial – Piano di Implementazione

> Documento generato il 4 settembre 2026  
> Basato su: `YSocial_analisi_codebase.md` (v4.0.0)  
> Da usare come guida operativa per l'implementazione delle correzioni  
> Branch di implementazione: `fix/critical-issues` (da `deps/sqlalchemy2-flask3-migration`)

---

## Come leggere questo documento

Ogni criticità è strutturata in:

- **Contesto** — perché il problema esiste e dove si manifesta
- **Passi di implementazione** — azioni concrete e ordinate, con comandi shell dove applicabile
- **Verifica** — come confermare che il problema è risolto
- **Definizione di "Done"** — criterio binario per chiudere il task

Le criticità sono ordinate per priorità di esecuzione. Le prime due devono essere risolte prima di qualsiasi altro lavoro.

---

## FASE 0 — Immediata (prima di tutto il resto)

---

### C1 — Secret Key Hardcoded

**Severità:** 🔴 Critica | **Effort:** ~2 ore | **Rischio rollback:** Basso  
**Stato:** ✅ RISOLTO (4 settembre 2026) — commit `69c766b9` su branch `fix/critical-issues`

#### Contesto

`y_web/__init__.py` contiene:

```python
app.config["SECRET_KEY"] = "4323432nldsf"
```

Qualsiasi persona con accesso al repository può forgiare cookie di sessione Flask e impersonare qualsiasi utente, inclusi gli amministratori. Il problema esiste in tutti gli ambienti che non sovrascrivono esplicitamente la chiave.

#### Passi di implementazione

**1. Aggiungere `python-dotenv` alle dipendenze**

In `requirements/base.txt`, aggiungere:
```
python-dotenv>=1.0.0
```

**2. Creare `.env.example`** nella root del repository:

```ini
# Copia questo file in .env e compila i valori prima di avviare YSocial.
# NON committare mai il file .env nel repository.

# Chiave segreta Flask — deve essere una stringa casuale lunga almeno 32 caratteri.
# Generala con: python -c "import secrets; print(secrets.token_hex(32))"
YSOCIAL_SECRET_KEY=replace-me-with-a-random-string

# (Opzionale) Tipo di database: sqlite o postgresql
# YSOCIAL_DB_TYPE=sqlite

# (Opzionale) URL PostgreSQL (richiesto solo se YSOCIAL_DB_TYPE=postgresql)
# YSOCIAL_DATABASE_URL=postgresql://user:password@localhost:5432/ysocial
```

**3. Aggiungere `.env` al `.gitignore`**

Verificare che `.gitignore` contenga (aggiungere se mancante):
```
.env
*.env
```

**4. Modificare `y_web/__init__.py`**

Sostituire il blocco della SECRET_KEY all'inizio di `create_app()`:

```python
# Prima (da rimuovere):
app.config["SECRET_KEY"] = "4323432nldsf"

# Dopo:
import os
from dotenv import load_dotenv
load_dotenv()  # carica .env se presente

secret_key = os.environ.get("YSOCIAL_SECRET_KEY")
if not secret_key:
    if os.environ.get("FLASK_ENV") == "production" or not app.debug:
        raise RuntimeError(
            "YSOCIAL_SECRET_KEY non impostata. "
            "Copia .env.example in .env e genera una chiave con: "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    # In sviluppo/debug genera una chiave temporanea con warning
    import secrets
    secret_key = secrets.token_hex(32)
    print("WARNING: YSOCIAL_SECRET_KEY non impostata. "
          "Usando chiave temporanea — le sessioni non sopravvivono al riavvio.")

app.config["SECRET_KEY"] = secret_key
```

**5. Aggiornare `CONTRIBUTING.md`**

Aggiungere una sezione "Setup locale" che documenta il requisito di `YSOCIAL_SECRET_KEY` e istruisce a copiare `.env.example`.

#### Verifica

```bash
# Deve restituire zero risultati
grep -r "4323432" y_web/

# Deve fallire (RuntimeError) se la variabile non è impostata in produzione
FLASK_ENV=production python -c "from y_web import create_app; create_app()"

# Deve funzionare normalmente con la variabile impostata
YSOCIAL_SECRET_KEY=test123test123test123test123test1 python -c "from y_web import create_app; create_app(); print('OK')"
```

#### Definizione di "Done"

- [ ] `grep -r "4323432" y_web/` → nessun risultato
- [ ] `.env.example` committato nel repository
- [ ] `.env` presente in `.gitignore`
- [ ] Avvio senza `YSOCIAL_SECRET_KEY` in modalità non-debug genera `RuntimeError` con messaggio utile
- [ ] `CONTRIBUTING.md` aggiornato

---

### C2 — File di Database Runtime Tracciati in Git

**Severità:** 🔴 Critica | **Effort:** ~3 ore | **Rischio rollback:** Basso  
**Stato:** ✅ RISOLTO (pre-esistente) — `.gitignore` già esclude i DB runtime; solo `data_schema/*.db` (reference) sono tracciati

#### Contesto

I seguenti file sono attualmente tracciati da git ma non dovrebbero esserlo:

| File | Dimensione | Problema |
|---|---|---|
| `y_web/db/dashboard.db` | ~58 MB | Database runtime attivo |
| `y_web/db/dummy.db` | ~5 MB | Database runtime di test |
| `y_web/db/database.db` | 0 B | File vuoto residuo |
| `y_web/system/yweb.db` | 0 B | File vuoto residuo |
| `y_web/yweb.db` | 0 B | File vuoto residuo |

I `.fuse_hidden*` in `y_web/db/` sono file temporanei del filesystem FUSE (visibili perché i database sono aperti da un processo) — non devono mai essere tracciati.

#### Passi di implementazione

**1. Aggiornare `.gitignore`** nella root del repository. Aggiungere:

```gitignore
# --- Database runtime (mai committare) ---
y_web/db/*.db
y_web/db/*.db-shm
y_web/db/*.db-wal
y_web/system/*.db
y_web/*.db
*.fuse_hidden*

# Eccezione: schemi di riferimento vuoti in data_schema/ sono OK
!data_schema/*.db
```

**2. Rimuovere i file dal tracking git** (senza cancellarli dal disco):

```bash
git rm --cached y_web/db/dashboard.db
git rm --cached y_web/db/dummy.db
git rm --cached y_web/db/database.db
git rm --cached y_web/system/yweb.db
git rm --cached y_web/yweb.db
# rimuovere eventuali altri .db tracciati
git rm --cached "y_web/db/.fuse_hidden*"  # se presenti nel tracking
```

**3. Committare la rimozione:**

```bash
git add .gitignore
git commit -m "chore: rimuovi database runtime dal tracking git

I file .db in y_web/db/ e y_web/system/ sono database runtime
che non devono essere versionati. Aggiornato .gitignore di conseguenza.
Il contenuto su disco non viene modificato."
```

**4. Nota su history passata**  
Se la dimensione del repository è un problema (i ~63 MB sono già nella history), valutare `git filter-repo --path y_web/db/dashboard.db --invert-paths` — ma questa operazione riscrive la history e richiede il coordinamento di tutto il team prima di eseguirla. Trattare come task separato.

**5. Verificare che `db_init/sqlite.py` crei i database nella posizione giusta**  
I database runtime vengono già creati in `y_web/db/` dal codice. Non è necessario cambiare il path di default, solo assicurarsi che `.gitignore` li escluda permanentemente.

#### Verifica

```bash
# Deve restituire solo i file in data_schema/
git ls-files | grep '\.db$'

# Deve essere vuoto (nessun file .db tracciato fuori da data_schema/)
git ls-files | grep '\.db$' | grep -v '^data_schema/'

# Il file esiste ancora su disco (non è stato cancellato)
ls -lh y_web/db/dashboard.db
```

#### Definizione di "Done"

- [ ] `git ls-files | grep '\.db$' | grep -v '^data_schema/'` → nessun risultato
- [ ] I file database esistono ancora su disco e l'applicazione funziona normalmente
- [ ] `.gitignore` contiene le regole per `*.db`, `*.db-shm`, `*.db-wal`, `.fuse_hidden*`
- [ ] Un nuovo database creato dall'applicazione non compare in `git status`

---

## FASE 1 — Sprint 1 (entro 2-3 settimane)

---

### C5 — Pulizia Branch Stale (Copilot e Non Mergiati)

**Severità:** 🟡 Media | **Effort:** ~3 ore | **Rischio rollback:** Nessuno

#### Contesto

Il repository ha 110+ branch locali. Tutti i branch `copilot/` (circa 85) hanno un corrispondente upstream remoto (`origin/copilot/...`) ma sono da considerare **stale**: rappresentano proposte automatiche di GitHub Copilot che sono state accettate, modificate o scartate nel branch principale, e non richiedono ulteriore lavoro.

La regola di pulizia è:
- **Eliminare**: tutti i branch con prefisso `copilot/` (localmente e su `origin`)
- **Mantenere**: tutti i branch non-`copilot/` che hanno upstream remoto
- **Mantenere e pushare**: `deps/sqlalchemy2-flask3-migration` (unico branch locale senza upstream — è il branch attivo di migrazione)

I branch da mantenere dopo la pulizia sono:

```
Admin-GUI, HPC, HPC+Reddit, YPhotoShare, activity_profiles, agent_plugins,
batch_fix, dashboard_fix, deps/sqlalchemy2-flask3-migration, experiment_matrix,
experiment_process_upgrade, forum_template, improved_batching, jupyter_lab_support,
main, opinion_dynamics, packaging, plugins, ray, second-skin, simple_ABM,
stop_failure_fix, telemetry, tutorial, ysocial_update
```

#### Passi di implementazione

**1. Verificare lo stato attuale** (ricognizione prima di agire):

```bash
# Lista branch copilot/ locali
git branch | grep 'copilot/' | wc -l

# Lista branch copilot/ remoti
git branch -r | grep 'origin/copilot/' | wc -l

# Verificare che nessun branch copilot/ sia merged nel main
git branch --merged main | grep 'copilot/'
```

**2. Eliminare branch `copilot/` locali:**

```bash
git branch | grep 'copilot/' | sed 's/^[ *]*//' | xargs git branch -D
```

**3. Eliminare branch `copilot/` remoti:**

```bash
# Genera la lista dei comandi di cancellazione (anteprima)
git branch -r | grep 'origin/copilot/' | sed 's|origin/||' | \
  awk '{print "git push origin --delete " $1}'

# Eseguire la cancellazione (una push batch è più efficiente)
git branch -r | grep 'origin/copilot/' | sed 's|origin/||' | \
  xargs -I{} git push origin --delete {}
```

> **Nota**: GitHub limita le operazioni bulk. Se il comando fallisce per rate limiting, eseguirlo in batch di 10-20 branch alla volta o usare la GitHub CLI: `gh api repos/{owner}/{repo}/git/refs/heads/copilot/{branch} -X DELETE`.

**4. Pushare il branch attivo di migrazione su remote:**

```bash
git push -u origin deps/sqlalchemy2-flask3-migration
```

**5. Configurare auto-delete su GitHub**  
In `Settings → General → Pull Requests` abilitare **"Automatically delete head branches"** per evitare accumuli futuri.

**6. Definire una naming convention** (aggiungere a `CONTRIBUTING.md`):

```
feat/<descrizione>    — nuova funzionalità
fix/<descrizione>     — correzione bug
chore/<descrizione>   — manutenzione, dipendenze, CI
research/<descrizione>— branch sperimentale/ricerca
```

#### Verifica

```bash
# Deve restituire 0
git branch | grep 'copilot/' | wc -l

# Deve restituire 0
git branch -r | grep 'origin/copilot/' | wc -l

# Branch attivo deve avere upstream
git branch -vv | grep deps/sqlalchemy2-flask3-migration
```

#### Definizione di "Done"

- [ ] Zero branch `copilot/` locali: `git branch | grep 'copilot/'` → vuoto
- [ ] Zero branch `copilot/` remoti: `git branch -r | grep 'origin/copilot/'` → vuoto
- [ ] `deps/sqlalchemy2-flask3-migration` ha upstream remoto (`origin/deps/...`)
- [ ] Auto-delete branch abilitato su GitHub
- [ ] Naming convention documentata in `CONTRIBUTING.md`

---

### C4 — Completamento Migrazione SA2 (Eliminazione Shim `fix_tests.py`)

**Severità:** 🟠 Alta | **Effort:** 3-5 giorni | **Rischio rollback:** Medio

#### Contesto

`fix_tests.py` (28 KB) è uno script che inietta shim di compatibilità (`_FakeSelect`, `_SelectRoutingSession`, `_ScalarsResult`) nei file di test che ancora usano l'API legacy SQLAlchemy 1.x (`Model.query.*`). L'esistenza di questo file significa che una porzione dei 165 test non verifica il comportamento reale del codice di produzione (già migrato a SA2).

Il `pytest.ini` ha già `error::sqlalchemy.exc.LegacyAPIWarning` e `error::sqlalchemy.exc.MovedIn20Warning`, quindi qualsiasi utilizzo dell'API legacy nei test viene rilevato automaticamente — ma lo shim aggira questi filtri intercettando le chiamate prima che raggiungano SQLAlchemy.

#### Strategia

L'approccio corretto è migrare i test residui file per file, rimuovendo progressivamente l'applicazione dello shim. Non è necessario fare tutto in un'unica PR.

#### Passi di implementazione

**1. Identificare i test che dipendono dallo shim**

Lo shim viene applicato da `fix_tests.py` in modo automatico su specifici file. Eseguire i test con lo shim disabilitato per vedere quali falliscono:

```bash
# Eseguire l'intera suite ignorando fix_tests.py
# (se fix_tests.py viene importato come plugin pytest, commentarne temporaneamente il contenuto)
pytest y_web/tests/ --tb=line -q 2>&1 | grep FAILED > /tmp/failing_tests.txt
cat /tmp/failing_tests.txt | wc -l
```

**2. Per ogni test fallito, applicare la migrazione SA2**

Pattern di migrazione standard:

```python
# Pattern legacy (da rimuovere):
result = SomeModel.query.filter_by(field=value).first()
results = SomeModel.query.all()
obj = SomeModel.query.get(pk)

# Pattern SA2 (corretto):
from sqlalchemy import select
result = db.session.scalars(select(SomeModel).filter_by(field=value)).first()
results = db.session.scalars(select(SomeModel)).all()
obj = db.session.get(SomeModel, pk)
```

Nei test che usano mock/stub del database, aggiornare il setup del mock:

```python
# Prima (mock legacy):
mock_db.session.query.return_value.filter_by.return_value.first.return_value = obj

# Dopo (mock SA2 — usare db.session.scalars + select):
# Preferire test di integrazione con SQLite in-memory invece di mock
# quando il test testa interazioni con il DB reale
```

**3. Priorità di migrazione**

Iniziare dai test più semplici (unit test su modelli) e procedere verso quelli più complessi (integration test di route):

- Priorità 1: `test_simple_models.py`, `test_phase1_src_models.py`, `test_phase2_src_data_access.py`
- Priorità 2: `test_phase3_src_experiment.py`, `test_phase4_src_packages.py`
- Priorità 3: Test di route (`test_auth_routes.py`, `test_admin_routes.py`, ecc.)
- Priorità 4: Test HPC e simulazione

**4. Aggiungere test sentinella**

Una volta migrati tutti i file, aggiungere in `test_app_structure.py` (o creare `test_sa2_compliance.py`):

```python
def test_no_legacy_query_patterns_in_tests():
    """Verifica che nessun file di test usi l'API legacy SQLAlchemy 1.x."""
    import ast
    import os
    test_dir = os.path.join(os.path.dirname(__file__))
    violations = []
    for fname in os.listdir(test_dir):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(test_dir, fname)
        source = open(path).read()
        if ".query.filter_by" in source or ".query.all()" in source or ".query.get(" in source:
            violations.append(fname)
    assert violations == [], f"Pattern SA1 trovati in: {violations}"

def test_fix_tests_script_does_not_exist():
    """fix_tests.py non deve più esistere una volta completata la migrazione SA2."""
    import os
    assert not os.path.exists(
        os.path.join(os.path.dirname(__file__), "..", "..", "fix_tests.py")
    ), "fix_tests.py ancora presente — migrazione SA2 non completata"
```

> **Nota**: il secondo test fallirà finché `fix_tests.py` esiste — aggiungerlo subito serve a documentare l'obiettivo e renderlo visibile nella CI.

**5. Rimuovere `fix_tests.py`** solo quando tutti i test passano senza di esso:

```bash
git rm fix_tests.py
git commit -m "chore: rimuovi shim SA2 fix_tests.py — migrazione test completata"
```

#### Verifica

```bash
# Deve passare senza shim
pytest y_web/tests/ -q --tb=short

# Deve essere 0 (nessun pattern legacy nei test)
grep -r "\.query\.filter_by\|\.query\.all()\|\.query\.get(" y_web/tests/ | wc -l

# fix_tests.py non deve esistere
ls fix_tests.py 2>&1 | grep "No such file"
```

#### Definizione di "Done"

- [ ] `fix_tests.py` non esiste nel repository
- [ ] Tutti i 165 test passano senza shim applicato
- [ ] `pytest.ini` mantiene `error::sqlalchemy.exc.LegacyAPIWarning`
- [ ] `test_fix_tests_script_does_not_exist` passa
- [ ] Zero occorrenze di `.query.filter_by`, `.query.all()`, `.query.get()` nei file di test

---

## FASE 2 — Sprint 2 (entro 1 mese)

---

### C3 — Sistema di Migrazione Senza Framework

**Severità:** 🟠 Alta | **Effort:** 3-5 giorni | **Rischio rollback:** Alto — procedere con cautela

#### Contesto

Le 31 migration in `y_web/migrations/` sono script Python manuali eseguiti da `y_web/db_init/migrations.py`. Non esiste tracking dello stato applicato: l'applicazione non sa quali migration sono già state eseguite su un dato database. Ogni migration include la propria logica di "skip if already applied" (`ALTER TABLE IF NOT EXISTS`, eccezioni catturate), ma non esiste una tabella centrale di versioning.

Il rischio principale non è tecnico ma operativo: con la crescita del progetto, la manutenzione di questo sistema diventa progressivamente più onerosa e soggetta a errori.

#### Strategia consigliata

Adottare **Flask-Migrate** (wrapper Alembic per Flask-SQLAlchemy), che è il standard de facto per progetti Flask con SQLAlchemy 2.x. Il passaggio è incrementale: le migration esistenti rimangono come documentazione, Alembic gestisce solo le future.

#### Passi di implementazione

**1. Aggiungere Flask-Migrate alle dipendenze**

In `requirements/base.txt`:
```
Flask-Migrate>=4.0.0
```

**2. Inizializzare Alembic nel progetto**

```bash
# Dalla root del progetto
flask --app y_social.py db init --directory y_web/alembic
```

Questo crea `y_web/alembic/` con la struttura standard Alembic (`env.py`, `script.py.mako`, `versions/`).

**3. Configurare `env.py` generato da Alembic**

Modificare `y_web/alembic/env.py` per usare il `db` e i modelli di YSocial:

```python
from y_web import db
from y_web.src.models import *  # importa tutti i modelli per l'autogenerazione

target_metadata = db.metadata
```

**4. Creare la migration "baseline" dallo schema attuale**

Questa migrazione rappresenta lo stato del database *dopo* che tutte le 31 migration manuali sono già state applicate:

```bash
flask --app y_social.py db migrate \
  --directory y_web/alembic \
  -m "baseline: stato schema post-migrazione-manuale" \
  --rev-id 0001_baseline
```

Revisionare il file generato in `y_web/alembic/versions/0001_baseline.py` e verificarne la correttezza.

**5. Marcare il database esistente come "già alla baseline"**

Per i database già esistenti che hanno già tutte le migration manuali applicate:

```bash
flask --app y_social.py db stamp \
  --directory y_web/alembic \
  0001_baseline
```

**6. Aggiornare `create_app()` in `y_web/__init__.py`**

Sostituire la chiamata a `run_migrations()` con il comando Alembic:

```python
# Prima:
from y_web.db_init.migrations import run_migrations
run_migrations(app, db_type, db)

# Dopo:
from flask_migrate import upgrade as alembic_upgrade
with app.app_context():
    alembic_upgrade()  # esegue solo le migration non ancora applicate
```

**7. Mantenere le migration manuali come sola lettura**

Non eliminare `y_web/migrations/` — diventa documentazione storica dello schema. Aggiungere un `README.md` nella directory:

```markdown
# Migration manuali (storiche)

Questa directory contiene i 31 script di migrazione manuale usati
prima dell'adozione di Flask-Migrate (settembre 2026).
Sono mantenuti come riferimento storico e documentazione.
Le nuove migration vanno create in y_web/alembic/versions/ con:
    flask db migrate -m "descrizione"
```

**8. Aggiungere alla CI**

```yaml
- name: Verifica migration Alembic up-to-date
  run: |
    flask --app y_social.py db check --directory y_web/alembic
```

#### Verifica

```bash
# Su database vuoto, deve applicare la baseline senza errori
rm -f /tmp/test_migration.db
YSOCIAL_SECRET_KEY=test DATABASE_PATH=/tmp/test_migration.db \
  flask --app y_social.py db upgrade --directory y_web/alembic

# Deve restituire la revisione corrente
flask --app y_social.py db current --directory y_web/alembic

# Deve restituire "up to date"
flask --app y_social.py db check --directory y_web/alembic
```

#### Definizione di "Done"

- [ ] `y_web/alembic/` inizializzato con revisione baseline
- [ ] `flask db upgrade` applicato su un database SQLite vuoto senza errori
- [ ] `flask db current` riporta la revisione corrente
- [ ] `create_app()` chiama `alembic_upgrade()` invece di `run_migrations()`
- [ ] La CI esegue `flask db check` su ogni PR
- [ ] `y_web/migrations/README.md` documenta il cambio di sistema

---

### C6 — Bug `BASE_DIR` in `helpers.py`: dati esperimento scritti sotto `src/`

**Severità:** 🟡 Media | **Effort:** ~2 ore | **Rischio rollback:** Basso  
**Stato:** ✅ RISOLTO (4 settembre 2026)

#### Contesto

L'architettura prevede due percorsi distinti e complementari:

| Percorso | Contenuto | Natura |
|---|---|---|
| `y_web/src/experiment/` | `access.py`, `clock.py`, `context.py`, `helpers.py`, `schedule_monitor.py`, `schema.py` | **Modulo Python** (business logic) — da non toccare |
| `y_web/experiments/{uuid}/` | Directory UUID con database, log, notebook Jupyter | **Dati runtime** (creati a runtime) |

A causa di un bug in `y_web/src/experiment/helpers.py`, le directory UUID venivano create erroneamente in `y_web/src/experiments/{uuid}/` invece di `y_web/experiments/{uuid}/`.

#### Causa radice

```python
# y_web/src/experiment/helpers.py — PRIMA (buggy)
BASE_DIR = Path(__file__).resolve().parents[1]
# __file__ = y_web/src/experiment/helpers.py
# parents[0] = y_web/src/experiment/
# parents[1] = y_web/src/   ← SBAGLIATO: mancava un livello di risalita
```

Di conseguenza:
```python
def get_experiment_dir(experiment):
    folder = db_name.removeprefix("experiments_")
    return BASE_DIR / "experiments" / folder  # → y_web/src/experiments/{uid} ← BUG
```

Il modulo `jupyter_utils.py` chiama `get_experiment_dir()` per determinare `notebook_dir`, producendo path sotto `src/` invece che nella root di progetto. Tutte le altre parti del codice (`_crud.py`, `server.py`, `client.py`) usavano correttamente `get_writable_path()` — solo `helpers.py` era fuori allineamento.

La stessa evidenza emerge dal test `test_phase3_src_experiment.py` (già presente nel repo) che documenta esplicitamente il contratto: `"y_web/src/experiment/ (Python package) and y_web/experiments/ (data directory)"`.

#### Fix applicato

**1. `y_web/src/experiment/helpers.py`** — sostituita la definizione di `BASE_DIR`:

```python
# PRIMA (buggy):
BASE_DIR = Path(__file__).resolve().parents[1]   # → y_web/src/

# DOPO (corretto):
BASE_DIR = get_writable_path() / "y_web"          # → <repo_root>/y_web/ in dev
                                                   # → ~/Library/.../YSocial/y_web/ in PyInstaller
```

`get_writable_path` era già importata nel file — il fix è una sostituzione di una sola riga. Questo allinea `helpers.py` al pattern usato da tutto il resto del codebase.

**2. Migrazione dati runtime esistenti**

Le 3 directory UUID trovate sotto `y_web/src/experiments/` contenevano solo sottodirectory `notebooks/` (create da Jupyter via il path buggy). La cartella `y_web/experiments/` conteneva già i dati di simulazione completi per gli stessi UUID. Le `notebooks/` sono state spostate in `y_web/experiments/{uuid}/notebooks/`.

I file sorgente stale in `y_web/src/experiments/` sono stati copiati in `_to_delete/src_experiments_stale/` (non rimossi automaticamente — richiedono `rm -rf` manuale, da eseguire dopo verifica).

**3. `.gitignore` aggiornato** con:

```gitignore
# Stale experiment data moved during C6 migration cleanup
/_to_delete/

# Guard against experiment data accidentally written under src/ again
/y_web/src/experiments/
```

(La regola `/y_web/experiments/` era già presente a riga 161.)

#### Azioni residue (manuali)

```bash
# Eliminare la cartella stale dopo aver verificato che y_web/experiments/ è completa
rm -rf y_web/_to_delete/src_experiments_stale/
rmdir y_web/src/experiments/  # dovrebbe essere vuota

# Committare il fix e la pulizia
git add y_web/src/experiment/helpers.py .gitignore
git commit -m "fix: correggi BASE_DIR in helpers.py — dati esperimento scritti sotto src/

helpers.py usava parents[1] che puntava a y_web/src/ invece di y_web/.
Sostituito con get_writable_path() / 'y_web' per allinearsi al pattern
usato da _crud.py, server.py e client.py e per supportare correttamente
sia modalità dev che PyInstaller.

Le directory UUID sono state migrate da y_web/src/experiments/ a
y_web/experiments/ (posizione corretta già documentata nei test).
Aggiornato .gitignore per prevenire regressioni."
```

#### Verifica

```bash
# helpers.py usa get_writable_path
grep "BASE_DIR" y_web/src/experiment/helpers.py
# Atteso: BASE_DIR = get_writable_path() / "y_web"

# Nessuna directory UUID sotto src/
ls y_web/src/experiments/ 2>/dev/null && echo "ATTENZIONE: ancora presente" || echo "OK"

# y_web/experiments/ contiene i dati
ls y_web/experiments/ | head -10

# Test struttura deve passare
pytest y_web/tests/test_phase3_src_experiment.py -v
```

#### Definizione di "Done"

- [x] `BASE_DIR` in `helpers.py` usa `get_writable_path() / "y_web"`
- [x] Dati UUID migrati in `y_web/experiments/`
- [x] `.gitignore` aggiornato (`/y_web/experiments/`, `/y_web/src/experiments/`, `/_to_delete/`)
- [ ] `rm -rf _to_delete/src_experiments_stale/` eseguito manualmente dopo verifica
- [ ] `rmdir y_web/src/experiments/` eseguito (svuotata la dir stale)
- [ ] Commit con il fix committato nel branch corrente
- [ ] `pytest y_web/tests/test_phase3_src_experiment.py` → tutti i test passano

---

### C8 — Configurazione Centralizzata

**Severità:** 🟡 Media | **Effort:** 1-2 giorni | **Rischio rollback:** Medio  
**Stato:** ✅ RISOLTO (4 settembre 2026) — commit `607b858f` su branch `fix/critical-issues`

#### Contesto

Parametri di configurazione come URL del database, URL LLM, Redis URL, parametri Ray sono distribuiti tra `y_social.py` (argomenti CLI), variabili d'ambiente impostate a runtime, e valori hardcoded in vari moduli. Non esiste un punto di verità unico.

#### Passi di implementazione

**1. Creare `y_web/config.py`** con classi di configurazione:

```python
"""Configurazione centralizzata YSocial."""
import os
from dotenv import load_dotenv

load_dotenv()

class BaseConfig:
    SECRET_KEY = os.environ.get("YSOCIAL_SECRET_KEY")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SEND_FILE_MAX_AGE_DEFAULT = 0
    TEMPLATES_AUTO_RELOAD = True
    SESSION_COOKIE_NAME = "YSocial_session"

    # LLM
    LLM_BACKEND = os.environ.get("LLM_BACKEND")
    LLM_URL = os.environ.get("LLM_URL")

    # Redis
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # Ray
    RAY_ADDRESS = os.environ.get("RAY_ADDRESS", "auto")

    @classmethod
    def validate(cls):
        """Verifica che i parametri obbligatori siano impostati."""
        errors = []
        if not cls.SECRET_KEY:
            errors.append("YSOCIAL_SECRET_KEY non impostata")
        if errors:
            raise RuntimeError("Configurazione incompleta:\n" + "\n".join(f"  - {e}" for e in errors))


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TESTING = False
    if not BaseConfig.SECRET_KEY:
        import secrets
        SECRET_KEY = secrets.token_hex(32)


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "test-secret-key-not-for-production"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    TESTING = False


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
```

**2. Aggiornare `create_app()` per accettare una classe di configurazione**

```python
def create_app(db_type="sqlite", desktop_mode=False, config_class=None):
    from y_web.config import config, DevelopmentConfig
    app = Flask(__name__, static_url_path="/static")

    if config_class is None:
        env = os.environ.get("FLASK_ENV", "development")
        config_class = config.get(env, DevelopmentConfig)

    app.config.from_object(config_class)
    app.config["DESKTOP_MODE"] = desktop_mode
    # ...resto invariato
```

**3. Aggiornare `conftest.py` nei test** per usare `TestingConfig`:

```python
@pytest.fixture
def app():
    from y_web.config import TestingConfig
    app = create_app(db_type="sqlite", config_class=TestingConfig)
    # ...
```

**4. Aggiornare `.env.example`** con tutti i parametri:

```ini
YSOCIAL_SECRET_KEY=replace-me
FLASK_ENV=development
LLM_BACKEND=ollama          # oppure: vllm, o URL custom host:port
LLM_URL=                    # lasciare vuoto se LLM_BACKEND è 'ollama' o 'vllm'
REDIS_URL=redis://localhost:6379/0
RAY_ADDRESS=auto
```

#### Verifica

```bash
# Deve stampare "OK" senza errori
YSOCIAL_SECRET_KEY=testkey python -c "
from y_web.config import ProductionConfig
ProductionConfig.validate()
print('OK')
"

# Deve sollevare RuntimeError
python -c "
from y_web.config import ProductionConfig
ProductionConfig.validate()
" 2>&1 | grep "Configurazione incompleta"
```

#### Definizione di "Done"

- [ ] `y_web/config.py` esiste con le tre classi di configurazione
- [ ] `create_app()` accetta `config_class` e lo usa
- [ ] I test usano `TestingConfig` con SQLite in-memory
- [ ] `.env.example` documenta tutti i parametri
- [ ] Nessun parametro di configurazione hardcoded al di fuori di `config.py` (eccetto valori di default espliciti)

---

## FASE 3 — Sprint 3 (ongoing)

---

### C9 — Standardizzazione Lock Dipendenze

**Severità:** 🟢 Bassa | **Effort:** ~3 ore | **Rischio rollback:** Basso  
**Stato:** ✅ RISOLTO (4 settembre 2026) — commit `e9714424` su branch `fix/critical-issues`

#### Contesto

Tre file con ruoli sovrapposti: `requirements.txt` (delega a `requirements/base.txt`), `requirements-baseline.txt` (copia di `requirements/base.txt` con bound diversi), `requirements.lock` (formato non standard). Questo rende ambiguo quale file sia autoritativo.

#### Passi di implementazione

**1. Adottare `pip-tools`**

```bash
pip install pip-tools
```

**2. Struttura target:**

```
requirements/
├── base.in        # dipendenze dirette senza pin (INPUT)
├── base.txt       # lock generato automaticamente con tutti i pin transitivi (OUTPUT)
├── dev.in         # dipendenze sviluppo (INPUT)
├── dev.txt        # lock sviluppo generato (OUTPUT)
└── test.in        # dipendenze test (INPUT)
    test.txt       # lock test generato (OUTPUT)
```

**3. Creare i file `.in`** dalle dipendenze attuali:

```bash
# Copiare il contenuto attuale di base.txt in base.in rimuovendo i pin esatti
# (mantenere solo i vincoli di versione range come >=, <, ecc.)
cp requirements/base.txt requirements/base.in
```

**4. Generare i lock file:**

```bash
pip-compile requirements/base.in --output-file requirements/base.txt
pip-compile requirements/dev.in --output-file requirements/dev.txt
pip-compile requirements/test.in --output-file requirements/test.txt
```

**5. Rimuovere i file ridondanti:**

```bash
git rm requirements.lock requirements-baseline.txt
# Aggiornare requirements.txt per puntare a requirements/base.txt
```

**6. Aggiungere alla CI:**

```yaml
- name: Verifica lock file aggiornato
  run: |
    pip-compile requirements/base.in --dry-run --quiet
    pip-compile requirements/dev.in --dry-run --quiet
```

**7. Configurare Dependabot** (`.github/dependabot.yml`):

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/requirements"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
```

#### Definizione di "Done"

- [ ] Solo file `.in` e `.txt` in `requirements/`, nessun `.lock` o `-baseline`
- [ ] `pip-compile` eseguibile per rigenerare i lock
- [ ] La CI verifica che i lock siano aggiornati rispetto agli `.in`
- [ ] Dependabot configurato per aggiornamenti settimanali automatici

---

## Riepilogo Esecutivo

| Fase | Criticità | Effort | Priorità |
|---|---|---|---|
| **0 — Immediata** | C1 Secret Key hardcoded ✅ | 2h | 🔴 Blocca tutto |
| **0 — Immediata** | C2 Database in git ✅ | 3h | 🔴 Blocca tutto |
| **1 — Sprint 1** | C5 Pulizia branch stale | 3h | 🟡 Igiene repository |
| **1 — Sprint 1** | C4 Eliminazione shim SA2 | 3-5gg | 🟠 Qualità test |
| **2 — Sprint 2** | C3 Flask-Migrate | 3-5gg | 🟠 Manutenibilità |
| **2 — Sprint 2** | C6 Bug `BASE_DIR` helpers.py ✅ | 2h | 🟡 Correttezza path dati |
| **2 — Sprint 2** | C8 Config centralizzata ✅ | 1-2gg | 🟡 Manutenibilità |
| **3 — Sprint 3** | C9 Lock dipendenze ✅ | 3h | 🟢 Best practice |

**Ordine di esecuzione assoluto**: C1 → C2 → C5 → C4 (in parallelo con C3 se possibile) → C6 → C8 → C9.

C1 e C2 non bloccano tecnicamentelo sviluppo delle altre feature, ma **devono essere risolte prima di qualsiasi deploy o condivisione pubblica** del repository.

---

*Documento da aggiornare ad ogni sprint completato.*
