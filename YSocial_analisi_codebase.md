# YSocial – Analisi della Codebase

> Documento generato il 2 settembre 2026  
> Analista: Claude (Cowork) su richiesta di Giulio Rossetti

---

## 1. Descrizione del Progetto

**Y Social** è un **Digital Twin di piattaforme di social media**, alimentato da LLM (Large Language Model), progettato per condurre simulazioni sociali in un ambiente *zero-code*. Il progetto è sviluppato nell'ambito della ricerca accademica (CNR / SoBigData++) e accompagnato da una pubblicazione su arXiv (arXiv:2408.00818).

L'obiettivo centrale è replicare le dinamiche di una piattaforma social (simile a X/Twitter o Reddit) popolata da agenti AI configurabili, permettendo a ricercatori di studiare comportamenti emergenti, diffusione di informazioni, polarizzazione e altri fenomeni sociali in ambiente controllato.

### 1.1 Stack Tecnologico

| Layer | Tecnologia |
|---|---|
| Backend web | Flask 2.1.2, Flask-Login, Flask-SQLAlchemy |
| Database | SQLite (default) / PostgreSQL (via SQLAlchemy) |
| AI / LLM | LangChain, Ollama, vLLM, API OpenAI-compatible |
| Analisi testo | NLTK (VADER sentiment), Perspective API (tossicità), Detoxify |
| Simulazione | Autogen (multi-agent), Ray (distributed computing) |
| Network analysis | NetworkX |
| Frontend | Template Friendkit (Jinja2), HTML/CSS/JS |
| Packaging | PyInstaller (eseguibili standalone), Docker, gunicorn+gevent |
| Analisi dati | JupyterLab integrato + libreria ySights |
| Notifiche/caching | Redis |

### 1.2 Struttura delle Directory Principali

```
YWeb/
├── y_social.py              # Entry point principale (browser mode)
├── y_social_launcher.py     # Launcher (desktop + browser mode)
├── requirements.txt
├── Dockerfile
├── deployment/              # Docker Compose, configurazioni deploy
├── y_web/                   # Applicazione Flask principale
│   ├── __init__.py          # App factory, lifecycle, compat shim
│   ├── db/                  # Definizioni DB aggiuntive
│   ├── db_init/             # Inizializzazione e migrazioni DB
│   ├── experiments/         # Logica degli esperimenti
│   ├── migrations/          # Schema migrations
│   ├── routes/              # Blueprint Flask
│   │   ├── admin/           # Pannello amministrativo
│   │   ├── api/             # API REST interne
│   │   ├── auth/            # Autenticazione
│   │   ├── errors/          # Gestione errori HTTP
│   │   ├── interactions/    # Interazioni social (like, share, commenti)
│   │   └── social/          # Feed, timeline, profili
│   ├── src/                 # Logica di business
│   │   ├── agents/          # Gestione agenti AI
│   │   ├── content/         # Gestione contenuti
│   │   ├── data_access/     # Layer di accesso ai dati
│   │   ├── experiment/      # Contesto e ciclo di vita esperimenti
│   │   ├── external_runtime/ # Runtime esterni (YClient, YServer, ecc.)
│   │   ├── forum/           # Modalità forum (Reddit-like)
│   │   ├── hpc/             # Supporto High Performance Computing
│   │   ├── llm/             # Integrazione LLM
│   │   ├── models/          # Modelli SQLAlchemy
│   │   ├── recsys/          # Sistemi di raccomandazione
│   │   ├── simulation/      # Orchestrazione simulazioni
│   │   ├── system/          # Utilità di sistema (Jupyter, processi)
│   │   └── telemetry/       # Logging eventi
│   ├── pyinstaller_utils/   # Utilities per packaging standalone
│   ├── static/              # Asset statici (JS, CSS, immagini)
│   └── templates/           # Template Jinja2
├── external/                # Runtime esterni clonati separatamente
├── data_schema/             # Schemi dati
├── docs/                    # Documentazione
└── scripts/                 # Script di utilità
```

---

## 2. Architettura

YSocial segue un'architettura **monolitica modulare** costruita attorno al pattern *Application Factory* di Flask. La separazione tra layer è discreta ma non rigida: la logica di business (`src/`) è sufficientemente distinta dalle route HTTP, mentre l'accesso ai dati avviene prevalentemente tramite SQLAlchemy direttamente nei route handler o in moduli helper.

### 2.1 Componenti Chiave

**App Factory (`create_app`)** — Inizializza Flask, configura il DB, registra i blueprint, imposta i context processor e avvia i background scheduler (log sync, experiment schedule monitor). La funzione è già abbastanza corposa (~350 righe) e incorporate molte responsabilità.

**Gestione Esperimenti** — Il sistema gestisce "esperimenti" come entità di primo livello: ogni esperimento ha il proprio stato (0=inattivo, 1=attivo), processi figli, istanza JupyterLab dedicata e potenzialmente database separato. Il contesto dell'esperimento attivo viene propagato via `before_request` / `teardown_request`.

**Agenti AI** — Gli agenti sono entità configurabili con tratti demografici, personalità, comportamenti e sistemi di raccomandazione personalizzati. Interagiscono con LLM tramite backend intercambiabili (Ollama, vLLM, OpenAI-compatible).

**Runtime Esterni** — YClient, YServer e varianti (Reddit, PhotoSharing, Simulator) sono processi separati clonati in `external/`. La comunicazione avviene tramite subprocess management e probabilmente file/socket locali.

---

## 3. Punti di Forza

- **Ampiezza funzionale notevole**: il progetto copre in modo coerente tutto il ciclo di vita di una simulazione social, dall'onboarding degli agenti fino all'analisi dei dati con JupyterLab.
- **Flessibilità dei backend LLM**: l'astrazione su Ollama/vLLM/OpenAI-compatible consente di operare sia in locale che in cloud.
- **Distribuzione accessibile**: il packaging tramite PyInstaller (eseguibili standalone per Linux/Mac/Windows) abbassa notevolmente la barriera d'ingresso per utenti non tecnici.
- **Supporto multi-database**: SQLite per sviluppo/uso locale, PostgreSQL per ambienti più robusti.
- **Documentazione buona**: README dettagliato, mkdocs configurato, paper di riferimento.
- **CI configurata**: presenza di GitHub Actions per i test.
- **Telemetria basilare**: logging eventi di start/stop per il monitoring.

---

## 4. Problemi Identificati e Punti di Miglioramento

### 4.1 Sicurezza 🔴 Critico

**SECRET_KEY hardcoded**
```python
# y_web/__init__.py riga 252
app.config["SECRET_KEY"] = "4323432nldsf"
```
La chiave segreta Flask è hardcoded nel sorgente. Chiunque acceda al codice può forgiare cookie di sessione. Va letta obbligatoriamente da variabile d'ambiente o da un secrets manager, con validazione all'avvio.

**Credenziali admin di default**
Il README documenta esplicitamente `admin@y-not.social` / `admin` come credenziali predefinite. Non esiste, a quanto risulta dall'analisi, un meccanismo di forzatura del cambio password al primo accesso. Questo è un rischio elevato per qualsiasi deploy non strettamente locale.

**Jupyter Lab aperto di default**
JupyterLab viene avviato per default senza autenticazione aggiuntiva oltre a quella di YSocial. In ambienti non localhost questo espone un'interfaccia di esecuzione di codice arbitrario. Il flag `--no_notebook` dovrebbe essere la modalità predefinita per i deploy non di ricerca.

**Token/API key in variabili d'ambiente senza validazione**
LLM_BACKEND e LLM_URL vengono impostati come `os.environ` senza sanificazione. Una URL malevola potrebbe causare SSRF (Server-Side Request Forgery).

---

### 4.2 Dipendenze e Compatibilità 🟠 Alto

**Shim di compatibilità SQLAlchemy manuale e fragile**
Il file `__init__.py` contiene un blocco `_ensure_flask_sqlalchemy_legacy_compat()` di ~80 righe che applica patch runtime a SQLAlchemy e Flask-SQLAlchemy per gestire l'incompatibilità tra Flask-SQLAlchemy 2.x e SQLAlchemy 2.x. Questo shim è:
- Difficile da mantenere
- Potenzialmente rotto da aggiornamenti minori
- Un segnale che le versioni delle dipendenze sono bloccate su versioni vecchie

La soluzione strutturale è aggiornare Flask-SQLAlchemy a `>=3.0` (compatibile con SQLAlchemy 2.x) e rimuovere lo shim.

**Versioni molto datate nel requirements.txt**
```
Flask==2.1.2          # Aprile 2022; attuale: 3.x
Flask-SQLAlchemy==2.5.1  # 2021; attuale: 3.x
SQLAlchemy>=1.4.31,<2.0.0  # Bloccato prima della 2.x
Werkzeug==2.1.2       # 2022
WTForms==2.3.3        # 2020
```
Versioni così vecchie comportano la mancanza di patch di sicurezza e incompatibilità crescenti con il resto dell'ecosistema Python.

**File artefatto `=1.4.31,`**
Nella root del progetto esiste un file chiamato letteralmente `=1.4.31,` (size 0). È quasi certamente il risultato di un `pip install "SQLAlchemy>=1.4.31,<2.0.0"` eseguito senza virgolette nella shell, che ha creato un file invece di installare il pacchetto. Va rimosso.

**Dipendenze AI pesanti non opzionali**
`ray[default]`, `redis`, `langchain*`, `jupyterlab`, `gunicorn`, `gevent` sono tutte nel requirements.txt principale. Per un'installazione leggera (solo simulazione locale) non è necessario tutto questo. Si consiglia di separare in `requirements-minimal.txt` e `requirements-full.txt` o usare extras di pyproject.toml.

---

### 4.3 Architettura e Design 🟠 Alto

**`create_app()` troppo grande**
La funzione `create_app` in `__init__.py` supera le 350 righe e svolge molteplici responsabilità: configurazione DB, registrazione blueprint, context processor (7 funzioni inline), filtri Jinja2, migrazioni, telemetria, scheduler. Andrebbero estratti in moduli dedicati (es. `context_processors.py`, `filters.py`, `startup.py`).

**Runtime esterni accoppiati tramite filesystem**
YClient/YServer/YSimulator sono processi separati gestiti come subprocessi. Questo rende il deploy complesso (multipli git clone nella directory `external/`) e la gestione degli errori opaca. Un approccio più moderno potrebbe prevedere comunicazione via REST/gRPC con health-check espliciti, o un orchestratore (Celery, Ray tasks).

**SQLite in modalità `threaded=False`**
```python
# y_social.py
if db_type.lower() == "sqlite":
    app.run(debug=debug, host=host, port=port, threaded=False)
```
Disabilitare il threading per evitare i problemi di locking di SQLite è una scelta pragmatica ma limita pesantemente la concorrenza. Non è adatto a simulazioni con molti agenti che scrivono simultaneamente. Andrebbe almeno documentato come limitazione e suggerito WAL mode (`PRAGMA journal_mode=WAL`).

**Nessun task queue per operazioni asincrone**
Operazioni potenzialmente lunghe (annotazione LLM, RSS parsing, avvio JupyterLab) sembrano essere eseguite in-process o in thread ad hoc. Un sistema come Celery o Ray Tasks darebbe visibilità, retry, e non blocker le richieste HTTP.

---

### 4.4 Qualità del Codice 🟡 Medio

**`except Exception: pass` diffuso**
Nell'`__init__.py` e in molti altri punti del codice si trovano blocchi `except Exception: pass` o `except Exception as e: print(...)`. Questo nasconde errori silenziosamente. I fallback dovrebbero almeno loggare con il modulo `logging` a livello WARNING/ERROR.

**Uso misto di `print()` e logging**
Il codice alterna `print(...)` e il modulo `logging`. In produzione, i print non sono strutturati, non hanno livelli di severità e non si integrano con sistemi di log aggregation. Andrebbe standardizzato l'uso di `logging` con handler configurabili.

**Bare `except` nei context processor**
I context processor (es. `inject_feed_home_url`, `inject_active_experiments`) avvolgono tutta la logica in `try/except Exception` restituendo valori di default in caso di qualsiasi errore. Questo può mascherare bug di logica che non verrebbero mai riportati.

**`SEND_FILE_MAX_AGE_DEFAULT = 0`**
Il caching degli asset statici è disabilitato globalmente:
```python
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
```
Questo è pensato per lo sviluppo ma è rimasto in produzione. In deploy con molti utenti, ogni richiesta al browser ricarica tutti gli asset statici (JS, CSS, immagini).

**`TEMPLATES_AUTO_RELOAD = True` sempre abilitato**
Flask controlla la data di modifica di ogni template ad ogni richiesta. In produzione, questo spreca I/O.

---

### 4.5 Testing 🟡 Medio

**Copertura test non valutabile dall'esterno**
Il progetto ha `pytest.ini`, `run_tests.py` e una directory `y_web/tests/`, segnale positivo. Tuttavia, la struttura dei test non è esplorabile senza accesso completo. La CI su GitHub Actions è presente ma andrebbe verificato se copre anche i path di integrazione (DB, LLM mock, simulazioni).

**Test con database reale**
Se i test usano SQLite senza mock del DB, l'isolamento potrebbe essere insufficiente e i test potrebbero interferire tra loro o dipendere dall'ordine di esecuzione.

---

### 4.6 Deploy e Configurazione 🟡 Medio

**Nessuna gestione di secrets in produzione**
Non è presente nessun meccanismo per gestire secrets in modo sicuro (`.env` con `python-dotenv`, Vault, AWS Secrets Manager, ecc.). Le configurazioni sensibili (chiave segreta, credenziali DB PostgreSQL, API key Perspective) devono essere gestite tramite variabili d'ambiente documentate.

**Docker Compose non include health check**
Dal README il Docker Compose avvia Ollama, YServer/YClient e YSocial, ma non è chiaro se ci siano health check tra i servizi. YSocial esegue già un controllo al boot per il LLM backend, ma questo potrebbe fallire se Ollama non è ancora pronto al momento dell'avvio.

**`gunicorn` nel requirements ma Flask viene avviato con `app.run()`**
In produzione il server Flask built-in non è adatto. Il file `requirements.txt` include `gunicorn` e `gevent`, ma l'entry point `y_social.py` usa `app.run()`. Non è chiaro se esista documentazione su come avviare in modalità produzione con gunicorn.

---

## 5. Riepilogo delle Priorità

| Priorità | Area | Intervento |
|---|---|---|
| 🔴 Critico | Sicurezza | Esternalizzare `SECRET_KEY` in env var |
| 🔴 Critico | Sicurezza | Forzare cambio password admin al primo accesso |
| 🔴 Critico | Sicurezza | Disabilitare JupyterLab di default in produzione |
| 🟠 Alto | Dipendenze | Aggiornare Flask, Flask-SQLAlchemy, SQLAlchemy e rimuovere shim |
| 🟠 Alto | Dipendenze | Eliminare file `=1.4.31,` dalla root |
| 🟠 Alto | Architettura | Refactoring `create_app()` in moduli separati |
| 🟠 Alto | Performance | Abilitare SQLite WAL mode; documentare limiti concorrenza |
| 🟡 Medio | Qualità | Sostituire `print()` con `logging` strutturato |
| 🟡 Medio | Qualità | Rimuovere `except Exception: pass` silenziosi |
| 🟡 Medio | Deploy | Disabilitare `SEND_FILE_MAX_AGE_DEFAULT=0` e `TEMPLATES_AUTO_RELOAD` in produzione |
| 🟡 Medio | Deploy | Documentare avvio con gunicorn per produzione |
| 🟢 Basso | Dipendenze | Separare requirements in minimal/full |
| 🟢 Basso | Testing | Aggiungere mock LLM e copertura integration test |

---

## 6. Conclusioni

YSocial è un progetto accademico maturo e funzionalmente ricco, con una visione chiara e un'implementazione che copre l'intero ciclo di vita di una simulazione social. La scelta di Flask come backbone è appropriata per la natura del progetto (prototipo di ricerca con interfaccia web), e l'architettura modulare è già sufficientemente strutturata.

I principali debiti tecnici si concentrano su tre aree: **sicurezza** (SECRET_KEY e credenziali hardcoded), **dipendenze datate** (stack Flask del 2021-2022 con shim di compatibilità manuale), e **configurazione production-ready** mancante (logging, caching, gestione secrets). 

Questi interventi, in larga parte circoscritti e non richiedenti riscritture architetturali, porterebbero il progetto a uno standard più solido per deployment in ambienti multi-utente e per contributi da parte della comunità open source.
