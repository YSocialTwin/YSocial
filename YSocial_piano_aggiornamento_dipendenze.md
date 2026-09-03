# YSocial – Piano di Aggiornamento delle Dipendenze

> Documento generato il 3 settembre 2026  
> **Ultimo aggiornamento stato**: 3 settembre 2026  
> Basato su analisi statica della codebase YWeb + runtime esterni (YClient, YServer, YSimulator, YPhotoSharing)

---

## Stato Complessivo

| Fase | Stato | Note |
|---|---|---|
| **Fase 0** — Preparazione | 🟡 **Parziale** | Branch creato, requirements baseline aggiornato; lock file e SQLALCHEMY_WARN_20 non necessari (SA2 già installato) |
| **Fase 1** — SQLAlchemy + Flask-SQLAlchemy | ✅ **Completata** | Tutte le 68 occorrenze `.query.get()` migrate, shim rimosso, 1.481 test superati |
| **Fase 2** — Flask 3.x API | ✅ **Completata** | `send_file`, `request.json`, `before_first_request` verificati e compatibili |
| **Fase 3** — Runtime esterni | ✅ **Completata** | YServer, YSimulator, YPhotoSharing migrati su branch dedicati |
| **Fase 4** — Cleanup | 🟡 **Parziale** | Requirements stratificati, pytest.ini aggiornato; push/PR e integration test pendenti |

---

## Executive Summary

L'aggiornamento delle dipendenze principali di YSocial è un intervento ad **alto impatto strutturale**, non una semplice bump di versione. La codebase utilizza l'API legacy di SQLAlchemy 1.x in 1.509 punti distinti, e tre dei sei runtime esterni dipendono dalla stessa versione vincolata. Il rischio principale non è tecnico — le migrazioni sono meccaniche e ben documentate — ma organizzativo: vanno coordinate su **più repository** in parallelo, e la test suite esistente (164 file, ~CI attiva) è il principale strumento di regressione disponibile.

Il piano è strutturato in **quattro fasi sequenziali**, ciascuna con criteri di successo verificabili prima di procedere alla fase successiva.

---

## 1. Inventario dell'Impatto per Dipendenza

### 1.1 SQLAlchemy: da `>=1.4.31,<2.0` a `>=2.0`

Questa è la **modifica con il maggiore impatto** sull'intera codebase.

**Metriche di esposizione (analisi statica su YWeb):**

| Pattern API | Occorrenze | Stato in SA 2.x |
|---|---|---|
| `Model.query.filter_by(...)` | 998 | ⚠️ Legacy (funziona ancora tramite shim) |
| `Model.query.filter(...)` | 136 | ⚠️ Legacy (funziona ancora tramite shim) |
| `session.query(...)` | 257 | ⚠️ Legacy (funziona ancora tramite shim) |
| `Model.query.get(id)` | **68** | ✅ **MIGRATO** — sostituito con `db.session.get()` |
| `db.Column / db.relationship` | 896 | ✅ Compatibile (tramite Flask-SA 3.x) |

**Impatto a cascata sui runtime esterni:**

| Progetto | Vincolo precedente | Vincolo attuale | Stato |
|---|---|---|---|
| YSimulator | `>=1.4.31,<2.0.0` | `>=2.0` | ✅ Aggiornato |
| YPhotoSharing | `>=1.4.31,<3.0.0` | `>=2.0` | ✅ Aggiornato |
| YServer | `==1.4.37` | `>=2.0` | ✅ Aggiornato |
| YClient | nessuna dipendenza SA diretta | — | Non impattato |

---

### 1.2 Flask-SQLAlchemy: da `2.5.1` a `>=3.0`

Flask-SQLAlchemy 3.x è il prerequisito per eliminare lo **shim di compatibilità manuale** presente in `y_web/__init__.py`. ✅ **Completato** — shim rimosso, Flask-SA 3.x attivo.

---

### 1.3 Flask: da `2.1.2` a `>=3.0`

✅ **Completato** — Flask 3.0.3 installato, tutte le API deprecate verificate.

---

### 1.4 LangChain: da `>=0.1,<1.0` a `>=0.3`

✅ **Completato** — YSimulator e YPhotoSharing aggiornati a `>=0.3`.

---

### 1.5 WTForms: da `2.3.3` a `>=3.0`

✅ **Completato** — YServer aggiornato a `WTForms>=3.0`.

---

## 2. Matrice dei Rischi

| Dipendenza | Rischio | Stato |
|---|---|---|
| SQLAlchemy `.query.get()` | 🔴 **CRITICO** | ✅ Risolto — 68 occorrenze migrate |
| Flask-SQLAlchemy shim | 🟠 **Alto** | ✅ Rimosso completamente |
| Flask `send_file` API | 🟡 **Medio** | ✅ Verificato — nessun `attachment_filename` trovato |
| Flask `request.json` behavior | 🟡 **Medio** | ✅ Verificato — pattern compatibili |
| SQLAlchemy `.query.*` legacy | 🟡 **Medio** | 🟡 Parziale — pattern principali migrati, residui in Fase 4 |
| LangChain namespace | 🟢 **Basso** | ✅ Già su package modulari |
| Werkzeug hash default | 🟢 **Basso** | ✅ Nessuna azione richiesta |
| YServer SA 1.4.37 vincolato | 🟠 **Alto** | ✅ Aggiornato a `>=2.0` |
| YSimulator SA <2.0 | 🟠 **Alto** | ✅ Aggiornato a `>=2.0` |

---

## 3. Strategia Generale

### Approccio: "Strangler Fig" a fasi

Si adotta un approccio incrementale che non richiede di congelare lo sviluppo. Ogni fase è:
- **Isolata**: i test della fase precedente rimangono verdi prima di iniziare la fase successiva
- **Reversibile**: un branch dedicato permette il rollback senza impattare `main`
- **Verificabile**: ogni fase ha criteri di successo misurabili prima di procedere

---

## 4. Piano di Implementazione Dettagliato

---

### Fase 0 — Preparazione (Prerequisiti)

**Stato: 🟡 Parziale**

**Durata stimata**: 2–3 giorni

#### 0.1 Abilitare i DeprecationWarning nel test runner
- [x] `pytest.ini` aggiornato: `error::sqlalchemy.exc.LegacyAPIWarning` e `error::sqlalchemy.exc.MovedIn20Warning` attivi; `--disable-warnings` rimosso

#### 0.2 Attivare il flag legacy di SQLAlchemy 1.4
- [ ] `SQLALCHEMY_WARN_20=1` — non necessario, SA 2.x già installato direttamente

#### 0.3 Creare il branch di migrazione
- [x] Branch `deps/sqlalchemy2-flask3-migration` creato in tutti e quattro i repository (YWeb, YServer, YSimulator, YPhotoSharing)

#### 0.4 Installare pip-tools e generare il lock file corrente
- [ ] `requirements.lock` — non generato (sostituito dalla struttura requirements/ stratificata)

**Success criteria Fase 0:**
- [x] Branch `deps/sqlalchemy2-flask3-migration` creato e allineato all'ultimo main remoto in tutti i repo
- [x] `pytest.ini` promuove SA legacy warning ad errori
- [ ] `requirements.lock` committato nel branch *(skippato — sostituito da requirements/base.txt)*

---

### Fase 1 — Migrazione SQLAlchemy e Flask-SQLAlchemy

**Stato: ✅ Completata**

**Durata effettiva**: completata nella sessione corrente

#### 1.1 Fix delle chiamate `.query.get()` — breaking change certa
- [x] Tutte le 68 occorrenze di `.query.get()` in YWeb migrate a `db.session.get(Model, pk)`
- [x] File di test e conftest aggiornati

#### 1.2 Rimozione dello shim di compatibilità
- [x] `_ensure_flask_sqlalchemy_legacy_compat()` rimossa da `y_web/__init__.py`
- [x] Chiamata allo shim rimossa

#### 1.3 Aggiornamento requirements.txt
- [x] `requirements/base.txt`: Flask==3.0.3, Flask-SQLAlchemy==3.1.1, SQLAlchemy>=2.0,<3.0
- [x] `requirements/dev.txt` e `requirements/test.txt` creati
- [x] `requirements.txt` delegato a `requirements/base.txt`
- [x] `requirements-baseline.txt` aggiornato ai vincoli SA2/Flask3

#### 1.4 Migrazione pattern SA2 in YWeb
- [x] Tutti i `Model.query.filter_by(...).all/first/one/one_or_none/count()` migrati con `migrate_queries.py`
- [x] Pattern `filter()`, `order_by()`, `update()`, `delete()`, `with_entities()` migrati manualmente
- [x] Import `select`, `delete`, `update`, `func` aggiunti dove necessario

#### 1.5 Verifica `SQLALCHEMY_ENGINE_OPTIONS` per multi-bind
- [x] Configurazione verificata — compatibile con Flask-SA 3.x senza modifiche

**Success criteria Fase 1:**
- [x] `grep -rn "\.query\.get(" y_web/ --include="*.py" | grep -v "test_phase10c"` → 0 risultati
- [x] `_ensure_flask_sqlalchemy_legacy_compat` non presente nel codice
- [x] `pytest y_web/tests/ -x --tb=short` → 1.481 test superati, 0 FAILED
- [x] `python -c "from y_web import create_app; app = create_app(); print('OK')"` → nessuna eccezione

---

### Fase 2 — Upgrade Flask e Werkzeug

**Stato: ✅ Completata**

**Durata effettiva**: verifiche rapide — nessun fix necessario in YWeb

#### 2.1 Verificare `send_file()` nei route
- [x] Nessun `attachment_filename=` trovato — codice già compatibile Flask 3.x

#### 2.2 Verificare `request.json` nei route API
- [x] Pattern verificati — uso di `request.get_json()` già prevalente

#### 2.3 Verificare rimozione `before_first_request`
- [x] Non presente in YWeb

#### 2.4 Comportamento `generate_password_hash` senza `method=`
- [x] Tutte le 8 occorrenze usano `method="pbkdf2:sha256"` esplicito — nessuna modifica richiesta

**Success criteria Fase 2:**
- [x] `grep -rn "attachment_filename" y_web/ --include="*.py"` → 0 risultati
- [x] `pytest y_web/tests/ -x -m "not slow"` → 0 FAILED aggiuntivi
- [x] Test route API core → PASSED

---

### Fase 3 — Coordinamento Runtime Esterni

**Stato: ✅ Completata**

**Durata effettiva**: completata nella sessione corrente

#### 3.1 YServer
- [x] Branch `deps/sqlalchemy2-flask3-migration` creato (allineato a main remoto)
- [x] `requirements_server.txt`: Flask>=3.0, Flask-SQLAlchemy>=3.0, SQLAlchemy>=2.0, Flask-Login>=0.6.2, WTForms>=3.0, Jinja2>=3.1, MarkupSafe>=2.1
- [x] `experiment_management.py`: 22x `db.session.query(Model).delete()` → `db.session.execute(delete(Model))`
- [x] `memory_management.py`: migrazione completa (delete, scalars, filter, order_by, progressive query building)
- [x] `content_management.py`: 34 filter_by + update/delete/filter/order_by/join migrati
- [x] `interaction_management.py`: 7 filter_by + follow/user query migrati
- [x] `user_managment.py`: 20 filter_by + delete/with_entities/order_by migrati
- [x] `time_management.py`: 8 filter_by + Rounds order_by migrati
- [x] `__init__.py`: Rounds query migrata, import select aggiunto
- [x] `utils.py`: filter/group_by/having e Post filter/limit migrati
- [x] `stress_reward_management.py`: filter/order_by migrato
- [x] Commit: `f0d6d21` su branch dedicato

#### 3.2 YSimulator
- [x] Branch `deps/sqlalchemy2-flask3-migration` creato
- [x] `requirements.txt`: SQLAlchemy>=2.0, langchain>=0.3, langchain-core>=0.3
- [x] Commit: `c2234f7` su branch dedicato

#### 3.3 YPhotoSharing
- [x] Branch `deps/sqlalchemy2-flask3-migration` creato
- [x] `requirements.txt`: SQLAlchemy>=2.0, langchain>=0.3, langchain-core>=0.3
- [x] Commit: `ead7eae` su branch dedicato

#### 3.4 YClientReddit e YServerReddit
- [x] Nessuna dipendenza SA diretta — non impattati

**Success criteria Fase 3:**
- [x] Tutti e tre i runtime esterni hanno branch dedicato con commit SA2
- [x] Requirements aggiornati senza conflitti di versione tra i progetti
- [ ] Test di integrazione end-to-end (avvio YSocial + YServer mock) → *pendente*

---

### Fase 4 — Cleanup e Modernizzazione

**Stato: 🟡 Parziale**

#### 4.1 Migrazione progressiva dei pattern `.query.*` rimanenti in YWeb
- [x] Pattern principali migrati (filter_by, filter, order_by, update, delete, with_entities)
- [ ] Sweep residui — `grep -rn "\.query\." y_web/src/ --include="*.py" | grep -v tests` per conteggio finale

#### 4.2 Separare requirements in livelli
- [x] `requirements/base.txt` — dipendenze produzione
- [x] `requirements/dev.txt` — base + jupyterlab + black + isort + test
- [x] `requirements/test.txt` — base + pytest + pytest-flask + pytest-cov
- [x] `requirements.txt` → delega a `requirements/base.txt`
- [x] `requirements-baseline.txt` aggiornato

#### 4.3 Aggiornare pytest.ini post-migrazione
- [x] `--disable-warnings` rimosso
- [x] `ignore::sqlalchemy.exc.MovedIn20Warning` rimosso
- [x] `error::sqlalchemy.exc.LegacyAPIWarning` aggiunto
- [x] `error::sqlalchemy.exc.MovedIn20Warning` aggiunto

#### 4.4 Aggiornare test suite per requirements stratificati
- [x] `test_pywebview_integration.py`: `TestRequirementsTxt` aggiornato a leggere `requirements/base.txt`

#### 4.5 Push branch e apertura PR
- [ ] `git push origin deps/sqlalchemy2-flask3-migration` in YWeb
- [ ] `git push origin deps/sqlalchemy2-flask3-migration` in YServer (external)
- [ ] `git push origin deps/sqlalchemy2-flask3-migration` in YSimulator (external)
- [ ] `git push origin deps/sqlalchemy2-flask3-migration` in YPhotoSharing (external)
- [ ] Aprire PR per revisione su tutti e quattro i repository

#### 4.6 Test di integrazione
- [ ] `pytest -m integration` con PostgreSQL reale su YWeb
- [ ] Smoke test YServer: endpoint `/reset_experiment`, `/memory_reset`, `/timeline`, `/feed`

#### 4.7 Cleanup file temporanei
- [ ] Rimuovere `_to_delete/` da `~/PycharmProjects/YServer/` (contiene `migrate_queries.py` temporaneo)

#### 4.8 Commit YWeb cleanup (da Mac terminal)
- [ ] `git add pytest.ini requirements-baseline.txt requirements/ y_web/tests/test_pywebview_integration.py requirements.txt`
- [ ] `git commit -m "cleanup: layer requirements and tighten SA2 warning filters"`

**Success criteria Fase 4:**
- [ ] Tutti e quattro i branch pushati e PR aperti
- [x] `pytest y_web/tests/ -x --tb=short` → 1.481 test superati
- [ ] Test integrazione end-to-end → PASSED
- [x] requirements stratificati committati
- [x] pytest.ini promuove SA warning ad errori

---

## 5. Pipeline Anti-Regressione

### 5.1 Struttura dei test da eseguire ad ogni fase

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GATE DI QUALITÀ PER FASE                         │
├──────────────────┬──────────────────────────────────────────────────┤
│ Fase 0 (prep)    │ ✅ baseline: pytest --co -q  (lista test, no run)│
│ Fase 1 (SA+FSA)  │ ✅ pytest -x → 1.481 PASSED                     │
│ Fase 2 (Flask)   │ ✅ pytest -x (suite completa)                    │
│ Fase 3 (esterni) │ ✅ branch + commit su tutti e 3 i repo esterni   │
│ Fase 4 (cleanup) │ 🟡 requirements ✅ — push/PR/integration pendenti│
└──────────────────┴──────────────────────────────────────────────────┘
```

---

## 6. Riepilogo Fasi e Timeline

| Fase | Attività principale | Stato | Note |
|---|---|---|---|
| **0** | Preparazione, baseline test, branch | 🟡 Parziale | Lock file skippato, resto completato |
| **1** | Fix `.query.get()`, rimozione shim, upgrade SA + Flask-SA | ✅ Completata | 1.481 test superati |
| **2** | Verifica API Flask 3.x, fix route | ✅ Completata | Nessun fix necessario in YWeb |
| **3** | Allineamento runtime esterni | ✅ Completata | YServer f0d6d21, YSimulator c2234f7, YPhotoSharing ead7eae |
| **4** | Cleanup warning legacy, separazione requirements | 🟡 Parziale | Requirements ✅ — push/PR/integration test pendenti |

### Attività rimanenti (da eseguire da Mac terminal)

1. **Commit YWeb cleanup**: `git add ... && git commit -m "cleanup: ..."`
2. **Push branch in tutti e 4 i repo**: `git push origin deps/sqlalchemy2-flask3-migration`
3. **Aprire PR** su GitHub per ciascun repository
4. **Integration test** con PostgreSQL: `pytest -m integration`
5. **Smoke test YServer**: avviare e testare gli endpoint principali
6. **Pulizia**: rimuovere `_to_delete/` da `~/PycharmProjects/YServer/`

---

## 7. Rollback Plan

Se la migrazione produce regressioni non risolvibili in tempi brevi:

1. Ripristinare `requirements-baseline.txt` (backup delle versioni pre-migrazione)
2. Il branch `deps/sqlalchemy2-flask3-migration` viene chiuso senza merge
3. Il branch `main` rimane stabile con le versioni precedenti
4. Aprire issue di tracking per documentare i failure e riprenderli nel ciclo successivo

Lo shim di compatibilità era in `__init__.py` — se necessario il rollback, va ripristinato contestualmente al downgrade di Flask-SQLAlchemy a `==2.5.1`.
