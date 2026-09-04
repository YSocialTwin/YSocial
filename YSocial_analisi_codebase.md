# YSocial — Analisi Codebase

> Documento generato il 4 settembre 2026  
> Versione analizzata: **4.0.0** — branch `fix/critical-issues`  
> Stack: Flask 3.x · SQLAlchemy 2.x · Python ≥ 3.9

---

## 1. Panoramica del progetto

YSocial è una piattaforma di simulazione di reti sociali (digital twin) che consente ai ricercatori di configurare ed eseguire esperimenti su popolazioni di agenti LLM che interagiscono su social network artificiali. Il sistema è composto da due componenti principali:

- **YWeb** (`y_web/`) — applicazione Flask che funge da server centrale: gestisce la UI web del ricercatore, il database degli esperimenti, il coordinamento dei client di simulazione e l'API REST.
- **YClient** (`external/YClient/`) — libreria Python (submodule git) che implementa gli agenti di simulazione. I client vengono lanciati come sottoprocessi separati (locale, HPC via Ray, ad-hoc) e comunicano con YWeb tramite API REST.

Le piattaforme social simulate sono tre: **microblogging** (stile Twitter), **forum** (stile Reddit), **photo sharing** (stile Instagram). Ogni esperimento può girare su una o più piattaforme contemporaneamente.

---

## 2. Entry point e avvio

| File | Ruolo |
|------|-------|
| `y_social.py` | Entry point principale. Parsa gli argomenti CLI (db_type, host, port, llm_backend, notebook, desktop_mode), configura l'LLM, chiama `create_app()` e avvia Flask. |
| `y_social_launcher.py` | Wrapper per il bundle PyInstaller (modalità desktop). |
| `entrypoint.sh` | Entry point Docker. |

Avvio tipico:
```bash
python y_social.py --db sqlite --port 8080 --llm ollama
```

LLM backend supportati: `ollama` (http://127.0.0.1:11434/v1), `vllm` (http://127.0.0.1:8000/v1), URL custom (`host:port`). Se omesso, le funzionalità LLM vengono disabilitate.

---

## 3. Struttura delle directory

```
YWeb/
├── y_social.py                  # Entry point principale
├── y_social_launcher.py         # Launcher desktop/PyInstaller
├── y_web/                       # Package Flask principale
│   ├── __init__.py              # Factory create_app()
│   ├── config.py                # Configurazione (BaseConfig, Dev, Test, Prod)
│   ├── alembic/                 # Gestione migrazioni (Flask-Migrate)
│   │   ├── env.py
│   │   └── versions/0001_baseline.py
│   ├── db/                      # DB runtime SQLite (gitignored)
│   ├── db_init/                 # Inizializzazione DB
│   │   ├── migrations.py        # Runner migrazioni manuali (legacy, fallback)
│   │   ├── sqlite.py            # Inizializzazione SQLite
│   │   └── postgresql.py        # Inizializzazione PostgreSQL
│   ├── migrations/              # 31 script SQL incrementali (storici)
│   ├── routes/                  # Blueprint Flask (17 totali)
│   │   ├── admin/               # Dashboard ricercatore
│   │   ├── api/                 # API REST (reddit, social, interview)
│   │   ├── auth/                # Autenticazione
│   │   ├── errors/              # Handler errori HTTP
│   │   ├── interactions/        # Azioni utente (follow, post, reazioni)
│   │   └── social/              # Viste piattaforme social
│   ├── src/                     # Logica di dominio (12 package)
│   ├── static/                  # Asset statici (10.545 file)
│   ├── templates/               # Template HTML (118 file)
│   └── tests/                   # Test suite (169 file, ~39K LOC)
├── external/YClient/            # Submodule: libreria agenti di simulazione
├── data_schema/                 # Schema DB di riferimento (SQLite + PostgreSQL)
├── deployment/                  # Docker compose, nginx
├── docs/                        # Documentazione progetto
├── requirements/                # Dipendenze pip-tools
│   ├── base.in / base.txt       # Dipendenze produzione
│   ├── dev.in / dev.txt         # Dipendenze sviluppo
│   └── test.in / test.txt       # Dipendenze test
└── .github/workflows/           # CI/CD GitHub Actions
```

---

## 4. Configurazione (`y_web/config.py`)

Quattro classi di configurazione con ereditarietà:

| Classe | Contesto | SECRET_KEY | DB |
|--------|----------|------------|-----|
| `BaseConfig` | Base comune | — | — |
| `DevelopmentConfig` | Locale / debug | `$YSOCIAL_SECRET_KEY` o random | SQLite auto-rilevato |
| `TestingConfig` | pytest | `test-secret-key-…` (hardcoded) | `sqlite:///:memory:` |
| `ProductionConfig` | Deploy | `$YSOCIAL_SECRET_KEY` (obbligatorio) | Configurato a runtime |

`get_config()` rileva automaticamente l'ambiente tramite `FLASK_ENV`. La configurazione per il DB (SQLALCHEMY_BINDS) viene iniettata a runtime in `create_app()` in base al `db_type` scelto.

---

## 5. Factory `create_app()`

`y_web/__init__.py` contiene `create_app(db_type, desktop_mode, config_class)`. I passi principali:

1. Creazione istanza Flask e caricamento config
2. Configurazione `SQLALCHEMY_BINDS` (sqlite o postgresql) tramite `create_sqlite_db()` / `create_postgresql_db()`
3. Inizializzazione estensioni: `db`, `LoginManager`
4. Registrazione blueprint (`register_blueprints(app)`)
5. Context processor injection (exp_id, LLM state, user info, release info, ecc.)
6. **Migrazioni database** (blocco C3):
   - Se Flask-Migrate è installato: auto-stamp dei DB pre-Alembic, poi `alembic_upgrade()`
   - Fallback: `run_migrations()` (runner manuale legacy)
7. Bootstrap telemetria, atexit cleanup

---

## 6. Database — Schema multi-bind

YSocial usa due database distinti, gestiti con `SQLALCHEMY_BINDS`:

| Bind key | File (SQLite) | Contenuto |
|----------|--------------|-----------|
| `db_admin` (default) | `y_web/db/dashboard.db` | Utenti admin, esperimenti, popolazioni, agenti, client, configurazioni |
| `db_exp` | `y_web/experiments/<UUID>/database_server.db` | Dati runtime dell'esperimento: post, follow, hashtag, reazioni, opinioni, ecc. |

**DB Admin** (`src/models/admin.py` — 37 modelli):
Gestione infrastruttura: `Admin_users`, `Exps`, `ExperimentScheduleGroup/Item/Status/Log`, `Population`, `Agent`, `Agent_Ext`, `Agent_Custom_Feature`, `Agent_Population`, `Agent_Profile`, `Page`, `Client`, `Client_Execution`, `ForumRssFeedResource`, `ForumImageFeedResource`, `Jupyter_instances`, `ReleaseInfo`, `BlogPost`, `LogFileOffset`, `ServerLogMetrics`, `ClientLogMetrics`, `HpcMonitorSettings`, `WatchdogSettings`, `OpinionGroup`, `OpinionDistribution`, `OpinionEvolutionCache`, `OpinionEvolutionSampledAgents`, `AdminInterviewSession`, `AdminInterviewMessage`, ecc.

**DB Experiment** (`src/models/experiment.py` — 29 modelli):
Dati sociali simulati: `User_mgmt`, `Post`, `Hashtags`, `Emotions`, `Post_emotions`, `Post_hashtags`, `Mentions`, `ReplyInboxState`, `ForumChatSession`, `ForumChatMessage`, `Reactions`, `Follow`, `Rounds`, `Recommendations`, `SysMessage`, `Reported`, `Articles`, `Websites`, `Voting`, `Interests`, `User_interest`, `Post_topics`, `Images`, `ImagePosts`, `Article_topics`, `Post_Sentiment`, `Post_Toxicity`, `Agent_Opinion`, `StressReward`.

**DB Config** (`src/models/config.py` — 14 modelli, bind `db_admin`):
Tabelle di configurazione condivise: `Profession`, `Nationalities`, `Education`, `Leanings`, `Languages`, `Toxicity_Levels`, `AgeClass`, `Content_Recsys`, `Follow_Recsys`, `Topic_List`, `Exp_Topic`, `Page_Topic`, `ActivityProfile`, `PopulationActivityProfile`.

### Migrazioni

- **Sistema corrente**: Flask-Migrate / Alembic (`y_web/alembic/`). Revisione baseline `0001_baseline` (no-op). Auto-stamp dei DB pre-Alembic al primo avvio.
- **Sistema legacy** (`y_web/db_init/migrations.py`): 31 script incrementali, mantenuto come fallback se Flask-Migrate non è installato.
- **Schema di riferimento** (`data_schema/`): dump SQLite e PostgreSQL dello stato iniziale; 4 migration SQL documentate.

---

## 7. Blueprint e routing

17 blueprint registrati tramite `y_web/routes/__init__.py`:

| Blueprint | Prefix | Funzione |
|-----------|--------|----------|
| `auth` | `/` | Login, logout, selezione esperimento |
| `main` | `/` | Viste piattaforme social (microblogging, forum, photo) |
| `user` (user_actions) | `/` | Follow, post, reazioni, interazioni utente |
| `admin` | `/admin` | Dashboard principale ricercatore |
| `experiments` | `/admin/experiments` | CRUD esperimenti, scheduling, HPC, opinion config |
| `clientsr` | `/admin/clients` | CRUD client, dettagli, esecuzione, recsys |
| `population` | `/admin/populations` | Gestione popolazioni di agenti |
| `agents` | `/admin/agents` | Gestione agenti |
| `pages` | `/admin/pages` | Gestione pagine (agenti istituzionali) |
| `users` | `/admin/users` | Gestione utenti admin |
| `ollama` | `/admin/ollama` | Gestione modelli Ollama |
| `lab` | `/admin/jupyter` | Integrazione JupyterLab |
| `tutorial` | `/admin/tutorial` | Wizard tutorial |
| `errors` | — | Handler 400/403/404/500 |
| `api_reddit` | `/api/reddit` | API compatibilità Reddit |
| `api_social` | `/api` | API REST core (agenti, post, follow) |
| `api_interview` | `/api/interview` | API per interviste agli agenti via LLM |

---

## 8. Logica di dominio (`y_web/src/`)

12 package indipendenti (~26K LOC):

| Package | Contenuto |
|---------|-----------|
| `agents/` | Gestione popolazioni (`population.py`), piattaforme (`platform.py`), feature custom (`custom_features.py`) |
| `content/` | Estrazione articoli, avatar, cover image, feed RSS, utilità testo |
| `data_access/` | Query DB per post, profili, trend, utenti (layer DAL) |
| `experiment/` | Accesso esperimento, clock simulazione, contesto, helpers, schema, schedule monitor |
| `external_runtime/` | Manager e registry per runtime esterni (HPC, vLLM) |
| `forum/` | Azioni forum (media, post, reazioni), hot rank, servizi (formatter, query, data class) |
| `hpc/` | Client HPC, parser/sync log, log metrics, backup popolazioni, server HPC |
| `llm/` | Compatibilità AutoGen, content annotation, image annotator, manager Ollama/vLLM, URL summarizer |
| `models/` | Modelli ORM (admin, config, experiment) |
| `recsys/` | Recommendation system (content-based, follow-based) |
| `simulation/` | Runner client/server, process registry, watchdog, execution backend, port manager, subprocess env |
| `system/` | Utilità path, check release/blog, desktop file handler, Jupyter utils, model cache |
| `telemetry/` | Raccolta e invio dati di utilizzo |

---

## 9. Modalità di esecuzione simulazione

| Modalità | Backend | Descrizione |
|----------|---------|-------------|
| **Locale** | subprocess Python | Client lanciati come sottoprocessi sul server YWeb. Default per sviluppo e uso desktop. |
| **HPC** | Ray (cluster) | Agenti distribuiti su cluster via Ray. Configurazione separata per ogni client. Sincronizzazione log via polling. |
| **Ad-hoc** | subprocess isolato | Singolo client avviato manualmente per test o debug. |
| **Desktop** | PyInstaller + pywebview | Bundle standalone (.app/.exe) con UI nativa. DB in path scrivibile separato. |

---

## 10. YClient (submodule)

`external/YClient/` — libreria Python per la simulazione degli agenti, pubblicata separatamente come package `yclient`.

Struttura principale:
- `y_client/classes/` — `base_agent.py`, `page_agent.py`, `fake_base_agent.py`, `fake_page_agent.py`, `time.py`
- `y_client/clients/` — `client_base.py`, `client_web.py`, `client_with_pages.py`
- `y_client/recsys/` — recommendation systems lato client

Il client comunica con YWeb via API REST (`api_social`, `api_reddit`). Ogni agente è un'istanza della classe `Agent` (o `PageAgent` per pagine istituzionali) che esegue azioni sociali (post, follow, react, ecc.) secondo un profilo demografico e LLM configurato.

---

## 11. Test suite

| Metrica | Valore |
|---------|--------|
| File di test | 169 |
| LOC test | ~39.000 |
| Framework | pytest |
| Copertura | pytest-cov → Codecov |
| Python CI | 3.10 (Ubuntu, GitHub Actions) |
| DB in test | `sqlite:///:memory:` (TestingConfig) |

Test organizzati per area: `test_phase*` (audit struttura moduli), `test_hpc_*` (HPC), `test_forum_*` (forum), `test_admin_*` (dashboard), ecc. Il file `_sa2_stubs.py` fornisce shim centralizzato per compatibilità SQLAlchemy 2.x nei mock di test.

`conftest.py` include un meccanismo di remapping dei path legacy (`/Users/rossetti/PycharmProjects/YWeb`) per garantire portabilità dei test.

---

## 12. Frontend

| Asset | Quantità |
|-------|---------|
| Template HTML | 118 |
| File JavaScript | 97 |
| File CSS | 32 |
| Immagini / SVG | ~10.400 |

Template organizzati in 7 directory: `admin/`, `error_pages/`, `forum/`, `login/`, `microblogging/`, `photo/`, `shared/`. Rendering server-side con Jinja2. Nessun framework JS moderno (Vue/React); JS vanilla + librerie esterne incluse staticamente.

---

## 13. CI/CD e deployment

**GitHub Actions** (`.github/workflows/`):
- `ci-tests.yml` — push/PR: install, pytest con coverage, upload Codecov
- `build-executables.yml` — build binari PyInstaller (macOS, Windows, Linux)
- `release_package.yml` — pubblicazione release
- `format-code.yml` — isort + black (auto-commit con `[skip ci]`)

**Docker** (`deployment/docker/`):
- Base: Ubuntu + Python 3 + Ollama
- Varianti: SQLite, PostgreSQL, GPU (CUDA), reverse proxy nginx
- Docker Compose per orchestrazione multi-container

**Configurazione runtime** via variabili d'ambiente:

| Variabile | Uso |
|-----------|-----|
| `YSOCIAL_SECRET_KEY` | Flask secret key (obbligatoria in produzione) |
| `FLASK_ENV` | Selezione config (development/testing/production) |
| `PG_HOST/PORT/DBNAME/USER/PASSWORD` | Connessione PostgreSQL |
| `DATABASE_URL` | URI database alternativo |

---

## 14. Dipendenze principali

Gestite con **pip-tools** (`requirements/base.in` → `base.txt`):

| Categoria | Librerie principali |
|-----------|-------------------|
| Web | Flask 3.x, Flask-Login, Flask-SQLAlchemy, Flask-WTF, Flask-Migrate, Werkzeug |
| Database | SQLAlchemy 2.x, sqlalchemy_utils, psycopg2-binary |
| LLM | langchain ≥0.3, langchain-ollama, langchain-openai, ollama |
| Distribuzione | Ray[default] ≥2.0, redis |
| NLP/ML | nltk, detoxify, perspective |
| Utilità | requests, tqdm, numpy, networkx, faker, feedparser, psutil, colorama |
| Desktop | pywebview, gunicorn, gevent |
| Interni | ysights, yclient-memory |

---

## 15. Stato del codebase (branch `fix/critical-issues`)

Rispetto a `main`, il branch corrente incorpora le seguenti correzioni e miglioramenti:

| Commit | Modifica |
|--------|---------|
| `69c766b9` | C1: rimozione SECRET_KEY hardcoded → `$YSOCIAL_SECRET_KEY` |
| `53b518c6` | C2: `.gitignore` rafforzato per DB runtime (*.db, WAL, FUSE) |
| `8b3bad6f` | Fix Python <3.10: `from __future__ import annotations` in `config.py` |
| `9cf5090f` | Fix `helpers.py`: `Path(get_writable_path()) / "y_web"` |
| `d7981a38` | C4: shim SA2 centralizzato in `tests/_sa2_stubs.py` |
| `607b858f` | C8: config centralizzata in `y_web/config.py` |
| `e9714424` | C9: lock dipendenze con struttura pip-tools |
| `6f38891d` | C3: integrazione Flask-Migrate/Alembic |
| `ebc49b66` | C3: auto-stamp DB pre-Alembic al primo avvio |

---

## 16. Aree di attenzione residue

| Area | Nota |
|------|------|
| **Branch stale** | Rimossi localmente. Pulizia remota (`origin/copilot/*`) ancora da eseguire. |
| **Alembic multi-bind** | La configurazione Alembic corrente gestisce un solo bind. La migrazione di `db_exp` (per-esperimento, UUID-based) richiederà una strategia separata quando verranno introdotte nuove colonne nel DB esperimento. |
| **conftest.py path hardcoded** | `_LEGACY_ROOT = Path("/Users/rossetti/PycharmProjects/YWeb")` — residuo di sviluppo locale, non critico ma da rimuovere. |
| **CI Python version** | CI usa Python 3.10, il codebase dichiara compatibilità ≥3.9. Il fix `from __future__ import annotations` è stato necessario per Python 3.9. Verificare copertura su 3.9. |
| **Static assets volume** | ~10.400 immagini in `y_web/static/` rendono il repository pesante. Candidati a gitignore o LFS se la dimensione diventa problematica. |

---

*Documento aggiornato il 4 settembre 2026 — analisi eseguita su branch `fix/critical-issues` (commit `ebc49b66`).*
