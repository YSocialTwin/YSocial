# YSocial — Analisi del Codebase

> **Data analisi:** settembre 2026  
> **Branch attivo:** `fix/critical-issues`  
> **Stack:** Python ≥ 3.10 · Flask 3.x · SQLAlchemy 2.x · Alembic (Flask-Migrate ≥ 4.0)

---

## 1. Panoramica del progetto

YSocial è una piattaforma web per la gestione e il controllo di simulazioni di social network artificiali. Permette ai ricercatori di configurare popolazioni di agenti LLM, avviare e monitorare simulazioni su diverse tipologie di piattaforma (microblogging, forum stile Reddit, photo-sharing), e raccogliere i dati prodotti.

Il repository principale (`YWeb`) contiene il frontend web (Flask), la logica di business, le API REST e il database amministrativo. Sei repository esterni (submodule Git in `external/`) forniscono i runtime di simulazione specializzati per ciascuna piattaforma.

---

## 2. Struttura del repository YWeb

```
YWeb/
├── y_social.py                  # Entry point CLI
├── y_web/                       # Package Flask principale
│   ├── __init__.py              # create_app() — factory Flask
│   ├── config.py                # Configurazione centralizzata (BaseConfig/Dev/Prod/Test)
│   ├── routes/                  # Registrazione blueprint
│   ├── src/                     # Logica applicativa (12 package)
│   │   ├── models/              # Modelli SQLAlchemy (3 file, 79 classi)
│   │   ├── agents/              # Gestione agenti
│   │   ├── content/             # Contenuti e recsys testuale
│   │   ├── data_access/         # Accesso dati (repositories)
│   │   ├── experiment/          # Ciclo di vita esperimento, schema DB exp
│   │   ├── external_runtime/    # Gestione plugin runtime esterni
│   │   ├── forum/               # Logica forum Reddit-like
│   │   ├── hpc/                 # Modalità HPC: log sync, metriche, watchdog
│   │   ├── llm/                 # Adapter LLM (Ollama, vLLM, OpenAI)
│   │   ├── recsys/              # Recommendation systems
│   │   ├── simulation/          # Process runner, watchdog, port manager
│   │   ├── system/              # Path utils, check release, blog
│   │   └── telemetry/           # Logging eventi
│   ├── alembic/                 # Configurazione Flask-Migrate
│   │   └── versions/0001_baseline.py   # Revisione baseline (no-op)
│   ├── db_init/                 # Inizializzazione DB per tipo
│   │   ├── sqlite.py            # Configura bind SQLite
│   │   ├── postgresql.py        # Configura bind PostgreSQL
│   │   └── migrations.py        # Runner migrazioni legacy (fallback)
│   ├── migrations/              # Script migrazioni manuali legacy
│   ├── templates/               # Jinja2 templates
│   ├── static/                  # Asset statici
│   ├── tests/                   # 165 test pytest
│   └── db/                      # File SQLite runtime (gitignore)
├── external/                    # Repository esterni (submodule)
│   ├── YClient/                 # Runtime client microblogging
│   ├── YClientReddit/           # Runtime client forum
│   ├── YServer/                 # Runtime server microblogging
│   ├── YServerReddit/           # Runtime server forum
│   ├── YSimulator/              # Runtime HPC distribuito (Ray)
│   ├── YPhotoSharing/           # Runtime photo-sharing
│   └── y_agents_plugins/        # Plugin agenti specializzati
├── requirements/
│   ├── base.in / base.txt       # Dipendenze produzione (pip-tools)
│   ├── dev.in / dev.txt         # Dipendenze sviluppo
│   └── test.in / test.txt       # Dipendenze test
├── .github/workflows/           # CI/CD GitHub Actions (5 workflow)
├── deployment/docker/           # Docker Compose
└── packaging/                   # Script packaging macOS (DMG/PyInstaller)
```

---

## 3. Database e ORM

### 3.1 Multi-bind SQLAlchemy

La configurazione usa due bind distinti:

| Bind key   | File                               | Scopo                                     |
|------------|------------------------------------|-------------------------------------------|
| `db_admin` | `y_web/db/dashboard.db`            | Dati amministrativi: utenti, esperimenti, agenti, log |
| `db_exp`   | `y_web/db/dummy.db` (startup)      | Placeholder; sostituito dinamicamente con il DB di ciascun esperimento attivo |

Gli URI di default (`SQLALCHEMY_DATABASE_URI`) e `db_admin` puntano allo stesso file. Ogni esperimento ha il proprio `y_web/experiments/<UUID>/database_server.db`.

### 3.2 Modelli SQLAlchemy (79 classi totali)

**`src/models/admin.py`** (36 classi, bind `db_admin`): `Admin_users`, `Exps`, `ExperimentSchedule*`, `Population`, `Agent`, `Agent_Ext`, `Agent_Custom_Feature`, `Agent_Population`, `Agent_Profile`, `Page`, `ForumRssFeedResource`, `ForumImageFeedResource`, `Client`, `Client_Execution`, `Ollama_Pull`, `Jupyter_instances`, `ReleaseInfo`, `BlogPost`, `DownloadNotification`, `LogFileOffset`, `ServerLogMetrics`, `ClientLogMetrics`, `HpcMonitorSettings`, `WatchdogSettings`, `OpinionGroup`, `OpinionDistribution`, `OpinionEvolutionCache`, `OpinionEvolutionSampledAgents`, `AdminInterviewSession`, `AdminInterviewMessage`.

**`src/models/config.py`** (14 classi, bind `db_admin`): lookup table per `Profession`, `Nationalities`, `Education`, `Leanings`, `Languages`, `Toxicity_Levels`, `AgeClass`, `Content_Recsys`, `Follow_Recsys`, `Topic_List`, `Exp_Topic`, `Page_Topic`, `ActivityProfile`, `PopulationActivityProfile`.

**`src/models/experiment.py`** (29 classi, bind `db_exp`): `User_mgmt`, `Post`, `Hashtags`, `Emotions`, `Post_emotions`, `Post_hashtags`, `Mentions`, `ReplyInboxState`, `ForumChatSession`, `ForumChatMessage`, `Reactions`, `Follow`, `Rounds`, `Recommendations`, `SysMessage`, `Reported`, `Articles`, `Websites`, `Voting`, `Interests`, `User_interest`, `Post_topics`, `Images`, `ImagePosts`, `Article_topics`, `Post_Sentiment`, `Post_Toxicity`, `Agent_Opinion`, `StressReward`.

### 3.3 Gestione migrazioni

**Schema `db_admin` (dashboard.db):** gestito da Alembic tramite Flask-Migrate. Al primo avvio, `create_app()` esegue:

1. Ispeziona tutti i bound engine tramite `MigrationContext` (SA2 native).
2. Stampa con `0001_baseline` i database senza `alembic_version`.
3. Esegue `alembic_upgrade()` → porta `db_admin` a HEAD.
4. Chiama `initialize_active_experiment_databases(app)`.

**Schema `db_exp` (database esperimento):** gestito da `ensure_experiment_schema_for_uri()` in `src/experiment/schema.py`. Il meccanismo usa `CREATE TABLE IF NOT EXISTS` più `ALTER TABLE ADD COLUMN` per aggiungere colonne mancanti, ed è completamente separato da Alembic. `initialize_active_experiment_databases()` interroga la tabella `Exps` (status=1), registra il bind per ogni esperimento attivo e invoca `ensure_experiment_schema_for_uri()` su ciascun DB.

---

## 4. Entry point e factory

`y_social.py` è il CLI principale. Accetta argomenti `--db-type`, `--host`, `--port`, `--debug`, `--llm-backend`, `--notebook`, `--desktop`.

`y_web/__init__.py` → `create_app(db_type, ...)` esegue in ordine:

1. Carica configurazione da `y_web/config.py` (env: `FLASK_ENV`, `YSOCIAL_SECRET_KEY`, `LLM_BACKEND`, `REDIS_URL`, `RAY_ADDRESS`).
2. Inizializza SQLAlchemy (`db.init_app`), Flask-Login, Flask-WTF.
3. Configura i bind DB (`db_init/sqlite.py` o `db_init/postgresql.py`).
4. Registra i 17 blueprint (`routes/__init__.py`).
5. Esegue le migrazioni Alembic (o fallback `run_migrations()` se Flask-Migrate non installato).
6. Inizializza log sync scheduler, telemetry, external runtime bootstrap.

---

## 5. Blueprint (17)

| Blueprint          | Prefisso/funzione principale              |
|--------------------|-------------------------------------------|
| `auth`             | Login, logout, selezione esperimento      |
| `main`             | Feed microblogging, pagina sociale        |
| `user` (actions)   | Follow, publish, react, interazioni       |
| `admin`            | Dashboard amministratore                  |
| `ollama`           | Configurazione backend LLM                |
| `population`       | Gestione popolazioni di agenti            |
| `pages`            | Gestione pagine (bot-page)                |
| `agents`           | Creazione e configurazione agenti         |
| `users`            | Gestione utenti esperimento               |
| `experiments`      | Ciclo di vita esperimento                 |
| `clientsr`         | Log e controllo client di simulazione     |
| `errors`           | Handler 400/403/404/500                   |
| `lab`              | Analisi dati, jupyter, analytics          |
| `tutorial`         | Wizard di configurazione guidata          |
| `api_reddit`       | API REST per simulazioni forum            |
| `api_social`       | API REST per simulazioni microblogging    |
| `api_interview`    | API REST per sessioni intervista agenti   |

---

## 6. Repository esterni

### 6.1 YClient (microblogging client)

Runtime Python che esegue gli agenti sul lato client. Esporta `Agent`, `PageAgent`, `FakeAgent`, `SimulationSlot`, `ContentRecSys`, `FollowRecSys`, `YClientWeb`. La logica di comportamento degli agenti (lettura feed, post, follow, reazioni) risiede qui.

### 6.2 YClientReddit (forum client)

Variante di YClient per scenari Reddit-like: gestione subreddit, thread, voting.

### 6.3 YServer (microblogging server)

Runtime Flask-SQLAlchemy che funge da server per il DB dell'esperimento. Contiene `schema_migrations.py` con migrazioni DDL manuali (es. `sys_messages` table evolution). Include shim di compatibilità SA2 in `__init__.py` tramite `_ensure_flask_sqlalchemy_legacy_compat()`.

### 6.4 YServerReddit (forum server)

Variante di YServer per scenari forum. Schema identico per `sys_messages`, stessa struttura di `schema_migrations.py`.

### 6.5 YSimulator (HPC distribuito)

Runtime distribuito basato su Ray per simulazioni large-scale. Struttura interna speculare a YClient+YServer (`YSimulator/YClient/`, `YSimulator/YServer/`). Aggiunge `agent_manager.py`, `churn_manager.py`, `activity_selector.py`, `reply_handler.py`, `ray_utils.py`. Dipendenze: Ray ≥ 2.0, Redis ≥ 4.0, SQLAlchemy ≥ 2.0, langchain ≥ 0.3. Test suite propria: 80+ test file.

### 6.6 YPhotoSharing (photo-sharing)

Runtime per simulazioni Instagram-like. Struttura YClient+YServer con `annotation.py`, `text_processing.py`, `annotation_processor.py`, `annotation_store.py`.

### 6.7 y_agents_plugins (plugin agenti)

Libreria di famiglie di agenti specializzati con architettura plugin. Famiglie registrate nel `registry.json`:

- **StressAttacker** — iniettore di stress sintetico su target demografici
- **Moderator** — agente moderatore con LLM
- **Propaganda** — agente di propaganda
- **MasterOfPuppets** — orchestratore di agenti
- **ComicRelief** — agente umoristico
- **HelloWorld** — agente di esempio

Struttura: `plugins/base.py` (ABC), `runtime/app.py`, `db/experiment.py`, `llm/langchain.py`.

---

## 7. Modalità di simulazione

| Modalità       | Runtime                  | Scheduling         | Scala            |
|----------------|--------------------------|--------------------|------------------|
| Standard       | YClient + YServer        | processo locale    | singola macchina |
| Forum          | YClientReddit + YServerReddit | processo locale | singola macchina |
| HPC            | YSimulator (Ray)         | Ray cluster        | multi-nodo       |
| Photo-sharing  | YPhotoSharing            | processo locale    | singola macchina |
| Ad-hoc         | `adhoc_client.py`        | on-demand          | singola macchina |

---

## 8. Infrastruttura di test

**165 file di test** in `y_web/tests/`. Copertura delle aree principali: autenticazione, admin, blueprint, API, modelli, simulazione, HPC, forum, opinion evolution, recsys, telemetry, path utils, PyInstaller, packaging Windows/macOS.

La suite include test di regressione (`test_phase*`) che verificano la corretta separazione dei package dopo il refactoring SA2. Il framework usa `pytest`, `pytest-flask`, `pytest-cov`.

**YSimulator** ha una suite separata con 80+ test (Ray, Redis, vLLM, recsys, opinion dynamics).

---

## 9. CI/CD

| Workflow                | Trigger               | Funzione                                  |
|-------------------------|-----------------------|-------------------------------------------|
| `ci-tests.yml`          | push / PR             | Test suite Python 3.10, coverage Codecov  |
| `format-code.yml`       | push                  | isort + black auto-format                 |
| `build-executables.yml` | tag / manuale         | Build PyInstaller macOS                   |
| `release_package.yml`   | tag                   | Release GitHub                            |
| `README.md`             | —                     | Documentazione workflow                   |

---

## 10. Dipendenze principali (base.in)

**Web:** Flask ≥ 3.0, Flask-Login, Flask-SQLAlchemy ≥ 3.0, Flask-Migrate ≥ 4.0, SQLAlchemy ≥ 2.0 < 3.0, Flask-WTF, Werkzeug ≥ 3.0, Jinja2, python-dotenv.

**AI/LLM:** langchain ≥ 0.3, langchain-core, langchain-ollama, langchain-openai, ollama, yclient-memory.

**HPC:** Ray[default] ≥ 2.0, Redis ≥ 4.0.

**NLP/ML:** NLTK ≥ 3.8, numpy, networkx, perspective, detoxify, pillow, feedparser.

**Sistema:** psycopg2-binary, sqlalchemy_utils, gunicorn, gevent, pywebview, psutil, requests, tqdm, faker.

---

## 11. Stato del branch attivo

Il branch `fix/critical-issues` (corrente, non ancora mergiato su `main`) ha risolto nell'ordine:

- **C8** — configurazione centralizzata in `y_web/config.py`
- **C9** — standardizzazione lock dipendenze (pip-tools)
- **C2** — regole `.gitignore` per DB runtime
- **C4** — shim SQLAlchemy 2 centralizzato in `_sa2_stubs.py`
- **C3** — integrazione Flask-Migrate/Alembic, auto-stamp DB pre-Alembic, fix `env.py`, multi-bind
- Cleanup test, rimozione `fix_tests.py`, auto-format

Commit recenti non ancora integrati su `main`:
- `c512dbd1` — alembic multi-bind + experiment DB migration al boot
- `ebc49b66` — auto-stamp + fix env.py logging guard
- *(precedenti)* — vari fix critici C2–C9

---

## 12. Criticità rilevanti non colmate

### C-A · Doppio sistema di migrazioni per i DB degli esperimenti ⚠️ Alta

Gli schema di `db_exp` (29 modelli in `experiment.py`) sono gestiti da `ensure_experiment_schema_for_uri()` con DDL diretto (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ADD COLUMN`). Questo meccanismo è separato e parallelo ad Alembic. Ogni nuovo campo aggiunto a `experiment.py` richiede una voce manuale in `_SQLITE_TABLES` o `_SQLITE_COLUMNS` di `schema.py` **e** una corrispondente modifica per PostgreSQL in `ensure_postgresql_experiment_schema()`. La mancanza di uno strato di migration unificato rende difficile verificare che tutti i DB degli esperimenti esistenti siano allineati allo schema corrente, soprattutto per installazioni PostgreSQL di produzione.

### C-B · YServer usa ancora shim SA2 legacy ⚠️ Media

`YServer/__init__.py` chiama `_ensure_flask_sqlalchemy_legacy_compat()` che patcha `sqlalchemy.orm.relation` a runtime. Questo shim è necessario perché YServer (e YServerReddit, YSimulator) instanziano Flask-SQLAlchemy con pattern da SA 1.x. Quando la SA2-compat shim verrà rimossa, questi runtime potrebbero rompersi. Non c'è coordinazione di versione documentata tra YWeb e i runtime esterni.

### C-C · `fix/critical-issues` non mergiato su `main` ⚠️ Media

Tutti i fix critici risiedono sul branch corrente. Il branch `main` è fermo a un commit precedente all'introduzione di Flask-Migrate. Finché il merge non avviene, un checkout di `main` produce un'istanza senza gestione Alembic, con il runner legacy.

### C-D · CI installa pytest direttamente, non da `requirements/test.txt` ℹ️ Bassa

Il workflow `ci-tests.yml` esegue `pip install pytest pytest-cov` anziché `pip install -r requirements/test.txt`. Qualsiasi dipendenza test aggiunta a `test.in` (es. `pytest-flask`) non viene installata automaticamente in CI, richiedendo aggiornamento manuale del workflow.

### C-E · Unica revisione Alembic (0001_baseline no-op) ℹ️ Bassa

Il repository contiene una sola revisione Alembic che non esegue DDL. Qualsiasi modifica futura allo schema di `db_admin` richiede la creazione manuale di una revisione con `flask db migrate`. Non c'è un processo documentato né un hook CI che verifichi che i modelli siano in sync con le revisioni.

### C-F · `YClient/__init__.py` usa `except:` nudo ℹ️ Bassa

Il blocco di import principale in `external/YClient/y_client/__init__.py` usa `except:` senza tipo, che inghiotte qualsiasi errore (inclusi `ImportError` da dipendenze mancanti) silenziosamente. Stesso pattern probabile in `YClientReddit`. In fase di debug può nascondere problemi reali di importazione.

### C-G · Packaging solo macOS ℹ️ Bassa

Gli script in `packaging/` e il workflow `build-executables.yml` supportano solo macOS (DMG via PyInstaller). Non esiste un equivalente per Windows o Linux.

### C-H · Schema_migrations nei runtime esterni non coordinato ℹ️ Informativa

`YServer`, `YServerReddit` e `YSimulator` contengono ciascuno `schema_migrations.py` con logica DDL propria (es. evoluzione di `sys_messages`). Queste migrazioni vengono applicate quando il runtime si avvia, indipendentemente da YWeb e da Alembic. Se un aggiornamento del runtime esterno modifica uno schema già presente nel DB di un esperimento vecchio, non c'è garanzia di ordine di applicazione rispetto alle migrazioni YWeb.

---

## 13. Valutazione complessiva

Il progetto è **architetturalmente maturo** per una piattaforma di ricerca: separazione netta dei ruoli (web control plane vs runtime di simulazione), supporto a più modalità operative (locale/HPC), suite di test estesa (165 + 80 test), pipeline CI funzionale, documentazione MkDocs.

Il refactoring SA2/Flask3 (branch `fix/critical-issues`) ha risolto le criticità bloccanti e il codebase è attualmente in uno stato stabile e avviabile. La criticità architetturale più rilevante non risolta è il **doppio sistema di schema management per i DB degli esperimenti** (C-A): finché `db_exp` e i runtime esterni continuano a usare DDL diretto invece di Alembic, ogni modifica allo schema dell'esperimento richiede aggiornamenti in punti multipli e non verificabili automaticamente. Questo è accettabile nello stato attuale del progetto, ma diventerà un freno alla manutenibilità con la crescita del numero di colonne e piattaforme.
