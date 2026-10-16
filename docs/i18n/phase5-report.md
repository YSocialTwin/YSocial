# Fase 5: audit finale (stato al 2026-10-16)

## Copertura (`python scripts/i18n/coverage_report.py`)
Catalogo core 2849/2849, TrainingModules 1622/1622, ScenarioDesign 128/128, frontend_adds-on 54/54, reactive_agents 85/85;
cataloghi JS (admin 445, core 6, simulation 118, tutorials 248, scenario_design 179, frontend_adds_on 72): tutti 100% per `it`.
`en_US_POSIX` è il pseudo-locale di sviluppo (en-XA), non una lingua utente.

## Residui dello scanner (`scan_unmarked.py`): 455 in 84 file
Quasi tutti falsi positivi (frammenti HTML dentro stringhe JS delle pagine admin) o codice legacy del tema
(`lightbox.js` 113, `tour.js`, `autocompletes.js`, `map.js`). Residui reali noti: nomi piattaforma in `admin-dashboard.js`,
`platform_type|capitalize` nel login, audit/log con testo nella lingua della richiesta.

## Criteri di uscita
- Glossario applicato: sì (`check_glossary.py`, 0 violazioni, test in CI).
- Nessun errore di segnaposto nei cataloghi: sì (`catalogs.py check` + test plurali/placeholder).
- Plurali, formati data/numero (filtri Babel; JS con `document.documentElement.lang`), `lang`/`dir`, aria-label: verificati.
- Overhead di risposta p95 <5%: **non dimostrato**: +0.4–1.8 ms/pagina (+35% sul solo render di pagine dense); cache per richiesta e per catalogo già attive. Decisione di accettazione al proprietario.
- Regressione visiva con en-XA: **non eseguita** (nessun browser nell'ambiente di sviluppo); da fare in CI/locale.
- Revisione madrelingua: **da fare** (`review-checklist.md`). Finché manca, l'italiano è **beta** (selettore: "Italiano (beta)"; `LANGUAGE_STATUS`).
- Gate G4 (esperimento reale in italiano per piattaforma): da eseguire.
