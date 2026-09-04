# YSocial – Piano di Implementazione

> Documento generato il 4 settembre 2026  
> Basato su: `YSocial_analisi_codebase.md` (v4.0.0)  
> Branch di lavoro: `fix/critical-issues`

---

## Stato implementazione

| Criticità | Effort | Stato |
|---|---|---|
| C1 — Secret Key hardcoded | 2h | ✅ Risolto — commit `69c766b9` |
| C2 — Database runtime in git | 3h | ⏳ Da fare |
| C3 — Flask-Migrate | 3-5gg | ⏳ Da fare |
| C4 — Eliminazione shim SA2 | 3-5gg | ⏳ Da fare |
| C5 — Pulizia branch stale | 3h | ⏳ Da fare |
| C6 — Bug `BASE_DIR` helpers.py | 2h | ✅ Risolto — commit in HEAD |
| C8 — Config centralizzata | 1-2gg | ✅ Risolto — commit `607b858f` |
| C9 — Lock dipendenze | 3h | ✅ Risolto — commit `e9714424` |

---

## Come leggere questo documento

Ogni criticità è strutturata in:

- **Contesto** — perché il problema esiste e dove si manifesta
- **Passi di implementazione** — azioni concrete e ordinate, con comandi shell dove applicabile
- **Verifica** — come confermare che il problema è risolto
- **Definizione di "Done"** — criterio binario per chiudere il task

---

## FASE 0 — Immediata

---

### C2 — File di Database Runtime Tracciati in Git

**Severità:** 🔴 Critica | **Effort:** ~3 ore | **Rischio rollback:** Basso

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
git rm --cached "y_web/db/.fuse_hidden*"  # se presenti nel tracking
```

**3. Committare la rimozione:**

```bash
git add .gitignore
git commit -m "chore(C2): rimuovi database runtime dal tracking git

I file .db in y_web/db/ e y_web/system/ sono database runtime
che non devono essere versionati. Aggiornato .gitignore di conseguenza.
Il contenuto su disco non viene modificato."
```

**4. Nota su history passata**  
Se la dimensione del repository è un problema (i ~63 MB sono già nella history), valutare `git filter-repo --path y_web/db/dashboard.db --invert-paths` — ma questa operazione riscrive la history e richiede il coordinamento di tutto il team prima di eseguirla. Trattare come task separato.

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

**1. Verificare lo stato attuale:**

```bash
git branch | grep 'copilot/' | wc -l
git branch -r | grep 'origin/copilot/' | wc -l
git branch --merged main | grep 'copilot/'
```

**2. Eliminare branch `copilot/` locali:**

```bash
git branch | grep 'copilot/' | sed 's/^[ *]*//' | xargs git branch -D
```

**3. Eliminare branch `copilot/` remoti:**

```bash
git branch -r | grep 'origin/copilot/' | sed 's|origin/||' | \
  xargs -I{} git push origin --delete {}
```

> **Nota**: GitHub limita le operazioni bulk. Se il comando fallisce per rate limiting, eseguirlo in batch di 10-20 branch alla volta o usare: `gh api repos/{owner}/{repo}/git/refs/heads/copilot/{branch} -X DELETE`.

**4. Pushare il branch attivo di migrazione su remote:**

```bash
git push -u origin deps/sqlalchemy2-flask3-migration
```

**5. Configurare auto-delete su GitHub**  
In `Settings → General → Pull Requests` abilitare **"Automatically delete head branches"**.

**6. Definire una naming convention** (aggiungere a `CONTRIBUTING.md`):

```
feat/<descrizione>    — nuova funzionalità
fix/<descrizione>     — correzione bug
chore/<descrizione>   — manutenzione, dipendenze, CI
research/<descrizione>— branch sperimentale/ricerca
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

Il `pytest.ini` ha già `error::sqlalchemy.exc.LegacyAPIWarning` e `error::sqlalchemy.exc.MovedIn20Warning`, ma lo shim aggira questi filtri intercettando le chiamate prima che raggiungano SQLAlchemy.

#### Passi di implementazione

**1. Identificare i test che dipendono dallo shim:**

```bash
pytest y_web/tests/ --tb=line -q 2>&1 | grep FAILED > /tmp/failing_tests.txt
cat /tmp/failing_tests.txt | wc -l
```

**2. Migrare ogni test fallito al pattern SA2:**

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

**3. Priorità di migrazione:**
- P1: `test_simple_models.py`, `test_phase1_src_models.py`, `test_phase2_src_data_access.py`
- P2: `test_phase3_src_experiment.py`, `test_phase4_src_packages.py`
- P3: Test di route (`test_auth_routes.py`, `test_admin_routes.py`, ecc.)
- P4: Test HPC e simulazione

**4. Aggiungere test sentinella** in `test_sa2_compliance.py`:

```python
def test_no_legacy_query_patterns_in_tests():
    import os
    test_dir = os.path.join(os.path.dirname(__file__))
    violations = []
    for fname in os.listdir(test_dir):
        if not fname.endswith(".py"):
            continue
        source = open(os.path.join(test_dir, fname)).read()
        if any(p in source for p in [".query.filter_by", ".query.all()", ".query.get("]):
            violations.append(fname)
    assert violations == [], f"Pattern SA1 trovati in: {violations}"

def test_fix_tests_script_does_not_exist():
    import os
    assert not os.path.exists(
        os.path.join(os.path.dirname(__file__), "..", "..", "fix_tests.py")
    ), "fix_tests.py ancora presente — migrazione SA2 non completata"
```

**5. Rimuovere `fix_tests.py`** solo quando tutti i test passano senza di esso:

```bash
git rm fix_tests.py
git commit -m "chore(C4): rimuovi shim SA2 fix_tests.py — migrazione test completata"
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

Le 31 migration in `y_web/migrations/` sono script Python manuali eseguiti da `y_web/db_init/migrations.py`. Non esiste tracking dello stato applicato: l'applicazione non sa quali migration sono già state eseguite su un dato database. Con la crescita del progetto, la manutenzione di questo sistema diventa progressivamente più onerosa.

#### Strategia consigliata

Adottare **Flask-Migrate** (wrapper Alembic per Flask-SQLAlchemy). Il passaggio è incrementale: le migration esistenti rimangono come documentazione, Alembic gestisce solo le future.

#### Passi di implementazione

**1. Aggiungere Flask-Migrate alle dipendenze** (`requirements/base.in`):

```
Flask-Migrate>=4.0.0
```

Rigenerare il lock:
```bash
pip-compile requirements/base.in --output-file requirements/base.txt
```

**2. Inizializzare Alembic:**

```bash
flask --app y_social.py db init --directory y_web/alembic
```

**3. Configurare `y_web/alembic/env.py`:**

```python
from y_web import db
from y_web.src.models import *
target_metadata = db.metadata
```

**4. Creare la migration "baseline":**

```bash
flask --app y_social.py db migrate \
  --directory y_web/alembic \
  -m "baseline: stato schema post-migrazione-manuale" \
  --rev-id 0001_baseline
```

**5. Marcare i database esistenti come "già alla baseline":**

```bash
flask --app y_social.py db stamp --directory y_web/alembic 0001_baseline
```

**6. Aggiornare `create_app()` in `y_web/__init__.py`:**

```python
# Prima:
from y_web.db_init.migrations import run_migrations
run_migrations(app, db_type, db)

# Dopo:
from flask_migrate import upgrade as alembic_upgrade
with app.app_context():
    alembic_upgrade()
```

**7. Aggiungere `y_web/migrations/README.md`:**

```markdown
# Migration manuali (storiche)

Questa directory contiene i 31 script di migrazione manuale usati
prima dell'adozione di Flask-Migrate (settembre 2026).
Sono mantenuti come riferimento storico.
Le nuove migration vanno create in y_web/alembic/versions/ con:
    flask db migrate -m "descrizione"
```

**8. Aggiungere check alla CI:**

```yaml
- name: Verifica migration Alembic up-to-date
  run: flask --app y_social.py db check --directory y_web/alembic
```

#### Definizione di "Done"

- [ ] `y_web/alembic/` inizializzato con revisione baseline
- [ ] `flask db upgrade` applicato su un database SQLite vuoto senza errori
- [ ] `flask db current` riporta la revisione corrente
- [ ] `create_app()` chiama `alembic_upgrade()` invece di `run_migrations()`
- [ ] La CI esegue `flask db check` su ogni PR
- [ ] `y_web/migrations/README.md` documenta il cambio di sistema

---

## Azioni residue (manuali — fuori git)

Le seguenti azioni richiedono permessi di cancellazione file sul disco:

```bash
# Cleanup stale UUID data da C6 (dopo aver verificato y_web/experiments/ completa)
rm -rf y_web/_to_delete/src_experiments_stale/
rmdir y_web/src/experiments/   # dovrebbe essere vuota
```

---

*Documento aggiornato al 4 settembre 2026 — branch `fix/critical-issues`.*
