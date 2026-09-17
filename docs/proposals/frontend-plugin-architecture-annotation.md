# Architettura a plugin per il frontend di YSocial — Proposta tecnica

**Stato:** proposta di design, non ancora implementata.
**Ambito:** frontend di `y_web` (piattaforma di microblogging), con caso d'uso guida "plugin di annotazione dei post".
**Data:** 2026-09-17

## 0. Contesto e vincoli osservati nel codebase

Questa proposta è stata elaborata leggendo direttamente il codice esistente in `y_web/`, per ancorare le scelte architetturali a pattern già in uso invece di introdurre convenzioni estranee al progetto. I vincoli rilevanti sono:

- **Stack**: Flask + Jinja2 lato server, nessun bundler/framework SPA. Ogni pagina (`feed.html`, `thread.html`, `profile.html`, …) include esplicitamente una lista fissa di `<script src="...">` in coda al documento. Coesistono jQuery (file storici come `global.js`, `async_updates.js`, con delega d'eventi `$(document).on('click', '.selector', fn)`) e moduli vanilla JS più recenti in stile IIFE (`mb-feed.js`, `mb-profile.js`, …) configurati via oggetti globali iniettati dal template, es. `window.YS_DATA_MB_FEED = {...}`.
- **Multi-tenancy dei dati**: due bind SQLAlchemy — `db_admin` (dati cross-esperimento: `Exps`, `Topic_List`, `Exp_Topic`, `ExpFrontendSettings`, `Admin_users`, …) e `db_exp` (dati del singolo esperimento: `Post`, `Interests`, `User_mgmt`, `Agent_Opinion`, …). Ogni esperimento ha il proprio database `db_exp`.
- **Esiste già un meccanismo di feature flag per‑esperimento**: la tabella `exp_frontend_settings` (`exp_id` PK/FK, `settings_json` TEXT, `updated_at`), il modello `ExpFrontendSettings` (`y_web/src/models/admin.py`), la funzione `_load_ui_settings(exp_id)` (`y_web/routes/social/helpers.py`) che restituisce un dizionario `ui` fuso con dei default, passato a ogni `render_template(..., ui=_load_ui_settings(exp_id))`, e un pannello admin dedicato (`/admin/frontend_settings`, `_frontend_settings.py`, `frontend_settings.html`). I template usano `{% if ui.annotation_topics %}` ecc. **Questo è il precedente diretto su cui innestare l'attivazione dei plugin per esperimento**: non lo sostituiamo, lo estendiamo con un meccanismo analogo ma dedicato ai plugin (si veda §1.4).
- **I "topic della simulazione"** sono il modello `Interests` (`db_exp`, `iid`, `interest`) collegati ai post tramite `Post_topics`, e alle preferenze utente tramite `User_interest`. Il catalogo cross‑esperimento è `Topic_List`/`Exp_Topic` (`db_admin`). Esiste già un'assegnazione **umana** di opinione per topic: la card "Topics & Opinions" in `edit_profile.html` fa scegliere all'utente, per ciascun topic assegnato all'esperimento, un livello di interesse (slider a 4 livelli) e un'opinione, salvati via `POST /update_topic_preferences/<user_id>`. Il plugin di annotazione riusa la stessa fonte dati (topic dell'esperimento) e uno stile di interazione coerente (slider/valore discreto), invece di inventare un paradigma nuovo.
- **L'opinione "di modello"** è già rappresentata come valore numerico continuo (`Agent_Opinion.opinion`, `REAL`) prodotto dagli agenti simulati, e come etichetta categorica (`positive`/`negative`/`neutral`) nei chip topic mostrati in `posts.html`/`thread-post.html` (annotazione automatica via `ContentAnnotator`, LLM‑based, in `y_web/src/llm/content_annotation.py`). Il plugin introduce un'annotazione **manuale/umana**, concettualmente parallela ma distinta: non va confusa con l'annotazione automatica esistente (che alimenta già una pagina di analytics, `admin/annotation_analytics.html`).
- **I commenti sono post**: `Post.comment_to` (default `-1`) e `Post.thread_id` fanno sì che un commento sia una riga `Post` come qualsiasi altro contenuto. Questo semplifica il modello dati del plugin: un'unica FK verso `post.id` copre sia i post che i commenti, senza bisogno di due tabelle di annotazione parallele.
- **Markup dei post**: ogni post nel feed/nella thread è renderizzato come `<div id="feed-post-{post_id}" class="card is-post">` con dentro `<div class="content-wrap" id="post-{post_id}">`, una sezione `.post-annotation-section` (chip automatici) e una `.post-action-section` (like/dislike/share/commenti). Questi id/classi sono lo **slot di aggancio** naturale per l'iniezione client‑side del controllo di annotazione (§1.6, §4).
- **Contenuto caricato dinamicamente**: `infinite-scroll.js` e `async_updates.js` inseriscono nuovi nodi `.card.is-post` nel DOM dopo il caricamento iniziale (scroll infinito, refresh automatico del feed). Qualunque meccanismo di plugin deve funzionare anche su questi nodi aggiunti a runtime, non solo su quelli presenti al load.
- **Autenticazione**: Flask‑Login; `current_user.username` identifica sia l'account dashboard (`Admin_users`) sia, per lookup, l'utente "in‑simulazione" (`User_mgmt`) con cui si sta navigando il frontend pubblico. Il CSRF di Flask‑WTF nel repo risulta applicato ai form, non alle chiamate AJAX/JSON esistenti (nessun token CSRF è iniettato/spedito dal JS attuale): le nuove API dei plugin seguiranno la stessa convenzione già in uso, salvo diversa indicazione del team in fase di implementazione.

Questi vincoli motivano le scelte descritte nelle sezioni seguenti: l'obiettivo è un sistema di plugin che **si comporta come un'estensione naturale di ciò che esiste già** (stesso stile di configurazione per esperimento, stesso stile di delega eventi, stesso stile di risposta JSON), non come un framework parallelo.

---

## 1. Architettura generale del sistema di plugin

### 1.1 Principi guida

1. **Opt‑in per esperimento, disattivato di default.** Un plugin installato nell'istanza non è visibile/attivo in nessun esperimento finché un amministratore non lo abilita esplicitamente per quell'esperimento.
2. **Isolamento dal markup principale.** Nessun template esistente (`feed.html`, `posts.html`, `thread-post.html`, `profile.html`, …) viene modificato per "sapere" di un plugin specifico. Esiste un unico punto di innesto generico, già presente in ogni pagina, che carica ciò che serve **se e solo se** qualche plugin è attivo.
3. **Costo marginale nullo quando disattivato.** Nessuna query, nessun asset, nessun nodo DOM aggiuntivo se il plugin non è abilitato per l'esperimento corrente (dettagliato in §5).
4. **Coerenza con i pattern esistenti.** Stesso stile per: configurazione per esperimento (estende `ExpFrontendSettings`), delega degli eventi DOM (`document`‑level, selettori namespaced), forma delle risposte JSON (`{"ok": true/false, ...}`), permessi admin (`check_privileges`).
5. **Plugin come unità autonoma e removibile.** Un plugin è una cartella autocontenuta (manifest + asset + eventuale blueprint + eventuale migrazione dati) che può essere aggiunta o rimossa senza toccare il codice del "core" applicativo, e senza lasciare residui quando disinstallato (le sue tabelle dati restano isolate e opzionalmente droppabili).

### 1.2 Anatomia di un plugin

Un plugin è una directory sotto un nuovo percorso `y_web/plugins/<plugin_id>/` (analogo concettualmente a `external/` per i moduli esterni, ma per estensioni frontend):

```
y_web/plugins/post_annotation/
├── manifest.json            # metadati, versione, permessi, superfici (surface) supportate
├── backend/
│   ├── __init__.py          # blueprint Flask opzionale, registrato solo se il plugin è installato
│   ├── models.py            # modelli SQLAlchemy dedicati (bind db_exp)
│   └── routes.py            # endpoint REST del plugin
├── frontend/
│   ├── plugin.js            # modulo IIFE, si registra presso YSPlugins (plugin-core)
│   └── plugin.css           # stili con prefisso di classe dedicato
├── templates/
│   └── admin_panel.html     # (opzionale) partial per un pannello di configurazione avanzato
└── migrations/
    └── 0001_create_tables.py
```

Il **manifest** è l'unica cosa che il core deve poter leggere senza importare codice Python del plugin (per popolare il registro anche se il plugin è disattivato):

```json
{
  "id": "post_annotation",
  "name": "Annotazione dei post",
  "version": "0.1.0",
  "description": "Etichettatura manuale di topic e opinione su post e commenti.",
  "surfaces": ["feed", "thread"],
  "frontend_entry": "frontend/plugin.js",
  "frontend_style": "frontend/plugin.css",
  "backend_blueprint": "y_web.plugins.post_annotation.backend:bp",
  "api_prefix": "post-annotation",
  "default_config": {
    "allow_multi_topic": true,
    "opinion_scale": "3-way"
  },
  "requires_role": "experiment_user"
}
```

- `surfaces`: le pagine/viste in cui il plugin va montato (mappate su una costante lato server, es. `feed.html` dichiara `surface="feed"`), così il loader inietta gli asset solo dove servono, non su ogni pagina dell'app (es. non nel pannello admin, non nel login).
- `backend_blueprint`: import path opzionale; se assente il plugin è puramente frontend (nessuna nuova route).
- `requires_role`: vincolo minimo di autorizzazione (utente di esperimento loggato, admin, ecc.), verificato sia server-side sia usato per decidere se iniettare gli asset.

### 1.3 Registro dei plugin (catalogo d'istanza)

Un plugin "installato" (presente in `y_web/plugins/`) non è automaticamente disponibile ovunque: viene prima **registrato** in una tabella cross‑esperimento, per bind `db_admin` (coerente con `Exps`, `ExpFrontendSettings`, `Topic_List`, che sono anch'essi dati d'istanza, non di singolo esperimento):

```python
class PluginRegistry(db.Model):
    """Catalogo dei plugin frontend installati in questa istanza di YSocial."""
    __bind_key__ = "db_admin"
    __tablename__ = "plugin_registry"

    id = db.Column(db.String(64), primary_key=True)     # slug, es. "post_annotation"
    name = db.Column(db.String(200), nullable=False)
    version = db.Column(db.String(20), nullable=False)
    manifest_json = db.Column(db.Text, nullable=False)   # copia del manifest al momento della sync
    status = db.Column(db.String(20), nullable=False, default="available")  # available|deprecated|broken
    discovered_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())
```

Il popolamento avviene tramite una **sincronizzazione idempotente all'avvio** (`PluginManager.discover_and_sync()`, chiamata in `y_web/__init__.py` dopo l'inizializzazione di `db`, analogamente a come oggi vengono seminati altri cataloghi di sistema): scansiona `y_web/plugins/*/manifest.json`, fa upsert in `plugin_registry`, marca come `broken` un plugin il cui manifest non parsa o il cui `backend_blueprint` non importa, e logga senza bloccare l'avvio dell'app (un plugin rotto non deve mai impedire il boot della piattaforma).

### 1.4 Attivazione e configurazione per esperimento

Specularmente a `exp_frontend_settings`, si introduce:

```python
class ExpPluginSettings(db.Model):
    """Stato di attivazione e configurazione di un plugin per un singolo esperimento."""
    __bind_key__ = "db_admin"
    __tablename__ = "exp_plugin_settings"

    exp_id = db.Column(db.Integer, db.ForeignKey("exps.idexp"), primary_key=True)
    plugin_id = db.Column(db.String(64), db.ForeignKey("plugin_registry.id"), primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    config_json = db.Column(db.Text, nullable=False, default="{}")  # override del default_config del manifest
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())
```

`(exp_id, plugin_id)` come chiave composita, esattamente come `exp_frontend_settings` usa `exp_id` come PK: stesso stile, granularità più fine (per plugin invece che un'unica riga per esperimento), perché ogni plugin ha una propria configurazione e un proprio ciclo di vita indipendente dagli altri.

Una funzione `_load_active_plugins(exp_id) -> list[PluginContext]` (nuovo modulo `y_web/src/plugins/loader.py`, stesso pattern di `_load_ui_settings`) restituisce, per l'esperimento corrente, solo i plugin con `enabled=True`, con il config fuso (`default_config` del manifest + `config_json` dell'esperimento). Questa funzione è l'unico punto da cui il resto dell'applicazione osserva "quali plugin sono vivi qui".

Il **pannello admin** riusa il pattern già collaudato di `/admin/frontend_settings`: una nuova voce `/admin/plugins` (blueprint `experiments`, stesso `check_privileges`) che elenca i plugin dal registro, per ciascuno mostra un toggle enable/disable per esperimento e un form generato dinamicamente dallo schema dei `default_config` (analogamente a come `frontend_settings.html` genera i controlli dai default). Nessuna nuova tecnologia UI: stesso markup, stesso JS di supporto (`admin-settings.js` esteso o un nuovo `admin-plugins.js` a fianco).

### 1.5 Ciclo di vita di un plugin

```
[installazione file]  →  discover_and_sync()  →  plugin_registry (status=available)
        │                                              │
        │                                admin abilita per esperimento X
        │                                              ▼
        │                                   exp_plugin_settings(exp_id=X, enabled=True)
        │                                              │
        │                        richiesta HTTP verso una pagina "surface" per X
        │                                              ▼
        │                              _load_active_plugins(X) → [post_annotation]
        │                                              │
        │                     template inietta un unico loader (§1.6) con i plugin attivi
        │                                              ▼
        │                          client: plugin-core.js monta plugin.js del plugin,
        │                          registra observer sul DOM, il plugin è "vivo" in pagina
        │                                              │
        │                     admin disabilita per l'esperimento X (o disinstalla il plugin)
        │                                              ▼
        │                    exp_plugin_settings.enabled=False → prossima request non lo carica più
        ▼
   rimozione della cartella plugin → discover_and_sync() marca "missing", righe exp_plugin_settings
   restano (storicamente informative) ma non hanno più effetto; un comando admin esplicito può
   fare cleanup (mai automatico, per non perdere configurazioni)
```

Da notare: la disattivazione è **immediata e non distruttiva** — i dati già raccolti da un plugin (es. le annotazioni salvate) restano nel proprio spazio dati anche a plugin disattivato, perché finalità dichiarata è il riuso per analisi successive (requisito esplicito del caso d'uso).

### 1.6 Punti di estensione frontend (extension points)

Si definisce un piccolo insieme chiuso di "slot" concettuali, ciascuno ancorato a un selettore stabile già esistente nel markup, così i plugin non devono conoscere i dettagli implementativi delle pagine:

| Slot | Superficie (`surfaces`) | Selettore di aggancio reale | Esempio d'uso |
|---|---|---|---|
| `post.card` | `feed`, `thread` | `.card.is-post` / `#feed-post-{id}` | evidenziazione hover, bottone di annotazione |
| `post.actions` | `feed`, `thread` | `.post-action-section` | aggiungere un'icona accanto a like/share |
| `post.meta` | `feed`, `thread` | `.post-annotation-section` | mostrare un badge "annotato" |
| `sidebar.profile` | `profile` | area a fianco della card "Topics & Opinions" | pannelli di riepilogo per un plugin |
| `admin.panel` | `admin` | pagina dedicata sotto `/admin/plugins/<id>` | configurazione avanzata plugin-specifica |

Il plugin dichiara nel manifest su quali `surfaces` opera; il core, lato client, espone helper per agganciarsi a questi slot senza che il plugin debba fare query‑selector fragili sparsi nel proprio codice (dettaglio in §4.3).

### 1.7 Autorizzazioni

Tre piani distinti, da non confondere:

1. **Chi può installare un plugin nell'istanza** — operazione di filesystem/deploy (copiare una cartella sotto `y_web/plugins/`), riservata a chi ha accesso all'ambiente server; non esposta via UI in questa fase. `discover_and_sync()` è idempotente e sicura da rieseguire.
2. **Chi può abilitarlo per un esperimento e configurarlo** — solo gli account amministratore (`Admin_users` con privilegi verificati da `check_privileges`, stesso guard usato da tutte le route di `/admin/**`), dal pannello `/admin/plugins`.
3. **Chi può usarlo mentre naviga il frontend pubblico** — determinato dal `requires_role` del manifest e verificato sia server-side (l'endpoint del plugin richiede `@login_required` e verifica il ruolo) sia client-side (il loader non inietta gli asset per un utente che non soddisfa il requisito, es. un plugin riservato ai soli account "ricercatore"). Per il plugin di annotazione, `requires_role: experiment_user` significa: chiunque sia autenticato come utente dell'esperimento (`User_mgmt`) può annotare — coerente con il fatto che like/commenti/post sono già disponibili a quel livello di autenticazione.

A livello di **sandboxing lato server**, ogni plugin backend è montato come blueprint Flask con prefisso obbligatorio `/<int:exp_id>/api/plugins/<plugin_id>/...`: due plugin non possono collidere sulle route perché il loro namespace include sempre il proprio `plugin_id`. A livello dati, ogni plugin usa tabelle proprie con prefisso `plugin_<plugin_id>_...` (bind `db_exp` se i dati sono per‑esperimento, `db_admin` se sono di configurazione/cross‑esperimento), mai tabelle condivise con il core: questo è ciò che rende un plugin removibile senza side‑effect su `Post`, `Interests`, ecc.

---

## 2. Scelte implementative consigliate

### 2.1 Isolamento dei plugin

- **Naming rigorosamente prefissato**: ogni classe CSS, id DOM, evento custom ed endpoint introdotto da un plugin porta il prefisso `ys-plugin-<plugin_id>-` (es. `ys-plugin-post_annotation-btn`). Questo evita per costruzione collisioni con le classi esistenti (`.like-button`, `.card`, `.content-wrap`, …), che il plugin non deve **mai** riusare o ridefinire.
- **Nessun inline nei template principali**: l'unico punto in cui un template esistente viene toccato è l'aggiunta, una tantum, di un singolo `{% include "shared/plugin_loader.html" %}` in coda alle pagine con `surfaces` rilevanti (`feed.html`, `thread.html`, `profile.html`). Questo include non conosce alcun plugin specifico: itera su `_load_active_plugins(exp_id)` e genera i tag necessari. Aggiungere/rimuovere/modificare un plugin non richiede mai toccare `feed.html`, `posts.html`, `thread-post.html` di nuovo.
- **CSS scoping**: oltre al prefisso di classe, gli elementi iniettati dal plugin nel DOM esistente (es. il bottone di annotazione) vengono creati come nodi a sé stanti con stile inline minimo + classe prefissata, non tramite modifica delle classi esistenti sulla card. Dove il plugin disegna superfici proprie e isolate (popover, pannello admin) si valuta l'uso di uno **Shadow DOM** (`element.attachShadow({mode:'open'})`) per garantire zero collisioni di stile in entrambe le direzioni (il tema dell'app non trapela nel plugin, lo stile del plugin non trapela nell'app) — consigliato per il popover di annotazione, opzionale per badge minuscoli.
- **Isolamento JS**: ogni plugin è un IIFE che espone un solo simbolo globale namespaced (`window.YSPlugin_post_annotation`), registrato presso il core (`YSPlugins.register(...)`), mai variabili globali libere.

### 2.2 Gestione dello stato

- Lo stato di un plugin vive **esclusivamente** dentro il proprio modulo IIFE (closure), mai in variabili globali condivise con `MB_FEED` o altri moduli esistenti.
- Comunicazione core → plugin e plugin → pagina avviene solo tramite **eventi DOM custom** (`CustomEvent`), mai chiamata diretta di funzioni tra moduli: il core emette `ys-plugin:post-mounted` quando una nuova card entra nel DOM (iniziale o da infinite scroll/refresh), i plugin ascoltano; un plugin può emettere un proprio evento (es. `ys-plugin:post_annotation:saved`) che altri plugin — mai il core stesso — possono opzionalmente ascoltare. Questo disaccoppia totalmente i plugin fra loro e dal codice esistente: rimuovere un plugin non lascia mai un "listener orfano" che referenzia qualcosa che non esiste più, perché nessuno chiama funzioni di un plugin per nome.
- Nessuno stato di plugin viene persistito in `localStorage`/`sessionStorage` per dati che contano ai fini dell'analisi: qualunque cosa debba sopravvivere oltre la sessione del browser va salvata via API sul backend (§2.3), non lato client.

### 2.3 Comunicazione con backend/API

- Convenzione URL fissa: `/<int:exp_id>/api/plugins/<plugin_id>/<resource>`, montata come blueprint Flask con `url_prefix` calcolato dal manifest, registrata da `PluginManager` solo per i plugin il cui backend importa correttamente.
- Formato di risposta coerente con lo stile già in uso in `_frontend_settings.py`: `{"ok": true, "data": {...}}` in successo, `{"ok": false, "error": "..."}` in errore, con status code HTTP appropriato (400/403/404).
- Autenticazione: `@login_required` di Flask‑Login, stesso meccanismo di sessione del resto dell'app; nessun sistema di token separato per i plugin.
- Le chiamate dal client usano `fetch()` con lo stesso stile "credentials: same-origin implicito" già usato implicitamente dalle chiamate `$.ajax` esistenti (nessun CSRF token da aggiungere, salvo che il team decida di introdurlo contestualmente per tutte le API, plugin incluse).

### 2.4 Caricamento condizionale

- **Un solo loader per pagina**, non uno per plugin: `templates/shared/plugin_loader.html`, incluso una volta, che:
  1. riceve dal contesto Jinja la lista dei plugin attivi per l'esperimento e rilevanti per la `surface` corrente (calcolata lato route, es. `surface="feed"` in `microblogging.py` quando renderizza `feed.html`);
  2. se la lista è vuota, non emette **nulla** (nessun tag, nessuno script);
  3. se non è vuota, emette prima sempre `plugin-core.js` (una sola volta, cacheable, invariato indipendentemente dai plugin attivi), poi un blocco `<script>window.YS_PLUGINS = {...}</script>` con id, config e `apiBase` per ciascun plugin attivo (stesso pattern di `window.YS_DATA_MB_FEED`), poi un `<link>`/`<script defer>` per ciascun asset di ciascun plugin attivo.
- **`plugin-core.js` è sempre incluso in fondo alla pipeline di script esistente** (poche centinaia di byte, cacheabile, nessuna dipendenza), ma fa immediatamente return se `window.YS_PLUGINS` è assente o vuoto: questo è ciò che garantisce il costo marginale nullo (§5) senza dover condizionare anche l'inclusione del core stesso.
- Gli script dei plugin usano l'attributo `defer`, così non bloccano il rendering e vengono eseguiti in ordine dopo il parsing, dopo `plugin-core.js`.

### 2.5 Compatibilità con il frontend esistente

- **Un solo punto di modifica ai template esistenti**, il già citato include universale; nessuna dipendenza da bundler/build step aggiuntivo, coerente con l'assenza di uno strumento simile nel resto del progetto.
- **Sopravvivenza al contenuto dinamico**: `plugin-core.js` registra un singolo `MutationObserver` sul contenitore dei post (`#posts-container`, lo stesso id già usato da `MB_FEED`/`InfiniteScroll`) che rileva l'aggiunta di nuovi `.card.is-post` (da scroll infinito o da refresh automatico) ed emette `ys-plugin:post-mounted` per ciascuno, sia per i nodi presenti al load iniziale sia per quelli aggiunti dopo. I plugin non devono mai fare polling o reimplementare la propria logica di rilevamento DOM.
- **Nessuna interferenza con gli handler esistenti**: i plugin non registrano mai listener su selettori usati dal core (`.like-button`, `.share-button`, `.fab-wrapper.is-comment`, …) e i propri controlli, quando cliccati, chiamano sempre `event.stopPropagation()` limitatamente al proprio nodo (mai `stopImmediatePropagation` a livello di card), cosicché un click sul bottone di annotazione non attivi accidentalmente l'apertura del post o altre azioni, ma un click altrove sulla card continui a comportarsi esattamente come oggi.
- **Nessuna modifica a `Post`, `Interests`, `Agent_Opinion` o altre tabelle core**: i plugin leggono da queste tabelle in sola lettura quando serve (es. elenco topic), ma scrivono solo nelle proprie tabelle dedicate.

### 2.6 Performance

- Zero richieste HTTP aggiuntive quando nessun plugin è attivo (nessun asset referenziato).
- Un'unica query aggiuntiva per request quando ci sono plugin potenzialmente attivi (`_load_active_plugins`, analoga in costo a `_load_ui_settings`, già eseguita oggi su ogni pagina — quindi il costo marginale reale è un secondo `SELECT` su una tabella piccola, cacheabile per la durata della request).
- Asset dei plugin serviti come file statici versionati (`/static/plugins/<plugin_id>/<version>/plugin.js`) per sfruttare la cache del browser tra una sessione e l'altra.
- Il `MutationObserver` del core osserva solo il contenitore dei post (non `document.body`) e processa i mutation record in un'unica callback batched, per non introdurre overhead percepibile durante lo scroll infinito.

---

## 3. Modello dati e API per il plugin di annotazione

### 3.1 Tabelle dedicate (bind `db_exp`, per‑esperimento)

Le annotazioni sono dati **per‑esperimento** (come `Post`, `Interests`, `Agent_Opinion`), quindi vivono nel database dell'esperimento, non in `db_admin`. Si introducono due tabelle, non una sola, per separare l'evento di annotazione (chi, quando, su quale post) dai suoi dettagli per topic (un'annotazione può coprire più topic, ciascuno con la propria opinione):

```python
class PluginPostAnnotation(db.Model):
    """Un evento di annotazione manuale su un post o commento (plugin post_annotation)."""
    __bind_key__ = "db_exp"
    __tablename__ = "plugin_post_annotation"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    annotator_user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=True)
    annotator_admin_username = db.Column(db.String(80), nullable=True)  # provenienza se annotato da account dashboard
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)  # soft delete: si conserva per analisi


class PluginPostAnnotationTopic(db.Model):
    """Coppia (topic, opinione) associata a una singola annotazione."""
    __bind_key__ = "db_exp"
    __tablename__ = "plugin_post_annotation_topic"

    id = db.Column(db.Integer, primary_key=True)
    annotation_id = db.Column(db.Integer, db.ForeignKey("plugin_post_annotation.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)
    opinion_value = db.Column(db.REAL, nullable=True)     # scala continua -1.0..1.0, coerente con Agent_Opinion.opinion
    opinion_label = db.Column(db.String(10), nullable=True)  # 'positive'|'neutral'|'negative', coerente con i chip in posts.html

    __table_args__ = (
        db.UniqueConstraint("annotation_id", "topic_id", name="uq_annotation_topic"),
    )
```

Motivazioni di design:

- **Due tabelle, non una riga JSON**: mantenere `(annotation_id, topic_id)` come righe distinte rende triviale interrogare "quante annotazioni menzionano il topic X" o "distribuzione delle opinioni sul topic Y" con semplice SQL/`GROUP BY`, requisito esplicito ("progettata in modo da poter essere interrogata e riutilizzata per analisi successive"). Un blob JSON per annotazione renderebbe queste query molto più costose.
- **`opinion_value` REAL + `opinion_label` categorico, entrambi opzionali ma non entrambi nulli** (vincolo applicato in fase di validazione API, non a livello di `CheckConstraint` per restare compatibili con SQLite): permette sia un'interfaccia utente a slider continuo (coerente con `Agent_Opinion.opinion`, comparabile direttamente in analisi umano‑vs‑modello) sia una scelta rapida a 3 valori (coerente con i chip `is-positive/is-neutral/is-negative` già mostrati sui post). La UI di riferimento (§4) userà uno slider a 3 posizioni che scrive sia il valore numerico (-1/0/1) sia l'etichetta, così entrambe le colonne sono sempre coerenti e le query di analisi possono scegliere quale usare.
- **`annotator_user_id` nullable + `annotator_admin_username`**: chi annota è quasi sempre l'utente in‑simulazione con cui si è autenticati (`User_mgmt`, stesso soggetto che mette "like" o pubblica un post), ma un account amministratore può annotare in modalità anteprima/verifica senza un `User_mgmt` associato: si registra allora solo `annotator_admin_username`, per non perdere la provenienza.
- **`is_deleted` (soft delete)**: un'annotazione ritirata dall'utente resta in tabella (con `is_deleted=True`) invece di essere cancellata fisicamente, per non invalidare eventuali analisi già in corso che referenziano l'`id`; le query di lettura "correnti" filtrano su `is_deleted=False`, le query di analisi storica possono scegliere di includerla.
- **FK verso `post.id`**, non una tabella separata per i commenti: dato che `comment_to != -1` marca già i commenti come righe `Post`, la stessa tabella di annotazione copre entrambi i casi senza duplicazione di schema o di codice.
- Migrazione dedicata `y_web/plugins/post_annotation/migrations/0001_create_tables.py`, seguendo esattamente lo stesso stile procedurale (SQLite + PostgreSQL, controllo idempotente dell'esistenza tabella) già usato in `y_web/migrations/add_frontend_settings_table.py`.

### 3.2 Registro e attivazione (bind `db_admin`)

Già descritti in §1.3/§1.4: `plugin_registry`, `exp_plugin_settings`. Per il plugin di annotazione, `default_config` copre almeno:

```json
{
  "max_topics_per_annotation": 5,
  "opinion_scale": "3-way",
  "require_at_least_one_topic": true,
  "allow_edit_own_annotations": true,
  "show_annotation_count_badge": true
}
```

### 3.3 Endpoint REST

Blueprint montato su `/<int:exp_id>/api/plugins/post-annotation/`:

| Metodo | Path | Scopo | Note |
|---|---|---|---|
| `GET` | `/topics` | Elenco dei topic disponibili per l'esperimento corrente | Riusa la stessa fonte dati della card "Topics & Opinions" di `edit_profile.html` (join `Exp_Topic`/`Topic_List` per il catalogo, `Interests` nel `db_exp` per gli id usati dai post) — nessuna logica nuova di lookup topic. |
| `GET` | `/posts/<int:post_id>/annotations` | Annotazioni esistenti sul post: proprie dell'utente corrente sempre; quelle altrui solo se il config/ruolo lo consente (di default, in fase di prototipo, ogni utente vede solo le proprie) | Risposta: lista di `{annotation_id, topics:[{topic_id, topic_name, opinion_value, opinion_label}], note, created_at}` |
| `POST` | `/posts/<int:post_id>/annotations` | Crea una nuova annotazione (o sostituisce quella esistente dell'utente corrente su quel post, se `allow_edit_own_annotations`) | Payload: `{"topics": [{"topic_id": 3, "opinion_value": 1.0, "opinion_label": "positive"}, ...], "note": "..."}`. Validazione server-side: `topic_id` deve appartenere ai topic dell'esperimento; almeno un topic se `require_at_least_one_topic`. |
| `DELETE` | `/posts/<int:post_id>/annotations/<int:annotation_id>` | Ritira la propria annotazione (soft delete) | Verifica che `annotation_id` appartenga all'utente richiedente (o che sia admin). |
| `GET` | `/admin/export` *(sotto `/admin/plugins/post-annotation/export`, non nel prefisso pubblico)* | Export CSV/JSON per esperimento, per analisi offline | Solo admin (`check_privileges`); include join con `Post`, `Interests`, `User_mgmt` per rendere l'export immediatamente leggibile senza dover ricostruire i riferimenti. |

Tutte le risposte seguono `{"ok": true, "data": ...}` / `{"ok": false, "error": "..."}`, coerentemente con `_frontend_settings.py`.

### 3.4 Riuso e confronto con dati esistenti

Poiché `opinion_value` usa la stessa scala di `Agent_Opinion.opinion` e `topic_id` referenzia lo stesso `interests.iid`, è possibile — come query di analisi successiva, non come funzionalità del prototipo minimo — confrontare l'opinione "percepita da un umano che legge il post" (`PluginPostAnnotationTopic.opinion_value`) con l'opinione "espressa dall'agente autore" (`Agent_Opinion.opinion` per lo stesso `id_post`/`topic_id`) e con l'etichetta prodotta dall'annotazione automatica LLM (`Post_topics` + logica di sentiment in `content_annotation.py`). Questo triangolo (umano/agente/LLM) è probabilmente il valore analitico principale del plugin, ed è **gratuito** grazie alla scelta di riusare le stesse convenzioni di id e scala invece di inventarne di nuove.

---

## 4. Struttura dei componenti e flusso di interazione utente

### 4.1 `plugin-core.js` (sempre presente, generico)

API minima esposta (nessuna dipendenza esterna, vanilla JS, coerente con lo stile IIFE di `mb-feed.js`):

```js
var YSPlugins = (function () {
  var registry = {};       // plugin_id -> module esposto da register()
  var mounted = new WeakSet();

  function init() {
    var cfg = window.YS_PLUGINS;
    if (!cfg || !cfg.active || cfg.active.length === 0) return; // no-op totale

    observePostContainer();
    // notifica i post già presenti al load iniziale
    document.querySelectorAll('.card.is-post').forEach(function (el) { notifyMounted(el); });
  }

  function register(pluginId, module) { registry[pluginId] = module; }

  function observePostContainer() {
    var container = document.getElementById('posts-container') || document.body;
    var mo = new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        m.addedNodes && m.addedNodes.forEach(function (node) {
          if (node.nodeType !== 1) return;
          if (node.matches && node.matches('.card.is-post')) notifyMounted(node);
          node.querySelectorAll && node.querySelectorAll('.card.is-post').forEach(notifyMounted);
        });
      });
    });
    mo.observe(container, { childList: true, subtree: true });
  }

  function notifyMounted(cardEl) {
    if (mounted.has(cardEl)) return;
    mounted.add(cardEl);
    var postId = (cardEl.id || '').replace('feed-post-', '');
    cardEl.dispatchEvent(new CustomEvent('ys-plugin:post-mounted', { bubbles: true, detail: { postId: postId, cardEl: cardEl } }));
  }

  function api(pluginId, path, opts) {
    var base = (window.YS_PLUGINS.apiBase || '') + '/' + pluginId + path;
    return fetch(base, Object.assign({ credentials: 'same-origin' }, opts || {}));
  }

  document.addEventListener('DOMContentLoaded', init);
  return { register: register, api: api };
})();
```

Punti chiave: `init()` ritorna immediatamente se non ci sono plugin attivi (garanzia di §5); l'evento `ys-plugin:post-mounted` è l'unico canale con cui i plugin scoprono i post, sia al load sia dopo scroll infinito/refresh; `api()` centralizza la convenzione URL di §2.3 così ogni plugin non la reimplementa.

### 4.2 `plugin.js` del plugin di annotazione

Modulo IIFE registrato presso il core, che ascolta `ys-plugin:post-mounted` e per ciascuna card:

1. aggiunge un listener `mouseenter`/`mouseleave` sul nodo `.card.is-post` che applica/rimuove una classe `ys-plugin-post_annotation-highlight` (bordo/ombra evidenziata, definita in `plugin.css`, mai sovrascrivendo lo stile esistente della card);
2. su `mouseenter`, se non già presente, inietta un piccolo pulsante discreto (icona "tag/etichetta") posizionato in overlay nell'angolo della card (`position: absolute`, dentro un contenitore proprio inserito dal plugin, non dentro `.post-action-section`, per non alterare il layout esistente dei bottoni like/share/commento);
3. il pulsante, al click, ferma la propagazione solo su se stesso e apre un **popover** (idealmente in Shadow DOM) con: elenco dei topic dell'esperimento (da `GET /topics`, con caching in memoria per la durata della pagina), selezione multipla, e per ciascun topic selezionato uno slider a 3 posizioni (Negativa / Neutra / Positiva) che scrive `opinion_value ∈ {-1, 0, 1}` e la label corrispondente — stessa metafora della card "Topics & Opinions" già presente in `edit_profile.html`, per continuità di UX;
4. al submit, chiama `YSPlugins.api('post_annotation', '/posts/' + postId + '/annotations', {method:'POST', body: JSON.stringify(payload)})`; in caso di successo mostra un piccolo badge "Annotato" accanto al pulsante (senza refresh di pagina, senza toccare `.post-annotation-section` esistente) e chiude il popover; in caso di errore mostra un messaggio inline nel popover, la card resta invariata.

### 4.3 Flusso utente

```
Utente naviga il feed
        │
        ▼
Passa il mouse su un post → card evidenziata (bordo) + appare il pulsante "annotate" discreto
        │
        ▼
Click sul pulsante → popover con elenco topic dell'esperimento
        │
        ▼
Seleziona uno o più topic → per ciascuno sceglie l'opinione percepita (positiva/neutra/negativa)
        │
        ▼
Conferma → richiesta POST asincrona → badge "Annotato ✓" mostrato sul post, popover chiuso
        │
        ▼
Il resto dell'interazione con il post (apertura thread, like, dislike, condivisione,
apertura commenti, navigazione al profilo dell'autore) continua a funzionare esattamente
come prima: nessuno di questi elementi è stato toccato dal plugin.
```

Se l'utente ha già annotato quel post, riaprendo il popover vede precompilati i topic/opinioni salvati (letti da `GET /posts/<id>/annotations`) e può modificarli (se `allow_edit_own_annotations`) o ritirarli.

### 4.4 Perché questo non interferisce con le interazioni esistenti

- Il pulsante di annotazione è un nodo **aggiunto**, non una modifica di un nodo esistente: non altera gli handler già collegati a `.like-button`, `.share-button`, `.fab-wrapper.is-comment`, ecc.
- L'evidenziazione hover usa una classe propria applicata alla card (`ys-plugin-post_annotation-highlight`), mai una classe esistente: non interferisce con eventuali stili `:hover` già presenti né con il dropdown "⋮" già presente in alto a destra della card.
- `event.stopPropagation()` è invocato **solo** all'interno del gestore click del pulsante del plugin, mai a livello dell'intera card: un click al di fuori del pulsante continua a comportarsi come oggi (es. click sul testo del post, sul nome utente, ecc. restano invariati).
- Il popover, se implementato in Shadow DOM, non può in alcun modo essere raggiunto dai selettori CSS globali del tema (`.card`, `.dropdown-menu`, …), eliminando ogni rischio di collisione di stile in entrambe le direzioni.

---

## 5. Garanzie di invarianza in assenza di plugin attivi

Requisito esplicito: con nessun plugin attivo per un dato esperimento, comportamento e prestazioni dell'applicazione **non devono cambiare** rispetto a oggi. Misure concrete:

1. **Zero query aggiuntive di rilievo**: `_load_active_plugins(exp_id)` esegue un singolo `SELECT` su `exp_plugin_settings WHERE exp_id = ? AND enabled = true`, tabella piccola e indicizzata sulla stessa chiave (`exp_id`) già usata da `exp_frontend_settings`; se il risultato è vuoto, il costo aggiuntivo rispetto a oggi è quello di una query indicizzata su una tabella con poche righe per esperimento — trascurabile rispetto al resto del rendering di pagina (che già esegue decine di query per popolare il feed).
2. **Zero markup aggiuntivo**: `shared/plugin_loader.html`, se la lista dei plugin attivi per la `surface` corrente è vuota, non emette alcun tag HTML (nessun commento, nessuno spazio significativo): il DOM prodotto è byte‑per‑byte identico a quello di oggi, verificabile con un diff testuale della risposta HTTP.
3. **Zero richieste HTTP aggiuntive**: nessun `<script>`/`<link>` di plugin viene referenziato; il browser non effettua alcuna richiesta in più.
4. **`plugin-core.js` come unica eccezione, ed è progettato per essere innocuo**: se si sceglie di includerlo sempre (per evitare persino il costo di un `{% if %}` sull'inclusione dello script stesso), il file è minuscolo, cacheabile in modo permanente (versionato nell'URL), e il suo `init()` ritorna immediatamente se `window.YS_PLUGINS` è assente/vuoto — nessun `MutationObserver` viene registrato, nessun costo a runtime. In alternativa più conservativa, si può condizionare anche l'inclusione di `plugin-core.js` alla presenza di almeno un plugin attivo per quella `surface`, eliminando anche questo singolo file quando non serve: si raccomanda questa seconda opzione per il prototipo iniziale, per rendere la garanzia "zero aggiunte" verificabile per costruzione e non solo per comportamento a runtime.
5. **Nessuna riga aggiunta alle tabelle core**: un plugin disattivato/disinstallato non tocca mai `post`, `interests`, `agent_opinion`, `user_mgmt`; le uniche righe che esistono sono nel proprio namespace (`plugin_post_annotation*`) e in `plugin_registry`/`exp_plugin_settings`.
6. **Contratto formale di isolamento** (da verificare in code review per ogni nuovo plugin, non solo per quello di annotazione): un plugin disattivato per un esperimento non deve mai (a) rispondere sulle proprie route con altro che 403/404, (b) apparire in alcuna risposta HTML di quell'esperimento, (c) essere osservabile lato client in alcun modo (`window.YS_PLUGINS` non lo elenca).

### 5.1 Test di non regressione consigliati

- **Snapshot/diff del DOM**: per ogni `surface` (`feed`, `thread`, `profile`), un test che renderizza la pagina con zero plugin registrati e con un plugin registrato-ma-disattivato, e verifica che l'HTML prodotto sia identico byte‑per‑byte in entrambi i casi (protegge sia da regressioni introdotte da `plugin_loader.html` sia da futuri plugin mal scritti).
- **Test di interazione esistente invariata**: riesecuzione della suite Playwright/E2E esistente (il repo ha già `.playwright-mcp`) con un plugin installato‑ma‑disattivato, verificando che like/dislike/share/commento/eliminazione post/navigazione producano le stesse richieste di rete e lo stesso stato finale della pagina di prima dell'introduzione del sistema di plugin.
- **Performance budget**: tempo di first render e numero di richieste di rete per `feed.html` misurati prima/dopo l'introduzione del loader, con soglia di tolleranza vicina a zero (es. ±1 query DB, 0 richieste HTTP, 0 KB di payload aggiuntivo) quando nessun plugin è attivo.
- **Test di attivazione/disattivazione a runtime**: abilitare un plugin per l'esperimento A e verificare che l'esperimento B (dove è disattivato) non lo veda in alcuna forma — protegge dal bug più pericoloso per un sistema "per esperimento": una condizione di scoping sbagliata che rende un plugin globale invece che opt‑in.

---

## 6. Roadmap incrementale

L'implementazione è organizzata in fasi via via più ambiziose, ciascuna con criteri di accettazione verificabili e senza mai lasciare l'applicazione in uno stato peggiore di prima di iniziare.

### Fase 0 — Fondamenta del sistema di plugin (nessun plugin reale)

- Introdurre `plugin_registry`, `exp_plugin_settings` (migrazioni SQLite + PostgreSQL, stile `add_frontend_settings_table.py`).
- Introdurre `PluginManager.discover_and_sync()`, chiamato all'avvio, con test che verifica che l'assenza della cartella `y_web/plugins/` (o una cartella vuota) non produce errori né voci nel registro.
- Introdurre `_load_active_plugins(exp_id)` (ritorna sempre lista vuota in questa fase, perché nessun plugin esiste ancora) e `shared/plugin_loader.html`, incluso in `feed.html`, `thread.html`, `profile.html`.
- **Criteri di accettazione**: con zero plugin installati, tutte le suite di test esistenti (`run_tests.py`, `pytest.ini`) passano invariate; diff del DOM delle pagine coinvolte è vuoto rispetto alla baseline pre‑modifica.
- **Test**: unit test su `PluginManager` (discovery con manifest valido/invalido/mancante); unit test su `_load_active_plugins` (nessun plugin → `[]`); test di integrazione Flask che verifica assenza di tag plugin nell'HTML.

### Fase 1 — Prototipo minimo del plugin di annotazione

- Tabelle `plugin_post_annotation`, `plugin_post_annotation_topic` (migrazione dedicata sotto `y_web/plugins/post_annotation/migrations/`).
- Blueprint minimo: solo `GET /topics` e `POST /posts/<id>/annotations` (niente edit, niente delete, niente export in questa fase).
- Frontend minimo: `plugin-core.js` + `plugin.js` con evidenziazione hover, pulsante, popover con **un solo topic selezionabile alla volta** e opinione a 3 valori; nessun badge "già annotato", nessun precaricamento delle annotazioni esistenti.
- Pannello admin minimale: un semplice toggle enable/disable per esperimento in `/admin/plugins` (senza editor di configurazione avanzata).
- **Criteri di accettazione**: con il plugin abilitato su un esperimento di prova, un utente può annotare un post con un topic e un'opinione, la riga compare correttamente nelle due tabelle; con il plugin disabilitato (anche sullo stesso esperimento), nessun elemento del plugin è visibile o raggiungibile (verifica manuale + test automatico); nessuna delle interazioni esistenti (like/dislike/share/commento/eliminazione/navigazione) cambia comportamento.
- **Test**: unit test backend (validazione payload, vincolo "topic deve appartenere all'esperimento", soft delete non ancora esposto ma schema pronto); test E2E minimo (hover → click → seleziona topic → submit → verifica riga in DB via query diretta nel test).
- **Anti-regressione**: eseguire l'intera suite E2E esistente con il plugin installato‑e‑disattivato prima di procedere alla Fase 2, per certificare che l'introduzione del codice del plugin (anche se inattivo) non abbia effetti collaterali.

### Fase 2 — Completamento funzionale

- Selezione multi‑topic per annotazione (`allow_multi_topic`), con vincolo `max_topics_per_annotation`.
- Editing e ritiro (soft delete) della propria annotazione; precaricamento delle annotazioni esistenti nel popover.
- Badge visivo "Annotato" sulla card quando l'utente corrente ha già annotato quel post.
- Estensione al surface `thread` (annotazione dei commenti, non solo dei post radice) — già supportata dallo schema dati (§3.1), qui si tratta solo di montare `plugin.js` anche su `thread.html` e verificare che il selettore `.card.is-post` copra correttamente anche i commenti nella pagina thread (`thread-post.html`).
- Gestione ruoli: eventuale distinzione fra "annotazione propria visibile solo a me" e "annotazioni aggregate visibili a tutti" (configurabile via `config_json`, di default privata).
- **Criteri di accettazione**: un utente può annotare, rivedere, modificare e ritirare le proprie annotazioni su post e commenti, sia nel feed sia nella vista thread; nessuna regressione sulle interazioni esistenti in nessuna delle due superfici.
- **Test**: casi limite (0 topic quando richiesto ≥1, superamento di `max_topics_per_annotation`, editing concorrente della stessa annotazione da due tab), test E2E su entrambe le superfici.

### Fase 3 — Analytics ed esportazione

- Endpoint admin `GET /admin/plugins/post-annotation/export` (CSV e JSON), con join `Post`/`Interests`/`User_mgmt` per un export "leggibile" senza post‑processing.
- Pannello admin di riepilogo (conteggio annotazioni per topic, distribuzione delle opinioni, confronto con `Agent_Opinion`/annotazione LLM automatica per lo stesso post/topic), costruito sullo stesso stile delle pagine analytics esistenti (`admin/annotation_analytics.html`, `admin-annotation-analytics.js`), senza però confondersi con l'annotazione automatica esistente (nomenclatura chiaramente distinta in UI: "Annotazioni manuali" vs "Annotazioni automatiche").
- **Criteri di accettazione**: un amministratore può esportare tutte le annotazioni di un esperimento in un formato direttamente caricabile in un notebook di analisi (coerente con l'uso di Jupyter già presente nel progetto, `src/system/jupyter_utils.py`); i numeri del pannello di riepilogo coincidono con query dirette sul database usate come baseline nei test.
- **Test**: correttezza dell'export su dataset di prova con annotazioni note; test di performance dell'export su un esperimento con volume realistico di post/annotazioni.

### Fase 4 — Hardening e generalizzazione

- Suite di test di non regressione automatizzata e obbligatoria in CI per **qualunque** nuovo plugin (non solo quello di annotazione): snapshot DOM a plugin disattivato, performance budget, verifica di scoping per esperimento.
- Documentazione per sviluppatori terzi ("come scrivere un nuovo plugin frontend"): struttura del manifest, convenzioni di naming, checklist di isolamento (§2.1), esempio minimo end‑to‑end basato sul plugin di annotazione come riferimento.
- Eventuale UI di gestione plugin più ricca nel pannello admin (upload di un plugin pacchettizzato, rollback a una versione precedente), fuori scope per il prototipo ma prevista come estensione naturale del registro già introdotto in Fase 0.
- **Criteri di accettazione**: un secondo plugin scritto da zero seguendo solo la documentazione, senza modificare codice core, si integra correttamente e passa la suite di non regressione al primo tentativo (prova indiretta che l'isolamento architetturale funziona davvero, non solo per il plugin che lo ha ispirato).

---

## Appendice — Riepilogo delle nuove tabelle

| Tabella | Bind | Scopo | Chiave |
|---|---|---|---|
| `plugin_registry` | `db_admin` | Catalogo dei plugin installati nell'istanza | `id` (slug) |
| `exp_plugin_settings` | `db_admin` | Attivazione/config di un plugin per un esperimento | `(exp_id, plugin_id)` |
| `plugin_post_annotation` | `db_exp` | Evento di annotazione manuale su un post/commento | `id` |
| `plugin_post_annotation_topic` | `db_exp` | Coppia (topic, opinione) di un'annotazione | `id`, unique `(annotation_id, topic_id)` |

Nessuna di queste tabelle introduce una foreign key verso strutture diverse da quelle già esistenti (`exps.idexp`, `post.id`, `interests.iid`, `user_mgmt.id`), a conferma che l'estensione si innesta sul modello dati attuale senza richiederne modifiche.


---

## Appendice — Scostamenti rispetto al documento originale (implementazione EducatYon, Fase 0/1)

Questa sezione documenta, come richiesto, gli scostamenti rilevanti tra le assunzioni del presente documento e quanto effettivamente implementato durante l'integrazione della suite EducatYon (branch `edu`), verificati confrontando le assunzioni con la struttura reale dei repository al momento del checkout.

1. **Repository di partenza vuoto.** Al momento dell'implementazione, `external/EducatYon` conteneva solo `README.md` (stub) e `.gitignore`: nessuna struttura `meta/`/`modules/` preesistente. L'intera struttura del manifest (`meta/info.json`, `meta/registry.json`) e dei moduli (`modules/post_annotation/{backend,frontend}`) è stata quindi creata da zero seguendo esattamente la convenzione descritta in questo documento (§ Layout suite), non adattata da un layout preesistente.

2. **Sistema di migrazione: Alembic è il meccanismo primario, non uno dei due alla pari.** Il documento originale non distingueva esplicitamente i due percorsi di migrazione già presenti in YWeb. In pratica, `y_web/__init__.py` sceglie Flask-Migrate/Alembic quando disponibile e ricade sul runner legacy (`run_migrations()` in `y_web/db_init/migrations.py`, script in `y_web/migrations/add_*.py`) solo quando Alembic non è importabile. Di conseguenza `educatyon_exp_module_settings` (tabella di configurazione, bind `db_admin`) è stata implementata con **entrambi** i percorsi: la revisione Alembic `0004_add_educatyon_exp_module_settings.py` come meccanismo primario, e `y_web/migrations/add_educatyon_module_settings.py` come fallback idempotente, esattamente sullo stesso modello già usato per `exp_frontend_settings`.

3. **Nessun `experiment_db_bind()` esplicito necessario nelle route del modulo.** Il documento ipotizzava che ogni query sul bind `db_exp` richiedesse un binding esplicito. In realtà YWeb espone già un hook globale `before_request` (`setup_experiment_context()` in `y_web/src/experiment/context.py`) che ribinda automaticamente `db_exp` quando la route ha `<int:exp_id>` nella propria URL rule. Le route del blueprint `post_annotation` (tutte montate sotto `/<int:exp_id>/api/plugins/educatyon/post_annotation/...`) beneficiano quindi di questo ribinding automatico "gratuito", senza bisogno di avvolgere ogni query in un context manager dedicato — semplificazione rispetto al codice di esempio nel corpo del documento.

4. **`Topic_List` / `Exp_Topic` sono bind `db_admin`, non `db_exp`.** L'elenco dei topic della simulazione (usato per popolare il popover di annotazione) non vive nel database dell'esperimento come inizialmente assunto, ma in tabelle admin-side; ottenere "i topic di un dato esperimento" richiede quindi un join `Exp_Topic` ⨝ `Topic_List` filtrato per `exp_id`, non una semplice query su `db_exp`. La route `GET .../topics` implementa questo join (con fallback a una lista di topic personalizzati via `custom_topics`, se configurata).

5. **Una sola tabella di configurazione per‑modulo, non due livelli (suite + modulo).** L'appendice del documento originale prevedeva `plugin_registry` (catalogo) + `exp_plugin_settings` (attivazione/config per esperimento) come coppia generica riusabile da qualunque plugin. Per la prima suite reale si è optato per una semplificazione: **una singola tabella** `educatyon_exp_module_settings` (bind `db_admin`, chiave composita `(exp_id, module_id)`, con `enabled` e `config_json`), dato che il "catalogo" dei moduli non necessita di persistenza — è ottenuto per lettura live del manifest (`meta/registry.json`), coerentemente con il pattern già collaudato in `y_agents_plugins`. Il nome delle tabelle applicative del modulo di annotazione è inoltre `plugin_educatyon_post_annotation(_topic)` (con prefisso di namespace `educatyon_`) anziché `plugin_post_annotation(_topic)`, per evitare collisioni qualora in futuro un'altra suite esterna definisse un modulo con lo stesso `module_id` (`post_annotation`).

6. **Migrazione JIT (just-in-time) per le tabelle del modulo, non in Alembic.** Le tabelle `plugin_educatyon_post_annotation`/`_topic` (bind `db_exp`, una per ciascun database di esperimento) non vengono create da una migrazione Alembic globale, ma da `ensure_module_schema()` — invocata solo quando un amministratore abilita il modulo per un esperimento specifico, tramite la funzione `migrate_sqlite_server()` fornita dal modulo stesso (`external/EducatYon/modules/post_annotation/backend/migrations.py`). Questo evita di creare tabelle inutilizzate in tutti gli esperimenti esistenti e mantiene la garanzia "impatto zero se non abilitato" anche a livello di schema del database.

Nessuno di questi scostamenti cambia le garanzie di compatibilità o isolamento descritte nel corpo del documento; riflettono unicamente dettagli implementativi emersi confrontando le assunzioni iniziali con la struttura reale del codice esistente.
