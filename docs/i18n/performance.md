# i18n performance check (G1 criterion: overhead under 5%)

Method: `create_app("sqlite")` on a clean copy of the repository at the commit before the i18n branch (`frontend_settings_forum_photo`) and at the Phase 1 head; Flask test client, admin session, 150 requests per page after 10 warm-up requests, median time, three alternating runs. Sandbox timings, so only the ratio is meaningful.

| Page | Before (ms) | After (ms) | Change |
|---|---:|---:|---:|
| `/admin/dashboard` | 4.45 to 4.59 | 4.67 to 4.77 | +2% to +7% |
| `/admin/user_details/<id>` (also gained the language box, +2.5 KB) | 2.65 to 2.84 | 2.83 to 3.25 | +4% to +23% |
| `/admin/experiments` | 2.99 to 3.20 | 3.24 to 3.46 | +2% to +16% |
| `/login` (0.3 ms render) | 0.30 | 0.44 | +0.14 ms |
| 404 page | 2.8 | 2.8 | 0% |

Run-to-run noise is about 5%, so the figures above are at the limit of the criterion for the heavier pages and above it for the trivial login page (+0.14 ms absolute).

Unit costs (Python 3.10, one request context): language selection 9 us once per request; template `_()` 8.4 us per call with Flask-Babel's default, 2.7 us per call after the optimisation described below (500 calls: 4.2 ms before, 1.4 ms after).

## Optimisation done in Phase 1

Flask-Babel resolves the translations on every `gettext()` call and Jinja's new-style `gettext` wrapper adds its own overhead. `y_web/i18n.py` now resolves the translations once per request (cached on `flask.g`) and installs a lighter `_()`/`gettext()` for templates with identical behaviour (variables escaped under autoescape, `%%` for a literal percent sign, `{% trans %}` and `ngettext` unchanged). Tests: `test_i18n_template_gettext.py`.

## Remaining risk for Phase 2

The admin templates hold about 1,900 unique strings and a heavy page renders a few hundred of them: at 2.7 us each that is roughly 1 ms on pages that render in 3 to 5 ms, still around the limit of the 5% criterion. The measurement must be repeated on the first converted area (F2-1) and, if needed, strings that never change can be resolved once per process instead of per request. Tracked as an open point of gate G1.

## F2-1 remeasurement (layout, menu, login, onboarding, errors)

F2-1 adds about 30 `_()` calls to every admin page (menu in `head.html`, top bar in `dash_head.html`) and the strings of login, onboarding and the four error pages. At 2.7 us per call the shared layout costs about 0.08 ms per admin page, around 2% of a 4 ms page and inside the run-to-run noise (about 5%). The admin pages converted in later tasks add their own strings, so the figure is re-checked at the end of F2-3 (heaviest pages: dashboard, experiment details, populations).

## F2-10: misura a fine Fase 2

Render dei template (sessione di test, mediana su molte iterazioni, baseline = commit prima dell'i18n):

| Pagina | prima | dopo | delta |
|---|---|---|---|
| dashboard | 3.5-3.9 ms | 4.0-4.3 ms | +10% |
| experiments | 2.5 ms | 2.9-3.1 ms | +15% |
| populations (645 `_()`) | 5.1 ms | 6.9 ms | +35% |
| miscellanea | 3.5 ms | 3.9 ms | +10% |
| agents (pagina con molti dati) | 57 ms | 58 ms | +1.5% |

Ottimizzazioni applicate: `_()` dei template con cache per-richiesta delle traduzioni e per-catalogo dei testi finali, `html_lang`/`text_direction` calcolati una volta per richiesta, `%%` risolto in cache.

Esito: il criterio "<5%" **non è rispettato** sul solo render dei template delle pagine più dense di stringhe (circa 2.6 us per chiamata `_()`, costo di invocazione Jinja). In termini assoluti il sovraccosto è 0.4-1.8 ms per pagina, trascurabile rispetto a query e rete; sulle pagine con dati reali (agents) è ~1.5%. Le pagine sono inoltre l'1-4% più grandi.
