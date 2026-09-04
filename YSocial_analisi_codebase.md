# YSocial – Analisi della Codebase

> Documento generato il 4 settembre 2026  
> Analista: Claude Sonnet 4.6 (Cowork) su richiesta di Giulio Rossetti  
> Versione analizzata: **4.0.0** — branch attivo: `deps/sqlalchemy2-flask3-migration`

---

## 1. Descrizione del Progetto

**YSocial** è un **Digital Twin di piattaforme di social media**, alimentato da LLM (Large Language Model), progettato per condurre simulazioni sociali in ambiente *zero-code*. Il progetto è sviluppato nell'ambito della ricerca accademica (CNR / SoBigData++) e accompagnato da una pubblicazione scientifica (arXiv:2408.00818).

L'obiettivo è replicare le dinamiche di una piattaforma social (X/Twitter, Reddit, Instagram-like) popolata da agenti AI configurabili, consentendo ai ricercatori di studiare fenomeni come diffusione dell'informazione, polarizzazione, opinion dynamics e tossicità in ambiente controllato e riproducibile.

---

## 2. Stack Tecnologico Attuale

| Layer | Tecnologia | Note |
|---|---|---|
| Backend web | Flask 3.0.3, Werkzeug ≥3.0 | Migrazione recente da Flask 2.x |
| ORM / Database | SQLAlchemy ≥2.0,<3.0, Flask-SQLAlchemy 3.1.1 | Migrazione SA2 appena completata |
| Database engine | SQLite (default) / PostgreSQL | psycopg2-binary |
| AI / LLM | LangChain ≥0.3, langchain-ollama, langchain-openai | Compatibile con Ollama e vLLM |
| Analisi testo | NLTK (VADER), Detoxify, Perspective API | detoxify ≥0.5.2 |
| Computing distribuito | Ray ≥2.0,<3.0, Redis ≥4.0 | Per esperimenti HPC |
| Network analysis | NetworkX | |
| Frontend | Jinja2 templates (tema Friendkit), HTML/CSS/JS | Template custom multi-blueprint |
| Packaging | PyInstaller + PyWebview, Docker + gunicorn/gevent | Modalità desktop e server |
| Analisi dati | JupyterLab integrato, libreria `ysights` | Integrazione notebook |
| Autenticazione | Flask-Login 0.6.3, Flask-WTF 1.2.2 | |
| Memoria agenti | `yclient-memory` (pacchetto esterno) | |

**Requisito Python:** ≥ 3.10

---

## 3. Architettura del Sistema

YSocial adotta un'architettura **monolitica modulare** costruita attorno al pattern *Application Factory* di Flask. Il nucleo applicativo (`y_web/`) è composto da:

- **82 file Python** nel layer `src/` (business logic)
- **60 file Python** nel layer `routes/` (blueprint HTTP)
- **31 migration script** in `migrations/`
- **165 file di test** in `y_web/tests/`

Il sistema si compone di due piani distinti: il **pannello di controllo** (Flask/web) e il **runtime di simulazione** (processi esterni orchestrati dal pannello).

### 3.1 Struttura delle Directory

```
YWeb/
├── y_social.py              # Entry point principale
├── y_social_launcher.py     # Launcher (desktop + browser mode)
├── y_social.spec            # Specifica PyInstaller
├── fix_tests.py             # Script di compatibilità SA2 per i test (28 KB)
├── requirements/
│   ├── base.txt             # Dipendenze produzione (pinnate)
│   ├── dev.txt              # Dipendenze sviluppo
│   └── test.txt             # Dipendenze test
├── requirements.lock        # Lock file (non standardizzato)
├── requirements-baseline.txt
├── y_web/                   # Applicazione Flask principale
│   ├── __init__.py          # App factory, lifecycle, context processors
│   ├── db/                  # File database runtime (dashboard.db ~58MB, dummy.db ~5MB)
│   ├── db_init/             # Inizializzazione schema (sqlite.py, postgresql.py)
│   ├── migrations/          # 31 script di migrazione manuale
│   ├── routes/              # Blueprint Flask (18 blueprints registrati)
│   │   ├── admin/           # Pannello amministrativo + sub-blueprints
│   │   ├── api/             # API REST (social, reddit, interview)
│   │   ├── auth/            # Autenticazione
│   │   ├── errors/          # Gestione errori HTTP
│   │   ├── interactions/    # Interazioni social (follow, post, reazioni)
│   │   └── social/          # Feed, timeline, profili, forum, foto
│   ├── src/                 # Business logic
│   │   ├── agents/          # Gestione agenti AI e popolazioni
│   │   ├── content/         # Estrazione articoli, avatar, feed RSS
│   │   ├── data_access/     # Strato di accesso dati (posts, profili, trend)
│   │   ├── experiment/      # Ciclo di vita esperimenti, scheduling, contesto
│   │   ├── experiments/     # Logica esperimenti (directory separata)
│   │   ├── external_runtime/# Manager runtime esterni (YClient, YServer, ecc.)
│   │   ├── forum/           # Modalità forum (Reddit-like)
│   │   ├── hpc/             # Supporto High Performance Computing
│   │   ├── llm/             # Integrazione LLM (Ollama, vLLM, annotazione)
│   │   ├── models/          # Modelli SQLAlchemy (admin, experiment, config)
│   │   ├── recsys/          # Sistemi di raccomandazione (content + follow)
│   │   ├── simulation/      # Orchestrazione simulazioni locali
│   │   ├── system/          # Utilità di sistema (Jupyter, path, release check)
│   │   └── telemetry/       # Logging eventi e telemetria
│   ├── pyinstaller_utils/   # Utilities per packaging standalone
│   ├── static/              # Asset statici
│   └── templates/           # Template Jinja2
├── external/                # Runtime esterni (7 plugin repos)
│   ├── YClient/             # Client microblogging
│   ├── YClientReddit/       # Client forum Reddit-like
│   ├── YServer/             # Server microblogging
│   ├── YServerReddit/       # Server forum Reddit-like
│   ├── YSimulator/          # Simulatore HPC distribuito
│   ├── YPhotoSharing/       # Client/server photo-sharing
│   ├── y_agents_plugins/    # Plugin agenti AI estesi
│   └── plugins.json         # Registro plugin
├── data_schema/             # Schemi DB di riferimento e prompt LLM
├── deployment/              # Docker + Nginx
└── docs/                    # Documentazione MkDocs
```

### 3.2 Ecosistema di Plugin Esterni

I sette repository esterni in `external/` rappresentano il **runtime di simulazione**, orchestrato dal pannello Flask. Ogni plugin copre uno scenario specifico:

| Plugin | Ruolo | Modalità |
|---|---|---|
| YClient | Client agenti – microblogging | Standard locale |
| YServer | Server simulazione – microblogging | Standard locale |
| YClientReddit | Client agenti – forum Reddit-like | Standard locale |
| YServerReddit | Server simulazione – forum Reddit-like | Standard locale |
| YSimulator | Runtime distribuito Ray-based | HPC |
| YPhotoSharing | Client/server – condivisione foto | Standard / HPC |
| y_agents_plugins | Famiglie di agenti estensibili | Tutti |

Il coordinamento avviene tramite `y_web/src/simulation/` (backend standard) e `y_web/src/hpc/` (backend HPC), con routing dinamico in `execution_backend.py`.

### 3.3 Modalità di Esecuzione

Il sistema supporta tre modalità operative:

1. **Browser mode** — Flask server + browser web (sviluppo e produzione)
2. **Desktop mode** — PyInstaller + PyWebview (distribuzione standalone per utenti finali)
3. **HPC mode** — Ray + Redis per esperimenti distribuiti su cluster

---

## 4. Stato Attuale e Recenti Sviluppi

### 4.1 Migrazione SA2 / Flask 3 (Completata di Recente)

La migrazione da SQLAlchemy 1.x → 2.x e Flask 2.x → 3.x è stata completata nel branch corrente (`deps/sqlalchemy2-flask3-migration`). I commit recenti documentano:

- Migrazione di **167 pattern di query** dall'API legacy (`Model.query.*`) alla nuova API SA2 (`db.session.scalars(select(Model)…)`)
- Aggiornamento di `pytest.ini` con filtri `error` su `LegacyAPIWarning` e `MovedIn20Warning`
- Creazione di `fix_tests.py` (28 KB) con shim di compatibilità SA2 per la suite di test

Lo script `fix_tests.py` introduce classi intermedie (`_FakeSelect`, `_SelectRoutingSession`, `_ScalarsResult`) per far funzionare i test legacy con la nuova API, il che indica che la suite di test **non è ancora completamente migrata** alla nuova API.

### 4.2 Stato Branches

Il repository presenta **oltre 110 branch locali**, di cui:

- ~85 branch `copilot/` (generati da GitHub Copilot per feature isolate)
- Branch tematici attivi: `main`, `HPC`, `HPC+Reddit`, `opinion_dynamics`, `plugins`, `packaging`, `ray`, `forum_template`
- Branch in apparente abbandono: `simple_ABM`, `second-skin`, `activity_profiles`, `experiment_matrix`

### 4.3 Test Suite

165 file di test coprono l'intera codebase con un approccio granulare. La struttura riflette il percorso evolutivo del refactoring (famiglie `test_phase*` documentano fasi di ristrutturazione). La dipendenza dallo shim in `fix_tests.py` indica che una porzione dei test non è ancora idiomatica per SA2.

---

## 5. Valutazione del Progetto

### 5.1 Punti di Forza

**Architettura e modularità.** Il pattern App Factory, la separazione tra `routes/` e `src/`, e il routing dinamico tra backend standard e HPC in `execution_backend.py` mostrano una struttura matura e scalabile.

**Copertura di test.** 165 file di test sono un patrimonio rilevante. La presenza di marker pytest (`slow`, `integration`, `unit`, `external_repo`) indica una disciplina di test strutturata.

**Ecosistema plugin.** Il sistema di plugin in `external/` con registro `plugins.json` è un'architettura estensibile che supporta diversi scenari di simulazione (microblogging, forum, foto, HPC) con un'interfaccia di orchestrazione comune.

**Supporto multi-modalità.** La capacità di eseguire in modalità browser, desktop standalone e HPC distribuito è un differenziatore significativo per un prodotto di ricerca accademico.

**Recente aggiornamento delle dipendenze.** La migrazione a Flask 3 / SA2 era necessaria per la longevità del progetto e rimuove debito tecnico critico.

### 5.2 Aree di Debolezza

**Maturità del ciclo di migrazione SA2.** La presenza di `fix_tests.py` come shim temporaneo invece di test completamente riscritti crea un layer di opacità sulla reale qualità dei test.

**Gestione configurazione e segreti.** La `SECRET_KEY` è hardcoded nel codice sorgente (`"4323432nldsf"`), il che è un problema di sicurezza fondamentale che pregiudica qualsiasi deploy in produzione.

**Proliferazione di branch.** 85+ branch `copilot/` mai mergiati/eliminati degradano la leggibilità del repository e complicano la comprensione dello stato del progetto.

**File di database nel repository.** Il file `y_web/db/dashboard.db` (~58 MB) e `dummy.db` (~5 MB) sono file di database runtime tracciati nel repository, il che è una cattiva pratica che inquina la history git e può portare a confusione.

**Sistema di migrazione personalizzato.** Le 31 migration sono script Python manuali senza framework (no Alembic), il che rende difficile la gestione dell'ordine di applicazione, la gestione dei rollback e il tracking dello stato.

**Doppia directory per logica esperimenti.** Esiste sia `y_web/src/experiment/` che `y_web/src/experiments/` (nota il plurale), suggerendo una separazione non ancora risolta.

---

## 6. Criticità Identificate e Pipeline di Risoluzione

### CRITICITÀ 1 — Secret Key Hardcoded in Sorgente

**Severità:** 🔴 Critica  
**Localizzazione:** `y_web/__init__.py` → `app.config["SECRET_KEY"] = "4323432nldsf"`

**Impatto:** Qualsiasi deploy di produzione espone la chiave di sessione Flask a chiunque abbia accesso al codice sorgente. Le sessioni utente possono essere forgiate da attori malevoli.

**Pipeline di risoluzione:**

1. Introdurre gestione variabili d'ambiente con `python-dotenv` o leggere da `os.environ`
2. Creare `.env.example` con `SECRET_KEY=<replace-me>` e `.env` in `.gitignore`
3. Sostituire la hardcoded key con `os.environ.get("YSOCIAL_SECRET_KEY", os.urandom(32).hex())`
4. Aggiungere validazione all'avvio: se la key è quella di default in non-debug mode, rifiutarsi di avviare
5. Documentare il requisito in `CONTRIBUTING.md` e nel `README`

**Criteri di successo:**  
- `grep -r "4323432" y_web/` restituisce zero risultati  
- Il test di avvio in produzione fallisce se `YSOCIAL_SECRET_KEY` non è impostata  
- La CI verifica l'assenza di secret hardcoded con `detect-secrets` o `trufflehog`

---

### CRITICITÀ 2 — File di Database Runtime Tracciati in Git

**Severità:** 🔴 Critica  
**Localizzazione:** `y_web/db/dashboard.db` (~58 MB), `y_web/db/dummy.db` (~5 MB), `y_web/db/database.db`, `y_web/system/yweb.db`, `y_web/yweb.db`

**Impatto:** La history git è gonfiata da file binari di grandi dimensioni. I database contengono dati di esperimenti che possono includere dati sensibili. I file `.fuse_hidden*` visibili nella directory indicano che i file sono aperti durante la sincronizzazione.

**Pipeline di risoluzione:**

1. Aggiungere a `.gitignore`: `y_web/db/*.db`, `y_web/db/*.db-shm`, `y_web/db/*.db-wal`, `*.fuse_hidden*`, `**/*.db` (eccetto schemi reference in `data_schema/`)
2. Rimuovere i file dalla tracking git con `git rm --cached`
3. Considerare `git filter-repo` per ripulire la history se le dimensioni del repository sono già significative
4. Creare una directory `data/` (gitignored) come path standard per i database runtime, aggiornando `db_init/sqlite.py`
5. Mantenere in `data_schema/` solo i database di schema di riferimento vuoti (già presente)

**Criteri di successo:**  
- `git ls-files | grep '\.db$'` restituisce solo i file in `data_schema/`  
- Dimensione del repository ridotta significativamente  
- Il `db_init` crea correttamente i database in una directory configurabile fuori dal sorgente

---

### CRITICITÀ 3 — Sistema di Migrazione Senza Framework

**Severità:** 🟠 Alta  
**Localizzazione:** `y_web/migrations/` (31 script Python manuali), `y_web/db_init/migrations.py`

**Impatto:** Nessun tracking dello stato applicato (quale migrazione è già stata eseguita su quale database), nessun meccanismo di rollback, ordine di esecuzione dipendente da convenzioni non enforce, impossibile verificare se un database di produzione è allineato al codice.

**Pipeline di risoluzione:**

1. Valutare l'adozione di **Flask-Migrate** (wrapper Alembic per Flask-SQLAlchemy) — il già presente SA2 lo supporta nativamente
2. Piano di migrazione incrementale:
   - Creare una migrazione Alembic iniziale che rispecchia lo stato attuale degli schemi
   - Convertire i 31 script esistenti in revisioni Alembic sequenziali (mantenendo i file originali come documentazione)
   - Aggiungere una tabella `alembic_version` al database per tracking automatico dello stato
3. Aggiornare `db_init/migrations.py` per invocare Alembic invece degli script custom
4. Aggiungere `flask db upgrade` al processo di avvio e alla CI

**Criteri di successo:**  
- `flask db current` riporta la revisione corrente su tutti gli ambienti  
- `flask db upgrade` è idempotente (applicabile su un database già aggiornato)  
- La CI esegue `flask db upgrade` su un database SQLite vuoto senza errori  
- Ogni nuova feature che modifica lo schema include la relativa revisione Alembic

---

### CRITICITÀ 4 — Shim SA2 nei Test (`fix_tests.py`)

**Severità:** 🟠 Alta  
**Localizzazione:** `fix_tests.py` (28 KB), test in `y_web/tests/` che ancora usano pattern legacy

**Impatto:** Lo shim `_SelectRoutingSession` / `_FakeSelect` nasconde bug reali nell'interazione con SA2. I test che passano attraverso lo shim non verificano il comportamento reale del codice di produzione. Il file di 28 KB introduce complessità di manutenzione non necessaria.

**Pipeline di risoluzione:**

1. Identificare l'elenco completo dei test che dipendono dallo shim (analisi statica o run con shim disabilitato)
2. Per ogni test dipendente, riscrivere il setup/teardown usando SA2 nativamente:
   - Sostituire `Model.query.filter_by(…)` con `db.session.scalars(select(Model).filter_by(…))`
   - Usare `db.session.get(Model, pk)` per lookup per chiave primaria
3. Rimuovere progressivamente l'applicazione dello shim file per file
4. Aggiungere un test sentinella che verifica che nessun file di test importi classi dallo shim
5. Eliminare `fix_tests.py` quando tutti i test sono migrati

**Criteri di successo:**  
- `fix_tests.py` non esiste più nel repository  
- `pytest.ini` mantiene `error::sqlalchemy.exc.LegacyAPIWarning`  
- L'intera suite di 165 test passa senza shim attivi  
- La CI esegue i test con `filterwarnings = error::sqlalchemy` su ogni PR

---

### CRITICITÀ 5 — Proliferazione di Branch e Gestione Repository

**Severità:** 🟡 Media  
**Localizzazione:** Repository git (110+ branch, ~85 branch `copilot/`)

**Impatto:** La navigazione del repository è compromessa. È difficile distinguere lo stato del lavoro in corso da branch abbandonati. La storia degli sviluppi è frammentata e inutilizzabile per audit o onboarding di nuovi collaboratori.

**Pipeline di risoluzione:**

1. Classificare i branch `copilot/` in tre categorie: già mergiato nel main, ancora rilevante, abbandonato
2. Eliminare i branch `copilot/` già mergiati o abbandonati:
   ```bash
   git branch -d <branch>           # localmente
   git push origin --delete <branch> # remotamente
   ```
3. Definire una branch naming convention per il team (e.g., `feat/`, `fix/`, `chore/`, `research/`)
4. Configurare una policy GitHub per l'eliminazione automatica dei branch dopo il merge
5. Archiviare i branch tematici non più attivi (e.g., `simple_ABM`, `second-skin`) come tag git prima della cancellazione

**Criteri di successo:**  
- Branch totali < 20 (main + branch tematici attivi + branch feature in corso)  
- Zero branch `copilot/` nel repository  
- La PR page è leggibile e riflette lo stato reale del lavoro  
- La policy di auto-delete post-merge è abilitata su GitHub

---

### CRITICITÀ 6 — Duplicazione Directory `experiment` vs `experiments`

**Severità:** 🟡 Media  
**Localizzazione:** `y_web/src/experiment/` e `y_web/src/experiments/`

**Impatto:** Ambiguità su dove risiede la logica degli esperimenti. Potenziale duplicazione di codice o responsabilità sovrapposte.

**Pipeline di risoluzione:**

1. Analizzare il contenuto e le dipendenze di entrambe le directory
2. Se `experiments/` contiene logica residua dell'era pre-refactoring, consolidarla in `experiment/` con le dovute PR
3. Eliminare la directory vuota/residua e aggiornare tutti gli import
4. Aggiungere un test di struttura (`test_app_structure.py` esiste già) che verifica l'assenza di directory duplicate

**Criteri di successo:**  
- Esiste una sola directory `experiment` (senza plurale)  
- Tutti gli import referenziano il percorso corretto  
- Nessuna duplicazione di classi o funzioni tra le due

---

### CRITICITÀ 7 — Gestione dei Repository Esterni senza Git Submodules

**Severità:** 🟡 Media  
**Localizzazione:** `external/` (7 repository copiati manualmente)

**Impatto:** Non è possibile tracciare a quale commit di ogni repo esterno corrisponde la copia locale. Aggiornamenti manuali soggetti ad errori. Nessuna garanzia di riproducibilità degli esperimenti su macchine diverse.

**Pipeline di risoluzione:**

1. Convertire `external/` da copie manuali a **git submodules** con pinning esplicito al commit:
   ```bash
   git submodule add https://github.com/YSocialTwin/YClient external/YClient
   git submodule add https://github.com/YSocialTwin/YServer external/YServer
   # … ecc.
   ```
2. Registrare la versione di ciascun submodule compatibile con la versione 4.0.0 di YWeb
3. Aggiornare `external_runtime/manager.py` e `registry.py` per leggere i submodule
4. Documentare il processo di update dei submodule nel `CONTRIBUTING.md`
5. Aggiungere alla CI un check che verifica che i submodule siano aggiornati al commit pinnato

**Criteri di successo:**  
- `.gitmodules` elenca tutti e 7 i repository esterni  
- `git submodule status` mostra commit esatti e non modifiche locali  
- Il clone del repository con `--recurse-submodules` riproduce l'ambiente correttamente  
- La CI fallisce se un submodule punta a un commit non-tagged

---

### CRITICITÀ 8 — Assenza di Gestione Centralizzata della Configurazione

**Severità:** 🟡 Media  
**Localizzazione:** `y_social.py`, `y_web/__init__.py`, configurazione distribuita

**Impatto:** Configurazioni come `SECRET_KEY`, URL del database, URL LLM, parametri Redis sono sparsi tra codice, variabili d'ambiente, e argomenti CLI senza un punto di verità unico. Difficile configurare ambienti diversi (sviluppo, test, produzione) in modo affidabile.

**Pipeline di risoluzione:**

1. Creare un modulo `y_web/config.py` con classi di configurazione (`DevelopmentConfig`, `TestingConfig`, `ProductionConfig`) che caricano da variabili d'ambiente
2. Centralizzare tutti i parametri configurabili: `SECRET_KEY`, `DATABASE_URL`, `LLM_BACKEND`, `LLM_URL`, `REDIS_URL`, `RAY_ADDRESS`
3. Aggiornare `create_app()` per accettare una classe di configurazione
4. Creare `.env.example` documentato con tutti i parametri richiesti
5. Aggiornare la documentazione di deployment

**Criteri di successo:**  
- Nessun parametro di configurazione hardcoded nel sorgente  
- `python -c "from y_web.config import ProductionConfig; ProductionConfig.validate()"` verifica tutti i requisiti  
- I test usano `TestingConfig` con database in-memory  
- Il `README` documenta ogni variabile d'ambiente supportata

---

### CRITICITÀ 9 — Lock delle Dipendenze Non Standardizzato

**Severità:** 🟢 Bassa  
**Localizzazione:** `requirements.lock`, `requirements-baseline.txt`, `requirements/base.txt`

**Impatto:** Tre file con ruoli sovrapposti e semantiche diverse. `requirements.lock` non è in un formato standard riconosciuto da `pip` o `pip-tools`. Riproducibilità degli ambienti potenzialmente compromessa.

**Pipeline di risoluzione:**

1. Adottare `pip-tools` o `uv` per la gestione dei lock file
2. `requirements/base.txt` → file di input con dipendenze senza pin
3. `requirements/base.lock.txt` → file generato automaticamente con tutti i pin transitivi
4. Eliminare `requirements.lock` e `requirements-baseline.txt` come duplicati
5. Aggiungere alla CI una verifica che il lock file sia aggiornato rispetto alle dipendenze dichiarate

**Criteri di successo:**  
- Un solo file lock generato automaticamente e verificato in CI  
- `pip install -r requirements/base.lock.txt` produce un ambiente identico su macchine diverse  
- Il processo di aggiornamento delle dipendenze è documentato e automatizzato (es. Dependabot)

---

## 7. Riepilogo Priorità e Roadmap

| # | Criticità | Severità | Effort Stimato | Priorità |
|---|---|---|---|---|
| 1 | Secret Key hardcoded | 🔴 Critica | Basso (1-2h) | **Immediata** |
| 2 | Database runtime in git | 🔴 Critica | Medio (4-8h) | **Immediata** |
| 3 | Sistema migrazione senza framework | 🟠 Alta | Alto (3-5 giorni) | Sprint 1 |
| 4 | Shim SA2 nei test | 🟠 Alta | Alto (3-5 giorni) | Sprint 1 |
| 5 | Proliferazione branch git | 🟡 Media | Basso (2-4h) | Sprint 1 |
| 6 | Duplicazione `experiment` vs `experiments` | 🟡 Media | Basso (2-4h) | Sprint 2 |
| 7 | External repos senza submodules | 🟡 Media | Medio (1-2 giorni) | Sprint 2 |
| 8 | Configurazione distribuita | 🟡 Media | Medio (1-2 giorni) | Sprint 2 |
| 9 | Lock dipendenze non standardizzato | 🟢 Bassa | Basso (2-4h) | Sprint 3 |

### Roadmap consigliata

**Fase 0 — Immediate (questa settimana)**  
Risolvere criticità 1 e 2: sicurezza della secret key e pulizia dei database dal repository. Entrambe hanno impatto immediato su sicurezza e igiene del repository con effort minimo.

**Sprint 1 (2-3 settimane)**  
Completare la migrazione SA2 eliminando lo shim (criticità 4), fare pruning dei branch `copilot/` (criticità 5), e iniziare la valutazione di Flask-Migrate (criticità 3 — fase di studio).

**Sprint 2 (1 mese)**  
Adottare Flask-Migrate per le future migrazioni (criticità 3), risolvere la duplicazione di directory (criticità 6), convertire `external/` a submodules (criticità 7), centralizzare la configurazione (criticità 8).

**Sprint 3 (ongoing)**  
Standardizzare il lock delle dipendenze (criticità 9) e istituire revisioni periodiche della codebase.

---

## 8. Indicatori di Salute del Progetto

| Metrica | Stato Attuale | Target |
|---|---|---|
| Test files | 165 | ✅ Ottimo |
| Branch attivi (escluso `copilot/`) | ~25 | ⚠️ Da ridurre a <15 |
| Shim SA2 attivi | Sì (`fix_tests.py`) | ❌ Da eliminare |
| Secret key hardcoded | Sì | ❌ Da correggere |
| DB runtime in git | Sì (~63 MB) | ❌ Da rimuovere |
| Sistema migrazione | Script custom | ⚠️ Valutare Alembic |
| Lock dipendenze standardizzato | No | ⚠️ Da migliorare |
| Submodules per repo esterni | No (copie manuali) | ⚠️ Da convertire |
| Configurazione centralizzata | No | ⚠️ Da implementare |
| Documentazione deploy | Parziale (README + MkDocs) | ⚠️ Da completare |

---

*Documento da aggiornare ad ogni major release o ciclo di sprint.*
