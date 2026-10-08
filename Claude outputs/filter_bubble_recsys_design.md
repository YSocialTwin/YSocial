# Filter Bubble Content Recommender — Documento di Design

**Progetto:** YWeb / YSocial — HPC Microblogging  
**Data:** 2026-09-16  
**Stato:** Bozza di progettazione  
**Nota:** Questo file non viene aggiunto al repository git.

---

## 1. Contesto e obiettivo

L'esperimento di microblogging HPC include una fase di onboarding in cui agli utenti umani viene chiesto di:
- specificare il **livello di interesse** per ciascun topic della simulazione (`interest_level ∈ [0.0, 1.0]`, salvato in `user_topic_interest`);
- indicare la propria **opinione** su ciascun topic (`opinion ∈ float`, salvato in `agent_opinion` con `tid = 0`).

L'obiettivo è realizzare un content recommender che sfrutti queste due sorgenti per costruire attorno all'utente umano una **filter bubble**: la sua timeline deve essere dominata da contenuti che parlano dei topic a lui più cari e che si allineano (o volutamente scontrano, a seconda del parametro di configurazione) con la sua visione del mondo.

Il sistema deve essere **invisibile agli agenti simulati**: non deve comparire tra i recommender selezionabili durante la creazione/configurazione di un client HPC, né deve essere assegnabile agli agenti nel population JSON.

---

## 2. Modello proposto: `FilterBubble`

### 2.1 Intuizione

Per ogni post `p` e ogni utente umano `u`, lo score complessivo è:

```
score(p, u) = Σ_{t ∈ topics(p)}  w_interest(u, t)  ×  w_opinion(u, t, p)
```

dove:

| Componente | Descrizione |
|---|---|
| `w_interest(u, t)` | Livello di interesse dell'utente per il topic `t` (`interest_level`), normalizzato |
| `w_opinion(u, t, p)` | Allineamento tra l'opinione dell'utente su `t` e la posizione del post |

### 2.2 Calcolo di `w_interest`

```python
w_interest(u, t) = interest_level[u][t]   # già in [0, 1]
# Se l'utente non ha espresso interesse per t → w = 0 → il post non riceve punteggio da t
```

### 2.3 Calcolo di `w_opinion`

L'allineamento è una **similarity gaussiana** tra l'opinione utente e quella del post:

```
w_opinion(u, t, p) = exp(-α × |opinion_u(t) - opinion_p(t)|²)
```

- `opinion_u(t)`: opinione dell'utente su `t`, letta da `agent_opinion` (tid=0, quello scritto all'onboarding)
- `opinion_p(t)`: sentiment del post su `t`, letto da `post_sentiment` (se disponibile) oppure stimato come media delle opinioni dell'autore del post sullo stesso topic
- `α` (parametro di ampiezza della bolla): default `α = 2.0`
  - `α` piccolo → bolla larga, opinioni diverse tolerate
  - `α` grande → bolla stretta, solo post molto allineati emergono
- Se l'utente non ha un'opinione su `t`, `w_opinion = 1.0` (solo il topic conta)
- Se il post non ha dati di sentiment per `t`, `w_opinion = 0.5` (valore neutro)

### 2.4 Score finale e ranking

```
final_score(p) = Σ_{t ∈ topics(p)} w_interest(u, t) × w_opinion(u, t, p)
```

I post vengono ordinati per `final_score` discendente.  
I post che ottengono `final_score = 0` (nessun topic in comune con gli interessi dell'utente) vengono relegati in coda, riempiendo la pagina con un fallback reverse-chrono.

---

## 3. Schema dei dati coinvolti

### 3.1 Database di simulazione (exp DB — SQLite)

| Tabella | Chiavi rilevanti | Ruolo |
|---|---|---|
| `user_topic_interest` | `user_id, topic_id, interest_level` | Interesse utente per topic (onboarding) |
| `agent_opinion` | `agent_id, tid, topic_id, opinion` | Opinione utente su topic (`tid=0` = onboarding) |
| `post_topics` | `post_id, topic_id` | Mapping post → topic/i trattati |
| `post_sentiment` | `post_id, topic_id, compound` | Sentiment (VADER) del post per topic |
| `post` | `id, user_id, content, round` | Post degli agenti |

### 3.2 Database admin (dashboard DB)

| Tabella | Dettaglio |
|---|---|
| `content_recsys` | Aggiungere riga con `enabled = 'HumanOnly'` |
| `interests` | Mappa `iid ↔ topic name`, ponte tra dashboard e sim DB |

---

## 4. Dettagli implementativi

### 4.1 Registrazione del modo nel database

Aggiungere in `data_schema/postgre_dashboard.sql` e nella migration:

```sql
INSERT INTO content_recsys (name, value, category, enabled) VALUES
  ('FilterBubble', '(FB) Filter Bubble — Personalized Interest Feed', 'Personalization', 'HumanOnly');
```

Il valore `'HumanOnly'` è un nuovo sentinel che:
- **non contiene** `'Standard'` → non appare nella lista Standard normale
- **non contiene** `'HPC'` → non appare nella lista HPC per agenti
- viene riconosciuto esplicitamente nei punti che lo devono mostrare agli utenti umani

### 4.2 Alias nel normalizzatore (`content_recsys.py`)

```python
# In mode_aliases dict:
"filterbubble": "FilterBubble",
"fb":           "FilterBubble",
"pif":          "FilterBubble",
```

### 4.3 Funzione di scoring (da aggiungere in `content_recsys.py`)

```python
def _filter_bubble_score(uid, exp_engine, alpha=2.0):
    """
    Return {post_id: score} dict based on user interest + opinion alignment.

    Uses raw SQL against the experiment DB (exp_engine) since user_topic_interest
    and agent_opinion live there, not in the dashboard DB.
    """
    uid_str = str(uid)
    scores = {}

    with exp_engine.connect() as conn:
        # 1. Load user interests: {topic_id: interest_level}
        rows = conn.execute(
            text("SELECT topic_id, interest_level FROM user_topic_interest WHERE user_id = :uid"),
            {"uid": uid_str},
        ).fetchall()
        if not rows:
            return {}  # no onboarding data → fall back to default
        interests = {str(r[0]): float(r[1]) for r in rows}

        # 2. Load user opinions: {topic_id: opinion}
        opinions = {}
        for sentinel in ("'0'", "0"):
            try:
                op_rows = conn.execute(
                    text(f"SELECT topic_id, opinion FROM agent_opinion "
                         f"WHERE agent_id = :aid AND tid = {sentinel}"),
                    {"aid": uid_str},
                ).fetchall()
                if op_rows:
                    opinions = {str(r[0]): float(r[1]) for r in op_rows}
                    break
            except Exception:
                pass

        # 3. Load post→topic mapping for posts NOT by this user
        pt_rows = conn.execute(
            text("SELECT pt.post_id, pt.topic_id "
                 "FROM post_topics pt "
                 "JOIN post p ON p.id = pt.post_id "
                 "WHERE p.user_id != :uid "
                 "  AND (p.comment_to IS NULL OR p.comment_to = -1)"),
            {"uid": uid_str},
        ).fetchall()
        # Build: {post_id: [topic_ids]}
        post_topics_map = {}
        for pid, tid in pt_rows:
            post_topics_map.setdefault(str(pid), []).append(str(tid))

        # 4. Load post sentiments: {(post_id, topic_id): compound}
        try:
            sent_rows = conn.execute(
                text("SELECT post_id, topic_id, compound FROM post_sentiment")
            ).fetchall()
            sentiments = {(str(r[0]), str(r[1])): float(r[2]) for r in sent_rows}
        except Exception:
            sentiments = {}

    # 5. Compute score for each post
    for post_id, topic_ids in post_topics_map.items():
        s = 0.0
        for topic_id in topic_ids:
            w_int = interests.get(topic_id, 0.0)
            if w_int == 0.0:
                continue
            u_opinion = opinions.get(topic_id)
            # Sentiment of post on this topic: use post_sentiment.compound if available
            # compound ∈ [-1, 1]; rescale to [0, 1] to match opinion scale
            raw_compound = sentiments.get((post_id, topic_id))
            if raw_compound is not None:
                p_opinion = (raw_compound + 1.0) / 2.0  # [-1,1] → [0,1]
            else:
                p_opinion = None

            if u_opinion is not None and p_opinion is not None:
                w_op = math.exp(-alpha * (u_opinion - p_opinion) ** 2)
            else:
                w_op = 0.5  # neutral when data is missing
            s += w_int * w_op
        if s > 0:
            scores[int(post_id)] = s

    return scores
```

### 4.4 Integrazione nel dispatcher `get_suggested_posts`

```python
elif mode == "FilterBubble":
    # Requires exp_engine passed as kwarg (or resolved inside)
    exp_engine = _resolve_exp_engine()   # vedi § 4.5
    bubble_scores = _filter_bubble_score(uid, exp_engine)

    if not bubble_scores:
        # Fallback: reverse chrono quando non ci sono dati di onboarding
        posts_query = db.session.query(Post).filter(
            Post.user_id != uid, _root_post_filter()
        )
        posts = _order_query_by_simulation_time(posts_query).paginate(
            page=page, per_page=per_page, error_out=False
        )
        additional_posts = None
    else:
        # Fetch all candidate posts, sort in Python by score, paginate manually
        ranked_ids = sorted(bubble_scores.keys(), key=lambda k: -bubble_scores[k])
        # Unscored posts appended in reverse-chrono order
        all_post_ids_set = set(ranked_ids)
        unscored = (
            db.session.query(Post.id)
            .filter(Post.user_id != uid, _root_post_filter(),
                    Post.id.notin_(all_post_ids_set))
            .order_by(desc(Post.id))
            .all()
        )
        unscored_ids = [r[0] for r in unscored]
        full_ranking = ranked_ids + unscored_ids

        # Paginate
        start = (page - 1) * per_page
        page_ids = full_ranking[start: start + per_page]

        if not page_ids:
            posts = _empty_pagination(page, per_page)
        else:
            id_to_score = {pid: i for i, pid in enumerate(page_ids)}
            fetched = (
                db.session.query(Post)
                .filter(Post.id.in_(page_ids))
                .all()
            )
            fetched.sort(key=lambda p: id_to_score.get(p.id, 999))
            posts = _manual_pagination(fetched, page, per_page, len(full_ranking))
        additional_posts = None
```

### 4.5 Risoluzione dell'exp_engine nel modulo recsys

Il modulo `content_recsys.py` non conosce direttamente `exp_id`. Le opzioni:

**Opzione A (raccomandata):** passare `exp_engine` come parametro opzionale di `get_suggested_posts`:

```python
def get_suggested_posts(uid, mode, page=1, per_page=10, follower_ratio=0.6, exp_engine=None):
```

Il chiamante (`microblogging.py` o `common.py`) lo risolve già per il proprio binding e lo passa:

```python
from flask import current_app
eng = db.engines.get("db_exp") or db.get_engine(current_app, bind="db_exp")
posts, extra = get_suggested_posts(user_id, user.recsys_type, page=p, exp_engine=eng)
```

**Opzione B:** lazy resolution tramite `current_app.extensions["sqlalchemy"].engines`.

### 4.6 Limitazione agli utenti umani: due livelli di controllo

#### Livello 1 — Catalogo recsys per agenti (HPC client matrix)

In `_load_recsys_options(simulator_type)` (`_frontend_settings.py`), il filtro è già:
```python
if r.enabled and (is_hpc or "standard" in (r.enabled or "").lower())
```
Il valore `'HumanOnly'` non contiene né `'HPC'` né `'Standard'`, quindi `FilterBubble` **non appare mai** nel catalogo degli agenti né nell'admin UI.

#### Livello 2 — edit_profile per utenti umani

`edit_profile` usa già `_load_recsys_options(simulator_type)` che filtra per tipo esperimento.  
Aggiungere un filtro separato che include `'HumanOnly'` **solo** quando il profilo in modifica appartiene a un utente umano (non a un agente simulato):

```python
def _load_recsys_options(simulator_type: str = "Standard", include_human_only: bool = False):
    is_hpc = (simulator_type or "").upper() == "HPC"

    def _to_list(model):
        rows = db.session.scalars(select(model).order_by(model.id.asc())).all()
        return [
            {"name": r.name, "label": r.value, "category": r.category or "Other"}
            for r in rows
            if r.enabled and (
                (is_hpc or "standard" in (r.enabled or "").lower())
                or (include_human_only and "humanonly" in (r.enabled or "").lower())
            )
        ]
    return {"content": _to_list(Content_Recsys), "follow": _to_list(Follow_Recsys)}
```

Nel route `edit_profile` in `common.py`:

```python
# Verifica se l'utente che si sta modificando è umano (non agente simulato)
_is_human = user.user_type in ("human", "admin", "user") or not _is_simulated_agent(user)
_recsys_opts = _load_recsys_options(_sim_type, include_human_only=_is_human)
```

#### Livello 3 — Runtime guard in `get_suggested_posts`

Come ultima linea di difesa, `FilterBubble` richiede dati di `user_topic_interest`; se la tabella è vuota o assente (come avviene per gli agenti), ritorna `{}` e scatta il fallback reverse-chrono.

---

## 5. Pipeline di integrazione

```
Fase 0 — Prerequisiti (verificare, non implementare)
  └─ Tabelle user_topic_interest e agent_opinion popolate dall'onboarding
  └─ post_topics compilata dall'HPC client per i post degli agenti
  └─ post_sentiment opzionale (se assente, w_opinion = 0.5 per tutti)

Fase 1 — DB seed
  ├─ Aggiungere riga FilterBubble in content_recsys (enabled='HumanOnly')
  ├─ Aggiornare data_schema/postgre_dashboard.sql
  └─ Aggiungere migration in y_web/db_init/migrations.py

Fase 2 — Alias e normalizzatore
  └─ Aggiungere 'filterbubble', 'fb', 'pif' in _normalize_content_recsys_mode()

Fase 3 — Funzione di scoring
  └─ Implementare _filter_bubble_score(uid, exp_engine, alpha) in content_recsys.py
  └─ Implementare _empty_pagination e _manual_pagination (helper interni)

Fase 4 — Dispatcher
  └─ Aggiungere branch FilterBubble in get_suggested_posts()
  └─ Aggiungere parametro exp_engine a get_suggested_posts (default None)

Fase 5 — Propagazione exp_engine ai call site
  └─ microblogging.py / common.py: risolvere engine e passarlo

Fase 6 — Filtri di visibilità
  └─ Aggiornare _load_recsys_options() con flag include_human_only
  └─ Aggiornare edit_profile route per rilevare utente umano e passare il flag
  └─ Verificare che il catalogo HPC client matrix NON mostri FilterBubble

Fase 7 — Default per utenti umani
  └─ Nella logica di join_experiment/_get_exp_default_recsys: se il nuovo utente
     è human e nessun default è configurato, considerare FilterBubble come default

Fase 8 — Testing
  └─ Unit: _filter_bubble_score con exp DB mock
  └─ Integrazione: feed con utente con onboarding completato
  └─ Regression: agenti non vedono FilterBubble nelle proprie opzioni
  └─ Edge: utente senza onboarding → fallback silenzioso a reverse-chrono
```

---

## 6. Criteri di successo

| # | Criterio | Metodo di verifica |
|---|---|---|
| S1 | Un utente umano con onboarding completato vede il feed ordinato prevalentemente per topic di suo interesse | Ispezione manuale + unit test su score |
| S2 | Post su topic con `interest_level = 0` non compaiono in prima pagina | Assert: nessun post con `bubble_score == 0` nella pagina 1 (se esistono post con score > 0) |
| S3 | Post il cui sentiment è allineato all'opinione dell'utente hanno score > post neutri/contrari, a parità di topic | Unit test con fixture sintetiche |
| S4 | `FilterBubble` **non compare** nelle opzioni recsys del client HPC matrix (`_build_recsys_matrix_rows`) | Test: mock `catalog` con FilterBubble → assenza dal payload `default_values` |
| S5 | `FilterBubble` **non compare** in `edit_profile` per utenti-agente (`user_type = "agent"`) | Test: `_load_recsys_options(include_human_only=False)` non include FB |
| S6 | `FilterBubble` **compare** in `edit_profile` per utenti umani in esperimento HPC | Test: `_load_recsys_options("HPC", include_human_only=True)` include FB |
| S7 | Utente senza dati di onboarding (`user_topic_interest` vuota) → feed identico a reverse-chrono, nessun errore | Test con exp DB che non ha righe per l'utente |
| S8 | Nessuna degradazione di performance percettibile: il feed con FilterBubble si carica in < 2× il tempo del feed reverse-chrono | Benchmark su exp DB con ~100k post |

---

## 7. Considerazioni progettuali aggiuntive

### 7.1 Tuning del parametro α

`α` potrebbe essere esposto nel `ExpFrontendSettings` come `filter_bubble_alpha` (float, default 2.0) cosicché il ricercatore possa variare la "larghezza" della bolla per ciascun esperimento. Valori indicativi:

| α | Effetto |
|---|---|
| 0.5 | Bolla larghissima: tutto ciò che tocca il topic entra |
| 2.0 | Default: solo post allineati entrano con peso significativo |
| 5.0 | Bolla stretta: solo post con opinione quasi identica |

### 7.2 Aggiornamento online degli interessi

In futuro si potrebbe aggiornare `interest_level` e `opinion` in tempo reale (ad esempio dopo ogni reazione dell'utente), rendendo la filter bubble adattiva durante la sessione.

### 7.3 Esclusione dal report analisi

Poiché `FilterBubble` è un recommender pensato per modellare la percezione soggettiva dell'utente umano, i suoi post-visti non dovrebbero essere confusi con i pattern di consumo degli agenti nelle analisi comparative. Aggiungere un flag `is_human_feed` alle metriche di telemetria se rilevante.

### 7.4 Nome canonico alternativo

Se il termine "Filter Bubble" è semanticamente esplicito in modo indesiderato per i partecipanti dell'esperimento, il frontend può mostrarlo come **"Personalized Feed"** (label nel DB) mantenendo il nome tecnico interno `FilterBubble`.

---

*Documento generato a supporto della progettazione, non versionato.*
