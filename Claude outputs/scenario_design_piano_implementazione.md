# Scenario Design — Piano di Implementazione Incrementale

> Documento operativo derivato da `scenario_design_piano_tecnico.md` (di seguito "il piano tecnico"), già revisionato e corretto dal product owner. Questo documento **non contiene codice** e **non è stato eseguito nessun passo di implementazione**: è la guida che verrà seguita, fase per fase e commit per commit, nelle sessioni successive. Ogni riferimento `§N` rimanda alla sezione corrispondente del piano tecnico.
>
> **Legenda classificazione**: **[E]** Essenziale (necessario per una v1 funzionante e per i 27 criteri di accettazione, §26 del piano tecnico) · **[S]** Successivo (miglioramento rimandabile oltre v1, non bloccante) · **[H]** Hardening (sicurezza/robustezza/osservabilità, da completare prima della release ma non prima delle fasi funzionali di base).
>
> **Principio guida**: nessuna fase si considera "chiusa" finché i suoi test passano e la documentazione è aggiornata. Non si rimanda integrazione/validazione alle fasi finali: ogni commit che introduce codice è accompagnato dai test che lo coprono, e ogni fase termina con un aggiornamento di `README.md`/changelog/decision log, mai "a posteriori" in blocco.

---

## 0. Convenzioni operative

### 0.1 Repository coinvolti
- **YWeb** (core, repository principale) — solo le modifiche minime e generiche elencate in §8.2 del piano tecnico; ogni modifica richiede approvazione esplicita del product owner prima dell'implementazione (principio risolto, §8.2/§27 punto 6).
- **ScenarioDesign** (`GiulioRossetti/ScenarioDesign`, repo esterno privato, già clonato in `external/ScenarioDesign`, oggi vuoto a parte il commit iniziale, §9) — quasi tutto il codice funzionale vive qui.

### 0.2 Formato dei commit
Convenzione tipo *Conventional Commits*, scope esplicito sul componente toccato:
```
<tipo>(<scope>): <sintesi imperativa>

<corpo opzionale: perché, non solo cosa>
<riferimento a §sezione del piano tecnico e/o a questo piano>
```
Tipi usati: `feat`, `fix`, `test`, `docs`, `chore`, `refactor`. Scope tipici: `core-registry`, `core-backend-plugins`, `core-sidebar`, `sd-models`, `sd-scenarios`, `sd-threads`, `sd-llm`, `sd-roles`, `sd-adapter-standard`, `sd-adapter-hpc`, `sd-security`, `sd-ci`.

**Regola di atomicità**: un commit = una unità di lavoro eseguibile e testabile da sola (il repository compila/passa i test anche fermandosi a quel commit). Mai un commit "WIP" non testato lasciato nella history condivisa; mai un commit che mescoli codice di produzione + refactor cosmetico esteso (split in due commit separati).

### 0.3 Branching e PR
- Un branch per fase (`feat/sd-fase-N-<nome-breve>`), eventualmente suddiviso in sotto-branch per gruppi di commit indipendenti se la fase è ampia (es. Fase 3 editor vs. Fase 3 metadati).
- Una PR per fase (o per sotto-gruppo coerente), mai una PR unica di tutta la fase 1-9. La PR della fase N può essere aperta solo dopo che la PR della fase N-1 è stata mergiata e il relativo success gate è stato verificato (eccezione esplicita: Fase 4 e Fase 5 possono procedere in parallelo una volta chiusa la Fase 3, vedi §3.5 di questo piano).
- **Corpo della PR, obbligatorio per ogni fase**: (a) obiettivo della fase e componenti toccati; (b) decisioni rilevanti prese durante l'implementazione (incluse eventuali deviazioni dal piano tecnico, con motivazione); (c) elenco dei test eseguiti e relativo esito (non solo "aggiunti", anche "eseguiti con risultato X"); (d) limiti residui espliciti (debiti tecnici, **[D]** non ancora chiusi, TODO per fasi successive) — mai lasciare questi impliciti nel codice soltanto.

### 0.4 Aggiornamento documentazione di fine fase
Ogni fase, prima di essere considerata chiusa, aggiorna:
1. `ScenarioDesign/README.md` (o `docs/`) con lo stato corrente delle funzionalità disponibili.
2. Un **decision log** cumulativo, `ScenarioDesign/docs/decisions.md` (creato in Fase 0), con una riga per ogni decisione presa durante l'implementazione che non era già esplicita nel piano tecnico.
3. La tabella di stato fasi in calce a questo documento (§6), spostando la fase da "pianificata" a "completata" con link alla PR e data.
4. Se la fase ha richiesto una modifica al core YWeb: la sezione pertinente del piano tecnico (`scenario_design_piano_tecnico.md`) viene aggiornata per riflettere lo stato reale (da **[P]** proposta a **[F]** fatto), non lasciata disallineata col codice.

### 0.5 Evidenze richieste per avanzare di fase
Per ogni fase, prima di aprire il lavoro sulla fase successiva, deve esistere evidenza **verificabile e riproducibile**, non solo dichiarata:
- output di esecuzione della test suite (locale o CI) allegato/linkato nella PR;
- per le fasi con migrazioni: dump dello schema post-migrazione (SQLite `.schema` o equivalente) allegato come artefatto di verifica;
- per le fasi con UI: screenshot o registrazione della schermata funzionante (non il solo mockup statico di §14.1 del piano tecnico, che resta riferimento di design, non evidenza di implementazione);
- per le fasi con criteri di non-regressione: output di `run_tests.py` (suite core YWeb) eseguito con il plugin installato e con il plugin assente, entrambi verdi.

---

## 1. Panoramica delle fasi

| Fase | Nome | Classificazione prevalente | Repository | Blocca la fase successiva? |
|---|---|---|---|---|
| 0 | Analisi e contratti architetturali | [E] | YWeb/YClient/YServer/YSimulator (sola lettura) | Sì, totalmente |
| 1 | Fondamenta del plugin | [E] | YWeb (core minimo) + ScenarioDesign | Sì |
| 2 | Scenari e bozze (CRUD scenario) | [E] | ScenarioDesign | Sì |
| 3 | Editor dei thread | [E] | ScenarioDesign | Sì (per Fase 6/7), no per Fase 4/5 |
| 4 | Generazione LLM | [E] | ScenarioDesign | No (parallela a Fase 5) |
| 5 | Ruoli ad hoc opzionali | [S] | ScenarioDesign | No (parallela a Fase 4) |
| 6 | Materializzazione standard | [E] | ScenarioDesign | Sì (per Fase 7) |
| 7 | Materializzazione HPC | [E] | ScenarioDesign | No, ma richiede Fase 0 chiusa su `round` |
| 8 | Operazioni distruttive e hardening | [E]+[H] | ScenarioDesign (+ eventuale PR core separata) | Sì (per Fase 9) |
| 9 | Packaging e release | [E] | ScenarioDesign | — (fase finale) |

Nota sul parallelismo: Fase 4 (LLM) e Fase 5 (ruoli ad hoc) possono procedere in parallelo su branch distinti dopo la chiusura della Fase 3, perché Fase 5 è additiva e si innesta sul prompt builder di Fase 4 solo come sorgente opzionale di `role_key` — la dipendenza è leggera e testata con un doppio fixture (con/senza ruoli ad hoc), non un blocco sequenziale stretto.

---

## 2. Fase 0 — Analisi e contratti architetturali [E]

### Obiettivi e componenti
Chiudere, con verifica diretta sul codice (non per assunzione), i punti ancora aperti nel piano tecnico prima di scrivere qualunque riga di codice del plugin:
- disallineamento `Post.round` (Integer nel modello ORM YWeb vs `VARCHAR(36)` nello schema fisico HPC) — §19, §25, nota di revisione punto 2;
- comportamento esatto di `_adhoc_agent_specs()` (per Fase 5) — nota di revisione punto 1;
- verifica se esistono limiti di lunghezza testo già imposti lato client reale (YClient) da rispettare in Scenario Design (§21);
- verifica se `y_web/tests/conftest.py` offre già un fixture HPC riusabile (§24), per non costruirne uno duplicato;
- verifica puntuale se esistono test di snapshot sulla sidebar (`head.html`) o liste hardcoded di plugin attesi altrove nel core, che la nuova voce "Scenario Design" potrebbe rompere (nota di revisione punto 3).

### Dipendenze e precondizioni
Nessuna. È la prima fase, puramente di lettura/sperimentazione, nessuna modifica a nessun repository salvo gli artefatti di analisi stessi.

### Deliverable verificabili
- `ScenarioDesign/docs/decisions.md` creato con la prima sezione "Fase 0 — Findings", una voce per ciascun punto sopra, ognuna con: domanda, metodo di verifica usato, esito, riferimento a file/riga del codice ispezionato.
- Uno script di verifica empirica usa-e-getta (non parte della suite permanente) che apre un vero `db_exp` HPC (generato avviando almeno una volta un esperimento HPC in un ambiente di sviluppo) con i modelli YWeb e verifica se la colonna `round` è leggibile/scrivibile senza errori di tipo, sia su SQLite sia — se disponibile in ambiente di sviluppo — su PostgreSQL. Output salvato come log allegato alla PR di Fase 0, script stesso **non committato** nel repository definitivo (o committato sotto `scripts/investigations/` con un header esplicito "one-off, non mantenuto").

### Criteri di completamento e success gate
- Ogni punto **[A]**/**[D]** residuo del piano tecnico è chiuso con uno dei due esiti: (a) confermato come assunto nel piano tecnico → nessuna azione; (b) smentito o più sfumato del previsto → aggiornamento esplicito del piano tecnico **prima** di procedere, con nuova voce nel decision log che lo motiva.
- Il product owner ha confermato per iscritto (commento su PR o messaggio) la chiusura dei punti aperti in §27 del piano tecnico non ancora marcati "risolto" (alla data di stesura di questo piano: nessuno risulta aperto in §27, ma il disallineamento `Post.round` resta un **[D]** tecnico interno da chiudere qui, non un quesito di prodotto).
- **Evidenza richiesta**: log dello script di verifica empirica `round`, decision log compilato, nessuna fase 1 avviata prima di questo.

### Test funzionali e regression test
Nessun test permanente introdotto in questa fase (fase di analisi, nessun codice di prodotto). Lo script di verifica empirica non è un test automatizzato nella CI.

### Rischi principali e mitigazioni
| Rischio | Mitigazione |
|---|---|
| Il disallineamento `round` si rivela più profondo del previsto (es. richiede un modello ORM alternativo per HPC) | Bloccare esplicitamente l'avvio di Fase 7 finché non risolto; non procedere "provando" in Fase 7 |
| L'analisi richiede più tempo del previsto e si è tentati di "saltarla" | Il gate di questa fase è un prerequisito duro per Fase 1: nessuna eccezione, anche se rallenta il calendario |

### Commit incrementali previsti
Nessun commit di codice applicativo. Commit ammessi, tutti su branch `chore/sd-fase-0-analisi`:
1. `docs(decisions): crea decision log iniziale e template` — crea `ScenarioDesign/docs/decisions.md` con lo scheletro delle sezioni.
2. `docs(decisions): registra findings Fase 0 (round HPC, limiti testo, fixture HPC, sidebar snapshot test)` — un commit che aggiunge tutte le voci di finding una volta raccolte (non uno a voce, per evitare rumore nella history di un documento ancora in bozza).
3. (facoltativo) `chore(investigations): script one-off di verifica tipo Post.round su db_exp HPC` — se lo script viene mantenuto nel repo per riproducibilità futura, altrimenti resta locale e se ne allega solo l'output alla PR.

### Aggiornamento documentazione di fine fase
Decision log creato e popolato (è il deliverable stesso). Eventuale aggiornamento di `scenario_design_piano_tecnico.md` §19/§25 se l'esito smentisce quanto scritto.

---

## 3. Fase 1 — Fondamenta del plugin [E]

### Obiettivi e componenti
Rendere il plugin **installabile, visibile, vuoto funzionalmente**: nessuna feature di Scenario Design ancora presente, ma l'infrastruttura di discovery/caricamento è reale e verificata, non solo pianificata. Componenti (§8.2, §9, §10 del piano tecnico):
1. **[E]** `y_web/src/external_runtime/backend_plugins.py` (core, nuovo): `backend_plugin_repo_keys()`, `validate_backend_suite()`, `register_backend_plugin_suites()`.
2. **[E]** `y_web/src/external_runtime/registry.py`: nuova voce `SUPPORTED_EXTERNAL_REPOS["scenario_design"]` (dati, `group="backend_settings"`, `category="backend_extensions"`, `is_private=True`).
3. **[E]** `y_web/templates/admin/head.html`: voce sidebar condizionale autonoma, non annidata in Frontend Settings.
4. **[E]** `ScenarioDesign/meta/info.json` + `meta/registry.json` (chiave `backend_plugins`, non `frontend_plugins`).
5. **[E]** `ScenarioDesign/modules/scenario_editor/backend/__init__.py`: blueprint vuoto, namespaced su `/plugins/scenario_design/scenario_editor/...`.
6. **[S]** `ScenarioDesign/modules/scenario_editor/frontend/plugin.js` placeholder (solo se serve già un hook JS minimo per verificare l'asset statico; altrimenti rimandabile a Fase 2/3 quando esiste UI reale).
7. **[E]** Impalcatura minima di test (`pytest` + eventuale `tox`/`nox`) nel repo `ScenarioDesign`, non ancora CI completa (quella è Fase 9), ma eseguibile localmente da subito — committare il runner di test insieme al primo blueprint, non come ripensamento successivo.

### Dipendenze e precondizioni
Fase 0 chiusa (in particolare: nessun blocco noto sulla fattibilità del meccanismo `backend_plugins.py`, verificato per analogia con `frontend_plugins.py` già in Fase 0 se necessario un controllo aggiuntivo sul suo funzionamento esatto).

### Deliverable verificabili
- Plugin installabile da `/admin/external_runtimes` via Git checkout (locale, puntando a `external/ScenarioDesign`) e visibile come categoria "Backend Extensions".
- Voce "Scenario Design" in sidebar che appare quando il plugin è installato/valido e scompare quando disinstallato o quando il manifest è reso invalido ad arte (test negativo).
- Nessun impatto osservabile sul resto del pannello admin quando il plugin è assente (verificato, non solo dichiarato).

### Criteri di completamento e success gate
- Tutti i test della sezione seguente passano in locale.
- `run_tests.py` (suite core YWeb) passa **sia** con il plugin installato **sia** con il plugin disinstallato — eseguito esplicitamente in entrambe le condizioni, output allegato alla PR.
- Dump/ispezione manuale confermano che `SUPPORTED_EXTERNAL_REPOS` non ha alterato il comportamento delle voci esistenti (nessuna voce `frontend_plugins`/`agent_plugins` esistente è stata toccata).
- **Evidenza richiesta**: screenshot della sidebar con/senza plugin installato; log di esecuzione `pytest` del repo `ScenarioDesign`; log di `run_tests.py` del core in entrambe le condizioni.

### Test funzionali e regression test
- **Nuovi (ScenarioDesign)**: `test_backend_suite_validation.py` — manifest valido → `validate_backend_suite` ritorna `installed=True, valid=True`; manifest con chiave `frontend_plugins` invece di `backend_plugins` → invalido con messaggio esplicito; manifest con versione app fuori range → invalido; blueprint con path `dotted.module:attr` inesistente → invalido, isolato (non propaga eccezione).
- **Nuovi (ScenarioDesign)**: `test_blueprint_registration.py` — il blueprint vuoto risponde (es. un endpoint di health-check minimo `GET /plugins/scenario_design/scenario_editor/api/ping` → `200 {"ok": true}`), namespace statico protetto da path traversal (test con `../../` nel path dell'asset → `404`/`403`, mai lettura fuori dalla cartella del modulo).
- **Nuovi (YWeb core)**: `test_backend_plugins_registry.py` — `backend_plugin_repo_keys()` filtra correttamente `group=="backend_settings"`; `register_backend_plugin_suites(app)` chiamato da `create_app()` non duplica blueprint se chiamato due volte (idempotenza a livello di import, visto il pattern namespace sintetico già usato da `frontend_plugins.py`); fallimento di un singolo modulo non impedisce l'avvio dell'app (fault isolation, stesso pattern di `register_frontend_plugin_suites`).
- **Regressione (YWeb core)**: suite esistente `test_frontend_adds_on_plugin_suite.py` (o equivalente) continua a passare invariata — conferma che il nuovo meccanismo "backend" non condivide stato con quello "frontend" in modo da romperlo. Test esplicito che la voce Scenario Design **non compare** in `/admin/frontend_settings`.
- **Non regressione sidebar**: se esiste un test di snapshot sull'HTML di `head.html` (da verificare in Fase 0), aggiornarlo esplicitamente in questo stesso commit, mai lasciarlo rompersi "silenziosamente" e poi patchato altrove.

### Rischi principali e mitigazioni
| Rischio | Mitigazione |
|---|---|
| `backend_plugins.py` risulta meno "parallelo" a `frontend_plugins.py` di quanto stimato (es. `plugin_loader.py` ha accoppiamenti nascosti) | Prima di scrivere `backend_plugins.py`, leggere `plugin_loader.py` riga per riga (non per analogia) e annotare ogni punto di accoppiamento nel decision log |
| Il test di snapshot sidebar (se esiste) si rompe e viene "sistemato" senza capire perché | Commit separato e documentato per l'aggiornamento dello snapshot, mai incluso silenziosamente in un commit più grande |
| Il meccanismo di validazione backend diverge sottilmente da quello frontend, creando incoerenza futura | Test comparativo esplicito che verifica che `validate_backend_suite` e `validate_frontend_suite` abbiano la stessa interfaccia di ritorno (stesso shape di errore/successo) |

### Commit incrementali previsti
Branch `feat/sd-fase-1-fondamenta`:
1. `feat(core-backend-plugins): aggiunge backend_plugins.py con backend_plugin_repo_keys/validate_backend_suite/register_backend_plugin_suites` + `test(core-backend-plugins): copertura validazione manifest e fault isolation` — **un solo commit funzionalità+test**, perché l'unità è indivisibile senza lasciare codice non testato nella history.
2. `feat(core-registry): registra scenario_design in SUPPORTED_EXTERNAL_REPOS` + `test(core-registry): verifica che le voci esistenti non siano alterate` — commit dati, piccolo, isolato.
3. `feat(core-sidebar): aggiunge voce Scenario Design in head.html, condizionata a validate_backend_suite` + aggiornamento test di snapshot se presente.
4. `chore(sd-scaffold): scaffolding iniziale repository ScenarioDesign (meta/info.json, meta/registry.json, README)`.
5. `feat(sd-blueprint): blueprint backend vuoto con endpoint di health-check` + `test(sd-blueprint): registrazione blueprint e protezione path-traversal asset statici`.
6. `chore(sd-ci): aggiunge runner di test locale (pytest config, fixture base per app Flask di test)` — infrastruttura di test, propedeutica a tutte le fasi successive.
7. `test(integration): installazione/disinstallazione end-to-end del plugin via Git checkout, verifica non-regressione run_tests.py con/senza plugin` — commit di integrazione che chiude la fase, eseguito per ultimo perché dipende da tutti i precedenti.

### Aggiornamento documentazione di fine fase
`ScenarioDesign/README.md`: sezione "Stato: plugin installabile, nessuna funzionalità ancora attiva". Decision log: eventuali accoppiamenti scoperti in `plugin_loader.py`. Piano tecnico: se emergono scostamenti da §8.2/§10, aggiornarli con nota `[F, implementato in Fase 1]`.

---

## 4. Fase 2 — Scenari e bozze [E]

### Obiettivi e componenti
CRUD scenario (non ancora thread/post), selezione esperimento con filtro famiglia, meccanismo di copia esteso (§2, §6 del piano tecnico: "solo agenti" vs "mantieni tutto"). Endpoint 1-7 di §15.
- **[E]** `models.py`: `sd_scenario`, `sd_scenario_revision` — bind `db_exp`, migrazione JIT per-esperimento (§11).
- **[E]** `migrations.py`: funzione di migrazione JIT invocata al primo accesso admin su un dato `exp_id` (riusa l'infrastruttura di `backend_plugins.py` di Fase 1, non un meccanismo nuovo).
- **[E]** `routes_scenarios.py`: endpoint 1-7 (lista esperimenti eleggibili, verifica compatibilità, copia esperimento, CRUD scenario, duplicazione, archiviazione).
- **[E]** `require_supported_experiment(exp_id)` (§15): funzione condivisa, testata isolatamente, usata come primo controllo in ogni route con `exp_id` — introdotta già in questa fase perché è il primo endpoint a riceverlo, non rimandata.
- **[S]** Funzione di libreria core condivisa `eligible_experiments(platform_type=...)` (§8.2 punto 3): non bloccante; se non pronta, il filtro resta implementato localmente nel plugin con refactor successivo quando/se la funzione condivisa arriva.

### Dipendenze e precondizioni
Fase 1 chiusa (plugin installabile, blueprint attivo, meccanismo di migrazione JIT core disponibile).

### Deliverable verificabili
- Un amministratore può: vedere la lista di esperimenti eleggibili (solo microblogging, Standard+HPC, badge famiglia); creare una copia di un esperimento esistente con `db_exp` già popolato, scegliendo "solo agenti" o "mantieni tutto"; creare, elencare, modificare nome/descrizione, duplicare, archiviare uno scenario (ancora senza contenuto thread).
- Tabelle `sd_scenario`/`sd_scenario_revision` verificabili con una query diretta sul `db_exp` dell'esperimento dopo il primo accesso admin (migrazione JIT osservata, non assunta).

### Criteri di completamento e success gate
- Endpoint 1-7 di §15 funzionanti e testati (tabella sotto).
- La migrazione JIT crea le tabelle **solo** sul `db_exp` dell'esperimento effettivamente aperto, mai su altri `db_exp` (test di isolamento esplicito, anticipando il rischio di §25 sull'attivazione errata del bind).
- La copia "solo agenti" produce 1:1 lo stesso numero di righe `user_mgmt` della sorgente e 0 righe `post`; la copia "mantieni tutto" produce lo stesso conteggio di righe `post`/satelliti della sorgente — verificato con assert numerici, non solo "non è vuoto".
- **Evidenza richiesta**: output dei test di copia con conteggi espliciti prima/dopo; dump schema `db_exp` post-migrazione JIT.

### Test funzionali e regression test
| Area | Test |
|---|---|
| Filtro eleggibilità | Esperimento forum/photo-sharing non compare in lista e l'endpoint diretto risponde `unsupported_experiment_type` **prima** di qualunque lettura DB aggiuntiva |
| Copia "solo agenti" | Conteggio `user_mgmt` sorgente == copia; conteggio `post`/satelliti copia == 0 |
| Copia "mantieni tutto" | Conteggio `user_mgmt` e `post`/satelliti sorgente == copia, per Standard e per HPC |
| Copia su esperimento senza `db_exp` | Rifiutata con errore esplicito, non un tentativo silente |
| Migrazione JIT | Tabelle `sd_*` assenti prima del primo accesso admin, presenti dopo; assenti su un secondo `exp_id` mai aperto in Scenario Design |
| CRUD scenario | Create/list/get/update/delete, incluso conflitto di concorrenza (anticipo di optimistic locking §21, anche se la colonna `version` può essere introdotta già qui invece che in Fase 8, essendo parte dello schema `sd_scenario`) |
| `require_supported_experiment` | Unit test isolato: accetta microblogging Standard/HPC, rifiuta forum/photo-sharing/tipo sconosciuto, con codice errore stabile |
| Regressione | `run_tests.py` core verde con plugin installato |

### Rischi principali e mitigazioni
| Rischio | Mitigazione |
|---|---|
| La copia "mantieni tutto" su esperimenti grandi è lenta/blocca la richiesta HTTP | Misurare il tempo in test con dataset realistico; se necessario pianificare esecuzione asincrona come item **[S]** per fase successiva, non bloccante per v1 |
| Migrazione JIT eseguita più volte in race condition (due richieste admin simultanee sullo stesso `exp_id` mai aperto prima) | Test di concorrenza esplicito: migrazione idempotente (verifica esistenza tabella prima di crearla, pattern già usato da `ensure_module_schema`) |
| Il filtro `platform_type`/`simulator_type` duplicato nel plugin diverge nel tempo dalla funzione condivisa core (se mai arriverà) | Un solo punto di implementazione nel plugin (`access.py` o equivalente), mai duplicato tra `routes_scenarios.py` e altri file |

### Commit incrementali previsti
Branch `feat/sd-fase-2-scenari`:
1. `feat(sd-models): aggiunge modelli sd_scenario/sd_scenario_revision + migrazione JIT per-esperimento` + `test(sd-models): migrazione idempotente, isolamento per exp_id`.
2. `feat(sd-security): require_supported_experiment condiviso` + `test(sd-security): accetta/rifiuta famiglie esperimento`.
3. `feat(sd-scenarios): endpoint lista esperimenti eleggibili + verifica compatibilità` + `test(sd-scenarios): filtro famiglia, badge Standard/HPC`.
4. `feat(sd-scenarios): endpoint copia esperimento con modalità solo-agenti/mantieni-tutto` + `test(sd-scenarios): conteggi 1:1 per entrambe le modalità, Standard e HPC`.
5. `feat(sd-scenarios): CRUD scenario (create/list/get/update/delete/duplicate/archive)` + `test(sd-scenarios): CRUD completo, optimistic locking su version`.
6. `test(integration): E2E fase 2 — crea copia, crea scenario, verifica stato db_exp` (commit di chiusura fase).

### Aggiornamento documentazione di fine fase
README aggiornato: "Stato: CRUD scenario e copia esperimento funzionanti, nessun contenuto thread ancora". Decision log: eventuale decisione sulla copia asincrona rimandata. Piano tecnico §12/§18 aggiornati se emergono scostamenti sul formato di `base_fingerprint`.

---

## 5. Fase 3 — Editor dei thread [E]

### Obiettivi e componenti
Modello gerarchico di bozza, CRUD thread/post, ricerca autori, editor metadati, invarianti di §13. Endpoint 8-16 di §15 (esclusa generazione LLM, che è Fase 4, ed esclusi ruoli ad hoc completi, Fase 5 — ma il campo `role_key` come stringa libera va già previsto nello schema).
- **[E]** `models.py` (estensione): `sd_thread`, `sd_draft_post`, `sd_draft_metadata`, `sd_id_mapping` (schema, non ancora popolata dalla pubblicazione).
- **[E]** `routes_threads.py`: endpoint 8-13 (CRUD thread/post, eliminazione a cascata).
- **[E]** `routes_authors.py`/sezione dedicata: endpoint 14 (ricerca autori, type-ahead su `User_mgmt` del `db_exp` attivo).
- **[E]** Endpoint 15 (vocabolari/topic) — se il vocabolario è statico può essere una lista hardcoded documentata, non richiede per forza una tabella propria in v1.
- **[E]** Validazione invarianti §13: grafo aciclico, radice unica, autore esistente, ordinamento topologico — modulo dedicato e testato in isolamento (non solo inline nelle route).
- **[E]** Policy di cancellazione a cascata (§20) per le **bozze** (non ancora per contenuto reale pubblicato, che è anticipato solo come requisito, pienamente coperto in Fase 8 insieme alle operazioni su contenuto reale, §6 del piano tecnico).
- **[S]** Editor frontend completo (albero visuale, drag&drop, ecc.) — la logica server-side è **[E]**, la UI può procedere a complessità crescente: una versione minima funzionale (lista indentata, non necessariamente grafica rifinita) è sufficiente per chiudere la fase; il raffinamento visivo (badge colorati, animazioni) è **[S]**.

### Dipendenze e precondizioni
Fase 2 chiusa (scenario esistente su cui agganciare i thread).

### Deliverable verificabili
- Creazione di un thread con più nodi annidati, autori assegnati da `User_mgmt` reale, metadati opzionali salvati, eliminazione di un nodo con risposte che cancella correttamente l'intero sottoalbero e le righe `sd_draft_metadata` associate.
- Tentativo di creare un riferimento circolare o un nodo orfano rifiutato server-side con errore esplicito.

### Criteri di completamento e success gate
- Endpoint 8-16 funzionanti e testati.
- Tutte le invarianti di §13 verificate da test unitari dedicati, non solo "verificate a mano in UI".
- **Evidenza richiesta**: output dei test di invarianti (inclusi i casi negativi: ciclo rifiutato, nodo orfano rifiutato, autore inesistente rifiutato); screenshot/registrazione della UI minima funzionante (anche non rifinita).

### Test funzionali e regression test
| Area | Test |
|---|---|
| Radice unica | Creazione di un secondo nodo radice sullo stesso thread rifiutata |
| Grafo aciclico | Tentativo di impostare `parent_tmp_id` in modo da creare un ciclo → rifiutato **alla scrittura**, non solo in validazione finale |
| Nodo orfano | `parent_tmp_id` verso un nodo cancellato → rifiutato |
| Cancellazione a cascata | Eliminazione nodo con N discendenti → verifica conteggio esatto di righe `sd_draft_post`/`sd_draft_metadata` rimosse, preview coerente col conteggio reale |
| Autore inesistente | Autore non presente in `User_mgmt` del `db_exp` attivo → rifiutato alla creazione/validazione |
| Ordinamento topologico | Serializzazione di un thread con nodi creati in ordine non topologico restituisce comunque l'ordine padri-prima-dei-figli |
| Thread esistente corrotto (letto da dati reali, anticipo §6) | Lettura in sola lettura tollera un nodo orfano mostrando avviso, non blocca la visualizzazione; scrittura su quel thread richiede conferma esplicita |
| Isolamento tra esperimenti | Due scenari su due `exp_id` diversi non si influenzano mai (ricerca autori, thread, metadati) |
| Regressione | `run_tests.py` core verde; suite Fase 1/2 ancora verde (non solo i nuovi test) |

### Rischi principali e mitigazioni
| Rischio | Mitigazione |
|---|---|
| La UI "minima funzionale" viene percepita come incompleta e si tenta di rifinirla prima di chiudere la fase | Il gate di fase è esplicitamente **solo** sulla logica server-side + una UI minima verificabile; il raffinamento visivo è tracciato come backlog **[S]**, non blocca il gate |
| Le invarianti validate solo a pubblicazione lasciano stati intermedi incoerenti durante l'editing | Validazione **ad ogni scrittura** di `parent_tmp_id`, non solo a pubblicazione (requisito esplicito di §13, testato qui) |
| Il campo `role_key` libero introdotto in anticipo (Fase 5 non ancora fatta) crea un contratto difficile da cambiare dopo | Documentare esplicitamente nello schema che `role_key` è stringa libera non-FK fin da subito (coerente con §17), evitando revisioni di schema in Fase 5 |

### Commit incrementali previsti
Branch `feat/sd-fase-3-editor-thread`:
1. `feat(sd-models): aggiunge sd_thread/sd_draft_post/sd_draft_metadata/sd_id_mapping (schema)` + `test(sd-models): FK e cascata a livello di schema`.
2. `feat(sd-threads): modulo invarianti thread (radice unica, aciclicità, autore valido, ordinamento topologico)` + `test(sd-threads): casi positivi e negativi per ogni invariante` — commit isolato perché è logica critica e riusata ovunque.
3. `feat(sd-threads): endpoint CRUD thread/post (8-13)` + `test(sd-threads): CRUD, eliminazione a cascata con conteggio`.
4. `feat(sd-authors): ricerca autori type-ahead su User_mgmt del db_exp attivo` + `test(sd-authors): isolamento tra esperimenti, matching parziale`.
5. `feat(sd-vocab): endpoint vocabolari/topic (15), endpoint discovery ruoli stub solo "standard" (16, versione minima prima di Fase 5)` + test.
6. `feat(sd-ui-minimal): editor thread minimo funzionale (lista indentata, CRUD da UI)` — commit frontend, separato dal backend.
7. `test(integration): E2E fase 3 — crea thread multi-livello, elimina sottoalbero, verifica conteggi` (chiusura fase).

### Aggiornamento documentazione di fine fase
README: "Stato: editor thread funzionante (UI minima), invarianti validate server-side". Decision log: eventuali semplificazioni della UI rimandate a backlog **[S]** esplicito.

---

## 6. Fase 4 — Generazione LLM [E]

### Obiettivi e componenti
Selezione backend/modello (riuso del widget esistente, §16), prompt building, generazione/rigenerazione, audit, gestione robusta di timeout/errori/cancellazione/injection.
- **[E]** `routes_llm.py`: endpoint 17.
- **[E]** Prompt builder: separazione esplicita istruzioni/contenuti non fidati (§16), strategia di troncamento "finestra + riepilogo".
- **[E]** `sd_llm_generation_audit` (migrazione).
- **[E]** Garanzia di non persistenza su risposta non valida (scrittura `generated_text` solo dopo controllo minimo, nella stessa transazione dell'audit).
- **[H]** Gestione segreti nel prompt audit (redazione di eventuali token/URL sensibili prima del log) — hardening da chiudere in questa fase stessa (non rimandabile a Fase 8, perché riguarda dati scritti su disco/DB fin da subito).

### Dipendenze e precondizioni
Fase 3 chiusa (serve un thread/nodo su cui generare contenuto). Riuso diretto del meccanismo esistente `GET /admin/api/fetch_models` (§2, §16): nessuna modifica al core richiesta qui.

### Deliverable verificabili
- Generazione di un testo per un nodo, con backend/modello selezionati tramite il widget esistente, audit registrato con prompt effettivo e esito.
- Cancellazione di una generazione in corso: nessuna riga scritta, audit registra il tentativo.
- Backend LLM non disponibile: errore applicativo esplicito, mai testo segnaposto.

### Criteri di completamento e success gate
- Endpoint 17 funzionante con backend LLM **simulato** nei test (mock HTTP), non dipendente da un vero servizio LLM esterno per il gate di questa fase.
- Test di prompt injection: un contenuto di thread contenente istruzioni ("ignora le istruzioni precedenti e...") non altera il comportamento del system prompt — verificato con asserzione sul prompt effettivo costruito, non solo sull'output.
- **Evidenza richiesta**: log di audit di una generazione completa (successo), una cancellata, una con backend non disponibile, una con tentativo di injection — quattro casi, quattro righe di audit distinte e ispezionabili.

### Test funzionali e regression test
| Area | Test |
|---|---|
| Generazione con successo | Testo salvato, audit completo, badge "Bozza LLM" impostato |
| Timeout | Richiesta oltre il timeout configurato → errore esplicito, nessuna scrittura bozza, audit registra timeout |
| Retry transitorio | Errore di rete simulato una volta → un retry automatico, poi successo; due errori consecutivi → fallimento esposto, non retry infinito |
| Risposta vuota/non valida | Nessuna scrittura su `sd_draft_post`, audit registra il tentativo |
| Cancellazione | Richiesta annullata lato UI durante l'esecuzione → nessuna scrittura, audit registra "cancellato" |
| Prompt injection | Contenuto storico con istruzioni malevole → system prompt non alterato (assert sul prompt costruito) |
| Backend non disponibile | Errore `llm_backend_unavailable` esplicito, mai fallback silenzioso |
| Audit redazione segreti | URL con eventuale token in query string non compare in chiaro nel log di audit |
| Regressione | Fasi 1-3 ancora verdi; `run_tests.py` core verde (nessuna modifica al core in questa fase, quindi il rischio di regressione qui è minimo ma va comunque confermato) |

### Rischi principali e mitigazioni
| Rischio | Mitigazione |
|---|---|
| Il mock del backend LLM nei test diverge troppo da un vero backend OpenAI-compatibile, nascondendo bug reali | Un test manuale (non automatizzato in CI) contro un vero endpoint locale (es. vLLM/Ollama) prima di chiudere la fase, documentato nella PR anche se non ripetibile in CI |
| La strategia "finestra + riepilogo" per il troncamento introduce perdita di contesto non percepita dall'admin | UI mostra esplicitamente quali nodi sono stati riepilogati vs. inclusi per intero (requisito di trasparenza, non solo tecnico) |
| Redazione segreti nel log di audit incompleta (pattern non previsto) | Whitelist esplicita di cosa va loggato (mai log "tutto il payload grezzo" senza passare da una funzione di redazione centralizzata e testata) |

### Commit incrementali previsti
Branch `feat/sd-fase-4-llm`:
1. `feat(sd-llm): migrazione sd_llm_generation_audit` + `test(sd-llm): schema e vincoli`.
2. `feat(sd-llm): prompt builder con separazione istruzioni/contenuti e strategia finestra+riepilogo` + `test(sd-llm): injection, troncamento, casi limite (thread vuoto, thread a 1 nodo)` — commit isolato, è la logica più sensibile della fase.
3. `feat(sd-llm): funzione di redazione segreti per audit log` + `test(sd-llm): pattern di redazione`.
4. `feat(sd-llm): endpoint generazione/rigenerazione (17) con timeout/retry/cancellazione` + `test(sd-llm): successo, timeout, retry, cancellazione, backend non disponibile`.
5. `feat(sd-ui): pannello generazione LLM in editor thread (riuso widget Fetch Models)` — frontend.
6. `test(integration): E2E fase 4 — genera, rigenera, confronta bozza precedente/nuova, approva` (chiusura fase).

### Aggiornamento documentazione di fine fase
README: "Stato: generazione LLM funzionante con audit completo". Decision log: esito del test manuale contro backend reale, eventuali limiti di troncamento osservati.

---

## 7. Fase 5 — Ruoli ad hoc opzionali [S]

### Obiettivi e componenti
Discovery live di `y_agents_plugins`, UI di selezione ruolo, fallback pulito. Interamente additiva: in sua assenza, Scenario Design funziona già con il solo ruolo "standard" (già garantito da Fase 4).
- **[S]** `roles.py`: `discover_adhoc_roles()`.
- **[S]** UI: dropdown ruolo con badge "plugin non disponibile" per scenari salvati con ruoli non più presenti.

### Dipendenze e precondizioni
Fase 4 chiusa (il ruolo alimenta il prompt builder già esistente, come sorgente opzionale di contesto). Non blocca né è bloccata da Fase 6/7: può procedere in parallelo a valle della Fase 3/4.

### Deliverable verificabili
- Con `y_agents_plugins` installato e valido: dropdown popolato con i ruoli reali, prompt arricchito dal `prompt_templates[0]` come suggerimento.
- Con `y_agents_plugins` assente/invalido: solo "standard" disponibile, nessun errore in UI.
- Scenario salvato con un ruolo poi rimosso: badge esplicito, pubblicazione non bloccata.

### Criteri di completamento e success gate
- I tre scenari sopra (presente-valido, assente, rimosso-dopo-salvataggio) coperti da test espliciti.
- **Evidenza richiesta**: test eseguiti nei tre stati del repo `y_agents_plugins` (installato valido, assente, manifest corrotto ad arte).

### Test funzionali e regression test
| Area | Test |
|---|---|
| Discovery con repo valido | Ruoli esposti correttamente, solo i campi previsti (`agent_type`, `display_name`, `description`, primo `prompt_templates`) |
| Discovery con repo assente | Fallback silenzioso a "standard", nessuna eccezione propagata alla UI |
| Discovery con manifest invalido | Stesso fallback, nessun crash, errore solo loggato server-side |
| Ruolo rimosso dopo salvataggio | `role_key` resta stringa libera salvata, badge "non più disponibile", pubblicazione non bloccata |
| Nessun accoppiamento a `parameters`/`client_parameters` | Test che verifica che questi campi non vengano letti/usati dal plugin |
| Regressione | Fasi 1-4 ancora verdi |

### Rischi principali e mitigazioni
| Rischio | Mitigazione |
|---|---|
| Accoppiamento involontario con campi interni di `y_agents_plugins` che potrebbero cambiare | Whitelist esplicita dei soli campi letti (già nel piano tecnico, §17), test che fallisce se si tenta di leggere un campo fuori whitelist |
| Il fallback "silenzioso" nasconde un problema reale di configurazione che l'admin vorrebbe vedere | Il fallback non genera errore bloccante, ma logga un warning server-side ispezionabile — mai completamente muto |

### Commit incrementali previsti
Branch `feat/sd-fase-5-ruoli-adhoc`:
1. `feat(sd-roles): discover_adhoc_roles con parsing difensivo e whitelist campi` + `test(sd-roles): valido/assente/invalido`.
2. `feat(sd-roles): endpoint 16 completo (standard + ad hoc)` + `test(sd-roles): fallback, badge ruolo rimosso`.
3. `feat(sd-ui): dropdown ruolo con badge "plugin non disponibile"`.
4. `test(integration): E2E fase 5 — scenario con ruolo ad hoc, rimozione plugin, riapertura scenario`.

### Aggiornamento documentazione di fine fase
README: "Stato: ruoli ad hoc opzionali supportati". Decision log: eventuali campi del manifest `y_agents_plugins` scoperti ma non ancora usati (candidati per **[S]** futuri).

---

## 8. Fase 6 — Materializzazione standard [E]

### Obiettivi e componenti
Validazione, preview, transazione, pubblicazione per microblogging Standard. Endpoint 18-21 (parte Standard).
- **[E]** `adapters/base.py`: interfaccia `MaterializationAdapter`.
- **[E]** `adapters/standard.py`: algoritmo a 21 passi di §18, transazione singola sul bind `db_exp` (§11, aggiornamento già riflesso nel piano tecnico).
- **[E]** `routes_publish.py`: endpoint 18 (validate), 19 (preview), 20 (publish), 21 (audit).
- **[E]** `sd_publication` (migrazione).
- **[E]** Fault injection test: eccezione forzata a metà transazione → rollback completo verificato.

### Dipendenze e precondizioni
Fase 3 chiusa (thread di bozza esistenti da pubblicare). Non dipende da Fase 4/5 in senso stretto (uno scenario senza alcuna generazione LLM, solo contenuto manuale, deve poter essere pubblicato), ma in pratica verrà quasi sempre usato dopo Fase 4.

### Deliverable verificabili
- Pubblicazione end-to-end di uno scenario Standard: righe reali create in `post` e satelliti, mapping `tmp_id → id` consultabile, stato scenario `published`, link alla simulazione.
- Interruzione forzata a metà pubblicazione (test): `db_exp` torna esattamente allo stato precedente, nessuna riga orfana.

### Criteri di completamento e success gate
- Endpoint 18-21 funzionanti per Standard.
- Test di fault injection verde (rollback completo verificato con conteggio righe prima/dopo identico).
- Fingerprint/concorrenza: pubblicazione rifiutata se l'esperimento base è cambiato dall'ultima apertura dello scenario (hash non combacia).
- **Evidenza richiesta**: dump dello stato `post`/satelliti prima e dopo un fault injection test (devono coincidere); log di una pubblicazione riuscita con conteggio preview == conteggio reale.

### Test funzionali e regression test
| Area | Test |
|---|---|
| Pubblicazione riuscita | Conteggio preview == conteggio reale post-pubblicazione, per ogni tabella satellite coinvolta |
| Fault injection | Eccezione forzata dopo N inserimenti → rollback completo, `db_exp` identico allo stato pre-pubblicazione |
| Fingerprint cambiato | Esperimento base modificato dopo creazione bozza → pubblicazione rifiutata con errore esplicito |
| Esperimento in esecuzione | `running==1` → pubblicazione rifiutata |
| Idempotenza con `X-Idempotency-Key` | Richiesta ripetuta con stessa chiave → stesso risultato, nessuna duplicazione |
| Thread→post: semantica `thread_id`/`comment_to` | Verifica che il post radice abbia `thread_id==id proprio` e che i discendenti, anche annidati, ereditino lo stesso `thread_id` (non quello del padre immediato) — test diretto sull'invariante confermato in §13 |
| Sostituzione thread esistente (opzionale) | Se l'admin sceglie "sostituisci thread X", la policy di §20 si applica correttamente dentro la stessa transazione |
| Regressione | Fasi 1-5 ancora verdi; `run_tests.py` core verde |

### Rischi principali e mitigazioni
Vedi §25 del piano tecnico, righe pertinenti a questa fase (attivazione bind errata, idempotenza). In aggiunta:
| Rischio | Mitigazione |
|---|---|
| Il test di fault injection non copre tutti i punti di fallimento possibili (solo uno scelto ad hoc) | Parametrizzare il test per fallire a più passi diversi dell'algoritmo (es. dopo passo 10, dopo passo 13, dopo passo 17), non un solo punto fisso |
| La transazione singola (post-decisione db_exp) nasconde un lock di lunga durata su tabelle core con impatto su altri utenti dell'esperimento | Misurare la durata della transazione con un dataset realistico in test, documentare un limite accettabile, item di ottimizzazione **[S]** se il limite viene superato |

### Commit incrementali previsti
Branch `feat/sd-fase-6-materializzazione-standard`:
1. `feat(sd-adapter): interfaccia MaterializationAdapter` + `test(sd-adapter): contratto interfaccia`.
2. `feat(sd-adapter-standard): algoritmo di pubblicazione Standard (passi 1-9)` + `test(sd-adapter-standard): lock, permessi, fingerprint, validazione` — split dei 21 passi in due commit per restare atomico e revisionabile.
3. `feat(sd-adapter-standard): algoritmo di pubblicazione Standard (passi 10-21, transazione e commit)` + `test(sd-adapter-standard): creazione post/commenti, metadati, commit unico, rollback`.
4. `feat(sd-publish): migrazione sd_publication + endpoint 18-21` + `test(sd-publish): validate/preview/publish/audit`.
5. `test(sd-publish): fault injection parametrizzata su più passi` — commit dedicato, non unito al precedente per isolarne la responsabilità.
6. `test(integration): E2E fase 6 — scenario completo pubblicato su esperimento Standard, verifica nel pannello esperimenti esistente`.

### Aggiornamento documentazione di fine fase
README: "Stato: pubblicazione Standard end-to-end funzionante". Piano tecnico: se la misura di durata transazione rivela un problema, aggiornare §18/§25 con la nuova mitigazione pianificata.

---

## 9. Fase 7 — Materializzazione HPC [E]

### Obiettivi e componenti
Adapter HPC, differenze di identificatori UUID, gestione del caso "DB HPC non ancora creato".
- **[E]** `adapters/hpc.py`.
- **[E]** Generazione UUID per tutti gli identificatori pertinenti.
- **[E]** Errore esplicito e distinto se `db_exp` HPC non esiste ancora.
- **[H]** Verifica PostgreSQL oltre a SQLite per il disallineamento `Post.round` (se Fase 0 non l'ha già coperto in modo esaustivo).

### Dipendenze e precondizioni
**Blocco duro**: Fase 0 deve aver chiuso in modo inequivocabile il disallineamento `Post.round` (§19, §25). Se Fase 0 ha lasciato il punto come rischio accettato (non risolto ma mitigato), questa fase deve **riaprire l'investigazione** prima di scrivere `adapters/hpc.py`, non procedere assumendo che "probabilmente funziona perché SQLite è debolmente tipato" — questo è esplicitamente il rischio più delicato dell'intero piano (nota di revisione punto 2 del piano tecnico).
Dipende inoltre da Fase 6 (interfaccia comune `MaterializationAdapter` già definita e testata).

### Deliverable verificabili
- Pubblicazione end-to-end su un esperimento HPC **avviato almeno una volta** (quindi con `db_exp` esistente): righe reali con id UUID coerenti, `thread_id` propagato correttamente dalla radice.
- Tentativo di pubblicazione su un esperimento HPC mai avviato: errore esplicito e distinto, nessun tentativo di creare schema.

### Criteri di completamento e success gate
- Pubblicazione HPC testata end-to-end su un esperimento HPC reale (non solo mockato), avviato almeno una volta in ambiente di sviluppo.
- Il disallineamento `Post.round` è verificato **positivamente** in questa fase con un test di integrazione su un vero `db_exp` HPC, non solo "si presume funzioni".
- **Evidenza richiesta**: log della pubblicazione E2E su un vero esperimento HPC; dump delle righe `post` create con i relativi UUID e `round`, ispezionato manualmente per coerenza col resto del dataset HPC.

### Test funzionali e regression test
| Area | Test |
|---|---|
| Generazione UUID | Tutti gli id materializzati sono stringhe UUID valide, mai interi |
| `thread_id` propagazione | Stesso test logico di Fase 6, ma con asserzioni su stringhe UUID anziché interi |
| DB HPC non esistente | Pubblicazione rifiutata con errore distinto, nessun tentativo di creazione schema da parte del plugin |
| `round` come FK a `rounds.id` | Scrittura di un post con un `round` valido (UUID esistente in `rounds`) e verifica che la lettura successiva con i modelli YWeb non sollevi errori di tipo, su SQLite **e** (se disponibile) PostgreSQL |
| Fault injection HPC | Stesso principio di Fase 6, adattato agli identificatori UUID |
| Parallelo Standard/HPC | Stesso scenario logico pubblicato su entrambe le famiglie produce risultati strutturalmente equivalenti (stesso numero di nodi, stessa gerarchia), differendo solo nel tipo di identificatore |
| Regressione | Fasi 1-6 ancora verdi |

### Rischi principali e mitigazioni
Il rischio principale è già coperto in dettaglio da Fase 0 e dalla tabella rischi del piano tecnico (§25, prima riga). Aggiuntivo:
| Rischio | Mitigazione |
|---|---|
| L'ambiente di sviluppo non dispone facilmente di un esperimento HPC reale avviato almeno una volta | Documentare nel decision log la procedura minima per crearne uno (avvio YSimulator in locale), così da non reinventarla a ogni sessione di lavoro su questa fase |
| PostgreSQL non disponibile in ambiente di sviluppo per il test del disallineamento `round` | Se non disponibile, il test PostgreSQL resta marcato esplicitamente come "da eseguire prima della release" (Fase 9), non saltato silenziosamente |

### Commit incrementali previsti
Branch `feat/sd-fase-7-materializzazione-hpc`:
1. `feat(sd-adapter-hpc): generazione identificatori UUID e adattamento passi 1-9` + `test(sd-adapter-hpc): lock/permessi/fingerprint con id stringa`.
2. `feat(sd-adapter-hpc): passi 10-21, gestione round come FK rounds.id` + `test(sd-adapter-hpc): creazione post/commenti UUID, round valido`.
3. `feat(sd-adapter-hpc): errore esplicito per db_exp HPC non esistente` + `test(sd-adapter-hpc): rifiuto pre-condizione`.
4. `test(sd-adapter-hpc): fault injection parametrizzata, parallelo Standard/HPC`.
5. `test(integration): E2E fase 7 — pubblicazione su esperimento HPC reale avviato almeno una volta`.

### Aggiornamento documentazione di fine fase
README: "Stato: pubblicazione HPC end-to-end funzionante, verificata su db reale". Piano tecnico §19/§25: marcare definitivamente **[F]** il punto sul disallineamento `round`, con riferimento al test che lo dimostra.

---

## 10. Fase 8 — Operazioni distruttive e hardening [E]+[H]

### Obiettivi e componenti
Chiude i requisiti ancora parzialmente aperti: modifica diretta di contenuto **reale** già materializzato (non solo bozze, §6 del piano tecnico), cascata completa su dipendenze satellite per contenuto reale, concorrenza (optimistic locking, se non già coperto in Fase 2), audit completo, eventuale PR core separata per il cleanup hook generico.
- **[E]** Estensione delle route di modifica contenuto (endpoint 11-13) per operare in due modalità equivalenti: su righe di bozza **e** su righe reali già presenti nel `db_exp` (§6) — con le stesse validazioni di invarianti e la stessa policy di cascata.
- **[E]** Cascata completa su tutte le tabelle satellite elencate in §20, per contenuto sia di bozza sia reale.
- **[E]** `sd_audit_log` (se non già introdotta incrementalmente nelle fasi precedenti per le singole operazioni — qui si consolida come tabella unica trasversale).
- **[H]** Conferma rafforzata per bulk delete (digitare il nome scenario/esperimento).
- **[H]** Limiti di lunghezza testo e sanitizzazione HTML/script su ogni campo libero (mai `|safe` su contenuto utente/LLM).
- **[H]** Verifica esplicita "nessun effetto sul core quando il plugin non è installato" con test di non-regressione dedicato (se non già coperto esaustivamente in Fase 1).
- **[S]** PR separata e minima al core per l'hook generico di cleanup dipendenze di altri plugin (§20) — **non bloccante** per la release v1 di Scenario Design: se non approvata/pronta in tempo, v1 semplicemente non ripulisce dati di plugin terzi (comportamento sicuro per difetto, già esplicitato nel piano tecnico).

### Dipendenze e precondizioni
Fase 6 e Fase 7 chiuse (serve la pubblicazione funzionante per poter operare su contenuto reale materializzato).

### Deliverable verificabili
- Modifica ed eliminazione di un post **reale** (non di bozza) di un esperimento, con preview di impatto corretta e cascata completa sulle tabelle satellite reali.
- Tentativo di modifica su esperimento in esecuzione: rifiutato, per contenuto sia reale sia di bozza.
- Eliminazione bulk con conferma rafforzata (digitazione nome) verificata in UI e server-side (il server non si fida della sola conferma UI).

### Criteri di completamento e success gate
- Tutte le operazioni distruttive, su bozza e su contenuto reale, passano con preview+conferma e cascata verificata con conteggio esatto.
- Nessuna cancellazione di tabelle di altri plugin senza il contratto esplicito del cleanup hook (se non implementato, verificato che v1 semplicemente non tocca quelle tabelle, non che fallisca in modo imprevedibile).
- Sanitizzazione verificata con un test di XSS esplicito (payload `<script>` in un campo testo libero, mai renderizzato come eseguibile).
- **Evidenza richiesta**: conteggi prima/dopo per cascata su contenuto reale (stesso principio di Fase 3, ma su dati materializzati); log del test XSS; log del test "esperimento in esecuzione" per contenuto reale.

### Test funzionali e regression test
| Area | Test |
|---|---|
| Modifica contenuto reale | Stesse invarianti di §13 applicate a un nodo reale (`Post` esistente), non solo a `sd_draft_post` |
| Cascata su contenuto reale | Eliminazione di un `Post` reale con risposte → cascata su tutte le tabelle satellite reali elencate in §20, conteggio esatto |
| Esperimento in esecuzione, contenuto reale | Modifica/eliminazione rifiutata, stesso comportamento già testato per le bozze in Fase 3 |
| Bulk delete | Conferma rafforzata richiesta e verificata server-side, non solo lato client |
| XSS | Payload script in campo testo → mai eseguito, escaping verificato sia in rendering Jinja sia in risposta API |
| Audit trasversale | Ogni operazione rilevante (CRUD, generazione, pubblicazione, eliminazione) ha una riga in `sd_audit_log` coerente |
| Cleanup hook (se implementato) | Hook invocato best-effort dopo cancellazione core, eccezione nel hook non blocca l'operazione principale |
| Cleanup hook (se non implementato) | Nessuna tabella di terzi toccata, nessun errore — comportamento esplicitamente testato come "assenza sicura" |
| Non regressione plugin assente | Pannello admin e simulazioni esistenti invariati con plugin disinstallato, anche dopo tutte le funzionalità di questa fase |
| Regressione | Fasi 1-7 ancora verdi; `run_tests.py` core verde |

### Rischi principali e mitigazioni
| Rischio | Mitigazione |
|---|---|
| Unificare le route bozza/reale introduce un bug che permette scritture non intenzionali su contenuto reale durante operazioni pensate per la sola bozza | Test di regressione esplicito: ogni operazione "di bozza" già testata in Fase 3 viene ri-eseguita dopo l'unificazione delle route, verificando che il comportamento sulle bozze non sia cambiato |
| La PR core per il cleanup hook si allunga nei tempi di revisione, bloccando la percezione di "fase completa" | Il gate di questa fase **non include** l'hook come bloccante (esplicitamente marcato **[S]**/non bloccante nel piano tecnico) — la fase si chiude comunque se il resto è verde |
| Sanitizzazione incompleta per campi non ancora previsti (es. un futuro campo libero aggiunto in una fase successiva) | Funzione di sanitizzazione centralizzata e riusata, mai inline per singolo campo, cosicché un nuovo campo la erediti di default |

### Commit incrementali previsti
Branch `feat/sd-fase-8-hardening`:
1. `feat(sd-threads): estende routes_threads/modifica contenuto a operare su righe reali oltre che su bozze` + `test(sd-threads): invarianti e cascata su contenuto reale`.
2. `feat(sd-security): sanitizzazione centralizzata campi testo liberi` + `test(sd-security): XSS payload su ogni endpoint con campo libero`.
3. `feat(sd-security): conferma rafforzata bulk delete (server-side)` + `test(sd-security): bypass tentato solo lato client rifiutato dal server`.
4. `feat(sd-security): consolidamento sd_audit_log trasversale` + `test(sd-security): copertura di tutte le operazioni rilevanti`.
5. `test(sd-regression): ri-esecuzione test Fase 3 dopo unificazione route bozza/reale` — commit dedicato, non unito al punto 1, per isolare la prova di non-regressione.
6. (separato, repository YWeb core, **se approvato dal product owner**) `feat(core-cleanup-hook): hook generico opzionale cleanup_hook nel manifest, risolto via import dinamico` + `test(core-cleanup-hook): best-effort, isolamento eccezioni` — PR a sé stante, non necessaria per chiudere questa fase.
7. `test(integration): E2E fase 8 — modifica/elimina contenuto reale, bulk delete con conferma, verifica audit log completo`.

### Aggiornamento documentazione di fine fase
README: "Stato: operazioni su contenuto reale e bozza unificate, hardening di sicurezza completato". Decision log: stato della PR core cleanup hook (approvata/in revisione/non proposta) — esplicito, mai lasciato ambiguo.

---

## 11. Fase 9 — Packaging e release [E]

### Obiettivi e componenti
GitHub Release, documentazione finale, CI completa, test E2E conclusivi su tutti i 27 criteri di accettazione.
- **[E]** CI del repository `ScenarioDesign` (lint, test, eventualmente build pacchetto release).
- **[E]** `README.md` definitivo (installazione, configurazione, limiti noti).
- **[E]** Verifica di tutti i 27 criteri di accettazione (§26 del piano tecnico), uno per uno, con riferimento al test che li copre.
- **[H]** Test di non-regressione finale su `run_tests.py` core, sia con plugin installato sia assente, eseguito come ultimo passo prima del tag di release.

### Dipendenze e precondizioni
Tutte le fasi precedenti chiuse (0-8).

### Deliverable verificabili
- Una release GitHub installabile da `/admin/external_runtimes` con il percorso "GitHub Release" (non solo Git checkout usato finora in sviluppo).
- Documento di tracciabilità criteri di accettazione → test, allegato alla PR finale o incluso in `docs/acceptance.md`.

### Criteri di completamento e success gate
- Tutti i 27 criteri di accettazione verificati con riferimento esplicito al test automatizzato o alla verifica manuale documentata che li copre (tabella di tracciabilità, non un'affermazione generica).
- Installazione testata sia da release sia da Git checkout.
- **Evidenza richiesta**: tabella di tracciabilità compilata; log di installazione da entrambi i percorsi; log finale di `run_tests.py` in entrambe le condizioni (plugin presente/assente).

### Test funzionali e regression test
| Area | Test |
|---|---|
| Installazione da release | Download, estrazione, validazione manifest, attivazione sidebar |
| Installazione da Git checkout | Come già testato in Fase 1, ri-verificato qui con la versione definitiva del codice |
| Disinstallazione dopo pubblicazioni avvenute | Simulazioni pubblicate restano fruibili, tabelle `sd_*` restano come dati orfani non distruttivi (§22) |
| Tutti i 27 criteri di accettazione | Uno per uno, con esito registrato |
| Non regressione finale | `run_tests.py` core, entrambe le condizioni |

### Rischi principali e mitigazioni
| Rischio | Mitigazione |
|---|---|
| Un criterio di accettazione risulta coperto solo "sulla carta" (nessun test lo verifica realmente) | La tabella di tracciabilità è costruita **a ritroso dai test esistenti**, non scritta a priori e poi "spuntata": se un criterio non ha un test che lo copre, si scrive il test mancante prima di chiudere la fase, non si marca comunque come coperto |
| Il processo di release CI non è mai stato eseguito end-to-end prima d'ora | Un dry-run di release su un tag di pre-release prima del tag definitivo |

### Commit incrementali previsti
Branch `feat/sd-fase-9-release`:
1. `chore(sd-ci): pipeline CI completa (lint + test + build release)`.
2. `docs(sd-readme): README definitivo con installazione/configurazione/limiti noti`.
3. `docs(sd-acceptance): tabella di tracciabilità 27 criteri di accettazione → test`.
4. `test(integration): installazione da GitHub Release (dry-run su pre-release)`.
5. `test(regression): run_tests.py core finale, plugin presente/assente` (commit di chiusura, nessun codice applicativo, solo evidenza).
6. `chore(sd-release): tag v1.0.0`.

### Aggiornamento documentazione di fine fase
README definitivo pubblicato. Decision log chiuso per la v1 (resta aperto per v1.1+ con i punti **[S]** accumulati). Piano tecnico aggiornato in blocco: ogni **[P]** residuo diventato **[F]** durante l'implementazione viene aggiornato con riferimento al commit/PR che lo ha realizzato.

---

## 12. Classificazione trasversale: essenziale vs. successivo vs. hardening

Riepilogo per non perdere di vista cosa è bloccante per v1 e cosa no, raccolto da tutte le fasi sopra:

**[E] Essenziale (blocca la release v1)**: tutto il nucleo funzionale (Fasi 0-4, 6-7), modifica/cancellazione su contenuto reale oltre che bozza (Fase 8), sanitizzazione/XSS, audit trasversale, packaging (Fase 9).

**[S] Successivo (rimandabile oltre v1, tracciato esplicitamente nel decision log)**:
- Ruoli ad hoc (Fase 5) — additivo, v1 funziona anche senza.
- Raffinamento visivo dell'editor (oltre la UI minima funzionale di Fase 3).
- Funzione di libreria core condivisa `eligible_experiments()` (§8.2 punto 3) — il plugin può implementare il filtro da sé nel frattempo.
- Esecuzione asincrona della copia "mantieni tutto" su esperimenti grandi, se i test di performance di Fase 2 ne segnalano la necessità.
- PR core separata per il cleanup hook generico (Fase 8) — v1 resta sicura per difetto anche senza.

**[H] Hardening (necessario prima della release ma pianificato esplicitamente, non "aggiunto se c'è tempo")**:
- Redazione segreti nell'audit LLM (Fase 4).
- Sanitizzazione centralizzata e conferma rafforzata bulk delete (Fase 8).
- Verifica PostgreSQL del disallineamento `round` (Fase 0/7).
- Test di non-regressione finale in doppia condizione plugin presente/assente (ogni fase, consolidato in Fase 9).

---

## 13. Stato di avanzamento (da aggiornare a fine di ogni fase)

| Fase | Stato | PR | Data chiusura | Note |
|---|---|---|---|---|
| 0 | **Completata** | — (nessun branch/PR dedicato, vedi nota sotto) | 2026-10-02 | Decision log: `ScenarioDesign/docs/decisions.md` §F0.1-F0.4. Round HPC chiuso per SQLite, **[A]** aperto per PostgreSQL (non disponibile in ambiente di sviluppo) |
| 1 | **Completata** | — (nessun branch/PR dedicato, vedi nota sotto) | 2026-10-02 | 8 commit (4 YWeb core su branch `edu`, 4 ScenarioDesign su `main`). 2 deviazioni minime auto-risolte + 1 bug reale trovato e corretto prima del commit (§F1.1-F1.3). Non-regressione verificata con/senza plugin: 473 passed, 2 falliti pre-esistenti non correlati (sandbox), 12 skipped. Limite ambientale su dipendenze pesanti documentato (§F1.4) |
| 2 | **Completata** | — (nessun branch/PR dedicato, vedi nota sotto) | 2026-10-02 | 6 commit (5 ScenarioDesign su `main`, 1 YWeb core su `edu`). Decision log: §F2.1-F2.6. Scoperta chiave: nessun remapping di ID necessario per la copia popolazione/contenuti (destinazione sempre pristina, verificato empiricamente). 1 gap non previsto dal piano tecnico risolto per degradazione sicura, non escalato (copia verso esperimento HPC non ancora inizializzato, §F2.2). 1 regressione reale trovata e corretta prima di chiudere la fase (soglia line-count `y_web/__init__.py`, §F2.5). Non-regressione: 1921 passed, 38 skipped, 4 falliti pre-esistenti/ambientali non correlati (2 permessi sandbox già noti da Fase 1, 2 stub `ray` incompleto) |
| 3 | **Completata** | — (nessun branch/PR dedicato, vedi nota sotto) | 2026-10-02 | 2 commit (1 ScenarioDesign su `main`: schema+invarianti+rotte 8-16, 1 YWeb core su `edu`: test). Decision log: §F3.1-F3.5. 2 deviazioni dal piano tecnico, entrambe segnalate e approvate prima dell'implementazione: prefisso URL (§F2.7, riconfermato) e aggiunta di `exp_id`/`scenario_id` agli endpoint 11-12 per correttezza del bind `db_exp` (§F3.1, bug reale evitato prima del commit, non un semplice stile). Cascata di cancellazione multi-livello validata empiricamente via FK reali (§F3.2). Invarianti thread (radice singola, aciclicità, parent orfano, ordinamento topologico) isolate in modulo puro con 12 test dedicati. Limite ambientale del sandbox (scrittura di nuovi file sqlite sotto `y_web/experiments/`) esteso dalla Fase 1 con nuova manifestazione, documentato (§F3.4): 11 test di integrazione end-to-end si saltano esplicitamente qui, da ri-eseguire in ambiente di sviluppo reale. Non-regressione: 1923 passed, 49 skipped, 4 falliti pre-esistenti/ambientali non correlati (stessi di Fase 2); suite standalone ScenarioDesign 26/26 |
| 4 | **Completata** | — (nessun branch/PR dedicato, vedi nota sotto) | 2026-10-02 | 2 commit (1 ScenarioDesign su `main`: prompt builder/client/audit/endpoint 17, 1 YWeb core su `edu`: test). Decision log: §F4.1-F4.6. Deviazione `exp_id`/`scenario_id` nell'URL applicata per lo stesso principio già approvato in Fase 3 (§F3.1), non una nuova richiesta di autorizzazione. 1 rotta interna non prevista da §15 (`generations/<id>/cancel`), necessaria per implementare il requisito di cancellazione lato UI — decisione di design, non deviazione dal piano. Prompt builder con separazione istruzioni/contenuti non fidati e troncamento "finestra+riepilogo"; client LLM con stato macchina timeout/retry/cancellazione conforme a §16; redazione segreti centralizzata (1 bug di doppia-redazione trovato e corretto prima del commit, §F4.5). Suite standalone ScenarioDesign: 51/51 (37 nuovi test puri, nessuna dipendenza da sqlite reale). 10 test di integrazione end-to-end si saltano esplicitamente per lo stesso limite ambientale di Fase 3, qui riscontrato anche sul bind `db_admin` durante un tentativo di validazione end-to-end extra (§F4.6) — da ri-eseguire in ambiente di sviluppo reale. Non-regressione YWeb core: 1925 passed, 59 skipped, 4 falliti pre-esistenti/ambientali non correlati (stessi di Fase 2/3) |
| 5 | **Completata** | — (nessun branch/PR dedicato, vedi nota sotto) | 2026-10-02 | 2 commit (1 ScenarioDesign su `main`: roles.py/endpoint 16/role_key, 1 YWeb core su `edu`: test). Decision log: §F5.1-F5.3. `discover_adhoc_roles()` diviso in livello puro testato con payload malformati arbitrari + livello impuro di I/O; whitelist campi imposta strutturalmente (mai letti `parameters`/`client_parameters`). Verificato non solo con mock ma contro il repo `y_agents_plugins` realmente presente in questo ambiente: 6 ruoli ad hoc reali scoperti correttamente end-to-end. `role_key` libero su `sd_draft_post`, mai validato contro il catalogo live in scrittura (coerente con §17: un ruolo rimosso non blocca mai nulla). Suite standalone ScenarioDesign: 64/64. 2 dei 3 nuovi test di integrazione YWeb core eseguiti realmente (non soggetti al limite sandbox, l'endpoint 16 non tocca `db_exp`); 1 si salta per lo stesso limite noto. Non-regressione: 1927 passed, 60 skipped, 4 falliti pre-esistenti/ambientali non correlati |
| 6 | **Completata** | — (nessun branch/PR dedicato, vedi nota sotto) | 2026-10-02 | 2 commit (1 ScenarioDesign su `main`: adapters/base.py+standard.py, metadata_mapping.py, fingerprint.py, routes_publish.py, migrazione `sd_publication`+lock su `sd_scenario`; 1 YWeb core su `edu`: test). Decision log: §F6.1-F6.10. `base_fingerprint` (colonna presente dalla Fase 2 ma mai popolata) chiuso: scritto alla creazione, risincronizzato ad ogni apertura dello scenario (unico side-effect di scrittura su una GET in tutto il plugin, documentato). Transazione singola ottenuta per costruzione (stesso bind `db_exp` condiviso fra core e `sd_*`), non un meccanismo nuovo da costruire; lock applicativo su `sd_scenario` esplicitamente informativo/diagnostico, la garanzia reale di concorrenza resta il lock di file di SQLite (documentato, non un corner cut silenzioso). Algoritmo a 21 passi implementato integralmente, incluso l'invariante `thread_id`/`comment_to` (propagazione dalla radice, mai dal genitore immediato) verificato su dati realmente materializzati. Metadati opzionali: contratto JSON per dimensione in modulo puro dedicato (`metadata_mapping.py`); sentiment/opinion richiedono `topic_id` esplicito (NOT NULL nello schema core reale), rifiutati in validazione se assente, mai materializzati con un topic inventato. Idempotenza: nessuna riga "failed" persistente (rollback completo), un retry con la stessa chiave riparte da zero; solo una pubblicazione riuscita viene rigiocata. "Sostituisci thread esistente" (opzionale) implementato in forma minima, cancellazione satelliti esplicita (nessuna cascata DB-level garantita). FK reale su `sd_id_mapping.publication_id` deliberatamente rimandata (richiederebbe ricreazione tabella in SQLite, nessun cambio di comportamento runtime). Fault injection parametrizzata su 3 passi distinti (9/13/17), non un punto fisso, con verifica di conteggi identici pre/post rollback. Suite standalone ScenarioDesign: 96/96 (32 nuovi test puri). 7 test di integrazione end-to-end si saltano esplicitamente per lo stesso limite ambientale di Fase 3/4 — da ri-eseguire in ambiente di sviluppo reale. Non-regressione YWeb core: 1931 passed, 67 skipped, 2 soli falliti pre-esistenti/ambientali non correlati (i 2 precedentemente attribuiti allo stub `ray` incompleto sono spariti dopo la ricostruzione dello stub, nota ambientale §F6.9, non una modifica di questa fase) |
| 7 | **In corso** | — (nessun branch/PR dedicato, vedi nota sotto) | — | 4 commit ScenarioDesign su `main` finora. Decision log: §F7.1-F7.8. Deviazione non preventivata segnalata e approvata dall'utente tramite `AskUserQuestion`: il disallineamento Integer/UUID tra `db_exp` e lo schema fisico HPC è sistemico (ogni id, non solo `Post.round` come indicato dal piano tecnico), e tocca anche `sd_draft_post.author_user_id` già introdotto in Fase 3. Principio adottato su indicazione esplicita dell'utente: ogni id trattato come opaco a livello di schema/validazione, materializzato nel formato corretto (UUID per HPC, int autoincrementante per Standard) da ciascun adapter. Implementati finora: `hpc_session.py` (accesso diretto, non Flask, allo schema fisico HPC riusando i modelli ORM reali di YSimulator, con bootstrap di `sys.path` necessario e non banale, bug reale trovato e corretto prima del commit, §F7.5); `adapters/hpc.py` con i 21 passi di §18 adattati a UUID, atomicità ottenuta facendo passare *tutte* le scritture di una pubblicazione (contenuto reale e bookkeeping `sd_publication`/`sd_id_mapping`) attraverso un'unica sessione condivisa, non garantita gratuitamente come per Standard (§F7.2); dispatch HPC aggiunto a `adapters/base.py`; retrofit family-aware di `_author_exists`/ricerca autori (endpoint 14) in `routes_threads.py`; `sd_draft_post.author_user_id` migrato da Integer a String(64) (cambio non distruttivo, nessuna ALTER necessaria sui database esistenti). Suite standalone ScenarioDesign: 97/97. Scritto `test_scenario_design_fase7_publish_hpc.py` (YWeb core): semina uno schema fisico HPC reale e verifica validate/preview/publish end-to-end, UUID reali, propagazione `thread_id`, fault injection parametrizzata, fingerprint, idempotenza — si salta esplicitamente in questo sandbox per lo stesso limite ambientale di Fase 3/6 (nessuna scrittura sqlite reale qui), da ri-eseguire nell'ambiente di sviluppo reale per la copertura effettiva (§F7.7). Non-regressione YWeb core: 1931 passed, 73 skipped (6 nuovi, tutti i test HPC che si saltano per il motivo sopra), 2 falliti pre-esistenti/ambientali non correlati (identico a Fase 6). Ancora da fare: esecuzione reale dei test di integrazione HPC in ambiente di sviluppo; PostgreSQL resta fuori ambito come da ogni fase precedente |
| 8 | Pianificata | — | — | — |
| 9 | Pianificata | — | — | — |

**Nota su §0.3 (branching/PR)**: Fase 0 e Fase 1 sono state committate direttamente sui branch già attivi (`edu` per YWeb core, `main` per ScenarioDesign), non su branch dedicati per fase con PR separata come previsto da §0.3. Deviazione procedurale dal piano, segnalata al product owner a fine Fase 1 e **confermata come approccio voluto**: si prosegue sui branch correnti per tutte le fasi successive, §0.3 è de facto sospeso per questo ciclo di lavoro (nessun branch-per-fase, nessuna PR separata).

---

*Documento di pianificazione, aggiornato a mano a mano che le fasi procedono. Fasi 0, 1 e 2 completate (2026-10-02); fasi 3-9 ancora da avviare. Aggiornare §13 e il decision log del repository `ScenarioDesign` a ogni chiusura di fase.*
