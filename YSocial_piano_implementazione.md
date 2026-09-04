# YSocial – Piano di Implementazione

> Documento generato il 4 settembre 2026  
> Basato su: `YSocial_analisi_codebase.md` (v4.0.0)  
> Branch di lavoro: `fix/critical-issues`

---

## Stato implementazione

| Criticità | Effort | Stato |
|---|---|---|
| C1 — Secret Key hardcoded | 2h | ✅ Risolto — commit `69c766b9` |
| C2 — Database runtime in git | 3h | ✅ Risolto — commit `53b518c6` |
| C3 — Flask-Migrate | 3-5gg | ✅ Risolto — commit `6f38891d` |
| C4 — Eliminazione shim SA2 | 3-5gg | ✅ Risolto — commit `d7981a38` |
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

## FASE 2 — Sprint 2 (entro 1 mese)

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
